"""job_probe — Background job monitoring system.

Job Probe is an independent system that watches sessions, detects job
associations, and triggers checkpoints at round thresholds.

Design principles:
- Agent does NOT know probe exists (transparent)
- Probe runs independently (cron or background thread)
- Probe actions do NOT consume agent message rounds
- Job files are the source of truth (Markdown + YAML frontmatter)
"""
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

# ── Config ──────────────────────────────────────────────────────────
JOBS_DIR = Path(__file__).parent.parent / "jobs"
WARNING_THRESHOLD = 80      # rounds — append warning to job
FORCE_THRESHOLD   = 85      # rounds — force summary + handoff prep
MAX_ROUNDS = 90             # hard limit where loop trims

# Lock protecting probe_tick() read-modify-write cycles
_probe_lock = threading.Lock()


def _ensure_dir() -> None:
    JOBS_DIR.mkdir(exist_ok=True)


# ── Frontmatter helpers ─────────────────────────────────────────────

_LIST_FIELDS = {"session_ids", "skills", "deliverables", "acceptance"}


def _parse_frontmatter(content: str) -> Tuple[Optional[dict], str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not m:
        return None, content
    try:
        from agent.skills import _parse_yamlish
        meta = _parse_yamlish(m.group(1))
    except Exception:
        meta = {}
    # Type correction: known list fields should be lists
    for k in _LIST_FIELDS:
        if k in meta and not isinstance(meta[k], list):
            if meta[k] in ("", None):
                meta[k] = []
            else:
                meta[k] = [meta[k]]
    return meta, content[m.end():].strip()


def _render_frontmatter(meta: dict) -> str:
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
    return "\n".join(lines)


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


# ── Job directory layout ─────────────────────────────────────────────
#
# jobs/JOB-001/
# ├── meta.md
# ├── sessions/
# │   ├── session-001.md
# │   └── session-002.md
# └── artifacts/
#     └── (symlinks or files)


def _next_job_id() -> str:
    """Scan jobs/ directory for highest JOB-NNN ID."""
    _ensure_dir()
    max_id = 0
    for p in JOBS_DIR.glob("JOB-*"):
        if not p.is_dir():
            continue
        m = re.match(r"JOB-(\d+)", p.name)
        if m:
            max_id = max(max_id, int(m.group(1)))
    return f"JOB-{max_id + 1:03d}"


def _ensure_job_dir(job_id: str) -> Path:
    d = JOBS_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "sessions").mkdir(exist_ok=True)
    (d / "artifacts").mkdir(exist_ok=True)
    return d


def _read_meta(job_id: str) -> Tuple[Optional[dict], str]:
    path = _ensure_job_dir(job_id) / "meta.md"
    if not path.exists():
        return None, ""
    content = path.read_text()
    return _parse_frontmatter(content)


def _write_meta(job_id: str, meta: dict, body: str = "") -> None:
    path = _ensure_job_dir(job_id) / "meta.md"
    content = _render_frontmatter(meta) + "\n" + body
    _atomic_write(path, content)


# ── Event logging ───────────────────────────────────────────────────

def _append_event(job_id: str, event: str) -> None:
    """Append event line to meta.md body (after ## Events section)."""
    meta, body = _read_meta(job_id)
    if meta is None:
        return

    ts = datetime.now().isoformat()
    line = f"- [{ts}] {event}\n"

    marker = "## Events"
    if marker in body:
        parts = body.split(marker, 1)
        before = parts[0]
        after = parts[1]
        # Find end of Events section (next ## or EOF)
        next_section = after.find("\n## ", 1)
        if next_section == -1:
            section = after
            rest = ""
        else:
            section = after[:next_section]
            rest = after[next_section:]
        section = section.rstrip("\n") + "\n" + line
        body = before + marker + section + rest
    else:
        body = body.rstrip() + f"\n\n{marker}\n\n{line}"

    meta["updated_at"] = ts
    _write_meta(job_id, meta, body)


# ── Session scanning ────────────────────────────────────────────────

def _scan_sessions_for_jobs() -> List[Tuple[str, str, int]]:
    """Scan open sessions, find those with JOB-XXX in title/purpose.

    Returns: [(session_id, job_id, message_count), ...]
    """
    try:
        from agent.memory import SessionDB
        db = SessionDB()
    except Exception:
        return []

    results = []
    for row in db.list_open_sessions():
        sid, created_at, title, purpose = row
        text = f"{title or ''} {purpose or ''}"
        m = re.search(r"(JOB-\d+)", text)
        if m:
            job_id = m.group(1)
            msgs = db.get_messages(sid, include_archived=False)
            results.append((sid, job_id, len(msgs)))

    return results


# ── Summary generation ──────────────────────────────────────────────

def _generate_session_summary(session_id: str, job_id: str) -> str:
    """Generate summary from session messages for handoff."""
    try:
        from agent.memory import SessionDB
        db = SessionDB()
        msgs = db.get_messages(session_id, include_archived=False)
    except Exception:
        return "# Summary\n\n(error reading session)\n"

    user_msgs = [m for m in msgs if m.get("role") == "user"]
    assistant_msgs = [m for m in msgs if m.get("role") == "assistant"]
    tool_msgs = [m for m in msgs if m.get("role") == "tool"]

    lines = [
        f"# Session Summary — {session_id}",
        "",
        f"- **Job:** {job_id}",
        f"- **Messages:** {len(msgs)} total ({len(user_msgs)} user, {len(assistant_msgs)} assistant, {len(tool_msgs)} tool)",
        f"- **Generated:** {datetime.now().isoformat()}",
        "",
    ]

    # Recent user requests (last 3)
    if user_msgs:
        lines.append("## Recent User Requests")
        for m in user_msgs[-3:]:
            content = m.get("content", "")[:200]
            lines.append(f"- {content}")
        lines.append("")

    # Key assistant outputs (last 3 non-error)
    if assistant_msgs:
        lines.append("## Key Outputs")
        count = 0
        for m in reversed(assistant_msgs):
            content = m.get("content", "").strip()
            if content and not content.startswith("Error:") and len(content) > 10:
                lines.append(f"- {content[:300]}")
                count += 1
                if count >= 3:
                    break
        lines.append("")

    # Todos if any
    try:
        todos = db.list_todos(session_id)
        if todos:
            lines.append("## Todos")
            for tid, content, status, created_at in todos:
                mark = "[x]" if status == "done" else "[ ]"
                lines.append(f"- {mark} {content}")
            lines.append("")
    except Exception:
        pass

    lines.append("## Next Step\n")
    if user_msgs:
        lines.append(f"Continue from: {user_msgs[-1].get('content', '')[:200]}")
    else:
        lines.append("Awaiting user input.")
    lines.append("")

    return "\n".join(lines)


def _write_session_summary(session_id: str, job_id: str, trigger: str = "threshold") -> Path:
    """Write session summary to job's sessions/ directory."""
    summary = _generate_session_summary(session_id, job_id)

    job_dir = _ensure_job_dir(job_id)
    sessions_dir = job_dir / "sessions"

    existing = sorted(sessions_dir.glob("session-*.md"))
    idx = len(existing) + 1

    frontmatter = {
        "session_id": session_id,
        "generated_at": datetime.now().isoformat(),
        "trigger": trigger,
    }

    content = _render_frontmatter(frontmatter) + summary
    path = sessions_dir / f"session-{idx:03d}.md"
    _atomic_write(path, content)
    return path


# ── Public probe functions ──────────────────────────────────────────

def probe_create_job(title: str, description: str = "", estimated_cycles: int = 1) -> str:
    """Create a new job directory and return its ID."""
    job_id = _next_job_id()
    _ensure_job_dir(job_id)

    meta = {
        "id": job_id,
        "title": title,
        "status": "active",
        "estimated_cycles": estimated_cycles,
        "current_cycle": 0,
        "session_ids": [],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }

    body = f"## Description\n{description}\n"
    _write_meta(job_id, meta, body)

    return f"Created {job_id}: {title}"


def probe_tick() -> str:
    """Run one probe tick: scan all sessions, check thresholds, act."""
    with _probe_lock:
        results = []

        for session_id, job_id, msg_count in _scan_sessions_for_jobs():
            meta, body = _read_meta(job_id)
            if meta is None:
                # Auto-create job if not exists
                probe_create_job(f"Auto-detected {job_id}", estimated_cycles=1)
                meta, body = _read_meta(job_id)
                if meta is None:
                    results.append(f"{job_id}: ERROR could not create/read job")
                    continue

            # Update session tracking
            session_ids = meta.get("session_ids", [])
            if session_id not in session_ids:
                session_ids.append(session_id)
                meta["session_ids"] = session_ids
                meta["updated_at"] = datetime.now().isoformat()
                _write_meta(job_id, meta, body)
                _append_event(job_id, f"SESSION_BOUND {session_id}")

            # Check thresholds
            if msg_count >= FORCE_THRESHOLD:
                path = _write_session_summary(session_id, job_id, trigger="force_threshold")
                _append_event(job_id, f"FORCE_SUMMARY session={session_id} rounds={msg_count} file={path.name}")
                results.append(f"{job_id}: force summary for {session_id} ({msg_count} rounds)")

            elif msg_count >= WARNING_THRESHOLD:
                _append_event(job_id, f"WARNING session={session_id} rounds={msg_count}/{MAX_ROUNDS}")
                results.append(f"{job_id}: warning for {session_id} ({msg_count} rounds)")

        if not results:
            return "Probe tick: no active jobs need attention."

        return "Probe tick:\n" + "\n".join(f"- {r}" for r in results)


def probe_status(job_id: str = "") -> str:
    """Return job status. If no job_id, list all jobs."""
    _ensure_dir()

    if job_id:
        meta, body = _read_meta(job_id)
        if meta is None:
            return f"Error: {job_id} not found."
        return _render_frontmatter(meta) + "\n" + body

    # List all jobs
    jobs = []
    for p in sorted(JOBS_DIR.glob("JOB-*")):
        if not p.is_dir():
            continue
        mid = p.name
        meta, _ = _read_meta(mid)
        if meta:
            jobs.append({
                "id": mid,
                "title": meta.get("title", "(untitled)"),
                "status": meta.get("status", "active"),
                "cycles": f"{meta.get('current_cycle', 0)}/{meta.get('estimated_cycles', 1)}",
            })

    if not jobs:
        return "No jobs found."

    lines = ["# Jobs", ""]
    for j in jobs:
        lines.append(f"- **{j['id']}**: {j['title']} ({j['status']}) — cycle {j['cycles']}")
    return "\n".join(lines)


def probe_handoff(job_id: str) -> str:
    """Prepare handoff package for a job's latest session."""
    meta, _ = _read_meta(job_id)
    if meta is None:
        return f"Error: {job_id} not found."

    session_ids = meta.get("session_ids", [])
    if not session_ids:
        return f"Error: {job_id} has no sessions."

    latest_sid = session_ids[-1]

    # Generate fresh summary
    path = _write_session_summary(latest_sid, job_id, trigger="handoff")
    _append_event(job_id, f"HANDOFF_PREP session={latest_sid} file={path.name}")

    # Build handoff snippet for user
    summary = path.read_text()
    _, body = _parse_frontmatter(summary)

    return f"Handoff ready for {job_id}: {path.name}\n\n{body[:800]}"


# ── Registry ────────────────────────────────────────────────────────
try:
    from agent.registry import registry

    registry.register(
        name="probe_create_job",
        description="Create a new job with title, optional description, and estimated cycles. Returns job ID.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "estimated_cycles": {"type": "integer", "default": 1},
            },
            "required": ["title"],
        },
        handler=probe_create_job,
    )
    registry.register(
        name="probe_tick",
        description="Run one probe tick: scan sessions, check thresholds, auto-summarize.",
        parameters={"type": "object", "properties": {}},
        handler=probe_tick,
    )
    registry.register(
        name="probe_status",
        description="Get job status. Pass job_id for details, or leave empty to list all jobs.",
        parameters={
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
        },
        handler=probe_status,
    )
    registry.register(
        name="probe_handoff",
        description="Prepare handoff package for a job's latest session. Returns summary + next steps.",
        parameters={
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
        handler=probe_handoff,
    )
except Exception:
    pass
