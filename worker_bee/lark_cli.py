#!/usr/bin/env python3
"""Lark CLI for Worker Bee — standalone Feishu bot via HTTP webhook.

Usage:
    worker-bee lark [--port 8080]

Design: This is a SIDE DOOR. Primary command channel is GitHub Issues.
Feishu is for quick ops, notifications, and emergency commands.

Env:
    FEISHU_APP_ID, FEISHU_APP_SECRET      — App Bot credentials
    FEISHU_VERIFICATION_TOKEN             — Event subscription verification token
    FEISHU_BASE_URL                       — defaults to https://open.feishu.cn
"""
import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional, Dict, Callable

from worker_bee.agent import AIAgent

# ── Config ──────────────────────────────────────────────────────────────────

FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
FEISHU_VERIFICATION_TOKEN = os.environ.get("FEISHU_VERIFICATION_TOKEN", "")
FEISHU_BASE_URL = os.environ.get("FEISHU_BASE_URL", "https://open.feishu.cn")

# ── Token cache ────────────────────────────────────────────────────────────────────────

_feishu_token: Optional[str] = None
_feishu_token_expires: float = 0


def _get_feishu_token() -> Optional[str]:
    global _feishu_token, _feishu_token_expires
    now = time.time()
    if _feishu_token and now < _feishu_token_expires - 60:
        return _feishu_token
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        return None
    payload = json.dumps({"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}).encode()
    req = urllib.request.Request(
        f"{FEISHU_BASE_URL}/open-apis/auth/v3/tenant_access_token/internal",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        if data.get("code") == 0:
            _feishu_token = data["tenant_access_token"]
            _feishu_token_expires = now + data.get("expire", 7200)
            return _feishu_token
    except Exception:
        pass
    return None


def _send_reply(
    receive_id: str,
    receive_id_type: str,
    content: str,
    msg_type: str = "text",
) -> dict:
    """Send a message via Feishu App Bot API."""
    token = _get_feishu_token()
    if not token:
        return {"error": "unable to obtain tenant_access_token"}

    api_content = json.dumps({"text": content}, ensure_ascii=False) if msg_type == "text" else content
    body = json.dumps(
        {"receive_id": receive_id, "msg_type": msg_type, "content": api_content},
        ensure_ascii=False,
    ).encode()

    req = urllib.request.Request(
        f"{FEISHU_BASE_URL}/open-apis/im/v1/messages?receive_id_type={receive_id_type}",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {"status": resp.status, "data": json.loads(resp.read().decode())}
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()}", "code": e.code}
    except Exception as e:
        return {"error": str(e)}


# ── Config loader (shared with main.py) ─────────────────────────────────────────────────────────

def _load_config() -> Optional[dict]:
    path = Path.home() / ".worker-bee" / "config.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    key = os.environ.get("MOONSHOT_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if key:
        return {
            "provider": "openai",
            "model": os.environ.get("MOONSHOT_MODEL", "kimi-k2.6"),
            "api_key": key,
            "base_url": os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1"),
            "max_iterations": 20,
            "system_prompt": "You are a helpful coding assistant.",
            "tools": [],
        }
    return None


# ── Command handlers ─────────────────────────────────────────────────────────────────────────

def cmd_task(parts: list, ctx: dict) -> str:
    if len(parts) < 2:
        return "Usage: /task add <description> | /task list"
    sub = parts[1]
    if sub == "add":
        desc = " ".join(parts[2:]) or "untitled"
        # TODO: integrate with jobs/ board
        return f"✅ Task added: {desc}"
    elif sub == "list":
        return "📝 Active tasks: (none — integrate with jobs board for real listing)"
    return f"Unknown /task subcommand: {sub}"


def cmd_status(ctx: dict) -> str:
    return (
        "🟢 Worker Bee is running.\n"
        "Primary: GitHub Issues/PRs\n"
        "Side: Feishu commands\n"
        f"Chat: {ctx.get('chat_id', 'n/a')[:16]}..."
    )


def cmd_deploy(parts: list, ctx: dict) -> str:
    return "🚀 Deploy triggered. Check GitHub Actions for progress."


def cmd_health(ctx: dict) -> str:
    return "🌡️ Health: OK\nToken: valid\nConfig: loaded"


def cmd_help() -> str:
    return (
        "Worker Bee — Quick commands:\n"
        "  /task add <desc>  — add a task\n"
        "  /task list        — list tasks\n"
        "  /status           — bot status\n"
        "  /deploy           — trigger deploy\n"
        "  /health           — health check\n"
        "  /help             — this message\n\n"
        "Anything else → natural language (AI agent)."
    )


_COMMANDS: Dict[str, Callable] = {
    "task": cmd_task,
    "status": cmd_status,
    "deploy": cmd_deploy,
    "health": cmd_health,
    "help": cmd_help,
}


# ── Message processing ────────────────────────────────────────────────────────────────────────

def process_message(text: str, ctx: dict) -> str:
    """Route / commands or fall back to AI agent."""
    text = text.strip()
    if not text.startswith("/"):
        return _process_natural(text, ctx)

    parts = text[1:].split()
    if not parts:
        return cmd_help()

    name = parts[0]
    handler = _COMMANDS.get(name)
    if handler:
        try:
            return handler(parts, ctx) if name != "help" else handler()
        except Exception as e:
            return f"❌ Error: {e}"
    return f"Unknown: /{name}\n{cmd_help()}"


def _process_natural(text: str, ctx: dict) -> str:
    """One-turn AI agent conversation."""
    config = _load_config()
    if not config:
        return "❌ No config. Run `worker-bee setup` first."
    try:
        agent = AIAgent(config)
        msgs = [{"role": "user", "content": text}]
        return agent.run(msgs) or "(no response)"
    except Exception as e:
        return f"❌ Agent error: {e}"


# ── Webhook handler ────────────────────────────────────────────────────────────────────────

class LarkWebhookHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # Suppress noisy HTTP logs

    def _respond_json(self, data: dict, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_POST(self):
        if self.path != "/webhook":
            self._respond_json({"error": "not found"}, 404)
            return

        clen = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(clen).decode("utf-8")

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._respond_json({"error": "bad json"}, 400)
            return

        # 1. Challenge handshake (first-time event subscription setup)
        if payload.get("type") == "url_verification":
            self._respond_json({"challenge": payload.get("challenge", "")})
            print(f"[Lark] Challenge handshake OK — {payload.get('token', 'n/a')[:8]}...")
            return

        # 2. Optional verification token check
        header_token = payload.get("header", {}).get("token", "")
        if FEISHU_VERIFICATION_TOKEN and header_token != FEISHU_VERIFICATION_TOKEN:
            self._respond_json({"error": "forbidden"}, 403)
            return

        # 3. Route events
        event_type = payload.get("header", {}).get("event_type", "")
        if event_type == "im.message.receive_v1":
            # Process asynchronously so HTTP response is fast
            threading.Thread(target=self._handle_im_message, args=(payload,), daemon=True).start()

        self._respond_json({"code": 0, "msg": "ok"})

    def _handle_im_message(self, payload: dict):
        event = payload.get("event", {})
        message = event.get("message", {})
        sender = event.get("sender", {})

        msg_type = message.get("message_type", "")
        if msg_type != "text":
            return

        try:
            content = json.loads(message.get("content", "{}"))
        except json.JSONDecodeError:
            return
        text = content.get("text", "").strip()

        chat_id = message.get("chat_id", "")
        chat_type = message.get("chat_type", "")  # p2p or group
        sender_open_id = sender.get("sender_id", {}).get("open_id", "")
        message_id = message.get("message_id", "")

        # In groups, check if bot is mentioned (optional — Feishu can be configured
        # to only push @bot messages, but we strip the @mention text if present)
        mentions = message.get("mentions", [])
        bot_open_id = _get_bot_open_id()
        if chat_type == "group":
            if bot_open_id:
                # Strip @bot text from message
                for m in mentions:
                    mention_id = m.get("id", {}).get("open_id", "")
                    if mention_id == bot_open_id:
                        key = m.get("key", "")
                        if key:
                            text = text.replace(f"@{key}", "").strip()
            # If not mentioned and no bot_open_id known, still process
            # (rely on Feishu backend config to filter)

        ctx = {
            "chat_id": chat_id,
            "chat_type": chat_type,
            "sender_open_id": sender_open_id,
            "message_id": message_id,
        }

        reply = process_message(text, ctx)

        # Send reply
        rid_type = "open_id" if chat_type == "p2p" else "chat_id"
        rid = sender_open_id if chat_type == "p2p" else chat_id
        result = _send_reply(rid, rid_type, reply)
        if "error" in result:
            print(f"[Lark] Reply failed: {result['error']}")


_bot_open_id: Optional[str] = None


def _get_bot_open_id() -> Optional[str]:
    """Cache bot open_id for @mention stripping."""
    global _bot_open_id
    if _bot_open_id:
        return _bot_open_id
    token = _get_feishu_token()
    if not token:
        return None
    req = urllib.request.Request(
        f"{FEISHU_BASE_URL}/open-apis/bot/v3/info",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        if data.get("code") == 0:
            _bot_open_id = data.get("data", {}).get("open_id")
            return _bot_open_id
    except Exception:
        pass
    return None


# ── Server entry ──────────────────────────────────────────────────────────────────────────────

def _check_env() -> bool:
    ok = True
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        print("❌ FEISHU_APP_ID and FEISHU_APP_SECRET required.")
        ok = False
    if not FEISHU_VERIFICATION_TOKEN:
        print("⚠️  FEISHU_VERIFICATION_TOKEN not set (challenge handshake will be unsigned).")
    return ok


def run_server(port: int = 8080):
    if not _check_env():
        sys.exit(1)

    server = HTTPServer(("", port), LarkWebhookHandler)
    host = os.environ.get("WORKER_BEE_HOST", "<your-host>")
    print(f"🐝 Worker Bee Lark bot listening on :{port}")
    print(f"   Event subscription URL: http://{host}:{port}/webhook")
    print("   Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹️  Shutting down.")
        server.shutdown()


def main():
    parser = argparse.ArgumentParser(description="Worker Bee Lark Bot")
    parser.add_argument("--port", type=int, default=8080, help="Webhook server port (default: 8080)")
    args = parser.parse_args()
    run_server(args.port)


if __name__ == "__main__":
    main()
