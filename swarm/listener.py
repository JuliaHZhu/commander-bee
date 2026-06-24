"""
swarm listener — NATS 订阅进程，将蜂群消息写入 mailbox。

职责单一：sub → 写文件。不做业务逻辑，不做路由决策。

启动方式：
    python swarm/listener.py [nats_url]
    # 默认 nats://localhost:4222

进程模型：
    - 独立 asyncio 进程，不在 Agent 循环内
    - 崩了不影响 Agent（只是收不到消息）
    - 配合 systemd 或 wb swarm listen 管理
"""
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import nats


# ── 配置 ──────────────────────────────────────────────
DEFAULT_NATS_URL = os.environ.get("SWARM_NATS_URL", "nats://localhost:4222")
MAILBOX_INBOX = Path.home() / ".worker-bee" / "mailbox" / "inbox"
NATS_TIMEOUT = float(os.environ.get("SWARM_NATS_TIMEOUT", "5"))


# ── 消息写入 ──────────────────────────────────────────

def _write_envelope(subject: str, reply_to: str, data: bytes):
    """将一条 NATS 消息写成 mailbox JSON 文件。"""
    MAILBOX_INBOX.mkdir(parents=True, exist_ok=True)

    try:
        payload = json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = {"raw": data.decode("utf-8", errors="replace")}

    envelope = {
        "subject": subject,
        "reply_to": reply_to or "",
        "data": payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sender": "swarm",
    }

    safe_subject = subject.replace(".", "-").replace("*", "star").replace(">", "gt")
    filename = f"{safe_subject}_{uuid.uuid4().hex[:8]}.json"
    filepath = MAILBOX_INBOX / filename

    filepath.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 主循环 ────────────────────────────────────────────

async def listen(nats_url: str = DEFAULT_NATS_URL, subject: str = "swarm.>"):
    """连接 NATS，订阅 subject，写入 mailbox。永不退出。"""
    print(f"[swarm-listener] 连接 {nats_url} ...")
    nc = await nats.connect(nats_url, connect_timeout=NATS_TIMEOUT)

    async def handler(msg):
        _write_envelope(msg.subject, msg.reply or "", msg.data)

    await nc.subscribe(subject, cb=handler)
    print(f"[swarm-listener] 就绪 — 监听 {subject} → {MAILBOX_INBOX}")

    # 一直跑，直到被信号中断
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\n[swarm-listener] 收到中断信号，正在 drain ...")
    finally:
        await nc.drain()
        print("[swarm-listener] 已断开")


# ── 入口 ──────────────────────────────────────────────

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_NATS_URL
    asyncio.run(listen(nats_url=url))
