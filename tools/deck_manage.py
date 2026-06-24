"""deck_manage — 薄执行层，让 Agent 能够查询和操作 Deck。

调用链：
  Agent → deck_manage Tool → DeckManager → 文件/内存
"""
from agent.main import load_config
from agent.deck import DeckManager
from agent.registry import registry


def deck_manage(action: str, tool_name: str = "") -> str:
    """Manage the current Deck — query mode, switch mode, or modify tools.

    Args:
        action: One of — mode, full, focus, add, drop, reset, list, log
        tool_name: Required for 'add' and 'drop' actions

    Returns:
        Human-readable result string.
    """
    cfg = load_config() or {}
    dm = DeckManager(cfg.get("tools", []), registry)

    action = action.lower().strip()

    if action == "mode":
        tools = dm.list_tools()
        return f"Mode: {dm.mode}\nTools ({len(tools)}): {', '.join(tools) if tools else '(none)'}"

    if action == "full":
        return dm.set_mode("full")

    if action == "focus":
        return dm.set_mode("focus")

    if action == "add":
        if not tool_name:
            return "Error: tool_name is required for 'add' action"
        return dm.add_tool(tool_name)

    if action == "drop":
        if not tool_name:
            return "Error: tool_name is required for 'drop' action"
        return dm.drop_tool(tool_name)

    if action == "reset":
        return dm.reset()

    if action == "list":
        tools = dm.list_tools()
        return f"Tools ({len(tools)}): {', '.join(tools) if tools else '(none)'}"

    if action == "log":
        import json
        return json.dumps(dm.get_log(), ensure_ascii=False, indent=2)

    return (
        f"Unknown action: '{action}'. "
        f"Available: mode, full, focus, add, drop, reset, list, log"
    )


registry.register(
    name="deck_manage",
    description=(
        "Manage the Agent's tool Deck — control which tools are available. "
        "Actions: mode (show status), full (all tools), focus (skill-only), "
        "add <tool>, drop <tool>, reset (re-match skills), list (show tools), log (stats)."
    ),
    parameters={
        "properties": {
            "action": {
                "type": "string",
                "description": "Action to perform: mode, full, focus, add, drop, reset, list, log",
            },
            "tool_name": {
                "type": "string",
                "description": "Tool name (required for add/drop)",
                "default": "",
            },
        },
        "required": ["action"],
    },
    handler=deck_manage,
    tags=["meta", "deck", "boundary"],
    category="meta",
)
