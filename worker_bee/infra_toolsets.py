"""InfraToolSet — 平台基础设施工具集。

职责边界（与 Skill 严格区分）：
  - InfraToolSet 决定「环境允许用什么」（厨房有什么食材）
  - Skill 决定「对话应该用什么」（菜谱需要什么食材）
  - Registry 存放「有什么可用」（食材库目录）

当前实现：永远本地 linux，所有工具默认可用。
"""
from typing import List


class InfraToolSet:
    """平台基础设施工具集。不是给 LLM 看的，是给系统看的。"""

    def __init__(self):
        pass

    def detect_platform(self) -> str:
        """检测当前运行平台。"""
        return "linux"

    @property
    def platform(self) -> str:
        return "linux"

    def get_available_tools(self) -> List[str]:
        """返回当前平台物理可用的工具列表。linux 不限制。"""
        return []

    def is_tool_available(self, _tool_name: str) -> bool:
        """检查某个工具在当前平台是否物理可用。"""
        return True

    def filter_tools(self, tool_names: List[str]) -> List[str]:
        """从给定工具列表中过滤出当前平台可用的。

        linux 平台：不过滤，全部放行。
        """
        return list(tool_names)

    def describe(self) -> str:
        """返回当前平台的描述，用于日志或调试。"""
        return "Platform: linux\n  本地运行 — 所有工具默认可用\n  Available infra tools: (unlimited)"

    def invalidate(self) -> None:
        """清空缓存。"""
        pass


# 模块级单例
infra = InfraToolSet()
