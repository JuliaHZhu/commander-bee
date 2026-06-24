"""
Cron job storage and management.

Jobs are stored in ~/.worker-bee/cron/jobs.json
Output is saved to ~/.worker-bee/cron/output/{job_id}/{timestamp}.md
"""

import copy
import json
import logging
import shutil
import tempfile
import threading
import os
import re
import fcntl
import contextlib
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any, Union

logger = logging.getLogger(__name__)

# =============================================================================
# Time helper (replaces hermes_time)
# =============================================================================

def _now() -> datetime:
    """Return current time as timezone-aware datetime (local timezone)."""
    return datetime.now().astimezone()


# =============================================================================
# Atomic replace helper (replaces utils.atomic_replace)
# =============================================================================

def atomic_replace(src: Union[str, Path], dst: Union[str, Path]):
    """Atomically replace dst with src (cross-platform best-effort)."""
    try:
        os.replace(str(src), str(dst))
    except OSError:
        # Fallback: copy then delete
        shutil.copy2(str(src), str(dst))
        try:
            os.unlink(str(src))
        except OSError:
            pass


# =============================================================================
# Optional croniter dependency
# =============================================================================

try:
    from croniter import croniter
    HAS_CRONITER = True
except ImportError:
    croniter = None  # type: ignore
    HAS_CRONITER = False


# =============================================================================
# Configuration
# =============================================================================

APP_DIR = Path.home() / ".worker-bee"
CRON_DIR = APP_DIR / "cron"
JOBS_FILE = CRON_DIR / "jobs.json"

# In-process lock protecting load_jobs->modify->save_jobs cycles.
_jobs_file_lock = threading.Lock()  # process-local guard for scheduler internals


_JOBS_LOCK_FILE = CRON_DIR / ".jobs.lock"


@contextlib.contextmanager
def _cross_process_lock():
    """Acquire an exclusive cross-process lock for jobs.json modifications.

    Uses fcntl.flock on a separate lock file — works across independent
    processes on the same host.  Complementing _jobs_file_lock (process-local),
    this prevents multi-instance data corruption during load-modify-save cycles.
    """
    ensure_dirs()
    # Create lock file if it doesn't exist (touch), then lock it
    _JOBS_LOCK_FILE.touch(exist_ok=True)
    with open(_JOBS_LOCK_FILE, 'r+') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
OUTPUT_DIR = CRON_DIR / "output"
ONESHOT_GRACE_SECONDS = 120


def _normalize_skill_list(skill: Optional[str] = None, skills: Optional[Any] = None) -> List[str]:
    """Normalize legacy/single-skill and multi-skill inputs into a unique ordered list."""
    if skills is None:
        raw_items = [skill] if skill else []
    elif isinstance(skills, str):
        raw_items = [skills]
    else:
        raw_items = list(skills)

    normalized: List[str] = []
    for item in raw_items:
        text = str(item or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _apply_skill_fields(job: Dict[str, Any]) -> Dict[str, Any]:
    """Return a job dict with canonical `skills` and legacy `skill` fields aligned."""
    normalized = dict(job)
    skills = _normalize_skill_list(normalized.get("skill"), normalized.get("skills"))
    normalized["skills"] = skills
    normalized["skill"] = skills[0] if skills else None
    return normalized


def _coerce_job_text(value: Any, fallback: str = "") -> str:
    """Coerce legacy/hand-edited nullable cron fields to strings for readers."""
    if value is None:
        return fallback
    return str(value)


def _schedule_display_for_job(job: Dict[str, Any]) -> str:
    display = _coerce_job_text(job.get("schedule_display")).strip()
    if display:
        return display

    schedule = job.get("schedule")
    if isinstance(schedule, dict):
        for key in ("display", "value", "expr", "run_at"):
            text = _coerce_job_text(schedule.get(key)).strip()
            if text:
                return text
    elif schedule is not None:
        return str(schedule)

    return "?"


def _normalize_job_record(job: Dict[str, Any]) -> Dict[str, Any]:
    """Return a read-safe cron job shape for UI/API/tool/scheduler consumers."""
    normalized = _apply_skill_fields(job)
    job_id = _coerce_job_text(normalized.get("id"), "unknown")
    prompt = _coerce_job_text(normalized.get("prompt"))
    normalized["id"] = job_id
    normalized["prompt"] = prompt

    name = _coerce_job_text(normalized.get("name")).strip()
    if not name:
        script = _coerce_job_text(normalized.get("script")).strip()
        label_source = (
            prompt
            or (normalized["skills"][0] if normalized.get("skills") else "")
            or script
            or job_id
            or "cron job"
        )
        name = label_source[:50].strip() or "cron job"
    normalized["name"] = name
    normalized["schedule_display"] = _schedule_display_for_job(normalized)

    state = _coerce_job_text(normalized.get("state")).strip()
    if not state:
        state = "scheduled" if normalized.get("enabled", True) else "paused"
    normalized["state"] = state

    return normalized


def _secure_dir(path: Path):
    """Set directory to owner-only access (0700). No-op on Windows."""
    try:
        os.chmod(path, 0o700)
    except (OSError, NotImplementedError):
        pass


def _secure_file(path: Path):
    """Set file to owner-only read/write (0600). No-op on Windows."""
    try:
        if path.exists():
            os.chmod(path, 0o600)
    except (OSError, NotImplementedError):
        pass


def ensure_dirs():
    """Ensure cron directories exist with secure permissions."""
    CRON_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _secure_dir(CRON_DIR)
    _secure_dir(OUTPUT_DIR)


# =============================================================================
# Schedule Parsing
# =============================================================================

def parse_duration(s: str) -> int:
    """Parse duration string into minutes.

    Examples:
        "30m" -> 30
        "2h" -> 120
        "1d" -> 1440
    """
    s = s.strip().lower()
    match = re.match(r'^(\d+)\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)$', s)
    if not match:
        raise ValueError(f"Invalid duration: '{s}'. Use format like '30m', '2h', or '1d'")

    value = int(match.group(1))
    unit = match.group(2)[0]  # First char: m, h, or d

    multipliers = {'m': 1, 'h': 60, 'd': 1440}
    return value * multipliers[unit]


def parse_schedule(schedule: str) -> Dict[str, Any]:
    """Parse schedule string into structured format.

    Returns dict with:
        - kind: "once" | "interval" | "cron"
        - For "once": "run_at" (ISO timestamp)
        - For "interval": "minutes" (int)
        - For "cron": "expr" (cron expression)

    Examples:
        "30m"              -> once in 30 minutes
        "2h"               -> once in 2 hours
        "every 30m"        -> recurring every 30 minutes
        "every 2h"         -> recurring every 2 hours
        "0 9 * * *"        -> cron expression
        "2026-02-03T14:00" -> once at timestamp
    """
    schedule = schedule.strip()
    original = schedule
    schedule_lower = schedule.lower()

    # "every X" pattern -> recurring interval
    if schedule_lower.startswith("every "):
        duration_str = schedule[6:].strip()
        minutes = parse_duration(duration_str)
        return {
            "kind": "interval",
            "minutes": minutes,
            "display": f"every {minutes}m"
        }

    # Check for cron expression (5 or 6 space-separated fields)
    parts = schedule.split()
    if len(parts) >= 5 and all(
        re.match(r'^[\d\*\-,/]+$', p) for p in parts[:5]
    ):
        if not HAS_CRONITER:
            raise ValueError("Cron expressions require 'croniter' package. Install with: pip install croniter")
        try:
            croniter(schedule)  # type: ignore
        except Exception as e:
            raise ValueError(f"Invalid cron expression '{schedule}': {e}")
        return {
            "kind": "cron",
            "expr": schedule,
            "display": schedule
        }

    # ISO timestamp (contains T or looks like date)
    if 'T' in schedule or re.match(r'^\d{4}-\d{2}-\d{2}', schedule):
        try:
            dt = datetime.fromisoformat(schedule.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.astimezone()
            return {
                "kind": "once",
                "run_at": dt.isoformat(),
                "display": f"once at {dt.strftime('%Y-%m-%d %H:%M')}"
            }
        except ValueError as e:
            raise ValueError(f"Invalid timestamp '{schedule}': {e}")

    # Duration like "30m", "2h", "1d" -> one-shot from now
    try:
        minutes = parse_duration(schedule)
        run_at = _now() + timedelta(minutes=minutes)
        return {
            "kind": "once",
            "run_at": run_at.isoformat(),
            "display": f"once in {original}"
        }
    except ValueError:
        pass

    raise ValueError(
        f"Invalid schedule '{original}'. Use:\n"
        f"  - Duration: '30m', '2h', '1d' (one-shot)\n"
        f"  - Interval: 'every 30m', 'every 2h' (recurring)\n"
        f"  - Cron: '0 9 * * *' (cron expression)\n"
        f"  - Timestamp: '2026-02-03T14:00:00' (one-shot at time)"
    )


def _ensure_aware(dt: datetime) -> datetime:
    """Return a timezone-aware datetime in local timezone."""
    if dt.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo
        return dt.replace(tzinfo=local_tz).astimezone()
    return dt.astimezone()


def _recoverable_oneshot_run_at(
    schedule: Dict[str, Any],
    now: datetime,
    *,
    last_run_at: Optional[str] = None,
) -> Optional[str]:
    """Return a one-shot run time if it is still eligible to fire."""
    if schedule.get("kind") != "once":
        return None
    if last_run_at:
        return None

    run_at = schedule.get("run_at")
    if not run_at:
        return None

    run_at_dt = _ensure_aware(datetime.fromisoformat(run_at))
    if run_at_dt >= now - timedelta(seconds=ONESHOT_GRACE_SECONDS):
        return run_at
    return None


def _compute_grace_seconds(schedule: dict) -> int:
    """Compute how late a job can be and still catch up instead of fast-forwarding."""
    MIN_GRACE = 120
    MAX_GRACE = 7200  # 2 hours

    kind = schedule.get("kind")

    if kind == "interval":
        period_seconds = schedule.get("minutes", 1) * 60
        grace = period_seconds // 2
        return max(MIN_GRACE, min(grace, MAX_GRACE))

    if kind == "cron" and HAS_CRONITER:
        try:
            now = _now()
            cron = croniter(schedule["expr"], now)  # type: ignore
            first = cron.get_next(datetime)
            second = cron.get_next(datetime)
            period_seconds = int((second - first).total_seconds())
            grace = period_seconds // 2
            return max(MIN_GRACE, min(grace, MAX_GRACE))
        except Exception:
            pass

    return MIN_GRACE


def compute_next_run(schedule: Dict[str, Any], last_run_at: Optional[str] = None) -> Optional[str]:
    """Compute the next run time for a schedule.

    Returns ISO timestamp string, or None if no more runs.
    """
    now = _now()

    if schedule["kind"] == "once":
        return _recoverable_oneshot_run_at(schedule, now, last_run_at=last_run_at)

    elif schedule["kind"] == "interval":
        minutes = schedule["minutes"]
        if last_run_at:
            last = _ensure_aware(datetime.fromisoformat(last_run_at))
            next_run = last + timedelta(minutes=minutes)
        else:
            next_run = now + timedelta(minutes=minutes)
        return next_run.isoformat()

    elif schedule["kind"] == "cron":
        if not HAS_CRONITER:
            logger.warning(
                "Cannot compute next run for cron schedule %r: 'croniter' is not installed.",
                schedule.get("expr"),
            )
            return None
        base_time = now
        if last_run_at:
            base_time = _ensure_aware(datetime.fromisoformat(last_run_at))
        cron = croniter(schedule["expr"], base_time)  # type: ignore
        next_run = cron.get_next(datetime)
        return next_run.isoformat()

    return None


# =============================================================================
# Job CRUD Operations
# =============================================================================

def load_jobs() -> List[Dict[str, Any]]:
    """Load all jobs from storage."""
    ensure_dirs()
    if not JOBS_FILE.exists():
        return []

    try:
        with open(JOBS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("jobs", [])
    except json.JSONDecodeError:
        try:
            with open(JOBS_FILE, 'r', encoding='utf-8') as f:
                data = json.loads(f.read(), strict=False)
                jobs = data.get("jobs", [])
                if jobs:
                    save_jobs(jobs)
                    logger.warning("Auto-repaired jobs.json (had invalid control characters)")
                return jobs
        except Exception as e:
            logger.error("Failed to auto-repair jobs.json: %s", e)
            raise RuntimeError(f"Cron database corrupted and unrepairable: {e}") from e
    except IOError as e:
        logger.error("IOError reading jobs.json: %s", e)
        raise RuntimeError(f"Failed to read cron database: {e}") from e


def save_jobs(jobs: List[Dict[str, Any]]):
    """Save all jobs to storage."""
    ensure_dirs()
    fd, tmp_path = tempfile.mkstemp(dir=str(JOBS_FILE.parent), suffix='.tmp', prefix='.jobs_')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump({"jobs": jobs, "updated_at": _now().isoformat()}, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        atomic_replace(tmp_path, JOBS_FILE)
        _secure_file(JOBS_FILE)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _normalize_workdir(workdir: Optional[str]) -> Optional[str]:
    """Normalize and validate a cron job workdir."""
    if workdir is None:
        return None
    raw = str(workdir).strip()
    if not raw:
        return None
    expanded = Path(raw).expanduser()
    if not expanded.is_absolute():
        raise ValueError(
            f"Cron workdir must be an absolute path (got {raw!r})."
        )
    resolved = expanded.resolve()
    if not resolved.exists():
        raise ValueError(f"Cron workdir does not exist: {resolved}")
    if not resolved.is_dir():
        raise ValueError(f"Cron workdir is not a directory: {resolved}")
    return str(resolved)


def create_job(
    prompt: Optional[str],
    schedule: str,
    name: Optional[str] = None,
    repeat: Optional[int] = None,
    deliver: Optional[str] = None,
    origin: Optional[Dict[str, Any]] = None,
    skill: Optional[str] = None,
    skills: Optional[List[str]] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    script: Optional[str] = None,
    context_from: Optional[Union[str, List[str]]] = None,
    enabled_toolsets: Optional[List[str]] = None,
    workdir: Optional[str] = None,
    no_agent: bool = False,
) -> Dict[str, Any]:
    """Create a new cron job."""
    parsed_schedule = parse_schedule(schedule)

    if repeat is not None and repeat <= 0:
        repeat = None

    if parsed_schedule["kind"] == "once" and repeat is None:
        repeat = 1

    if deliver is None:
        deliver = "origin" if origin else "local"

    job_id = uuid.uuid4().hex[:12]
    now = _now().isoformat()

    normalized_skills = _normalize_skill_list(skill, skills)
    normalized_model = str(model).strip() if isinstance(model, str) else None
    normalized_provider = str(provider).strip() if isinstance(provider, str) else None
    normalized_base_url = str(base_url).strip().rstrip("/") if isinstance(base_url, str) else None
    normalized_model = normalized_model or None
    normalized_provider = normalized_provider or None
    normalized_base_url = normalized_base_url or None
    normalized_script = str(script).strip() if isinstance(script, str) else None
    normalized_script = normalized_script or None
    normalized_toolsets = [str(t).strip() for t in enabled_toolsets if str(t).strip()] if enabled_toolsets else None
    normalized_toolsets = normalized_toolsets or None
    normalized_workdir = _normalize_workdir(workdir)
    normalized_no_agent = bool(no_agent)

    if normalized_no_agent and not normalized_script:
        raise ValueError(
            "no_agent=True requires a script -- with no agent and no script "
            "there is nothing for the job to run."
        )

    if isinstance(context_from, str):
        context_from = [context_from.strip()] if context_from.strip() else None
    elif isinstance(context_from, list):
        context_from = [str(j).strip() for j in context_from if str(j).strip()] or None
    else:
        context_from = None

    prompt_text = _coerce_job_text(prompt)
    label_source = (prompt_text or (normalized_skills[0] if normalized_skills else None) or (normalized_script if normalized_no_agent else None)) or "cron job"
    job = {
        "id": job_id,
        "name": name or label_source[:50].strip(),
        "prompt": prompt_text,
        "skills": normalized_skills,
        "skill": normalized_skills[0] if normalized_skills else None,
        "model": normalized_model,
        "provider": normalized_provider,
        "base_url": normalized_base_url,
        "script": normalized_script,
        "no_agent": normalized_no_agent,
        "context_from": context_from,
        "schedule": parsed_schedule,
        "schedule_display": parsed_schedule.get("display", schedule),
        "repeat": {
            "times": repeat,  # None = forever
            "completed": 0
        },
        "enabled": True,
        "state": "scheduled",
        "paused_at": None,
        "paused_reason": None,
        "created_at": now,
        "next_run_at": compute_next_run(parsed_schedule),
        "last_run_at": None,
        "last_status": None,
        "last_error": None,
        "last_delivery_error": None,
        "deliver": deliver,
        "origin": origin,
        "enabled_toolsets": normalized_toolsets,
        "workdir": normalized_workdir,
        "retry_count": 0,
    }

    with _cross_process_lock():
        jobs = load_jobs()
        jobs.append(job)
        save_jobs(jobs)

    return job


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Get a job by ID."""
    jobs = load_jobs()
    for job in jobs:
        if job["id"] == job_id:
            return _normalize_job_record(job)
    return None


class AmbiguousJobReference(LookupError):
    """Raised when a job name matches more than one job."""

    def __init__(self, ref: str, matches: List[Dict[str, Any]]):
        self.ref = ref
        self.matches = matches
        ids = ", ".join(m["id"] for m in matches)
        super().__init__(
            f"Job name '{ref}' is ambiguous -- matches {len(matches)} jobs: {ids}. "
            f"Use the job ID instead."
        )


def resolve_job_ref(ref: str) -> Optional[Dict[str, Any]]:
    """Resolve a job reference (ID or name) to a job record."""
    if not ref:
        return None
    jobs = load_jobs()
    for job in jobs:
        if job["id"] == ref:
            return _normalize_job_record(job)
    ref_lower = ref.lower()
    name_matches = [j for j in jobs if (j.get("name") or "").lower() == ref_lower]
    if not name_matches:
        return None
    if len(name_matches) > 1:
        raise AmbiguousJobReference(
            ref, [_normalize_job_record(j) for j in name_matches]
        )
    return _normalize_job_record(name_matches[0])


def list_jobs(include_disabled: bool = False) -> List[Dict[str, Any]]:
    """List all jobs, optionally including disabled ones."""
    jobs = [_normalize_job_record(j) for j in load_jobs()]
    if not include_disabled:
        jobs = [j for j in jobs if j.get("enabled", True)]
    return jobs


def update_job(job_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update a job by ID, refreshing derived schedule fields when needed."""
    with _cross_process_lock():
        jobs = load_jobs()
        for i, job in enumerate(jobs):
            if job["id"] != job_id:
                continue

            if "workdir" in updates:
                _wd = updates["workdir"]
                if _wd in {None, "", False}:
                    updates["workdir"] = None
                else:
                    updates["workdir"] = _normalize_workdir(_wd)

            updated = _apply_skill_fields({**job, **updates})
            schedule_changed = "schedule" in updates

            if "skills" in updates or "skill" in updates:
                normalized_skills = _normalize_skill_list(updated.get("skill"), updated.get("skills"))
                updated["skills"] = normalized_skills
                updated["skill"] = normalized_skills[0] if normalized_skills else None

            if schedule_changed:
                updated_schedule = updated["schedule"]
                if isinstance(updated_schedule, str):
                    updated_schedule = parse_schedule(updated_schedule)
                    updated["schedule"] = updated_schedule
                updated["schedule_display"] = updates.get(
                    "schedule_display",
                    updated_schedule.get("display", updated.get("schedule_display")),
                )
                if updated.get("state") != "paused":
                    updated["next_run_at"] = compute_next_run(updated_schedule)

            if updated.get("enabled", True) and updated.get("state") != "paused" and not updated.get("next_run_at"):
                updated["next_run_at"] = compute_next_run(updated["schedule"])

            jobs[i] = updated
            save_jobs(jobs)
            return _normalize_job_record(jobs[i])
    return None


def pause_job(job_id: str, reason: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Pause a job without deleting it. Accepts a job ID or name."""
    job = resolve_job_ref(job_id)
    if not job:
        return None
    return update_job(
        job["id"],
        {
            "enabled": False,
            "state": "paused",
            "paused_at": _now().isoformat(),
            "paused_reason": reason,
        },
    )


def resume_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Resume a paused job and compute the next future run from now."""
    job = resolve_job_ref(job_id)
    if not job:
        return None

    next_run_at = compute_next_run(job["schedule"])
    return update_job(
        job["id"],
        {
            "enabled": True,
            "state": "scheduled",
            "paused_at": None,
            "paused_reason": None,
            "next_run_at": next_run_at,
        },
    )


def trigger_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Schedule a job to run on the next scheduler tick."""
    job = resolve_job_ref(job_id)
    if not job:
        return None
    return update_job(
        job["id"],
        {
            "enabled": True,
            "state": "scheduled",
            "paused_at": None,
            "paused_reason": None,
            "next_run_at": _now().isoformat(),
        },
    )


def remove_job(job_id: str) -> bool:
    """Remove a job by ID or name."""
    with _cross_process_lock():
        job = resolve_job_ref(job_id)
        if not job:
            return False
        canonical_id = job["id"]
        jobs = load_jobs()
        original_len = len(jobs)
        jobs = [j for j in jobs if j["id"] != canonical_id]
        if len(jobs) < original_len:
            save_jobs(jobs)
            return True
    return False


def mark_job_run(job_id: str, success: bool, error: Optional[str] = None,
                 delivery_error: Optional[str] = None):
    """Mark a job as having been run."""
    with _jobs_file_lock:
        jobs = load_jobs()
        for i, job in enumerate(jobs):
            if job["id"] == job_id:
                now = _now().isoformat()
                job["last_run_at"] = now
                job["last_status"] = "ok" if success else "error"
                job["last_error"] = error if not success else None
                job["last_delivery_error"] = delivery_error

                if job.get("repeat"):
                    job["repeat"]["completed"] = job["repeat"].get("completed", 0) + 1

                    times = job["repeat"].get("times")
                    completed = job["repeat"]["completed"]
                    if times is not None and times > 0 and completed >= times:
                        jobs.pop(i)
                        save_jobs(jobs)
                        return

                job["next_run_at"] = compute_next_run(job["schedule"], now)

                if job["next_run_at"] is None:
                    kind = job.get("schedule", {}).get("kind")
                    if kind in {"cron", "interval"}:
                        job["state"] = "error"
                        if not job.get("last_error"):
                            job["last_error"] = (
                                "Failed to compute next run for recurring "
                                "schedule (is 'croniter' installed?)"
                            )
                        logger.error(
                            "Job '%s' (%s) could not compute next_run_at; "
                            "leaving enabled and marking state=error.",
                            job.get("name", job["id"]),
                            kind,
                        )
                    else:
                        job["enabled"] = False
                        job["state"] = "completed"
                elif job.get("state") != "paused":
                    job["state"] = "scheduled"

                save_jobs(jobs)
                return

        logger.warning("mark_job_run: job_id %s not found, skipping save", job_id)


def mark_job_rate_limited(job_id: str, retry_delay_minutes: int = 10):
    """Mark a job as rate-limited and schedule retry.

    Sets state='rate_limited' and next_run_at = now + retry_delay_minutes.
    Increments retry_count. If retry_count > 10, marks as failed instead.
    """
    with _jobs_file_lock:
        jobs = load_jobs()
        for job in jobs:
            if job["id"] == job_id:
                retry_count = job.get("retry_count", 0) + 1
                if retry_count > 10:
                    job["state"] = "error"
                    job["last_status"] = "error"
                    job["last_error"] = f"Rate limited {retry_count} times. Giving up."
                    job["retry_count"] = retry_count
                else:
                    job["state"] = "rate_limited"
                    job["retry_count"] = retry_count
                    job["next_run_at"] = (_now() + timedelta(minutes=retry_delay_minutes)).isoformat()
                    job["last_error"] = f"Rate limited (retry {retry_count}/10, next try at {job['next_run_at']})"
                save_jobs(jobs)
                return
        logger.warning("mark_job_rate_limited: job_id %s not found", job_id)


def retry_rate_limited_jobs() -> List[str]:
    """Find all rate_limited jobs and reset their next_run_at to now.

    Returns list of retried job IDs.
    """
    with _jobs_file_lock:
        jobs = load_jobs()
        retried = []
        now = _now().isoformat()
        for job in jobs:
            if job.get("state") == "rate_limited":
                job["next_run_at"] = now
                job["state"] = "scheduled"
                retried.append(job["id"])
        if retried:
            save_jobs(jobs)
        return retried


def get_rate_limited_jobs() -> List[Dict[str, Any]]:
    """Get all jobs currently in rate_limited state."""
    return [_normalize_job_record(j) for j in load_jobs() if j.get("state") == "rate_limited"]


def advance_next_run(job_id: str) -> bool:
    """Preemptively advance next_run_at for a recurring job before execution."""
    with _jobs_file_lock:
        jobs = load_jobs()
        for job in jobs:
            if job["id"] == job_id:
                kind = job.get("schedule", {}).get("kind")
                if kind not in {"cron", "interval"}:
                    return False
                now = _now().isoformat()
                new_next = compute_next_run(job["schedule"], now)
                if new_next and new_next != job.get("next_run_at"):
                    job["next_run_at"] = new_next
                    save_jobs(jobs)
                    return True
                return False
        return False


def get_due_jobs() -> List[Dict[str, Any]]:
    """Get all jobs that are due to run now."""
    with _jobs_file_lock:
        return _get_due_jobs_locked()


def _get_due_jobs_locked() -> List[Dict[str, Any]]:
    """Inner implementation of get_due_jobs(); must be called with _jobs_file_lock held."""
    now = _now()
    raw_jobs = load_jobs()
    jobs = [_apply_skill_fields(j) for j in copy.deepcopy(raw_jobs)]
    due = []
    needs_save = False

    for job in jobs:
        if not job.get("enabled", True):
            continue

        next_run = job.get("next_run_at")
        if not next_run:
            schedule = job.get("schedule", {})
            kind = schedule.get("kind")

            recovered_next = _recoverable_oneshot_run_at(
                schedule,
                now,
                last_run_at=job.get("last_run_at"),
            )
            recovery_kind = "one-shot" if recovered_next else None

            if not recovered_next and kind in {"cron", "interval"}:
                recovered_next = compute_next_run(schedule, now.isoformat())
                if recovered_next:
                    recovery_kind = kind

            if not recovered_next:
                continue

            job["next_run_at"] = recovered_next
            next_run = recovered_next
            logger.info(
                "Job '%s' had no next_run_at; recovering %s run at %s",
                job.get("name", job["id"]),
                recovery_kind,
                recovered_next,
            )
            for rj in raw_jobs:
                if rj["id"] == job["id"]:
                    rj["next_run_at"] = recovered_next
                    needs_save = True
                    break

        next_run_dt = _ensure_aware(datetime.fromisoformat(next_run))
        if next_run_dt <= now:
            schedule = job.get("schedule", {})
            kind = schedule.get("kind")

            grace = _compute_grace_seconds(schedule)
            if kind in {"cron", "interval"} and (now - next_run_dt).total_seconds() > grace:
                new_next = compute_next_run(schedule, now.isoformat())
                if new_next:
                    logger.info(
                        "Job '%s' missed its scheduled time (%s, grace=%ds). "
                        "Fast-forwarding to next run: %s",
                        job.get("name", job["id"]),
                        next_run,
                        grace,
                        new_next,
                    )
                    for rj in raw_jobs:
                        if rj["id"] == job["id"]:
                            rj["next_run_at"] = new_next
                            needs_save = True
                            break
                    continue

            due.append(job)

    if needs_save:
        save_jobs(raw_jobs)

    return due


def save_job_output(job_id: str, output: str):
    """Save job output to file."""
    ensure_dirs()
    job_output_dir = OUTPUT_DIR / job_id
    job_output_dir.mkdir(parents=True, exist_ok=True)
    _secure_dir(job_output_dir)

    timestamp = _now().strftime("%Y-%m-%d_%H-%M-%S")
    output_file = job_output_dir / f"{timestamp}.md"

    fd, tmp_path = tempfile.mkstemp(dir=str(job_output_dir), suffix='.tmp', prefix='.output_')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(output)
            f.flush()
            os.fsync(f.fileno())
        atomic_replace(tmp_path, output_file)
        _secure_file(output_file)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return output_file
