"""Deck — 运行时工具边界。

核心设计：堆栈思维。
  装填（Procure）= 把相关工具压进来
  抽取（Draw）  = LLM 只能从这个栈里拿
  约束（Halt）  = 栈里没有就停

冗余：固定 +3 卡槽，从基础工具池按顺序填。
"""
from typing import List


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
