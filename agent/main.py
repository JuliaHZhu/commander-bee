#!/usr/bin/env python3
"""Worker Bee — Lightweight AI agent with tool access.

Usage:
    worker-bee              Start interactive session
    worker-bee setup        Configure API key and model
    worker-bee -m "hello"   Quick model ping test
    worker-bee -c "hello"   Quick channel ping test (Feishu/Discord)
    worker-bee -v           Show version

Options:
    -m, --model-ping MSG    Quick model ping test
    -c, --channel-ping MSG  Quick channel ping test
    -v, --version           Show version
    -h, --help              Show this help

Config:
    export MOONSHOT_API_KEY=sk-...        # or OPENAI_API_KEY
    export MOONSHOT_PROVIDER=openai       # or anthropic
    export MOONSHOT_MODEL=kimi-k2.6
    export MOONSHOT_BASE_URL=https://api.moonshot.cn/v1
"""
import argparse
import json
import os
import sys
import threading
from pathlib import Path

from agent.agent import AIAgent
from agent.memory import SessionDB
from agent.skills import SkillManager
from agent.registry import registry
from agent.infra_toolsets import InfraToolSet
from agent.deck import build_deck, Deck, DeckManager

VERSION = "0.1.1"

_tick_stop = threading.Event()
_tick_thread = None


def _cron_tick_loop(config: dict, skill_mgr):
    """Background thread: tick every 60 seconds."""
    from cron import scheduler
    while not _tick_stop.is_set():
        try:
            scheduler.tick(config, skill_mgr)
        except Exception as e:
            print(f"  [Cron tick error: {e}]")
        _tick_stop.wait(60)


def _config_dir() -> Path:
    """Return the user config directory (~/.worker-bee)."""
    return Path.home() / ".worker-bee"


def get_config_path():
    _config_dir().mkdir(parents=True, exist_ok=True)
    return str(_config_dir() / "config.json")


def load_config():
    """Load config from file or env. Returns dict or None."""
    path = get_config_path()
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    key = os.environ.get("MOONSHOT_API_KEY") or os.environ.get("OPENAI_API_KEY")
    base = os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1")
    if key:
        return _make_config("openai", "kimi-k2.6", key, base)
    return None


def _make_config(provider, model, api_key, base_url, max_iter=60, temperature=0.0):
    import socket
    default_bee_id = socket.gethostname().lower().replace(".", "-")
    return {
        "model": model,
        "provider": provider,
        "api_key": api_key,
        "base_url": base_url,
        "max_iterations": max_iter,
        "temperature": temperature,
        "auto_confirm": False,
        "bee_id": default_bee_id,
        "system_prompt": (
            "You are a helpful coding assistant. You have access to tools:\n"
            "- sys_terminal: run shell commands\n"
            "- fs_read_file / fs_write_file / fs_search_files: file operations\n"
            "- net_web_search / net_web_extract: web access\n"
            "- agent_delegate_task: delegate a single subtask to a child agent\n"
            "- agent_delegate_parallel: delegate multiple subtasks in parallel\n"
            "- agent_cross_validate: run the same task through multiple models for comparison\n"
            "Think step by step. Prefer reading files before editing.\n\n"
            "## Terminal Efficiency\n"
            "- When the user says 'do it', 'just run it', 'batch mode', or similar intent, "
            "set require_confirmation=false in sys_terminal calls for that turn.\n"
            "- When running a sequence of related commands, prefer require_confirmation=false "
            "after the first command succeeds.\n"
            "- NEVER set require_confirmation=false for: rm -rf, sudo, mkfs, dd, curl | sh, "
            "or any disk/format operation."
        ),
        "tools": [
            "sys_terminal",
            "fs_read_file", "fs_write_file", "fs_search_files",
            "net_web_search", "net_web_extract",
            "agent_delegate_task", "agent_delegate_parallel", "agent_cross_validate"
        ]
    }


def setup():
    """Interactive onboarding — just provider + api_key."""
    print("=" * 45)
    print("  Worker Bee — Setup")
    print("=" * 45)
    print()

    # Provider
    print("Provider:")
    print("  [1] OpenAI-compatible / Moonshot (OpenAI protocol)")
    print("  [2] Anthropic / Volcano (Anthropic protocol)")
    p = input("> ").strip()
    if p == "2":
        provider = "anthropic"
        default_model = "kimi-k2.6"
        default_base = "https://ark.cn-beijing.volces.com/api/coding"
    else:
        provider = "openai"
        default_model = "kimi-k2.6"
        default_base = "https://api.moonshot.cn/v1"

    # API Key
    print()
    key = input("API Key: ").strip()
    if not key:
        print("❌ API key required.")
        sys.exit(1)

    # Optional overrides
    print()
    model = input(f"Model [{default_model}]: ").strip() or default_model
    base = input(f"Base URL [{default_base}]: ").strip() or default_base
    temp_str = input("Temperature [0.0]: ").strip()
    try:
        temperature = float(temp_str) if temp_str else 0.0
    except ValueError:
        temperature = 0.0

    # Bee ID (for swarm identification)
    import socket
    default_bee = socket.gethostname().lower().replace(".", "-")
    print()
    bee_id = input(f"Bee ID (for swarm) [{default_bee}]: ").strip() or default_bee

    # Lark / Feishu write permission
    print()
    lark_write = input("Allow lark-cli write operations? (send messages, upload files, edit docs) [y/N]: ").strip().lower()
    lark_allow_write = lark_write == "y"

    config = _make_config(provider, model, key, base, temperature=temperature)
    config["bee_id"] = bee_id
    config["lark_allow_write"] = lark_allow_write
    path = get_config_path()
    with open(path, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    import stat
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    print()
    print(f"✅ Saved to {path}")
    print(f"   Provider: {provider} | Model: {model} | Temperature: {temperature}")

    # ── Create agent.md + soul.md ──
    prompt_dir = _config_dir()
    prompt_dir.mkdir(parents=True, exist_ok=True)

    agent_md = prompt_dir / "agent.md"
    if not agent_md.exists():
        agent_md.write_text(_AGENT_MD_TEMPLATE, encoding="utf-8")
        print(f"✅ Created {agent_md}")
    else:
        print(f"⏭️  {agent_md} already exists — skipped")

    soul_md = prompt_dir / "soul.md"
    if not soul_md.exists():
        soul_md.write_text(_SOUL_MD_TEMPLATE, encoding="utf-8")
        print(f"✅ Created {soul_md}")
    else:
        print(f"⏭️  {soul_md} already exists — skipped")

    print()
    print("📝  Edit these files to customize the agent's behavior:")
    print(f"    {agent_md}")
    print(f"    {soul_md}")
    print()

    # ── Verify: confirm files are readable ──
    agent_size = len(agent_md.read_text())
    soul_size = len(soul_md.read_text())
    print(f"✅ Verified: {agent_size} chars loaded from agent.md, {soul_size} chars from soul.md")
    print("   Next worker-bee run will inject them into the system prompt.")


_AGENT_MD_TEMPLATE = """\
# Agent Behavior

## Tool Usage
- Read files before editing them.
- Verify before claiming something works.
- Prefer terminal commands over Python scripts for one-liners.

## Task Handling
- Break complex tasks into sequential steps.
- Report progress after each major step.
- If stuck after 3 attempts, ask for clarification.

## Boundaries
- Never modify files outside the project workspace.
- Never run destructive commands (rm -rf, format disk) without confirmation.
"""

_SOUL_MD_TEMPLATE = """\
# Agent Personality

## Tone
- Concise. No fluff.
- Direct. State what you will do, then do it.
- Honest. If you don't know, say so.

## Identity
- You are a Worker Bee — a focused task agent.
- One task at a time. One board at a time.
- You are not a chatbot. You are a tool-using worker.

## Style
- Prefer tables over paragraphs when comparing options.
- Use Chinese when the user writes in Chinese.
- Code blocks over descriptions for configuration.
"""


def ping_model(message: str, temperature: float | None = None):
    """Quick model connectivity test."""
    config = load_config()
    if not config:
        print("❌ No config. Run: worker-bee setup")
        sys.exit(1)
    if temperature is not None:
        config["temperature"] = temperature
    print(f"→ Pinging {config['model']} ({config['provider']}) temp={config.get('temperature', 0.0)}...")
    try:
        agent = AIAgent(config)
        msgs = [{"role": "user", "content": message}]
        resp = agent.run(msgs)
        print("← Response:")
        print(resp)
    except Exception as e:
        print(f"❌ Failed: {e}")
        sys.exit(1)


def config_cmd(args: list[str]):
    """Handle 'config' subcommand.

    Usage:
        worker-bee config              # show current config (api_key masked)
        worker-bee config temperature 0.5
        worker-bee config max_iterations 50
    """
    path = get_config_path()
    config = load_config()
    if not config:
        print("❌ No config found. Run: worker-bee setup")
        sys.exit(1)

    if not args:
        # Show config (mask api_key)
        display = dict(config)
        key = display.get("api_key", "")
        if key:
            display["api_key"] = key[:6] + "..." + key[-4:]
        print(json.dumps(display, indent=2, ensure_ascii=False))
        print(f"\nConfig file: {path}")
        return

    # Set a key
    if len(args) != 2:
        print("Usage: worker-bee config [key value]")
        print("   or: worker-bee config")
        sys.exit(1)

    key, value = args[0], args[1]
    if key not in config:
        print(f"⚠️ Unknown key '{key}'. Available: {', '.join(config.keys())}")
        sys.exit(1)

    # Coerce type based on existing value
    original = config[key]
    if isinstance(original, bool):
        config[key] = value.lower() in ("true", "1", "yes")
    elif isinstance(original, (int, float)):
        try:
            config[key] = type(original)(value)
        except ValueError:
            print(f"❌ Cannot convert '{value}' to {type(original).__name__}")
            sys.exit(1)
    else:
        config[key] = value

    with open(path, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"✅ Updated {key} = {config[key]}")
    print(f"   Config file: {path}")


def ping_channel(message: str):
    """Quick channel connectivity test (Feishu/Discord).

    Tries multiple send paths in order:
      1. Feishu App Bot API (if FEISHU_APP_ID + FEISHU_APP_SECRET present)
      2. Feishu Webhook (if FEISHU_WEBHOOK_URL present)
      3. Discord Webhook (if DISCORD_WEBHOOK_URL present)
    """
    from tools.send_message import send_message

    # 1. Try Feishu App Bot (works even on linux if env vars present)
    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    if app_id and app_secret:
        # Resolve target chat_id / DM
        target = os.environ.get("FEISHU_HOME_CHANNEL", "")
        # If running inside Hermes, also try current DM session
        session_key = os.environ.get("HERMES_SESSION_KEY", "")
        if not target and session_key:
            parts = session_key.split(":")
            if len(parts) >= 2 and parts[-2] in ("dm", "group"):
                target = parts[-1]

        if target:
            print(f"→ Sending via Feishu App Bot API to {target[:20]}...")
            result = send_message(
                message,
                platform="feishu",
                receive_id=target,
                receive_id_type="chat_id",
            )
            print("← Result:", result)
            return
        else:
            print("⚠️  Feishu App Bot credentials found but no target chat_id.")
            print("   Set FEISHU_HOME_CHANNEL or run inside Hermes Feishu context.")
            return

    # 2. Try Webhook modes
    infra = InfraToolSet()
    plat = infra.platform

    if plat == "feishu":
        print("→ Sending via Feishu Webhook...")
        result = send_message(message)
        print("← Result:", result)
        return

    if plat == "discord":
        print("→ Sending via Discord Webhook...")
        result = send_message(message)
        print("← Result:", result)
        return

    # 3. Nothing configured
    print("❌ No messaging platform configured.")
    print("   Options:")
    print("   • App Bot (full):  export FEISHU_APP_ID='xxx' FEISHU_APP_SECRET='yyy'")
    print("   • Webhook (simple): export FEISHU_WEBHOOK_URL='https://open.feishu.cn/...'")
    print("   • Discord:          export DISCORD_WEBHOOK_URL='https://discord.com/...'")


def run_session(temperature_override: float | None = None):
    """Main interactive session."""
    config = load_config()
    if not config:
        print("❌ No config found.")
        print("Run: worker-bee setup")
        sys.exit(1)

    if temperature_override is not None:
        config["temperature"] = temperature_override

    if config.get("auto_confirm"):
        os.environ["WORKER_BEE_AUTO_CONFIRM"] = "true"
    else:
        os.environ.pop("WORKER_BEE_AUTO_CONFIRM", None)

    agent = AIAgent(config)
    db = SessionDB()
    skill_mgr = SkillManager()
    infra = InfraToolSet()
    deck_mgr = DeckManager(config.get("tools", []), registry)

    base_system_prompt = agent.system_prompt

    loaded_skills = skill_mgr.load_all()
    if loaded_skills:
        print(f"Loaded {len(loaded_skills)} skill(s): {', '.join(loaded_skills)}")

    plat = infra.platform
    print(f"Platform: {plat}")
    if plat != "linux":
        available = infra.get_available_tools()
        print(f"Infra tools: {', '.join(available) if available else 'none'}")
    print()
    print(f"Deck mode: {deck_mgr.mode}  (use /deck to manage)")
    print()

    # Start cron scheduler in background
    global _tick_thread
    if _tick_thread is not None and _tick_thread.is_alive():
        _tick_stop.set()
        _tick_thread.join(timeout=2)
    _tick_stop.clear()
    _tick_thread = threading.Thread(
        target=_cron_tick_loop,
        args=(config, skill_mgr),
        daemon=True,
        name="cron-tick"
    )
    _tick_thread.start()
    print("[Cron scheduler] started — tick every 60s")
    print()

    sessions = db.list_sessions()
    if sessions:
        print(f"Found {len(sessions)} session(s). Type 'new' for new session, or number to resume.")
        for i, (sid, created, title) in enumerate(sessions[:5]):
            print(f"  {i}: [{sid}] {title or '(no title)'} — {created[:19]}")
        choice = input("> ").strip()
        if choice.lower() == "new":
            session_id = db.create_session()
            messages = []
        else:
            try:
                session_id = sessions[int(choice)][0]
                messages = db.get_messages(session_id)
            except (ValueError, IndexError):
                session_id = db.create_session()
                messages = []
    else:
        session_id = db.create_session()
        messages = []

    # ── auto handoff injection ────────────────────────────────────────────────
    handoff = db.get_handoff()
    if handoff:
        messages.insert(0, {"role": "user", "content": f"[Handoff] {handoff}"})
        print(f"[Handoff loaded] {handoff[:80]}...")

    # Session-aware system prompt so the agent knows its session ID
    agent.system_prompt = f"{base_system_prompt}\n\nCurrent session ID: {session_id}"

    print(f"\n✨ Worker Bee — Session: {session_id}")
    print("Commands: /exit, /history, /tools, /clear, /todo, /skills, /cats, /infra, /export")
    print("-" * 50)

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("/exit", "exit", "quit"):
            break
        if user_input.lower() == "/history":
            for m in messages[-10:]:
                role = m["role"]
                content = m.get("content", "")[:80].replace("\n", " ")
                tags = m.get("tags", [])
                tag_str = f"  tags:{','.join(tags)}" if tags else ""
                print(f"  [{role:10}] {content}...{tag_str}")
            continue
        if user_input.lower() == "/tools":
            cats = registry.list_by_category()
            for cat, names in sorted(cats.items()):
                print(f"  [{cat}] {', '.join(names)}")
            continue
        if user_input.lower() == "/cats":
            for cat, names in sorted(registry.list_by_category().items()):
                print(f"  {cat}: {len(names)} tool(s)")
            continue
        if user_input.lower() == "/infra":
            print(infra.describe())
            continue
        if user_input.lower() == "/clear":
            messages = []
            print("Context cleared.")
            continue
        if user_input.lower().startswith("/todo"):
            _handle_todo(user_input, db, session_id)
            continue
        if user_input.lower().startswith("/task"):
            print("⚠️  /task is deprecated. Use natural language or /todo instead.")
            continue
        if user_input.lower() == "/skills":
            skills = skill_mgr.list_skills()
            if skills:
                for name, meta in skills.items():
                    triggers = meta.get("triggers", [])
                    tools = meta.get("tools", [])
                    trig_str = f"  triggers: {', '.join(triggers)}" if triggers else ""
                    tool_str = f"  tools: {', '.join(tools)}" if tools else ""
                    print(f"  • {name}: {meta.get('description', 'No description')}{trig_str}{tool_str}")
            else:
                print("No skills loaded.")
            continue
        if user_input.lower() == "/export":
            path = db.export_handoff(session_id)
            print(f"Handoff exported to: {path}")
            print("  Start a new session with: worker-bee --continue <path>")
            continue
        if user_input.lower().startswith("/deck"):
            _handle_deck(user_input, deck_mgr)
            continue

        # --- Deck procurement: gather tools BEFORE execution ---
        print("  [Procuring deck...]", flush=True)

        # 1. Match skills by triggers
        matched_skills = skill_mgr.match_skills(user_input)
        if not matched_skills:
            matched_skills = []

        # 2. Collect tools from matched skills
        skill_tools = skill_mgr.get_tools_for_skills(matched_skills)

        # 3. Build deck via DeckManager (dual-mode: full / focus)
        deck = deck_mgr.procure(skill_tools, infra.filter_tools)

        print(f"  [Deck ready: {deck.size()} tools]  (mode: {deck_mgr.mode})")

        # --- Dynamic context injection for skill-authoring skills ---
        skill_context = skill_mgr.build_context_for_skills(matched_skills)
        if skill_context:
            # Check if any matched skill is an authoring skill
            has_authoring = any(
                (skill_mgr.get_skill(sn) or {}).get("category") == "skill-authoring"
                for sn in matched_skills
            )
            if has_authoring:
                # Inject project metadata: existing skills and tools
                lines = ["\n## Active Project Context (auto-injected)"]
                lines.append("### Existing Skills")
                for name, meta in skill_mgr.list_skills().items():
                    triggers = meta.get("triggers", [])
                    trig_str = f"  [{', '.join(triggers)}]" if triggers else ""
                    lines.append(f"- {name}{trig_str}")
                lines.append("\n### Existing Tools")
                for name in sorted(registry.list_tools()):
                    info = registry.get_tool_info(name)
                    desc = info.get("description", "")[:50] if info else ""
                    lines.append(f"- {name}: {desc}")
                skill_context += "\n".join(lines)
            # Temporarily augment system prompt with skill context
            agent.system_prompt = f"{agent.system_prompt}\n\n{skill_context}"

        # --- Tag extraction: leading #tags are stripped and stored separately ---
        tags, clean_input = _extract_tags(user_input)

        messages.append({"role": "user", "content": clean_input, "tags": tags})
        db.save_message(session_id, "user", clean_input, tags=tags)

        print("\nAgent: ", end="", flush=True)
        try:
            response = agent.run(messages, deck=deck)
        except Exception as e:
            response = f"Error: {e}"
        finally:
            # Restore original system prompt (keeping session ID suffix)
            if skill_context:
                agent.system_prompt = f"{base_system_prompt}\n\nCurrent session ID: {session_id}"

        # Halt if the agent hit the iteration limit — the deck was insufficient
        if response == "(reached max iterations)":
            print(response)
            print("\n⚠️  The task could not be completed with the current tool deck.")
            print("   This usually means the approach needs to change, or a tool is missing.")
            print("   Please rephrase your request or check /tools and /skills.")
            messages.append({"role": "assistant", "content": response})
            db.save_message(session_id, "assistant", response)
            continue

        print(response)

        messages.append({"role": "assistant", "content": response})
        db.save_message(session_id, "assistant", response)

    # Stop cron scheduler
    _tick_stop.set()
    if _tick_thread:
        _tick_thread.join(timeout=5)
        from cron import scheduler
        scheduler.shutdown()
        print("[Cron scheduler] stopped")

    # Export handoff on exit
    try:
        handoff_path = db.export_handoff(session_id)
        print(f"[Handoff] exported to {handoff_path}")
    except Exception as e:
        print(f"[Handoff] export failed: {e}")

    # Auto-save crude handoff for next session
    try:
        h = _make_handoff(messages)
        if h:
            db.save_handoff(session_id, h)
            print("[Handoff] saved for next session")
    except Exception as e:
        print(f"[Handoff] save failed: {e}", file=sys.stderr)

    print(f"\nSession {session_id} saved.")


def _handle_todo(cmd: str, db: SessionDB, session_id: str):
    parts = cmd.split(None, 2)
    if len(parts) == 1:
        todos = db.list_todos(session_id)
        if not todos:
            print("No todos.")
            return
        for tid, content, status, created in todos:
            mark = "✓" if status == "done" else "○"
            print(f"  {mark} [{tid}] {content}")
    elif parts[1] == "add" and len(parts) == 3:
        tid = db.add_todo(session_id, parts[2])
        print(f"Added todo [{tid}].")
    elif parts[1] == "done" and len(parts) == 3:
        try:
            db.update_todo_status(int(parts[2]), "done")
            print(f"Marked todo {parts[2]} as done.")
        except ValueError:
            print("Usage: /todo done <id>")
    elif parts[1] == "pending" and len(parts) == 3:
        try:
            db.update_todo_status(int(parts[2]), "pending")
            print(f"Marked todo {parts[2]} as pending.")
        except ValueError:
            print("Usage: /todo pending <id>")
    elif parts[1] == "delete" and len(parts) == 3:
        try:
            db.delete_todo(int(parts[2]))
            print(f"Deleted todo {parts[2]}.")
        except ValueError:
            print("Usage: /todo delete <id>")
    else:
        print("Usage: /todo, /todo add <text>, /todo done <id>, /todo pending <id>, /todo delete <id>")


def _extract_tags(text: str):
    """Extract leading #tags from user input.

    Example:
        "#design #question how does this work?" -> (["#design", "#question"], "how does this work?")
        "no tags here" -> ([], "no tags here")
    """
    words = text.split()
    tags = []
    idx = 0
    for i, w in enumerate(words):
        if w.startswith("#") and len(w) > 1:
            tags.append(w)
            idx = i + 1
        else:
            break
    clean = " ".join(words[idx:]) if idx > 0 else text
    return tags, clean


def _make_handoff(messages) -> str:
    """Crude handoff: last user + last assistant text."""
    if not messages:
        return ""
    last_user = ""
    last_assistant = ""
    for m in reversed(messages):
        if m["role"] == "user" and not last_user:
            last_user = str(m.get("content", ""))[:200]
        if m["role"] == "assistant" and not last_assistant:
            last_assistant = str(m.get("content", ""))[:200]
        if last_user and last_assistant:
            break
    parts = []
    if last_user:
        parts.append(f"User: {last_user}")
    if last_assistant:
        parts.append(f"Agent: {last_assistant}")
    return " | ".join(parts) if parts else ""


def _handle_deck(cmd: str, deck_mgr: DeckManager):
    """Handle /deck subcommands in interactive session."""
    parts = cmd.split()
    if len(parts) == 1:
        # /deck alone — show status
        tools = deck_mgr.list_tools()
        print(f"Mode: {deck_mgr.mode}")
        print(f"Tools ({len(tools)}): {', '.join(tools) if tools else '(none)'}")
        return
    sub = parts[1].lower()
    if sub == "mode":
        print(f"Current mode: {deck_mgr.mode}")
    elif sub == "full":
        print(deck_mgr.set_mode("full"))
    elif sub == "focus":
        print(deck_mgr.set_mode("focus"))
    elif sub == "add" and len(parts) == 3:
        print(deck_mgr.add_tool(parts[2]))
    elif sub == "drop" and len(parts) == 3:
        print(deck_mgr.drop_tool(parts[2]))
    elif sub == "reset":
        print(deck_mgr.reset())
    elif sub == "list":
        tools = deck_mgr.list_tools()
        print(f"Tools ({len(tools)}): {', '.join(tools) if tools else '(none)'}")
    elif sub == "log":
        log = deck_mgr.get_log()
        print(json.dumps(log, ensure_ascii=False, indent=2))
    else:
        print("Usage: /deck [mode|full|focus|add <tool>|drop <tool>|reset|list|log]")


def main():
    parser = argparse.ArgumentParser(
        prog="worker-bee",
        description="Lightweight AI agent with tool access.",
        add_help=False,
    )
    parser.add_argument("command", nargs="?", choices=["setup", "config", "retry-rate-limited"], help="Command")
    parser.add_argument("config_args", nargs="*", help="Extra args for config command")
    parser.add_argument("-m", "--model-ping", metavar="MSG", help="Quick model ping test")
    parser.add_argument("-c", "--channel-ping", metavar="MSG", help="Quick channel ping test (Feishu/Discord)")
    parser.add_argument("-t", "--temperature", type=float, default=None, help="Override temperature (0.0–1.0)")
    parser.add_argument("-v", "--version", action="store_true", help="Show version")
    parser.add_argument("-h", "--help", action="store_true", help="Show help")
    args = parser.parse_args()

    if args.version:
        print(f"worker-bee {VERSION}")
        return

    if args.help:
        print("""Worker Bee — Lightweight AI Agent

Usage:
  worker-bee                    Start interactive session
  worker-bee setup              Configure API key and model
  worker-bee config             Show current config
  worker-bee config key value   Update a config value
  worker-bee retry-rate-limited Immediately retry all rate-limited jobs
  worker-bee -m "hello"         Quick model connectivity test
  worker-bee -c "hello"         Quick channel connectivity test
  worker-bee -t 0.5             Start session with temperature override
  worker-bee -v                 Show version

Config:
  export MOONSHOT_API_KEY=sk-...        # or OPENAI_API_KEY
  export MOONSHOT_PROVIDER=openai       # or anthropic
  export MOONSHOT_MODEL=kimi-k2.6
  export MOONSHOT_BASE_URL=https://api.moonshot.cn/v1

Interactive commands:
  /exit     Exit session
  /tools    List available tools
  /skills   List loaded skills
  /clear    Clear conversation
  /todo     Manage todos
  /history  Show recent messages
  /export   Export session summary to markdown
""")
        return

    if args.model_ping:
        ping_model(args.model_ping, temperature=args.temperature)
        return

    if args.channel_ping:
        ping_channel(args.channel_ping)
        return

    if args.command == "setup":
        setup()
        return

    if args.command == "config":
        config_cmd(args.config_args)
        return

    if args.command == "retry-rate-limited":
        from cron.jobs import retry_rate_limited_jobs, get_rate_limited_jobs
        pending = get_rate_limited_jobs()
        if not pending:
            print("API 正常，无待恢复任务。")
            return
        retried = retry_rate_limited_jobs()
        print(f"已恢复 {len(retried)} 个因限流暂停的任务，下个 tick 执行。")
        return

    # Default: run interactive session
    run_session(temperature_override=args.temperature)


if __name__ == "__main__":
    main()
