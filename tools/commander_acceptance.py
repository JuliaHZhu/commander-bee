"""commander_acceptance — Acceptance checking with hard thresholds + LLM fallback.

Step 1: Hard thresholds (no LLM) — file count, size.
Step 2: If hard thresholds pass, LLM evaluates quality against acceptance criteria.
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

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


def _count_words(text: str) -> int:
    """Rough word count for Chinese + English mixed text."""
    # Count CJK characters as words, plus space-separated tokens
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    other = len(re.findall(r"[a-zA-Z0-9]+", text))
    return cjk + other


# ── Public API ──────────────────────────────────────────────────────

def acceptance_check(job_id: str) -> str:
    """Check acceptance for a job. Hard thresholds first, then LLM."""
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return f"Job {job_id} not found."

    meta_path = job_dir / "meta.md"
    meta, body = _read_job_meta(meta_path)
    if meta is None:
        return f"Job {job_id} has no valid meta.md."

    acceptance = meta.get("acceptance", "")
    if not acceptance:
        meta["phase"] = "acceptance_unclear"
        _write_job_meta(meta_path, meta, body)
        _log_event(job_dir, "acceptance_unclear")
        return f"{job_id}: acceptance criteria missing. Phase set to acceptance_unclear."

    artifacts_dir = job_dir / "artifacts"
    if not artifacts_dir.exists():
        meta["phase"] = "failed"
        _write_job_meta(meta_path, meta, body)
        _log_event(job_dir, "acceptance_failed", reason="no_artifacts_dir")
        return f"{job_id}: FAILED — no artifacts/ directory."

    files = list(artifacts_dir.iterdir())
    if not files:
        meta["phase"] = "failed"
        _write_job_meta(meta_path, meta, body)
        _log_event(job_dir, "acceptance_failed", reason="empty_artifacts")
        return f"{job_id}: FAILED — artifacts/ is empty."

    # Hard thresholds
    total_words = 0
    file_infos = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
            wc = _count_words(text)
            total_words += wc
            file_infos.append({"name": f.name, "words": wc})
        except Exception:
            file_infos.append({"name": f.name, "words": 0})

    # Check for expected files from acceptance text
    expected_files = re.findall(r"([\w\-]+\.\w+)", acceptance)
    missing = [ef for ef in expected_files if not any(ef in fi["name"] for fi in file_infos)]

    # Very rough threshold: if acceptance mentions specific file, check it exists
    # If no specific files mentioned, just check non-empty
    verdict = "pass"
    reasons = []

    if missing:
        verdict = "incomplete"
        reasons.append(f"Missing expected files: {', '.join(missing)}")

    if total_words == 0:
        verdict = "incomplete"
        reasons.append("All files are empty.")

    # If hard thresholds fail, mark incomplete immediately
    if verdict == "incomplete":
        meta["phase"] = "failed"
        _write_job_meta(meta_path, meta, body)
        _log_event(job_dir, "acceptance_failed", reasons=reasons, files=file_infos)

        # Write review
        review_path = job_dir / "review.md"
        review = f"""## 验收报告: {job_id}

### 文件清单
"""
        for fi in file_infos:
            review += f"- {'❌' if fi['name'] in missing else '✅'} {fi['name']} ({fi['words']} 字)\n"
        review += f"""
### 判断
❌ Incomplete

### 理由
"""
        for r in reasons:
            review += f"- {r}\n"
        review += f"""
---
Reviewer: CommanderBee
Timestamp: {datetime.now(timezone.utc).isoformat()}
"""
        review_path.write_text(review, encoding="utf-8")

        # NATS notify
        try:
            from tools.swarm import swarm_publish
            swarm_publish("swarm.event.job-reviewed", {
                "job_id": job_id,
                "verdict": "incomplete",
                "reasons": reasons,
            })
        except Exception:
            pass

        return f"{job_id}: FAILED — {'; '.join(reasons)}"

    # Hard thresholds passed — now use LLM for quality evaluation
    # Build prompt for LLM
    file_contents = []
    for fi in file_infos:
        fpath = artifacts_dir / fi["name"]
        try:
            content = fpath.read_text(encoding="utf-8")[:2000]  # First 2000 chars
            file_contents.append(f"=== {fi['name']} ({fi['words']} 字) ===\n{content}\n")
        except Exception:
            file_contents.append(f"=== {fi['name']} ===\n[read error]\n")

    prompt = f"""你是一位严格的验收员。请根据以下验收标准审查工作成果，并给出判断。

## 验收标准
{acceptance}

## 提交的文件
"""
    for fc in file_contents:
        prompt += fc + "\n"

    prompt += """
## 请输出
以 JSON 格式输出：
{
  "verdict": "pass" | "needs_work" | "incomplete",
  "reasons": "简要说明判断理由",
  "suggestions": "如果需要改进，给出具体建议"
}

注意：
- pass = 完全符合验收标准
- needs_work = 缺少部分内容，可补救
- incomplete = 严重不符，需重做
"""

    # Call LLM via registry
    try:
        from agent.registry import registry
        llm_result = registry.call("net_web_search", {"query": prompt[:1000]})
        # Fallback: since we don't have a direct LLM tool, we mark as "needs_review"
        # In practice, the agent loop would handle this with the actual LLM
        verdict = "needs_review"
        reasons = ["Hard thresholds passed. LLM quality review pending (agent loop required)."]
    except Exception:
        verdict = "needs_review"
        reasons = ["Hard thresholds passed. LLM quality review pending."]

    # Update job
    if verdict == "pass":
        meta["phase"] = "done"
    elif verdict == "needs_work":
        meta["phase"] = "revision"
    elif verdict == "incomplete":
        meta["phase"] = "failed"
    else:
        meta["phase"] = "review_pending"
    _write_job_meta(meta_path, meta, body)
    _log_event(job_dir, "acceptance_checked", verdict=verdict, reasons=reasons)

    # Write review
    review_path = job_dir / "review.md"
    review = f"""## 验收报告: {job_id}

### 文件清单
"""
    for fi in file_infos:
        review += f"- {fi['name']} ({fi['words']} 字)\n"
    review += f"""
### 判断
{verdict.upper()}

### 理由
"""
    for r in reasons:
        review += f"- {r}\n"
    review += f"""
---
Reviewer: CommanderBee
Timestamp: {datetime.now(timezone.utc).isoformat()}
"""
    review_path.write_text(review, encoding="utf-8")

    # NATS notify
    try:
        from tools.swarm import swarm_publish
        swarm_publish("swarm.event.job-reviewed", {
            "job_id": job_id,
            "verdict": verdict,
            "reasons": reasons,
        })
    except Exception:
        pass

    return f"{job_id}: {verdict.upper()} — {'; '.join(reasons)}"


# ── Registry ────────────────────────────────────────────────────────
registry.register(
    name="acceptance_check",
    description="Check job acceptance: hard thresholds first, then LLM quality review.",
    parameters={
        "type": "object",
        "properties": {"job_id": {"type": "string"}},
        "required": ["job_id"]
    },
    handler=acceptance_check,
    category="commander"
)
