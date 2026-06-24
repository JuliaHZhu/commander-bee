"""
swarm tools — NATS 蜂群通信的 Agent 工具。

两个工具：
  1. swarm_publish  — 广播消息（fire-and-forget）
  2. swarm_request  — 请求-回复（等结果，带超时）

依赖：nats-py（需安装到 worker-bee venv）
环境变量：SWARM_NATS_URL（默认 nats://localhost:4222）

Agent 不直接 subscribe——收消息由 swarm/listener.py 后台进程负责，
写入 mailbox/inbox/，Agent 用 fs_read_file 读取。
"""
import asyncio
import json
import os
import uuid

from agent.registry import registry


# ── 配置 ──────────────────────────────────────────────
NATS_URL = os.environ.get("SWARM_NATS_URL", "nats://localhost:4222")

# 读取 config.json 获取 bee_id（setup 时已写入）
_BEE_ID = None

def _get_bee_id() -> str:
    global _BEE_ID
    if _BEE_ID is not None:
        return _BEE_ID
    try:
        cfg = json.loads((Path.home() / ".worker-bee" / "config.json").read_text(encoding="utf-8"))
        _BEE_ID = cfg.get("bee_id", "unknown-bee")
    except Exception:
        _BEE_ID = "unknown-bee"
    return _BEE_ID

# 每个 sender 的递增 sequence（重启后重置，timestamp + UUID 保证唯一性）
_sender_sequence = 0

def _next_sequence() -> int:
    global _sender_sequence
    _sender_sequence += 1
    return _sender_sequence

from pathlib import Path


# ── 内部：连接 + 发送 + 断开 ──────────────────────────

def _run_async(coro):
    """运行协程并返回结果。

    Worker-bee 的 Agent 循环是同步的，tool handler 也是同步函数。
    正常情况下 asyncio.run() 即可。
    如果在已有事件循环中调用（如 pytest-asyncio），直接报错——同步
    tool 不应该在异步上下文中被调用。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        raise RuntimeError(
            "swarm tool 不能在已有 asyncio 事件循环中调用。"
            "Worker-bee 的 Agent 循环是同步的——tool handler 只在同步上下文中执行。"
        )


async def _publish(subject: str, payload: dict):
    import nats
    nc = await nats.connect(NATS_URL)
    try:
        js = nc.jetstream()
        envelope = {
            "message_id": str(uuid.uuid4()),
            "subject": subject,
            "data": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sender": _get_bee_id(),
            "sequence": _next_sequence(),
        }
        await js.publish(subject, json.dumps(envelope, ensure_ascii=False).encode())
    finally:
        await nc.drain()


async def _request(subject: str, payload: dict, timeout: int, retries: int = 3):
    import nats
    envelope = {
        "message_id": str(uuid.uuid4()),
        "subject": subject,
        "data": payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sender": _get_bee_id(),
        "sequence": _next_sequence(),
    }
    last_error = None
    for attempt in range(1, retries + 1):
        nc = await nats.connect(NATS_URL)
        try:
            resp = await nc.request(
                subject,
                json.dumps(envelope, ensure_ascii=False).encode(),
                timeout=timeout,
            )
            return resp.data.decode()
        except asyncio.TimeoutError:
            last_error = f"Timeout (attempt {attempt}/{retries})"
            if attempt < retries:
                await asyncio.sleep(1)
        except Exception as e:
            last_error = f"{type(e).__name__}: {e} (attempt {attempt}/{retries})"
            if attempt < retries:
                await asyncio.sleep(1)
        finally:
            await nc.drain()
    raise Exception(f"swarm_request failed after {retries} retries. Last error: {last_error}")


# ── 工具 1：发布（广播）───────────────────────────────

def swarm_publish(subject: str, payload: dict) -> str:
    """向蜂群广播消息。fire-and-forget，不保证送达。
    
    参数:
        subject: NATS subject，格式 swarm.{类别}.{动作}
                 示例: swarm.task.deck-build, swarm.event.done
        payload: JSON 可序列化的字典
                 示例: {"paper_id": "p001", "action": "build_deck"}
    
    返回: 成功时返回确认字符串，失败时返回错误信息。
    
    约束:
        - 不发给自己。同机的 swarm_listener 会收到并写 mailbox
        - subject 只用 a-z 0-9 . -
        - 发送后消息副本建议写 mailbox/sent/（用 fs_write_file）
    """
    try:
        _run_async(_publish(subject, payload))
        return json.dumps({"ok": True, "subject": subject, "payload": payload}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


# ── 工具 2：请求（问答）───────────────────────────────

def swarm_request(subject: str, payload: dict, timeout: int = 60) -> str:
    """向蜂群发出请求并等待单个回复。用于查询场景。60秒超时，失败自动重试3次。
    
    参数:
        subject: NATS subject，格式 swarm.query.{服务名}
                 示例: swarm.query.vector-search, swarm.query.status
        payload: JSON 可序列化的请求体
                 示例: {"query": "agent architecture", "top_k": 5}
        timeout: 超时秒数（默认 60）。超时返回错误。
    
    返回: 回复的 JSON 字符串，或超时/错误信息。
    
    约束:
        - 必须有某个 bee 订阅了对应 subject，否则 NoRespondersError
        - payload 大小默认限制 1MB（NATS 配置限制）
        - 不要用这个发不需要回复的消息（浪费超时等待）
    """
    try:
        result = _run_async(_request(subject, payload, timeout))
        return result
    except asyncio.TimeoutError:
        return json.dumps({"ok": False, "error": f"请求超时 ({timeout}s): {subject}"}, ensure_ascii=False)
    except Exception as e:
        error_name = type(e).__name__
        return json.dumps({"ok": False, "error": f"{error_name}: {e}"}, ensure_ascii=False)


# ── 注册到 Registry ──────────────────────────────────

registry.register(
    name="swarm_publish",
    description=(
        "Publish a message to the swarm via NATS. Fire-and-forget — no reply expected. "
        "Subject format: swarm.{category}.{action}. "
        "Payload must be JSON-serializable. "
        "Use for: broadcasting events, dispatching tasks, sending heartbeats."
    ),
    parameters={
        "properties": {
            "subject": {
                "type": "string",
                "description": "NATS subject, e.g. swarm.task.deck-build, swarm.event.done"
            },
            "payload": {
                "type": "object",
                "description": "JSON-serializable payload dict"
            },
        },
        "required": ["subject", "payload"]
    },
    handler=swarm_publish,
    tags=["swarm", "nats", "publish"],
    category="swarm"
)

registry.register(
    name="swarm_request",
    description=(
        "Send a request to the swarm via NATS and wait for a reply. "
        "Use for queries: vector search, status check, data fetch. "
        "Subject format: swarm.query.{service}. "
        "Timeout in seconds (default 10). "
        "Raises NoRespondersError if no subscriber is listening."
    ),
    parameters={
        "properties": {
            "subject": {
                "type": "string",
                "description": "NATS subject, e.g. swarm.query.vector-search, swarm.query.status"
            },
            "payload": {
                "type": "object",
                "description": "JSON-serializable request payload"
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 10)",
                "default": 10
            },
        },
        "required": ["subject", "payload"]
    },
    handler=swarm_request,
    tags=["swarm", "nats", "request"],
    category="swarm"
)
