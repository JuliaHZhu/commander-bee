#!/usr/bin/env python3
"""
wb — WorkerBee unified CLI.

Direct command-line access to job-probe and todo-ball-machine,
without routing through the agent loop.

Usage:
    wb job create "title" "description" [--cycles N]
    wb job ls
    wb job status JOB-001
    wb job handoff JOB-001
    wb job audit JOB-001
    wb job tick

    wb todo dashboard
    wb todo today
    wb todo draw morning
    wb todo quick
    wb todo complete morning
    wb todo history [N]
    wb todo stats [N]
    wb todo day [YYYY-MM-DD]
    wb todo box
    wb todo cycle
    wb todo new-cycle [name]
"""

import argparse
import shutil
import sys
from pathlib import Path

# Ensure repo root is importable when running in dev mode
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_LARK_CLI = shutil.which("lark-cli") or str(Path.home() / ".local" / "bin" / "lark-cli")


# ---------------------------------------------------------------------------
# Job sub-command
# ---------------------------------------------------------------------------
def _job_create(args):
    from tools.job_probe import probe_create_job
    out = probe_create_job(
        title=args.title,
        description=args.description or "",
        estimated_cycles=args.cycles,
    )
    print(out)


def _job_ls(args):
    from tools.job_probe import probe_status
    out = probe_status()
    print(out)


def _job_status(args):
    from tools.job_probe import probe_status
    out = probe_status(job_id=args.job_id)
    print(out)


def _job_handoff(args):
    from tools.job_probe import probe_handoff
    out = probe_handoff(job_id=args.job_id)
    print(out)


def _job_audit(args):
    from tools.job_probe import probe_status
    out = probe_status(job_id=args.job_id)
    print(out)


def _job_tick(args):
    from tools.job_probe import probe_tick
    out = probe_tick()
    print(out)


def _job_run(args):
    """Execute a job: read meta, infer skill, run tools, write artifacts."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))

    from tools.job_probe import _read_meta, _ensure_job_dir, _append_event, _atomic_write
    from worker_bee.registry import registry

    job_id = args.job_id
    meta, body = _read_meta(job_id)
    if meta is None:
        print(f"Error: {job_id} not found.")
        sys.exit(1)

    title = meta.get("title", "")
    # description may be in meta or in body; fallback to title
    description = meta.get("description", "")
    if not description and body:
        # Extract only the ## Description section, ignore Events / other sections
        import re as _re
        m = _re.search(r"## Description\s*\n+(.*?)(?=\n## |\Z)", body, _re.DOTALL)
        if m:
            description = m.group(1).strip()
        else:
            # No Description section — grab first non-heading paragraph
            lines = [l.strip() for l in body.splitlines() if l.strip() and not l.strip().startswith("#")]
            description = " ".join(lines[:3]) if lines else title

    # Ensure numeric fields are int
    meta["current_cycle"] = int(meta.get("current_cycle", 0))
    meta["estimated_cycles"] = int(meta.get("estimated_cycles", 1))

    # Simple skill inference from title keywords
    title_lower = title.lower()
    if any(k in title_lower for k in ("调研", "研究", "research", "search", "调查", "查找")):
        skill = "research"
    elif any(k in title_lower for k in ("写", "write", "draft", "生成", "create")):
        skill = "write"
    else:
        skill = "general"

    print(f"[{job_id}] Detected skill: {skill}")
    print(f"[{job_id}] Title: {title}")

    # --- Research skill execution ---
    if skill == "research":
        # Build a clean search query:
        # 1. Start from title, strip meta verbs
        # 2. If result is too short, append description nouns
        meta_verbs = ("调研", "研究", "research", "search", "调查", "查找", "了解", "分析")
        clean_title = title
        for verb in meta_verbs:
            clean_title = clean_title.replace(verb, "")
        clean_title = clean_title.strip()

        query = clean_title if clean_title else title
        # NOTE: We intentionally do NOT append description to the search query.
        # Title already contains the core entity; description is human-readable
        # context that may confuse search engines with meta-verbs.
        print(f"[{job_id}] Searching: {query}")

        results = registry.call("net_web_search", {"query": query, "num_results": 5})
        print(f"[{job_id}] Search returned {len(results)} chars")

        # Extract top URLs
        import re
        urls = re.findall(r"https?://[^\s\n]+", results)
        extracts = []
        for url in urls[:3]:
            print(f"[{job_id}] Extracting: {url}")
            text = registry.call("net_web_extract", {"url": url})
            extracts.append(f"## Source: {url}\n\n{text[:1500]}\n")

        # Build report
        report_lines = [
            f"# 调研报告: {title}",
            "",
            f"生成时间: {__import__('datetime').datetime.now().isoformat()}",
            "",
            "## 搜索结果",
            "",
            results,
            "",
            "## 内容摘要",
            "",
            "\n".join(extracts),
            "",
            "## 结论",
            "",
            "（待 AI 总结）",
            "",
        ]
        report = "\n".join(report_lines)

        # Write artifacts with naming: {skill}-{YYYY-MM-DD}-{type}.md
        from datetime import datetime as _dt
        today = _dt.now().strftime("%Y-%m-%d")

        job_dir = _ensure_job_dir(job_id)
        artifacts_dir = job_dir / "artifacts"

        # Save extracts individually
        for idx, extract in enumerate(extracts, 1):
            # Extract domain from "## Source: url" line for filename
            src_line = extract.split("\n")[0]
            domain = f"source-{idx}"
            m = __import__("re").search(r"Source: https?://([^/]+)", src_line)
            if m:
                domain = m.group(1).replace(".", "_")
            extract_path = artifacts_dir / f"{skill}-{today}-extract-{domain}.md"
            _atomic_write(extract_path, extract)
            print(f"[{job_id}] Extract written: {extract_path.name}")

        # Save main report
        report_path = artifacts_dir / f"{skill}-{today}-report.md"
        tmp = report_path.with_suffix(".tmp")
        tmp.write_text(report, encoding="utf-8")
        tmp.replace(report_path)

        _append_event(job_id, f"JOB_RUN skill={skill} query='{query}' artifacts={len(extracts)+1}")
        print(f"[{job_id}] Report written: {report_path.name}")

    else:
        print(f"[{job_id}] Skill '{skill}' execution not yet implemented.")
        sys.exit(1)

    # Update meta
    meta["current_cycle"] = meta.get("current_cycle", 0) + 1
    from tools.job_probe import _write_meta
    _write_meta(job_id, meta, body)
    print(f"[{job_id}] Cycle {meta['current_cycle']}/{meta.get('estimated_cycles', 1)} complete.")


def _add_job_parser(sub):
    job = sub.add_parser("job", help="Job probe commands")
    job_sub = job.add_subparsers(dest="job_cmd", required=True)

    p = job_sub.add_parser("create", help="Create a new job")
    p.add_argument("title")
    p.add_argument("description", nargs="?", default="")
    p.add_argument("--cycles", type=int, default=1, help="Estimated cycles (default 1)")
    p.set_defaults(func=_job_create)

    p = job_sub.add_parser("ls", help="List all jobs")
    p.set_defaults(func=_job_ls)

    p = job_sub.add_parser("status", help="Show job details")
    p.add_argument("job_id")
    p.set_defaults(func=_job_status)

    p = job_sub.add_parser("handoff", help="Generate handoff package for a job")
    p.add_argument("job_id")
    p.set_defaults(func=_job_handoff)

    p = job_sub.add_parser("audit", help="Audit / review a job")
    p.add_argument("job_id")
    p.set_defaults(func=_job_audit)

    p = job_sub.add_parser("tick", help="Manually trigger probe tick")
    p.set_defaults(func=_job_tick)

    p = job_sub.add_parser("run", help="Execute a job (auto-detect skill and run)")
    p.add_argument("job_id")
    p.set_defaults(func=_job_run)


# ---------------------------------------------------------------------------
# Todo sub-command
# ---------------------------------------------------------------------------
def _todo_dashboard(args):
    from tools.todo_ball_machine import todo_ball_machine
    print(todo_ball_machine(action="dashboard"))


def _todo_today(args):
    from tools.todo_ball_machine import todo_ball_machine
    print(todo_ball_machine(action="today"))


def _todo_draw(args):
    from tools.todo_ball_machine import todo_ball_machine
    print(todo_ball_machine(action="draw", session=args.session))


def _todo_quick(args):
    from tools.todo_ball_machine import todo_ball_machine
    print(todo_ball_machine(action="quick_draw"))


def _todo_complete(args):
    from tools.todo_ball_machine import todo_ball_machine
    print(todo_ball_machine(action="complete", session=args.session))


def _todo_history(args):
    from tools.todo_ball_machine import todo_ball_machine
    n = str(args.days) if args.days else None
    print(todo_ball_machine(action="history", content=n))


def _todo_stats(args):
    from tools.todo_ball_machine import todo_ball_machine
    n = str(args.days) if args.days else None
    print(todo_ball_machine(action="stats", content=n))


def _todo_day(args):
    from tools.todo_ball_machine import todo_ball_machine
    d = args.date or None
    print(todo_ball_machine(action="day", content=d))


def _todo_box(args):
    from tools.todo_ball_machine import todo_ball_machine
    print(todo_ball_machine(action="box_list"))


def _todo_cycle(args):
    from tools.todo_ball_machine import todo_ball_machine
    print(todo_ball_machine(action="cycle_status"))


def _todo_new_cycle(args):
    from tools.todo_ball_machine import todo_ball_machine
    print(todo_ball_machine(action="new_cycle", content=args.name))


def _add_todo_parser(sub):
    todo = sub.add_parser("todo", help="Todo Ball Machine commands")
    todo_sub = todo.add_subparsers(dest="todo_cmd", required=True)

    p = todo_sub.add_parser("dashboard", aliases=["d"], help="System dashboard")
    p.set_defaults(func=_todo_dashboard)

    p = todo_sub.add_parser("today", aliases=["t"], help="Today's sessions")
    p.set_defaults(func=_todo_today)

    p = todo_sub.add_parser("draw", help="Draw a session (morning/afternoon/evening/overtime)")
    p.add_argument("session")
    p.set_defaults(func=_todo_draw)

    p = todo_sub.add_parser("quick", aliases=["q"], help="Quick draw three sessions")
    p.set_defaults(func=_todo_quick)

    p = todo_sub.add_parser("complete", aliases=["done"], help="Mark session complete")
    p.add_argument("session")
    p.set_defaults(func=_todo_complete)

    p = todo_sub.add_parser("history", aliases=["h"], help="History (default 7 days)")
    p.add_argument("days", nargs="?", type=int, default=7)
    p.set_defaults(func=_todo_history)

    p = todo_sub.add_parser("stats", aliases=["s"], help="Stats report (default 7 days)")
    p.add_argument("days", nargs="?", type=int, default=7)
    p.set_defaults(func=_todo_stats)

    p = todo_sub.add_parser("day", help="Detail for a specific date (YYYY-MM-DD)")
    p.add_argument("date", nargs="?", default=None)
    p.set_defaults(func=_todo_day)

    p = todo_sub.add_parser("box", aliases=["b"], help="Box quota list")
    p.set_defaults(func=_todo_box)

    p = todo_sub.add_parser("cycle", aliases=["c"], help="Cycle status")
    p.set_defaults(func=_todo_cycle)

    p = todo_sub.add_parser("new-cycle", help="Start a new cycle")
    p.add_argument("name", nargs="?", default=None)
    p.set_defaults(func=_todo_new_cycle)


# ---------------------------------------------------------------------------
# Swarm sub-command
# ---------------------------------------------------------------------------
def _swarm_listen(args):
    """Start the NATS swarm listener (background process)."""
    import subprocess
    import os
    from pathlib import Path

    listener_path = Path(__file__).parent.parent / "swarm" / "listener.py"
    if not listener_path.exists():
        print(f"Error: listener not found at {listener_path}")
        sys.exit(1)

    nats_url = args.url or os.environ.get("SWARM_NATS_URL", "nats://localhost:4222")
    print(f"[wb swarm listen] Starting listener → {nats_url}")
    print("[wb swarm listen] Writing messages to ~/.worker-bee/mailbox/inbox/")
    print("[wb swarm listen] Press Ctrl+C to stop")
    sys.stdout.flush()

    try:
        subprocess.run(
            [sys.executable, str(listener_path), nats_url],
            check=True,
        )
    except KeyboardInterrupt:
        print("\n[wb swarm listen] Stopped.")


def _swarm_status(args):
    """Check NATS connection and listener health."""
    import asyncio
    import os
    import nats
    from pathlib import Path

    nats_url = os.environ.get("SWARM_NATS_URL", "nats://localhost:4222")

    # Check NATS connection
    try:
        async def _check():
            nc = await nats.connect(nats_url, connect_timeout=3)
            url = nc.connected_url.netloc
            await nc.drain()
            return url
        connected = asyncio.run(_check())
        print(f"✅ NATS: connected to {connected}")
    except Exception as e:
        print(f"❌ NATS: {e}")

    # Check mailbox
    inbox = Path.home() / ".worker-bee" / "mailbox" / "inbox"
    if inbox.exists():
        unread = len(list(inbox.glob("*.json")))
        print(f"📬 Mailbox: {unread} unread, inbox={inbox}")
    else:
        print("📭 Mailbox: not initialized (no messages yet)")

    # Check if listener process is running
    import subprocess
    result = subprocess.run(
        ["pgrep", "-f", "swarm/listener.py"],
        capture_output=True, text=True,
    )
    if result.stdout.strip():
        print(f"🟢 Listener: running (PID {result.stdout.strip().split()[0]})")
    else:
        print("🔴 Listener: not running (start with: wb swarm listen)")


def _add_swarm_parser(sub):
    swarm = sub.add_parser("swarm", help="NATS swarm communication")
    swarm_sub = swarm.add_subparsers(dest="swarm_cmd", required=True)

    p = swarm_sub.add_parser("listen", help="Start NATS listener (writes messages to mailbox)")
    p.add_argument("url", nargs="?", default=None, help="NATS URL (default: nats://localhost:4222)")
    p.set_defaults(func=_swarm_listen)

    p = swarm_sub.add_parser("status", help="Check NATS connection and listener health")
    p.set_defaults(func=_swarm_status)


# ---------------------------------------------------------------------------
# Workspace sub-command
# ---------------------------------------------------------------------------
def _workspace_show(args):
    from worker_bee.workspace import get_workspace
    print(get_workspace())


def _add_workspace_parser(sub):
    ws = sub.add_parser("workspace", help="Show the current workspace path")
    ws.set_defaults(func=_workspace_show)


# ---------------------------------------------------------------------------
# Lark / Feishu sub-command
# ---------------------------------------------------------------------------
def _lark_who(args):
    """Resolve a contact name to open_id."""
    import subprocess, json
    result = subprocess.run(
        [_LARK_CLI, "contact", "+search-user", "--query", args.name],
        capture_output=True, text=True, timeout=10,
    )
    try:
        data = json.loads(result.stdout)
        users = data.get("items", data.get("data", {}).get("items", []))
    except json.JSONDecodeError:
        print(result.stdout[:500])
        return
    if not users:
        print(f"No results for '{args.name}'")
        return
    for u in users[:5]:
        name = u.get("name", "?")
        uid = u.get("open_id", u.get("user_id", "?"))
        email = u.get("email", "")
        dept = ", ".join(u.get("department_names", []))
        print(f"{name:20s}  {uid}  {email}  {dept}")


def _lark_chats(args):
    """List or search group chats."""
    import subprocess, json
    cmd = [_LARK_CLI, "im", "+chat-list"]
    if args.query:
        cmd = [_LARK_CLI, "im", "+chat-search", "--query", args.query]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    try:
        data = json.loads(result.stdout)
        chats = data.get("items", data.get("data", {}).get("items", []))
    except json.JSONDecodeError:
        print(result.stdout[:500])
        return
    if not chats:
        print(f"No chats found" + (f" for '{args.query}'" if args.query else ""))
        return
    for c in chats[:20]:
        name = c.get("name", "?")
        cid = c.get("chat_id", "?")
        members = c.get("member_count", "?")
        print(f"{name:30s}  {cid}  ({members} members)")


def _lark_send(args):
    """Send a message — resolves name to ID automatically."""
    import json, subprocess

    # Check write permission (same gate as tools/lark.py)
    config_path = Path.home() / ".worker-bee" / "config.json"
    try:
        cfg = json.loads(config_path.read_text())
        if not cfg.get("lark_allow_write", False):
            print("Write operations are disabled. Enable with: wb setup → lark_allow_write: true")
            return
    except (FileNotFoundError, json.JSONDecodeError):
        print("Write operations are disabled (no config or invalid). Run: wb setup")
        return

    if args.group:
        # Resolve group name
        r = subprocess.run(
            [_LARK_CLI, "im", "+chat-search", "--query", args.group],
            capture_output=True, text=True, timeout=10,
        )
        try:
            data = json.loads(r.stdout)
            chats = data.get("items", data.get("data", {}).get("items", []))
        except json.JSONDecodeError:
            print(f"Error searching groups: {r.stdout[:200]}")
            return
        exact = [c for c in chats if c.get("name", "").lower() == args.group.lower()]
        if exact:
            chat = exact[0]
        elif chats:
            print(f"Group '{args.group}' not found exactly. Did you mean:")
            for c in chats[:5]:
                print(f"  - {c.get('name', '?')}")
            return
        else:
            print(f"Group not found: {args.group}")
            return
        cid = chat["chat_id"]
        name = chat.get("name", args.group)
        text = " ".join(args.msg) if isinstance(args.msg, list) else (args.msg or "")
        if not text.strip():
            print("Message is empty. Usage: wb lark send --group <name> <message text>")
            return
        cmd = [_LARK_CLI, "im", "+messages-send", "--chat-id", cid, "--text", text]
    elif args.to:
        # Resolve user name
        r = subprocess.run(
            [_LARK_CLI, "contact", "+search-user", "--query", args.to],
            capture_output=True, text=True, timeout=10,
        )
        try:
            data = json.loads(r.stdout)
            users = data.get("items", data.get("data", {}).get("items", []))
        except json.JSONDecodeError:
            print(f"Error searching users: {r.stdout[:200]}")
            return
        exact = [u for u in users if u.get("name", "").lower() == args.to.lower()]
        if exact:
            user = exact[0]
        elif users:
            print(f"User '{args.to}' not found exactly. Did you mean:")
            for u in users[:5]:
                print(f"  - {u.get('name', '?')}")
            return
        else:
            print(f"User not found: {args.to}")
            return
        uid = user.get("open_id", user.get("user_id"))
        uname = user.get("name", args.to)
        text = " ".join(args.msg) if isinstance(args.msg, list) else (args.msg or "")
        if not text.strip():
            print("Message is empty. Usage: wb lark send --to <name> <message text>")
            return
        cmd = [_LARK_CLI, "im", "+messages-send", "--user-id", uid, "--text", text]
        name = uname
    else:
        print("Specify --to <name> or --group <name>")
        return

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    try:
        data = json.loads(result.stdout)
        if data.get("ok"):
            msg_id = data.get("data", {}).get("message_id", "?")
            print(f"✅ Sent to {name} (msg_id: {msg_id})")
        else:
            err = data.get("error", {}).get("message", result.stdout[:200])
            print(f"❌ {err}")
    except json.JSONDecodeError:
        print(result.stdout[:500])


def _lark_inbox(args):
    """Pull recent messages from a user or group — resolves name to ID."""
    import subprocess, json

    if args.group:
        r = subprocess.run(
            [_LARK_CLI, "im", "+chat-search", "--query", args.group],
            capture_output=True, text=True, timeout=10,
        )
        try:
            data = json.loads(r.stdout)
            chats = data.get("items", data.get("data", {}).get("items", []))
        except json.JSONDecodeError:
            print(f"Error: {r.stdout[:200]}")
            return
        exact = [c for c in chats if c.get("name", "").lower() == args.group.lower()]
        if exact:
            chat = exact[0]
        elif chats:
            print(f"Group '{args.group}' not found exactly. Did you mean:")
            for c in chats[:5]:
                print(f"  - {c.get('name', '?')}")
            return
        else:
            print(f"Group not found: {args.group}")
            return
        cid = chat["chat_id"]
        label = chat.get("name", args.group)
        cmd = [_LARK_CLI, "im", "+chat-messages-list", "--chat-id", cid, "--limit", str(args.limit)]
    elif args.from_user:
        r = subprocess.run(
            [_LARK_CLI, "contact", "+search-user", "--query", args.from_user],
            capture_output=True, text=True, timeout=10,
        )
        try:
            data = json.loads(r.stdout)
            users = data.get("items", data.get("data", {}).get("items", []))
        except json.JSONDecodeError:
            print(f"Error: {r.stdout[:200]}")
            return
        exact = [u for u in users if u.get("name", "").lower() == args.from_user.lower()]
        if exact:
            user = exact[0]
        elif users:
            print(f"User '{args.from_user}' not found exactly. Did you mean:")
            for u in users[:5]:
                print(f"  - {u.get('name', '?')}")
            return
        else:
            print(f"User not found: {args.from_user}")
            return
        uid = user.get("open_id", user.get("user_id"))
        label = user.get("name", args.from_user)
        cmd = [_LARK_CLI, "im", "+chat-messages-list", "--user-id", uid, "--limit", str(args.limit)]
    else:
        print("Specify --from <name> or --group <name>")
        return

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    try:
        data = json.loads(result.stdout)
        msgs = data.get("items", data.get("data", {}).get("items", []))
    except json.JSONDecodeError:
        print(result.stdout[:500])
        return

    print(f"📬 {label} — last {len(msgs)} messages:\n")
    for m in reversed(msgs):
        sender = m.get("sender", {}).get("name", m.get("sender_name", "?"))
        body = m.get("body", {}).get("content", "")
        # Try to get plain text from various message formats
        if not body:
            body = m.get("content", "")
        # Truncate long messages
        if len(body) > 200:
            body = body[:200] + "…"
        ts = m.get("create_time", "")
        print(f"[{ts}] {sender}: {body}")


def _add_lark_parser(sub):
    lark = sub.add_parser("lark", help="Feishu/Lark operations — resolve names to IDs")
    lark_sub = lark.add_subparsers(dest="lark_cmd", required=True)

    p = lark_sub.add_parser("who", help="Find a user by name → open_id")
    p.add_argument("name", help="Name or partial name")
    p.set_defaults(func=_lark_who)

    p = lark_sub.add_parser("chats", help="List/search group chats")
    p.add_argument("query", nargs="?", default="", help="Optional search keyword")
    p.set_defaults(func=_lark_chats)

    p = lark_sub.add_parser("send", help="Send a message (resolves name → ID)")
    p.add_argument("--to", default="", help="User name to DM")
    p.add_argument("--group", default="", help="Group name")
    p.add_argument("msg", nargs="*", default=[], help="Message text")
    p.set_defaults(func=_lark_send)

    p = lark_sub.add_parser("inbox", help="Pull recent messages from a user or group")
    p.add_argument("--from", dest="from_user", default="", help="User name")
    p.add_argument("--group", default="", help="Group name")
    p.add_argument("--limit", type=int, default=20, help="Max messages (default: 20)")
    p.set_defaults(func=_lark_inbox)

    p = lark_sub.add_parser("serve", help="Start Feishu Lark webhook bot server")
    p.add_argument("--port", type=int, default=8080, help="Webhook server port (default: 8080)")
    p.set_defaults(func=_lark_serve)


def _lark_serve(args):
    """Start the Feishu Lark webhook server."""
    from worker_bee.lark_cli import run_server
    run_server(port=args.port)


# ---------------------------------------------------------------------------
# Deck sub-command
# ---------------------------------------------------------------------------
def _add_deck_parser(sub):
    """wb deck — Deck 模式控制。"""
    deck_sub = sub.add_parser("deck", help="Deck mode control")
    deck_cmds = deck_sub.add_subparsers(dest="deck_cmd", required=True)

    # deck mode
    p = deck_cmds.add_parser("mode", help="Set deck mode (auto|full|focus)")
    p.add_argument("value", choices=["auto", "full", "focus"], help="Deck mode")
    p.set_defaults(func=_deck_mode)

    # deck status
    p = deck_cmds.add_parser("status", help="Show current deck mode")
    p.set_defaults(func=_deck_status)

    # deck log
    p = deck_cmds.add_parser("log", help="Show deck usage log")
    p.add_argument("--limit", type=int, default=10, help="Number of entries to show")
    p.set_defaults(func=_deck_log)


def _deck_mode(args):
    """Set deck mode in config."""
    import json
    from pathlib import Path
    
    config_path = Path.home() / ".worker-bee" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
    else:
        config = {}
    
    config["deck_mode"] = args.value
    
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    
    print(f"Deck mode set to: {args.value}")


def _deck_status(args):
    """Show current deck mode."""
    import json
    from pathlib import Path
    
    config_path = Path.home() / ".worker-bee" / "config.json"
    
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
        mode = config.get("deck_mode", "auto")
    else:
        mode = "auto"
    
    print(f"Current deck mode: {mode}")
    print()
    print("Modes:")
    print("  auto  - Full mode when no skills matched, focus mode otherwise (default)")
    print("  full  - Always use all config.tools")
    print("  focus - Always use skill tools + redundancy only")


def _deck_log(args):
    """Show deck usage log."""
    from pathlib import Path
    import json
    
    log_path = Path.home() / ".worker-bee" / "deck_log.jsonl"
    
    if not log_path.exists():
        print("No deck log found.")
        return
    
    with open(log_path) as f:
        lines = f.readlines()
    
    entries = [json.loads(line) for line in lines[-args.limit:]]
    
    print(f"Last {len(entries)} deck operations:")
    print()
    for entry in entries:
        ts = entry.get("timestamp", "?")
        mode = entry.get("mode", "?")
        tools = entry.get("tool_count", "?")
        skills = ", ".join(entry.get("matched_skills", []))
        print(f"{ts} | {mode:8s} | {tools:2d} tools | skills: {skills or '(none)'}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="wb",
        description="WorkerBee CLI — direct access to job and todo systems.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  wb job create 'Refactor auth' 'Split JWT logic into service' --cycles 2\n"
            "  wb job ls\n"
            "  wb job status JOB-001\n"
            "  wb job tick\n"
            "  wb todo dashboard\n"
            "  wb todo draw morning\n"
            "  wb todo quick\n"
            "  wb todo stats 14\n"
            "  wb workspace\n"
            "  wb swarm listen\n"
            "  wb lark serve --port 8080\n"
            "  wb lark who 张三\n"
            "  wb lark chats\n"
            "  wb lark send --to 张三 hello\n"
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    _add_job_parser(sub)
    _add_todo_parser(sub)
    _add_swarm_parser(sub)
    _add_workspace_parser(sub)
    _add_lark_parser(sub)
    _add_deck_parser(sub)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
