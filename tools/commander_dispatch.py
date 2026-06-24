"""commander_dispatch — Job dispatch engine.

Pure rule engine. No LLM.
"""
import json
import os
from pathlib import Path
from typing import List, Optional, Tuple

from agent.registry import registry

CMDR_DIR = Path(__file__).parent.parent
BEES_PATH = CMDR_DIR / "bees.json"
JOBS_DIR = CMDR_DIR / "commander-jobs"

_SILENT_THRESHOLD_SEC = int(os.environ.get("CB_SILENT_THRESHOLD", "120"))


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _parse_iso(ts):
    from datetime import datetime, timezone
    ts = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(ts)


def _seconds_since(ts: str) -> float:
    from datetime import datetime, timezone
    try:
        return (datetime.now(timezone.utc) - _parse_iso(ts)).total_seconds()
    except Exception:
        return float("inf")


def _read_job_meta(job_path: Path) -> Tuple[Optional[dict], str]:
    """Read YAML frontmatter + body from meta.md."""
    import re
    if not job_path.exists():
        return None, ""
    content = job_path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not m:
        return None, content
    try:
        from agent.skills import _parse_yamlish
        meta = _parse_yamlish(m.group(1))
    except Exception:
        meta = {}
    return meta, content[m.end():].strip()


def _write_job_meta(job_path: Path, meta: dict, body: str) -> None:
    lines = ["---"]
    for k, v in meta.items():
        if v is None:
            continue
        if isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---\n")
    content = "\n".join(lines) + "\n" + body
    tmp = job_path.with_suffix(job_path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(job_path)


def _log_event(job_dir: Path, event_type: str, **kwargs) -> None:
    """Append event to events.jsonl."""
    from datetime import datetime, timezone
    events_path = job_dir / "events.jsonl"
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
    }
    event.update(kwargs)
    with events_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


# ── Public API ──────────────────────────────────────────────────────

def dispatch_scan() -> str:
    """Scan commander-jobs/ for created jobs and dispatch to best-matching bee."""
    from datetime import datetime, timezone

    if not JOBS_DIR.exists():
        return "No commander-jobs/ directory."

    bees = _load_json(BEES_PATH, [])
    dispatched = []
    failed = []

    for job_dir in sorted(JOBS_DIR.glob("JOB-*")):
        if not job_dir.is_dir():
            continue
        meta_path = job_dir / "meta.md"
        meta, body = _read_job_meta(meta_path)
        if meta is None:
            continue
        if meta.get("phase") != "created":
            continue

        required = meta.get("required_skills", [])
        if not required:
            failed.append((job_dir.name, "no_required_skills"))
            _log_event(job_dir, "dispatch_failed", reason="no_required_skills")
            continue

        # Find matching bees
        candidates = []
        for b in bees:
            if b.get("status") != "alive":
                continue
            if _seconds_since(b.get("last_heartbeat", "")) > _SILENT_THRESHOLD_SEC:
                continue
            bee_skills = set(b.get("skills", []))
            if not set(required).issubset(bee_skills):
                continue
            current = len(b.get("current_jobs", []))
            max_c = b.get("max_concurrent", 1)
            if current >= max_c:
                continue
            candidates.append(b)

        if not candidates:
            failed.append((job_dir.name, "no_matching_bee"))
            _log_event(job_dir, "dispatch_failed",
                       reason="no_matching_bee",
                       required_skills=required)
            continue

        # Sort: most recent heartbeat first, then fewest jobs
        candidates.sort(
            key=lambda b: (
                -_seconds_since(b.get("last_heartbeat", "")),  # most recent first
                len(b.get("current_jobs", [])),
            )
        )
        chosen = candidates[0]
        bee_id = chosen["bee_id"]

        # Update job
        meta["owner"] = bee_id
        meta["phase"] = "dispatched"
        meta["dispatched_at"] = datetime.now(timezone.utc).isoformat()
        _write_job_meta(meta_path, meta, body)
        _log_event(job_dir, "dispatched", owner=bee_id)

        # Update bee
        jobs = chosen.get("current_jobs", [])
        if job_dir.name not in jobs:
            jobs.append(job_dir.name)
            chosen["current_jobs"] = jobs
        _save_json(BEES_PATH, bees)

        # Send NATS notification
        try:
            from tools.swarm import swarm_publish
            swarm_publish(
                "swarm.task.new-job",
                {
                    "job_id": job_dir.name,
                    "owner": bee_id,
                    "meta_path": str(meta_path),
                    "required_skills": required,
                },
            )
        except Exception as e:
            # NATS failure is non-fatal — bee can poll or job will be redispatched
            _log_event(job_dir, "nats_publish_failed", error=str(e))

        dispatched.append((job_dir.name, bee_id))

    lines = ["# Dispatch Scan", ""]
    if dispatched:
        lines.append(f"Dispatched {len(dispatched)} job(s):")
        for jid, bid in dispatched:
            lines.append(f"- {jid} -> {bid}")
    else:
        lines.append("No jobs dispatched.")
    if failed:
        lines.append("")
        lines.append(f"Failed {len(failed)} job(s):")
        for jid, reason in failed:
            lines.append(f"- {jid}: {reason}")
    return "\n".join(lines)


def dispatch_job(job_id: str) -> str:
    """Dispatch a specific job by ID."""
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return f"Job {job_id} not found."
    meta_path = job_dir / "meta.md"
    meta, body = _read_job_meta(meta_path)
    if meta is None:
        return f"Job {job_id} has no valid meta.md."
    if meta.get("phase") != "created":
        return f"Job {job_id} is not in 'created' phase (current: {meta.get('phase')})."

    # Force dispatch — same logic as scan but for one job
    required = meta.get("required_skills", [])
    bees = _load_json(BEES_PATH, [])
    candidates = []
    for b in bees:
        if b.get("status") != "alive":
            continue
        if _seconds_since(b.get("last_heartbeat", "")) > _SILENT_THRESHOLD_SEC:
            continue
        bee_skills = set(b.get("skills", []))
        if required and not set(required).issubset(bee_skills):
            continue
        current = len(b.get("current_jobs", []))
        max_c = b.get("max_concurrent", 1)
        if current >= max_c:
            continue
        candidates.append(b)

    if not candidates:
        return f"No matching bee for {job_id} (required: {required})."

    candidates.sort(key=lambda b: (-_seconds_since(b.get("last_heartbeat", "")), len(b.get("current_jobs", []))))
    chosen = candidates[0]
    bee_id = chosen["bee_id"]

    from datetime import datetime, timezone
    meta["owner"] = bee_id
    meta["phase"] = "dispatched"
    meta["dispatched_at"] = datetime.now(timezone.utc).isoformat()
    _write_job_meta(meta_path, meta, body)
    _log_event(job_dir, "dispatched", owner=bee_id)

    jobs = chosen.get("current_jobs", [])
    if job_id not in jobs:
        jobs.append(job_id)
        chosen["current_jobs"] = jobs
    _save_json(BEES_PATH, bees)

    try:
        from tools.swarm import swarm_publish
        swarm_publish(
            "swarm.task.new-job",
            {"job_id": job_id, "owner": bee_id, "meta_path": str(meta_path), "required_skills": required},
        )
    except Exception as e:
        _log_event(job_dir, "nats_publish_failed", error=str(e))

    return f"Dispatched {job_id} -> {bee_id}"


# ── Registry ────────────────────────────────────────────────────────
registry.register(
    name="dispatch_scan",
    description="Scan commander-jobs/ and auto-dispatch created jobs to matching Worker Bees.",
    parameters={"type": "object", "properties": {}},
    handler=dispatch_scan,
    category="commander"
)
registry.register(
    name="dispatch_job",
    description="Dispatch a specific job by ID to the best-matching Worker Bee.",
    parameters={
        "type": "object",
        "properties": {"job_id": {"type": "string"}},
        "required": ["job_id"]
    },
    handler=dispatch_job,
    category="commander"
)
