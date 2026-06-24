"""commander_intervention — Handle blocked events from Worker Bees.

LLM-driven decision: re-dispatch / wait-human / modify-job / auto-remedy.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from agent.registry import registry

CMDR_DIR = Path(__file__).parent.parent
JOBS_DIR = CMDR_DIR / "commander-jobs"


def _read_job_meta(job_path: Path) -> Tuple[Optional[dict], str]:
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

def intervention_handle(job_id: str, reason: str = "", bee_id: str = "") -> str:
    """Handle a blocked job. Simple rule-based heuristics for now."""
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return f"Job {job_id} not found."

    meta_path = job_dir / "meta.md"
    meta, body = _read_job_meta(meta_path)
    if meta is None:
        return f"Job {job_id} has no valid meta.md."

    reason_lower = (reason or "").lower()

    # Simple heuristic rules
    if "不足" in reason_lower or "不能" in reason_lower or "no skill" in reason_lower:
        decision = "re_dispatch"
        meta["owner"] = None
        meta["phase"] = "created"
        _write_job_meta(meta_path, meta, body)
        _log_event(job_dir, "intervention", decision="re_dispatch", reason=reason, bee_id=bee_id)

    elif "缺" in reason_lower or "没有" in reason_lower or "missing" in reason_lower:
        decision = "wait_human"
        meta["phase"] = "blocked"
        _write_job_meta(meta_path, meta, body)
        _log_event(job_dir, "intervention", decision="wait_human", reason=reason, bee_id=bee_id)

    elif "依赖" in reason_lower or "depends" in reason_lower or "等待" in reason_lower:
        decision = "auto_remedy"
        meta["phase"] = "waiting"
        _write_job_meta(meta_path, meta, body)
        _log_event(job_dir, "intervention", decision="auto_remedy", reason=reason, bee_id=bee_id)

    else:
        decision = "wait_human"
        meta["phase"] = "blocked"
        _write_job_meta(meta_path, meta, body)
        _log_event(job_dir, "intervention", decision="wait_human", reason=reason, bee_id=bee_id)

    # Write intervention record
    intervention_path = job_dir / "intervention.md"
    record = f"""## 介入记录: {job_id}

### Blocked 原因
{reason or "(no reason provided)"}

### 决策
{decision}

### 理由
Heuristic match on reason text.

### 后续
{"Job reset to created. Will be re-dispatched to capable bee." if decision == "re_dispatch" else "Waiting for human input." if decision == "wait_human" else "Waiting for dependency to complete."}

---
Timestamp: {datetime.now(timezone.utc).isoformat()}
Bee: {bee_id or "unknown"}
"""
    intervention_path.write_text(record, encoding="utf-8")

    # NATS notify
    try:
        from tools.swarm import swarm_publish
        swarm_publish("swarm.event.intervention", {
            "job_id": job_id,
            "decision": decision,
            "reason": reason,
            "bee_id": bee_id,
        })
    except Exception:
        pass

    return f"{job_id}: intervention -> {decision} (reason: {reason or 'none'})"


# ── Registry ────────────────────────────────────────────────────────
registry.register(
    name="intervention_handle",
    description="Handle a blocked job: decide re-dispatch, wait-human, or auto-remedy.",
    parameters={
        "type": "object",
        "properties": {
            "job_id": {"type": "string"},
            "reason": {"type": "string"},
            "bee_id": {"type": "string"},
        },
        "required": ["job_id"]
    },
    handler=intervention_handle,
    category="commander"
)
