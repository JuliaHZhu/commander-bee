"""Deck — 运行时工具边界。

核心设计：堆栈思维。
  装填（Procure）= 把相关工具压进来
  抽取（Draw）  = LLM 只能从这个栈里拿
  约束（Halt）  = 栈里没有就停

冗余：固定 +3 卡槽，从基础工具池按顺序填。

v0.1.1 新增：双模式 Deck 系统
  full  = 全工具模式（默认）：使用 config.tools 全量
  focus = Deck 专注模式：仅使用 skill_tools + 基础冗余
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


# 基础工具池：按优先级排序，用于填充冗余卡槽
BASELINE_POOL = [
    "fs_read_file",
    "fs_search_files",
    "sys_terminal",
    "send_message",
    "cronjob",
]


class Deck:
    """不可变工具集——就是一个有序列表。

    一旦构建，执行时 LLM 只能从这个列表里选工具。
    """

    def __init__(self, tools: List[str], registry):
        self._registry = registry
        # 去重保留顺序
        seen = set()
        self.tools = []
        for t in tools:
            if t not in seen:
                seen.add(t)
                self.tools.append(t)

    def has(self, name: str) -> bool:
        return name in self.tools

    def schemas(self) -> List[dict]:
        """返回 Deck 内所有工具的 schema（原始格式）。"""
        out = []
        for t in self.tools:
            if self._registry.has_tool(t):
                s = self._registry.get_schema(t)
                if s:
                    out.append(s)
        return out

    def get_schemas_for_protocol(self, protocol: str) -> List[dict]:
        """返回 Deck 内所有工具的 schema，按协议转换。
        
        Anthropic 格式（默认）：直接返回 registry schema。
        OpenAI 格式：转换为 function-calling 格式。
        """
        raw = self.schemas()
        if protocol == "openai":
            converted = []
            for s in raw:
                converted.append({
                    "type": "function",
                    "function": {
                        "name": s["name"],
                        "description": s["description"],
                        "parameters": s.get("input_schema", {"type": "object"}),
                    },
                })
            return converted
        return raw

    def size(self) -> int:
        return len(self.tools)

    def __repr__(self) -> str:
        return f"Deck({self.tools})"


def build_deck(
    skill_tools: List[str],
    registry,
    redundancy: int = 3,
) -> Deck:
    """采购一个 Deck。

    Args:
        skill_tools: 匹配 skills 声明的工具
        registry: 工具注册表
        redundancy: 冗余卡槽数（默认 3）

    Returns:
        Deck(skill_tools + 填充的基础工具)
    """
    tools = list(skill_tools)

    # 冗余：从 BASELINE_POOL 按顺序填，填满 redundancy 个卡槽
    filled = 0
    for t in BASELINE_POOL:
        if filled >= redundancy:
            break
        if t not in tools and registry.has_tool(t):
            tools.append(t)
            filled += 1

    return Deck(tools, registry)


# ——————————————————————————————————————————————————————————
# DeckManager — 双模式管理 + 使用日志
# ——————————————————————————————————————————————————————————

class DeckManager:
    """管理 Deck 的模式、状态和使用日志。

    两种模式：
      full  — 全工具模式（默认），使用 config.tools 中的所有工具
      focus — Deck 专注模式，仅使用 skill_tools + 基础冗余

    日志路径：~/.worker-bee/deck_log.json
    """

    FALLBACK_TOOLS = ["fs_read_file", "fs_search_files", "sys_terminal"]

    def __init__(self, config_tools: List[str], registry, log_path: Optional[Path] = None):
        self.config_tools = list(config_tools)
        self._registry = registry
        self._mode = "full"          # "full" | "focus"
        self._focus_tools: List[str] = []
        self._log_path = log_path or (Path.home() / ".worker-bee" / "deck_log.json")
        self._ensure_dir()

    def _ensure_dir(self):
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    # —— mode ——
    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> str:
        """切换模式，返回确认信息。"""
        mode = mode.lower().strip()
        if mode not in ("full", "focus"):
            return f"未知模式: {mode}。可用: full, focus"
        if self._mode != mode:
            self._mode = mode
            self._log_mode_switch()
        return f"当前模式: {self._mode}"

    # —— focus deck 操作 ——
    def set_focus_tools(self, tools: List[str]):
        """在 focus 模式下锁定工具列表。"""
        self._focus_tools = list(dict.fromkeys(tools))

    def add_tool(self, tool: str) -> str:
        """往当前 Deck 增加一个工具。"""
        if not self._registry.has_tool(tool):
            return f"错误: 工具 '{tool}' 不在注册表中"
        if self._mode == "full":
            if tool not in self.config_tools:
                self.config_tools.append(tool)
            return f"已在全工具模式下添加 '{tool}'"
        else:
            if tool not in self._focus_tools:
                self._focus_tools.append(tool)
            return f"已在专注模式下添加 '{tool}'"

    def drop_tool(self, tool: str) -> str:
        """从当前 Deck 移除一个工具。"""
        if self._mode == "full":
            if tool in self.config_tools:
                self.config_tools.remove(tool)
            return f"已在全工具模式下移除 '{tool}'"
        else:
            if tool in self._focus_tools:
                self._focus_tools.remove(tool)
            return f"已在专注模式下移除 '{tool}'"

    def reset(self) -> str:
        """清空 focus tools，重新等待 trigger 匹配。"""
        self._focus_tools = []
        return "Deck 已重置。下次输入将触发新的 skill 匹配。"

    def list_tools(self) -> List[str]:
        """列出当前 Deck 中的工具。"""
        if self._mode == "full":
            return list(self.config_tools)
        return list(self._focus_tools)

    # —— procure deck ——
    def procure(
        self,
        skill_tools: List[str],
        infra_filter,
    ) -> Deck:
        """根据当前模式采购 Deck。

        Args:
            skill_tools: 匹配到的 skill 工具列表
            infra_filter: infra.filter_tools 方法

        Returns:
            构建好的 Deck 实例
        """
        if self._mode == "full":
            tools = list(self.config_tools)
        else:
            if not skill_tools:
                tools = list(self.FALLBACK_TOOLS)
            else:
                deck = build_deck(skill_tools, self._registry, redundancy=3)
                tools = deck.tools
            # 合并用户手动添加的 focus_tools
            tools = list(dict.fromkeys(tools + self._focus_tools))

        final_tools = infra_filter(tools)
        deck = Deck(final_tools, self._registry)
        self._log_combo(deck.tools)
        return deck

    # —— 日志 ——
    def _log_path_exists(self) -> bool:
        return self._log_path.exists()

    def _load_log(self) -> dict:
        if not self._log_path_exists():
            return {"combos": {}, "mode_switches": 0, "focus_sessions": 0}
        try:
            return json.loads(self._log_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"combos": {}, "mode_switches": 0, "focus_sessions": 0}

    def _save_log(self, data: dict):
        try:
            self._log_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _log_combo(self, tools: List[str]):
        if not tools:
            return
        data = self._load_log()
        key = "+".join(sorted(tools))
        today = datetime.now().strftime("%Y-%m-%d")
        if key in data["combos"]:
            data["combos"][key]["count"] += 1
            data["combos"][key]["last_used"] = today
        else:
            data["combos"][key] = {"count": 1, "last_used": today}
        self._save_log(data)

    def _log_mode_switch(self):
        data = self._load_log()
        data["mode_switches"] = data.get("mode_switches", 0) + 1
        if self._mode == "focus":
            data["focus_sessions"] = data.get("focus_sessions", 0) + 1
        self._save_log(data)

    def get_log(self) -> dict:
        """获取 Deck 使用日志。"""
        return self._load_log()
