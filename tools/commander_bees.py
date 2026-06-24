"""commander_bees — Bees.json heartbeat registry & maintenance.

Pure rule engine. No LLM involved.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from agent.registry import registry

# ── Config ──────────────────────────────────────────────────────────
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(ts: str) -> datetime:
    """Parse ISO timestamp, handling both Z and +00:00 suffixes."""
    ts = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(ts)


def _seconds_since(ts: str) -> float:
    try:
        return (datetime.now(timezone.utc) - _parse_iso(ts)).total_seconds()
    except Exception:
        return float("inf")


# ── Public API ──────────────────────────────────────────────────────

def bees_list(status_filter: str = "") -> str:
    """List all registered bees. Optionally filter by status."""
    bees = _load_json(BEES_PATH, [])
    if status_filter:
        bees = [b for b in bees if b.get("status") == status_filter]
    if not bees:
        return "No bees registered."
    lines = ["# Bees", ""]
    for b in bees:
        lines.append(
            f"- **{b['bee_id']}** ({b.get('hostname', '?')}) | "
            f"status={b.get('status', '?')} | "
            f"jobs={len(b.get('current_jobs', []))}/{b.get('max_concurrent', '?')} | "
            f"skills={', '.join(b.get('skills', []))} | "
            f"heartbeat={b.get('last_heartbeat', 'never')}"
        )
    return "\n".join(lines)


def bees_heartbeat(bee_id: str, hostname: str = "", skills: list = None,
                   max_concurrent: int = 3, current_jobs: list = None) -> str:
    """Register or update a bee's heartbeat.

    If bee_id does not exist, auto-register. If silent, revive to alive.
    """
    bees = _load_json(BEES_PATH, [])
    now = _now_iso()
    skills = skills or []
    current_jobs = current_jobs or []

    for b in bees:
        if b["bee_id"] == bee_id:
            b["hostname"] = hostname or b.get("hostname", "")
            b["skills"] = skills if skills else b.get("skills", [])
            b["max_concurrent"] = max_concurrent if max_concurrent else b.get("max_concurrent", 3)
            b["current_jobs"] = current_jobs
            b["last_heartbeat"] = now
            if b.get("status") == "silent":
                b["status"] = "alive"
            _save_json(BEES_PATH, bees)
            return f"Updated heartbeat for {bee_id}"

    # New bee
    bees.append({
        "bee_id": bee_id,
        "hostname": hostname or bee_id,
        "status": "alive",
        "skills": skills,
        "max_concurrent": max_concurrent,
        "current_jobs": current_jobs,
        "last_heartbeat": now,
    })
    _save_json(BEES_PATH, bees)
    return f"Registered new bee {bee_id}"


def bees_update_status(bee_id: str, status: str) -> str:
    """Manually update a bee's status."""
    bees = _load_json(BEES_PATH, [])
    for b in bees:
        if b["bee_id"] == bee_id:
            b["status"] = status
            _save_json(BEES_PATH, bees)
            return f"Updated {bee_id} status to {status}"
    return f"Bee {bee_id} not found"


def bees_assign_job(bee_id: str, job_id: str) -> str:
    """Add a job to bee's current_jobs."""
    bees = _load_json(BEES_PATH, [])
    for b in bees:
        if b["bee_id"] == bee_id:
            jobs = b.get("current_jobs", [])
            if job_id not in jobs:
                jobs.append(job_id)
                b["current_jobs"] = jobs
                _save_json(BEES_PATH, bees)
            return f"Assigned {job_id} to {bee_id}"
    return f"Bee {bee_id} not found"


def bees_unassign_job(bee_id: str, job_id: str) -> str:
    """Remove a job from bee's current_jobs."""
    bees = _load_json(BEES_PATH, [])
    for b in bees:
        if b["bee_id"] == bee_id:
            jobs = b.get("current_jobs", [])
            if job_id in jobs:
                jobs.remove(job_id)
                b["current_jobs"] = jobs
                _save_json(BEES_PATH, bees)
            return f"Unassigned {job_id} from {bee_id}"
    return f"Bee {bee_id} not found"


# ── Registry ────────────────────────────────────────────────────────
registry.register(
    name="bees_list",
    description="List all registered Worker Bees. Filter by status: alive, silent.",
    parameters={
        "type": "object",
        "properties": {
            "status_filter": {"type": "string", "description": "Filter by status: alive, silent, or empty for all"}
        }
    },
    handler=bees_list,
    category="commander"
)
registry.register(
    name="bees_heartbeat",
    description="Register or update a bee heartbeat. Auto-creates new bee if not exists.",
    parameters={
        "type": "object",
        "properties": {
            "bee_id": {"type": "string"},
            "hostname": {"type": "string"},
            "skills": {"type": "array", "items": {"type": "string"}},
            "max_concurrent": {"type": "integer", "default": 3},
            "current_jobs": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["bee_id"]
    },
    handler=bees_heartbeat,
    category="commander"
)
