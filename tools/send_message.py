"""Send message — Feishu (App Bot API + Webhook fallback) and Discord webhook.

Design note: This is a **notification outlet** only. Worker Bee receives commands
exclusively via GitHub (Issues/PRs); send_message is used to notify completion,
failures, or WorldBee pheromones. It does NOT accept commands from messaging
platforms.

Feishu modes (priority order):
  1. App Bot API → requires FEISHU_APP_ID + FEISHU_APP_SECRET
     Supports chat_id / open_id / user_id / thread_id via receive_id.
  2. Webhook fallback → requires FEISHU_WEBHOOK_URL (text only, group only)
  3. Discord webhook → requires DISCORD_WEBHOOK_URL

Environment:
  FEISHU_APP_ID, FEISHU_APP_SECRET  — App Bot credentials
  FEISHU_WEBHOOK_URL                — Custom bot webhook (fallback)
  FEISHU_HOME_CHANNEL               — Default chat_id when receive_id omitted
  DISCORD_WEBHOOK_URL               — Discord webhook URL
"""
import json
import os
import time
import urllib.request
from typing import Optional

from worker_bee.registry import registry

# ── Feishu App Bot state (minimal in-memory cache) ─────────────────────────────
_FEISHU_TOKEN_CACHE: Optional[dict] = None


# ── Feishu App Bot helpers ────────────────────────────────────────────────────────

def _feishu_app_credentials() -> Optional[tuple]:
    """Return (app_id, app_secret) if available, else None."""
    app_id = os.environ.get("FEISHU_APP_ID") or os.environ.get("FEISHU_APPID")
    secret = os.environ.get("FEISHU_APP_SECRET") or os.environ.get("FEISHU_APP_SECRET_KEY")
    if app_id and secret:
        return (app_id, secret)
    return None


def _feishu_base_url() -> str:
    return os.environ.get("FEISHU_BASE_URL", "https://open.feishu.cn")


def _get_feishu_token() -> Optional[str]:
    """Fetch tenant_access_token, with simple memory caching."""
    global _FEISHU_TOKEN_CACHE

    # Check cache
    if _FEISHU_TOKEN_CACHE:
        if time.time() < _FEISHU_TOKEN_CACHE["expires_at"] - 60:
            return _FEISHU_TOKEN_CACHE["token"]

    creds = _feishu_app_credentials()
    if not creds:
        return None

    app_id, app_secret = creds
    base = _feishu_base_url()
    payload = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/open-apis/auth/v3/tenant_access_token/internal",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

    if data.get("code") != 0:
        return None

    token = data.get("tenant_access_token")
    expire = data.get("expire", 7200)
    if token:
        _FEISHU_TOKEN_CACHE = {
            "token": token,
            "expires_at": time.time() + expire,
        }
    return token


def _send_feishu_app(
    content: str,
    receive_id: str,
    receive_id_type: str,
    msg_type: str = "text",
) -> str:
    """Send via Feishu App Bot API (im/v1/messages)."""
    token = _get_feishu_token()
    if not token:
        return json.dumps({"error": "unable to obtain tenant_access_token"}, ensure_ascii=False)

    base = _feishu_base_url()
    # text content must be JSON string: {"text": "hello"}
    if msg_type == "text":
        api_content = json.dumps({"text": content}, ensure_ascii=False)
    elif msg_type == "post":
        api_content = content  # caller already formatted
    else:
        api_content = content

    body = json.dumps(
        {
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": api_content,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{base}/open-apis/im/v1/messages?receive_id_type={receive_id_type}",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return json.dumps(
                {"status": resp.status, "data": data},
                ensure_ascii=False,
            )
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ── Feishu Webhook (legacy fallback) ───────────────────────────────────────────────────

def _send_feishu_webhook(content: str) -> str:
    """Send text message via Feishu custom bot webhook."""
    url = os.environ.get("FEISHU_WEBHOOK_URL", "")
    if not url:
        return json.dumps({"error": "FEISHU_WEBHOOK_URL not set"}, ensure_ascii=False)
    payload = {
        "msg_type": "text",
        "content": {"text": content},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            return json.dumps({"status": resp.status, "body": body}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ── Discord Webhook ─────────────────────────────────────────────────────────────

def _send_discord(content: str) -> str:
    """Send text message via Discord webhook."""
    url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not url:
        return json.dumps({"error": "DISCORD_WEBHOOK_URL not set"}, ensure_ascii=False)
    payload = {"content": content}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8") or "(empty)"
            return json.dumps({"status": resp.status, "body": body}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ── Public API ─────────────────────────────────────────────────────────────────────────

def send_message(
    content: str,
    platform: Optional[str] = None,
    receive_id: Optional[str] = None,
    receive_id_type: Optional[str] = None,
) -> str:
    """Send a message to the configured messaging platform.

    Platform selection priority:
      1. Explicit ``platform`` arg ("feishu" or "discord")
      2. Auto-detect from env vars (App Bot → Webhook → Discord)

    Feishu App Bot (recommended):
      - Requires FEISHU_APP_ID + FEISHU_APP_SECRET
      - Supports chat_id, open_id, user_id, thread_id via ``receive_id_type``
      - When ``receive_id`` is omitted, falls back to FEISHU_HOME_CHANNEL

    Feishu Webhook (fallback):
      - Requires FEISHU_WEBHOOK_URL
      - Text only, group only

    Discord:
      - Requires DISCORD_WEBHOOK_URL

    Args:
        content: Message text.
        platform: "feishu" | "discord" | None (auto-detect).
        receive_id: Target chat/user/thread ID. Defaults to FEISHU_HOME_CHANNEL for Feishu.
        receive_id_type: "chat_id" | "open_id" | "user_id" | "thread_id". Defaults to "chat_id".
    """
    # -- resolve platform --
    if platform is None:
        if _feishu_app_credentials() or os.environ.get("FEISHU_WEBHOOK_URL"):
            platform = "feishu"
        elif os.environ.get("DISCORD_WEBHOOK_URL"):
            platform = "discord"
        else:
            return json.dumps(
                {"error": "No messaging platform configured. "
                          "Set FEISHU_APP_ID+FEISHU_APP_SECRET (App Bot), "
                          "or FEISHU_WEBHOOK_URL (webhook), "
                          "or DISCORD_WEBHOOK_URL."},
                ensure_ascii=False,
            )

    # -- Discord branch --
    if platform == "discord":
        return _send_discord(content)

    # -- Feishu branch --
    if platform == "feishu":
        # Prefer App Bot if credentials exist
        if _feishu_app_credentials():
            rid = receive_id or os.environ.get("FEISHU_HOME_CHANNEL", "")
            if not rid:
                return json.dumps(
                    {"error": "No receive_id provided and FEISHU_HOME_CHANNEL not set. "
                              "Pass receive_id or set FEISHU_HOME_CHANNEL env var."},
                    ensure_ascii=False,
                )
            rid_type = receive_id_type or "chat_id"
            return _send_feishu_app(content, rid, rid_type)

        # Fallback to webhook
        if os.environ.get("FEISHU_WEBHOOK_URL"):
            return _send_feishu_webhook(content)

        return json.dumps(
            {"error": "Feishu platform selected but no credentials or webhook configured."},
            ensure_ascii=False,
        )

    return json.dumps({"error": f"Unsupported platform: {platform}"}, ensure_ascii=False)


# ── Registry ──────────────────────────────────────────────────────────────────────────

registry.register(
    name="send_message",
    description="Send a text message to the configured messaging platform.",
    parameters={
        "properties": {
            "content": {
                "type": "string",
                "description": "The message text to send. Keep it concise.",
            },
            "platform": {
                "type": "string",
                "description": (
                    "Optional override: 'feishu' or 'discord'. "
                    "If omitted, auto-detects from env vars. "
                    "Feishu: FEISHU_APP_ID+FEISHU_APP_SECRET (App Bot) or FEISHU_WEBHOOK_URL. "
                    "Discord: DISCORD_WEBHOOK_URL."
                ),
                "enum": ["feishu", "discord"],
            },
            "receive_id": {
                "type": "string",
                "description": "Target chat/user/thread ID. Defaults to FEISHU_HOME_CHANNEL env var for Feishu.",
            },
            "receive_id_type": {
                "type": "string",
                "description": "Feishu ID type: 'chat_id' (default), 'open_id', 'user_id', 'thread_id'.",
                "enum": ["chat_id", "open_id", "user_id", "thread_id"],
            },
        },
        "required": ["content"],
    },
    handler=send_message,
    tags=["messaging", "infra"],
    category="infra",
)
