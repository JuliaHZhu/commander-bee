"""
Cron job scheduler — executes due jobs.

Provides tick() which checks for due jobs and runs them.
The gateway calls this every 60 seconds from a background thread.

Uses a file-based lock (~/.worker-bee/cron/.tick.lock) so only one tick
runs at a time if multiple processes overlap.
"""

import concurrent.futures
import contextvars
import json
import logging
import os
import subprocess
import sys
import urllib.request

from pathlib import Path
from typing import List, Optional, Any

try:
    import fcntl
except ImportError:
    fcntl = None

sys.path.insert(0, str(Path(__file__).parent.parent))

from cron.jobs import (
    get_due_jobs,
    mark_job_run,
    save_job_output,
    advance_next_run,
    OUTPUT_DIR,
    CRON_DIR,
)

from worker_bee.workspace import get_workspace

logger = logging.getLogger(__name__)

SILENT_MARKER = "[SILENT]"

# ── Workspace guard for cron scripts ─────────────────────────────────────────────────────

_CRON_WORKSPACE = str(get_workspace())


def _is_inside_workspace(path: str) -> bool:
    try:
        target = Path(path).resolve()
        root = Path(_CRON_WORKSPACE).resolve()
        return target == root or root in target.parents
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Delivery — simplified: Feishu / Discord webhook only
# ---------------------------------------------------------------------------

KNOWN_PLATFORMS = frozenset({"feishu", "discord"})


def _send_feishu(content: str) -> str:
    """Send text message via Feishu bot webhook."""
    url = os.environ.get("FEISHU_WEBHOOK_URL", "")
    if not url:
        return json.dumps({"error": "FEISHU_WEBHOOK_URL not set"}, ensure_ascii=False)
    payload = {"msg_type": "text", "content": {"text": content}}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            return json.dumps({"status": resp.status, "body": body}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _send_discord(content: str) -> str:
    """Send text message via Discord webhook."""
    url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not url:
        return json.dumps({"error": "DISCORD_WEBHOOK_URL not set"}, ensure_ascii=False)
    payload = {"content": content}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8") or "(empty)"
            return json.dumps({"status": resp.status, "body": body}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _platform_has_webhook(platform: str) -> bool:
    if platform == "feishu":
        return bool(os.environ.get("FEISHU_WEBHOOK_URL"))
    if platform == "discord":
        return bool(os.environ.get("DISCORD_WEBHOOK_URL"))
    return False


def _send_to_platform(content: str, platform: str) -> str:
    if platform == "feishu":
        return _send_feishu(content)
    if platform == "discord":
        return _send_discord(content)
    return json.dumps({"error": f"Unsupported platform: {platform}"}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Resolve delivery targets
# ---------------------------------------------------------------------------

def _resolve_origin(job: dict) -> Optional[dict]:
    origin = job.get("origin")
    if not isinstance(origin, dict):
        return None
    platform = origin.get("platform")
    chat_id = origin.get("chat_id")
    if platform and chat_id:
        return origin
    return None


def _normalize_deliver_value(deliver: Any) -> str:
    if deliver is None or deliver == "":
        return "local"
    if isinstance(deliver, (list, tuple)):
        parts = [str(p).strip() for p in deliver if str(p).strip()]
        return ",".join(parts) if parts else "local"
    return str(deliver)


def _resolve_single_delivery_target(job: dict, deliver_value: str) -> Optional[dict]:
    origin = _resolve_origin(job)

    if deliver_value == "local":
        return None

    if deliver_value == "origin":
        if origin:
            return {
                "platform": origin["platform"],
                "chat_id": str(origin["chat_id"]),
                "thread_id": origin.get("thread_id"),
            }
        # Fallback: any platform with a configured webhook
        for platform in sorted(KNOWN_PLATFORMS):
            if _platform_has_webhook(platform):
                return {"platform": platform, "chat_id": "home", "thread_id": None}
        return None

    if ":" in deliver_value:
        platform_name, _ = deliver_value.split(":", 1)
        platform_key = platform_name.lower()
        if platform_key not in KNOWN_PLATFORMS:
            return None
        return {"platform": platform_key, "chat_id": "home", "thread_id": None}

    platform_name = deliver_value.lower()
    if origin and origin.get("platform") == platform_name:
        return {
            "platform": platform_name,
            "chat_id": str(origin["chat_id"]),
            "thread_id": origin.get("thread_id"),
        }
    if platform_name not in KNOWN_PLATFORMS:
        return None
    if not _platform_has_webhook(platform_name):
        return None
    return {"platform": platform_name, "chat_id": "home", "thread_id": None}


_ROUTING_TOKENS = frozenset({"all"})


def _expand_routing_tokens(part: str) -> List[str]:
    token = part.lower()
    if token not in _ROUTING_TOKENS:
        return [part]
    expanded = []
    for platform in sorted(KNOWN_PLATFORMS):
        if _platform_has_webhook(platform):
            expanded.append(platform)
    return expanded


def _resolve_delivery_targets(job: dict) -> List[dict]:
    deliver = _normalize_deliver_value(job.get("deliver", "local"))
    if deliver == "local":
        return []

    raw_parts = [p.strip() for p in deliver.split(",") if p.strip()]
    parts: List[str] = []
    for raw in raw_parts:
        parts.extend(_expand_routing_tokens(raw))

    seen = set()
    targets = []
    for part in parts:
        target = _resolve_single_delivery_target(job, part)
        if target:
            key = (target["platform"].lower(), str(target["chat_id"]), target.get("thread_id"))
            if key not in seen:
                seen.add(key)
                targets.append(target)
    return targets


# ---------------------------------------------------------------------------
# Output + context_from helpers
# ---------------------------------------------------------------------------

def load_most_recent_output(job_ids: List[str]) -> str:
    """Load the most recent output from upstream jobs."""
    parts = []
    for job_id in job_ids:
        job_output_dir = OUTPUT_DIR / job_id
        if not job_output_dir.exists():
            continue
        files = sorted(job_output_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            try:
                content = files[0].read_text(encoding="utf-8")
                parts.append(f"--- Output from job {job_id} ---\n{content}\n")
            except Exception as e:
                logger.warning("Failed to read output for job %s: %s", job_id, e)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Build job prompt (skills loading)
# ---------------------------------------------------------------------------

def build_job_prompt(
    job: dict,
    skill_manager,
    context_from_outputs: str = "",
) -> str:
    """Build the full prompt for a cron job, including skill context."""
    prompt = _coerce_job_text(job.get("prompt"), "")
    skills = job.get("skills") or []

    parts = []
    if context_from_outputs:
        parts.append(context_from_outputs)

    if skills and skill_manager:
        skill_ctx = skill_manager.build_context_for_skills(skills)
        if skill_ctx:
            parts.append(skill_ctx)

    if parts:
        full = "\n\n".join(parts)
        if prompt:
            return f"{full}\n\n---\n\n{prompt}"
        return full
    return prompt


def _coerce_job_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    return str(value)


# ---------------------------------------------------------------------------
# Script execution
# ---------------------------------------------------------------------------

def run_job_script(script_path: str, job: dict, output_path: str) -> str:
    """Run a script for a cron job and return its stdout."""
    workdir = job.get("workdir")
    resolved_script = Path(script_path).expanduser()
    if not resolved_script.is_absolute():
        resolved_script = Path.cwd() / resolved_script

    # Workspace guard
    if not _is_inside_workspace(str(resolved_script)):
        return (
            f"Error: script outside workspace disallowed. "
            f"Script: {resolved_script} | Workspace: {_CRON_WORKSPACE}"
        )

    if not resolved_script.exists():
        return f"Script not found: {resolved_script}"

    interpreter = sys.executable
    if resolved_script.suffix == ".sh":
        interpreter = "/bin/bash"
    elif resolved_script.suffix == ".bash":
        interpreter = "/bin/bash"

    env = dict(os.environ)
    env["CRON_JOB_ID"] = job.get("id", "")
    env["CRON_OUTPUT_PATH"] = output_path
    env["CRON_PROMPT"] = _coerce_job_text(job.get("prompt"), "")

    try:
        result = subprocess.run(
            [interpreter, str(resolved_script)],
            capture_output=True,
            text=True,
            cwd=workdir or None,
            env=env,
            timeout=300,
        )
        output = result.stdout
        if result.stderr:
            output += f"\n\n[stderr]\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n\n[exit code {result.returncode}]"
        return output
    except subprocess.TimeoutExpired:
        return "Script timed out after 300 seconds"
    except Exception as e:
        return f"Script execution failed: {e}"


# ---------------------------------------------------------------------------
# File lock
# ---------------------------------------------------------------------------

_lock_path = CRON_DIR / ".tick.lock"
_lock_file = None


def acquire_tick_lock() -> bool:
    """Acquire an exclusive file lock for the tick process."""
    global _lock_file
    CRON_DIR.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(_lock_path), os.O_RDWR | os.O_CREAT)
        _lock_file = os.fdopen(fd, "r+")
        if fcntl:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (OSError, IOError):
        if _lock_file:
            try:
                _lock_file.close()
            except OSError:
                pass
            _lock_file = None
        return False


def release_tick_lock():
    """Release the tick file lock."""
    global _lock_file
    if _lock_file:
        try:
            if fcntl:
                fcntl.flock(_lock_file.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            _lock_file.close()
        except OSError:
            pass
        _lock_file = None


# ---------------------------------------------------------------------------
# Run a single job
# ---------------------------------------------------------------------------

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="cron")


def run_job(job: dict, default_config: dict, skill_manager=None) -> None:
    """Execute a single cron job."""
    job_id = job.get("id", "?")
    job_name = job.get("name", job_id)
    logger.info("Running job '%s' (%s)", job_name, job_id)

    # Advance next_run_at for recurring jobs before execution (anti-double-fire)
    advance_next_run(job_id)

    output = ""
    success = False
    error = None
    delivery_error = None

    try:
        # Build context_from
        context_from = job.get("context_from")
        context_from_outputs = ""
        if isinstance(context_from, list) and context_from:
            context_from_outputs = load_most_recent_output(context_from)

        # Script-only mode
        if job.get("no_agent") and job.get("script"):
            script_path = job["script"]
            output_file = save_job_output(job_id, "")
            output = run_job_script(script_path, job, str(output_file))
            success = True
        else:
            # Agent mode
            # Inject pending tasks assigned to this job
            task_context = ""
            try:
                from worker_bee.memory import SessionDB
                db = SessionDB()
                pending = db.get_pending_tasks_for_job(job_id)
                if pending:
                    lines = ["[Pending tasks assigned to you]", ""]
                    for tid, content, pri in pending:
                        star = "⭐" if pri > 0 else ""
                        lines.append(f"  #{tid}{star}: {content}")
                    task_context = "\n".join(lines) + "\n\n"
            except Exception:
                pass  # Task DB may not exist yet; non-critical

            full_prompt = build_job_prompt(job, skill_manager, context_from_outputs)
            if task_context:
                full_prompt = task_context + full_prompt
            if not full_prompt.strip():
                output = "Job has no prompt. Nothing to do."
                success = True
            else:
                # Build agent config
                agent_config = dict(default_config)
                if job.get("model"):
                    agent_config["model"] = job["model"]
                if job.get("provider"):
                    agent_config["provider"] = job["provider"]
                if job.get("base_url"):
                    agent_config["base_url"] = job["base_url"]

                # Toolsets
                toolsets = job.get("enabled_toolsets")
                if toolsets:
                    agent_config["tools"] = toolsets

                from worker_bee.agent import AIAgent

                agent = AIAgent(agent_config)
                messages = [{"role": "user", "content": full_prompt}]
                output = agent.run(messages, tools=toolsets if toolsets is not None else [])
                success = True

    except Exception as e:
        logger.exception("Job '%s' failed: %s", job_name, e)
        error = str(e)
        output = f"Error: {e}"

    # Save output
    save_job_output(job_id, output)

    # Deliver
    is_silent = output.strip().startswith(SILENT_MARKER)
    if not is_silent:
        targets = _resolve_delivery_targets(job)
        for target in targets:
            platform = target["platform"]
            try:
                result = _send_to_platform(output, platform)
                parsed = json.loads(result)
                if "error" in parsed:
                    logger.warning(
                        "Delivery to %s failed for job '%s': %s",
                        platform, job_name, parsed["error"],
                    )
                    delivery_error = f"{platform}: {parsed['error']}"
            except Exception as e:
                logger.warning("Delivery to %s failed for job '%s': %s", platform, job_name, e)
                delivery_error = f"{platform}: {e}"

    mark_job_run(job_id, success, error, delivery_error)
    logger.info("Job '%s' finished — success=%s", job_name, success)


# ---------------------------------------------------------------------------
# Tick — main entry point
# ---------------------------------------------------------------------------

def tick(default_config: dict, skill_manager=None) -> int:
    """Check for due jobs and execute them. Also run job-probe tick.

    Returns the number of agent jobs executed (probe tick is separate).
    """
    if not acquire_tick_lock():
        logger.info("Tick lock held by another process; skipping.")
        return 0

    try:
        # ── Job Probe tick (background monitoring, never fails tick) ──
        try:
            from tools.job_probe import probe_tick
            probe_result = probe_tick()
            if "no active jobs" not in probe_result.lower():
                logger.info("Probe tick: %s", probe_result.replace("\n", " | "))
        except Exception:
            logger.exception("Probe tick failed")

        jobs = get_due_jobs()
        if not jobs:
            return 0

        logger.info("Tick: %d job(s) due", len(jobs))
        futures = []
        for job in jobs:
            ctx = contextvars.copy_context()
            future = _executor.submit(ctx.run, run_job, job, default_config, skill_manager)
            futures.append(future)

        for future in futures:
            try:
                future.result(timeout=600)
            except Exception:
                logger.exception("Cron job execution failed")

        return len(jobs)
    finally:
        release_tick_lock()


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------

def shutdown():
    """Shut down the scheduler thread pool."""
    _executor.shutdown(wait=False)
