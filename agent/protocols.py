"""Protocol abstraction — isolates Anthropic/OpenAI format differences.

Each protocol handles: client init, message conversion, response extraction,
and the actual API call.  The agent loop never branches on provider.
"""
import json
from typing import Any, Dict, List, Optional


# ── protocol-neutral helpers ────────────────────────────────────────────

def _normalize_args(value: Any) -> dict:
    """Convert pydantic/namespace arguments to plain dict."""
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {}


# ── Protocol interface (duck-typed, no ABC overhead) ────────────────────

class Protocol:
    """Protocol implementation for one provider family."""

    @staticmethod
    def create(config: dict) -> "Protocol":
        provider = config.get("provider", "anthropic")
        if provider == "openai":
            return OpenAIProtocol(config)
        return AnthropicProtocol(config)

    # ── subtypes override these ──────────────────────────────────────

    def build_messages(self, internal_msgs: List[Dict]) -> List[Dict]:
        raise NotImplementedError

    def build_response(self, api_msg) -> dict:
        """Return {text, reasoning, tool_calls}."""
        raise NotImplementedError

    def build_assistant_block(self, text: str, reasoning: Optional[str],
                              tool_calls: List[Dict]) -> dict:
        """Build an assistant message for the API message list."""
        raise NotImplementedError

    def build_tool_result_block(self, tool_call_id: str, content: str) -> dict:
        """Build a tool-result message for the API message list."""
        raise NotImplementedError

    def api_call(self, system_prompt: str, api_msgs: List[Dict],
                 tools: Optional[List[Dict]], model: str):
        raise NotImplementedError


# ── Anthropic ───────────────────────────────────────────────────────────

class AnthropicProtocol(Protocol):
    def __init__(self, config: dict):
        from anthropic import Anthropic
        self.client = Anthropic(
            api_key=config["api_key"],
            base_url=config.get("base_url"),
        )

    def build_messages(self, internal_msgs: List[Dict]) -> List[Dict]:
        api_msgs = []
        for m in internal_msgs:
            role = m["role"]
            content = m.get("content", "")
            if role == "tool":
                api_msgs.append({
                    "role": "user",
                    "content": [{"type": "tool_result",
                                 "tool_use_id": m.get("tool_call_id", ""),
                                 "content": content}],
                })
            elif role == "assistant" and m.get("tool_calls"):
                blocks = []
                reasoning = m.get("reasoning")
                if reasoning:
                    blocks.append({"type": "thinking", "thinking": reasoning})
                if content:
                    blocks.append({"type": "text", "text": content})
                for tc in m["tool_calls"]:
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", tc.get("tool_use_id", "")),
                        "name": tc.get("name", tc.get("function", {}).get("name", "")),
                        "input": tc["input"] if tc.get("input") is not None else tc.get("function", {}).get("arguments", {}) or tc.get("arguments", {}),
                    })
                api_msgs.append({"role": "assistant", "content": blocks})
            else:
                api_msgs.append({"role": role, "content": content})
        return api_msgs

    def build_response(self, api_msg) -> dict:
        """Extract text, reasoning, and tool_calls from an Anthropic response."""
        texts = []
        reasoning_parts = []
        tool_calls = []

        for block in api_msg.content:
            btype = getattr(block, "type", None)
            if btype == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": _normalize_args(block.input),
                })
            elif btype == "thinking" and hasattr(block, "thinking"):
                reasoning_parts.append(block.thinking)
            elif hasattr(block, "text"):
                texts.append(block.text)

        return {
            "text": "\n".join(texts),
            "reasoning": "\n".join(reasoning_parts) if reasoning_parts else None,
            "tool_calls": tool_calls,
        }

    def build_assistant_block(self, text: str, reasoning: Optional[str],
                              tool_calls: List[Dict]) -> dict:
        blocks = []
        if reasoning:
            blocks.append({"type": "thinking", "thinking": reasoning})
        if text:
            blocks.append({"type": "text", "text": text})
        for tc in tool_calls:
            blocks.append({
                "type": "tool_use",
                "id": tc["id"],
                "name": tc["name"],
                "input": tc["arguments"],
            })
        return {"role": "assistant", "content": blocks}

    def build_tool_result_block(self, tool_call_id: str, content: str) -> dict:
        return {
            "role": "user",
            "content": [{"type": "tool_result",
                         "tool_use_id": tool_call_id,
                         "content": content}],
        }

    def api_call(self, system_prompt: str, api_msgs: List[Dict],
                 tools: Optional[List[Dict]], model: str, temperature: float = 0.0):
        kwargs = {
            "model": model,
            "max_tokens": 4096,
            "messages": api_msgs,
            "system": system_prompt,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if tools:
            kwargs["tools"] = tools
        return self.client.messages.create(**kwargs)


# ── OpenAI ──────────────────────────────────────────────────────────────

class OpenAIProtocol(Protocol):
    def __init__(self, config: dict):
        from openai import OpenAI
        self.client = OpenAI(
            api_key=config["api_key"],
            base_url=config.get("base_url"),
        )

    @staticmethod
    def _to_openai_tool(tc: dict) -> dict:
        return {
            "id": tc["id"],
            "type": "function",
            "function": {
                "name": tc["name"],
                "arguments": json.dumps(tc["arguments"]),
            },
        }

    def build_messages(self, internal_msgs: List[Dict]) -> List[Dict]:
        api_msgs = []
        for m in internal_msgs:
            role = m["role"]
            content = m.get("content", "")
            if role == "tool":
                api_msgs.append({
                    "role": "tool",
                    "tool_call_id": m.get("tool_call_id", ""),
                    "content": content,
                })
            elif role == "assistant" and m.get("tool_calls"):
                payload = {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [self._to_openai_tool(tc) for tc in m["tool_calls"]],
                }
                reasoning = m.get("reasoning")
                if reasoning:
                    payload["reasoning_content"] = reasoning
                api_msgs.append(payload)
            else:
                api_msgs.append({"role": role, "content": content})
        return api_msgs

    def build_response(self, api_msg) -> dict:
        """Extract text, reasoning, and tool_calls from an OpenAI response."""
        msg = api_msg.choices[0].message
        tool_calls = []
        for tc in (msg.tool_calls or []):
            tool_calls.append({
                "id": tc.id,
                "name": tc.function.name,
                "arguments": json.loads(tc.function.arguments),
            })

        reasoning = getattr(msg, "reasoning_content", None)
        if reasoning is None and hasattr(msg, "model_extra") and msg.model_extra:
            reasoning = msg.model_extra.get("reasoning_content")

        return {
            "text": msg.content or "",
            "reasoning": reasoning,
            "tool_calls": tool_calls,
        }

    def build_assistant_block(self, text: str, reasoning: Optional[str],
                              tool_calls: List[Dict]) -> dict:
        payload = {
            "role": "assistant",
            "content": text,
            "tool_calls": [self._to_openai_tool(tc) for tc in tool_calls],
        }
        if reasoning:
            payload["reasoning_content"] = reasoning
        return payload

    def build_tool_result_block(self, tool_call_id: str, content: str) -> dict:
        return {"role": "tool", "tool_call_id": tool_call_id, "content": content}

    def api_call(self, system_prompt: str, api_msgs: List[Dict],
                 tools: Optional[List[Dict]], model: str, temperature: float = 0.0):
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "system", "content": system_prompt}] + api_msgs,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        return self.client.chat.completions.create(**kwargs)
