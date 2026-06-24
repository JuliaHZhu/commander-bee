"""Protocol-agnostic agent conversation loop.

This module runs the core agent loop — it never branches on provider.
All protocol details (message format, API call shape, response extraction)
are handled by the Protocol object passed in.
"""
from typing import Dict, List, Optional
import time

from agent.registry import registry
from agent.audit import log_tool_call


def _trim_messages(messages, max_len=60):
    """Drop oldest full turn(s) from head. Never orphan tool_calls."""
    while len(messages) > max_len:
        i = 0
        while i < len(messages) and messages[i].get("role") == "system":
            i += 1
        if i >= len(messages):
            break

        # The first non-system message MUST be a user message to form a
        # deletable turn. If it's assistant/tool, skip forward to the next
        # user so we don't split a turn in half.
        if messages[i].get("role") != "user":
            while i < len(messages) and messages[i].get("role") != "user":
                i += 1
            if i >= len(messages):
                break

        j = i + 1
        while j < len(messages) and messages[j].get("role") != "user":
            j += 1
        del messages[i:j]


def run_conversation(
    agent,          # AIAgent instance (for config, protocol, max_iterations access)
    messages: List[Dict],
    tools: Optional[List[str]] = None,
    deck=None,
) -> str:
    """Run one turn of conversation with automatic tool-use loop.

    Args:
        agent: AIAgent instance — supplies protocol, model, system_prompt, max_iterations.
        messages: Conversation history in internal format.
        tools: Optional list of enabled tool names.
        deck: Optional Deck; if provided, tools drawn ONLY from the Deck.

    Returns:
        Final assistant text response, or "(reached max iterations)".
    """
    protocol = agent.protocol
    max_iters = agent.max_iterations
    max_ctx = getattr(agent, "max_context_messages", 90)

    # ── resolve tools ──────────────────────────────────────────────────
    if deck is not None:
        active_tools = deck.get_schemas_for_protocol(agent._protocol_name)
        if not active_tools:
            active_tools = None
    else:
        active_tools = agent._build_tools(tools)

    api_msgs = protocol.build_messages(messages)

    temperature = getattr(agent, "temperature", 0.0)
    for _ in range(max_iters):
        response = protocol.api_call(
            agent.system_prompt, api_msgs, active_tools, agent.model, temperature,
        )
        result = protocol.build_response(response)

        if not result["tool_calls"]:
            return result["text"]

        # ── record assistant turn ───────────────────────────────────
        assistant_msg: dict = {
            "role": "assistant",
            "content": result["text"],
            "tool_calls": result["tool_calls"],
        }
        if result["reasoning"]:
            assistant_msg["reasoning"] = result["reasoning"]
        messages.append(assistant_msg)

        api_msgs.append(protocol.build_assistant_block(
            result["text"], result["reasoning"], result["tool_calls"],
        ))

        # ── execute tools ───────────────────────────────────────────
        for tc in result["tool_calls"]:
            t0 = time.time()
            try:
                tool_result = registry.call(tc["name"], tc["arguments"])
                dt = (time.time() - t0) * 1000
                log_tool_call(tc["name"], tc["arguments"], tool_result, dt, error=False)
            except Exception as e:
                # Log detailed error internally; return generic message to LLM
                # to prevent information leakage via exception strings.
                _err_detail = f"Tool error: {e}"
                dt = (time.time() - t0) * 1000
                log_tool_call(tc["name"], tc["arguments"], _err_detail, dt, error=True)
                tool_result = "Tool execution failed. Please check your request and try again."
            tool_msg = {
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": tool_result,
            }
            messages.append(tool_msg)
            api_msgs.append(protocol.build_tool_result_block(
                tc["id"], tool_result,
            ))

        # ── crude context trim ──────────────────────────────────────
        if len(messages) > max_ctx:
            _trim_messages(messages, max_ctx)
            api_msgs = protocol.build_messages(messages)

    return "(reached max iterations)"
