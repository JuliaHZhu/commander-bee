"""commander_monitor — Bee heartbeat & job timeout monitor.

Pure rule engine. No LLM.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from agent.registry import registry

CMDR_DIR = Path(__file__).parent.parent
BEES_PATH = CMDR_DIR / "bees.json"
JOBS_DIR = CMDR_DIR / "commander-jobs"
MONITOR_LOG = CMDR_DIR / "monitor.log"

_SILENT_THRESHOLD_SEC = int(os.environ.get("CB_SILENT_THRESHOLD", "120"))
_ACCEPT_TIMEOUT_SEC = int(os.environ.get("CB_ACCEPT_TIMEOUT", "600"))
_EXECUTE_TIMEOUT_SEC = int(os.environ.get("CB_EXECUTE_TIMEOUT", "14400"))


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
    ts = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(ts)


def _seconds_since(ts: str) -> float:
    try:
        return (datetime.now(timezone.utc) - _parse_iso(ts)).total_seconds()
    except Exception:
        return float("inf")


def _read_job_meta(job_path: Path) -> Tuple[Optional[dict], str]:
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
    events_path = job_dir / "events.jsonl"
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
    }
    event.update(kwargs)
    with events_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


# ── Public API ──────────────────────────────────────────────────────

def monitor_tick() -> str:
    """Run one monitor tick: check heartbeats and job timeouts."""
    bees = _load_json(BEES_PATH, [])
    now = datetime.now(timezone.utc).isoformat()

    bees_silent = 0
    jobs_recovered = 0
    jobs_accept_timeout = 0
    jobs_execute_timeout = 0

    # 1. Check bee heartbeats
    for b in bees:
        hb = b.get("last_heartbeat", "")
        if _seconds_since(hb) > _SILENT_THRESHOLD_SEC:
            if b.get("status") == "alive":
                b["status"] = "silent"
                bees_silent += 1
            # Recover assigned jobs
            for job_id in list(b.get("current_jobs", [])):
                job_dir = JOBS_DIR / job_id
                meta_path = job_dir / "meta.md"
                meta, body = _read_job_meta(meta_path)
                if meta and meta.get("owner") == b["bee_id"]:
                    meta["owner"] = None
                    meta["phase"] = "created"
                    _write_job_meta(meta_path, meta, body)
                    _log_event(job_dir, "job_recovered", reason="bee_silent", bee_id=b["bee_id"])
                    jobs_recovered += 1
            b["current_jobs"] = []

    _save_json(BEES_PATH, bees)

    # 2. Check job timeouts
    if JOBS_DIR.exists():
        for job_dir in sorted(JOBS_DIR.glob("JOB-*")):
            if not job_dir.is_dir():
                continue
            meta_path = job_dir / "meta.md"
            meta, body = _read_job_meta(meta_path)
            if meta is None:
                continue

            phase = meta.get("phase", "")
            dispatched_at = meta.get("dispatched_at", "")
            started_at = meta.get("started_at", "")

            # Accept timeout: dispatched but not started within 10min
            if phase == "dispatched" and dispatched_at:
                if _seconds_since(dispatched_at) > _ACCEPT_TIMEOUT_SEC:
                    meta["owner"] = None
                    meta["phase"] = "created"
                    meta["dispatched_at"] = None
                    _write_job_meta(meta_path, meta, body)
                    _log_event(job_dir, "accept_timeout")
                    jobs_accept_timeout += 1

            # Execute timeout: executing but not done within 4h
            elif phase == "executing" and started_at:
                if _seconds_since(started_at) > _EXECUTE_TIMEOUT_SEC:
                    # Send rescind command
                    try:
                        from tools.swarm import swarm_publish
                        swarm_publish(
                            "swarm.command.rescind",
                            {"job_id": job_dir.name, "reason": "execute_timeout"},
                        )
                    except Exception as e:
                        _log_event(job_dir, "rescind_failed", error=str(e))
                    _log_event(job_dir, "execute_timeout")
                    jobs_execute_timeout += 1

    # 3. Write monitor log
    log_entry = {
        "timestamp": now,
        "bees_silent": bees_silent,
        "jobs_recovered": jobs_recovered,
        "jobs_accept_timeout": jobs_accept_timeout,
        "jobs_execute_timeout": jobs_execute_timeout,
    }
    with MONITOR_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    lines = ["# Monitor Tick", ""]
    lines.append(f"Bees marked silent: {bees_silent}")
    lines.append(f"Jobs recovered: {jobs_recovered}")
    lines.append(f"Accept timeouts: {jobs_accept_timeout}")
    lines.append(f"Execute timeouts: {jobs_execute_timeout}")
    return "\n".join(lines)


# ── Registry ────────────────────────────────────────────────────────
registry.register(
    name="monitor_tick",
    description="Run one monitor tick: check bee heartbeats and job timeouts.",
    parameters={"type": "object", "properties": {}},
    handler=monitor_tick,
    category="commander"
)
