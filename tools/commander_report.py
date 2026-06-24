"""commander_report — Summarize swarm status into human-readable report.

LLM-driven for summary generation. Pure rules for data aggregation.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from agent.registry import registry

CMDR_DIR = Path(__file__).parent.parent
BEES_PATH = CMDR_DIR / "bees.json"
JOBS_DIR = CMDR_DIR / "commander-jobs"


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


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


# ── Public API ──────────────────────────────────────────────────────

def report_generate() -> str:
    """Generate a status report of the swarm and jobs."""
    bees = _load_json(BEES_PATH, [])

    bees_alive = [b for b in bees if b.get("status") == "alive"]
    bees_busy = [b for b in bees_alive if len(b.get("current_jobs", [])) > 0]
    bees_silent = [b for b in bees if b.get("status") == "silent"]

    jobs = []
    if JOBS_DIR.exists():
        for job_dir in sorted(JOBS_DIR.glob("JOB-*")):
            if not job_dir.is_dir():
                continue
            meta, _ = _read_job_meta(job_dir / "meta.md")
            if meta:
                jobs.append({
                    "id": job_dir.name,
                    "phase": meta.get("phase", "unknown"),
                    "title": meta.get("title", "(untitled)"),
                    "owner": meta.get("owner"),
                    "updated_at": meta.get("updated_at", ""),
                })

    phases = {}
    for j in jobs:
        p = j["phase"]
        phases[p] = phases.get(p, 0) + 1

    # Recent done jobs (top 5)
    done_jobs = [j for j in jobs if j["phase"] == "done"]
    done_jobs.sort(key=lambda j: j.get("updated_at", ""), reverse=True)
    recent_done = done_jobs[:5]

    # Anomalies
    anomalies = []
    for j in jobs:
        if j["phase"] == "blocked":
            anomalies.append(f"- {j['id']}: blocked, owner={j['owner']}")
        elif j["phase"] == "failed":
            anomalies.append(f"- {j['id']}: failed, needs re-dispatch")
    for b in bees_silent:
        anomalies.append(f"- {b['bee_id']}: silent since {b.get('last_heartbeat', '?')}")

    lines = [
        "## 蜂群状态报告",
        f"**生成时间**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
        "",
        "### 蜂群状态",
        f"- 在线 Bee: {len(bees_alive)} 台" + (f" ({', '.join(b['bee_id'] for b in bees_alive)})" if bees_alive else ""),
        f"- 繁忙 Bee: {len(bees_busy)} 台",
        f"- 离线 Bee: {len(bees_silent)} 台" + (f" ({', '.join(b['bee_id'] for b in bees_silent)})" if bees_silent else ""),
        "",
        "### 任务进度",
    ]
    for p in ["created", "dispatched", "executing", "review_pending", "revision", "done", "blocked", "failed"]:
        if p in phases:
            lines.append(f"- {p}: {phases[p]} 个")
    total = len(jobs)
    lines.append(f"- 总计: {total} 个")

    if recent_done:
        lines.extend(["", "### 最近完成（Top 5）"])
        for j in recent_done:
            lines.append(f"- {j['id']}: {j['title']} · ✅ {j.get('updated_at', '')[:16]}")

    if anomalies:
        lines.extend(["", "### 需要注意"])
        lines.extend(anomalies)
    else:
        lines.extend(["", "### 需要注意", "- 无异常"])

    return "\n".join(lines)


# ── Registry ────────────────────────────────────────────────────────
registry.register(
    name="report_generate",
    description="Generate a human-readable status report of the swarm and jobs.",
    parameters={"type": "object", "properties": {}},
    handler=report_generate,
    category="commander"
)
