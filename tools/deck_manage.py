"""deck_manage — Agent 查询和控制 Deck 模式的工具。

提供给 Agent 查询当前 Deck 状态、切换模式的能力。
不提供 add/drop 单个工具的能力（设计上不支持）。
"""
import json
import subprocess
from pathlib import Path


def deck_manage(action: str) -> dict:
    """Deck 管理工具。
    
    Args:
        action: 操作类型
            - "status": 查询当前 Deck 模式和统计
            - "set_full": 切换到全工具模式
            - "set_focus": 切换到专注模式
            - "set_auto": 切换到自动模式（默认）
    
    Returns:
        操作结果
    """
    config_path = Path.home() / ".worker-bee" / "config.json"
    
    if action == "status":
        # 读取当前模式
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
            mode = config.get("deck_mode", "auto")
        else:
            mode = "auto"
        
        # 读取最近的 log 统计
        log_path = Path.home() / ".worker-bee" / "deck_log.jsonl"
        if log_path.exists():
            with open(log_path) as f:
                lines = f.readlines()
            recent = [json.loads(line) for line in lines[-5:]]
        else:
            recent = []
        
        return {
            "current_mode": mode,
            "description": {
                "auto": "Full mode when no skills matched, focus mode otherwise",
                "full": "Always use all config.tools",
                "focus": "Always use skill tools + redundancy only"
            }[mode],
            "recent_runs": recent,
        }
    
    elif action in ["set_full", "set_focus", "set_auto"]:
        # 提取目标模式
        target_mode = action.replace("set_", "")
        
        # 写入配置
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
        else:
            config = {}
        
        old_mode = config.get("deck_mode", "auto")
        config["deck_mode"] = target_mode
        
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        
        return {
            "success": True,
            "old_mode": old_mode,
            "new_mode": target_mode,
            "message": f"Deck mode changed from {old_mode} to {target_mode}",
        }
    
    else:
        return {
            "error": f"Unknown action: {action}",
            "valid_actions": ["status", "set_full", "set_focus", "set_auto"],
        }


# ── Registry ──────────────────────────────────────────────────────────────────────────

from worker_bee.registry import registry

registry.register(
    name="deck_manage",
    description="Query and control Deck mode. Use 'status' to check current mode, 'set_*' to switch modes.",
    parameters={
        "properties": {
            "action": {
                "type": "string",
                "enum": ["status", "set_full", "set_focus", "set_auto"],
                "description": "Action: status (query), set_full/set_focus/set_auto (switch mode)",
            },
        },
        "required": ["action"],
    },
    handler=deck_manage,
    tags=["deck", "mode"],
    category="infra",
)

