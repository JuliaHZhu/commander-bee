---
name: deck-control
description: 控制 Deck 模式切换与工具边界
trigger: deck, 工具, 模式, mode, focus, full
tools:
  - deck_manage
category: meta
composability: atomic
---

# Deck 控制 Skill

## 什么是 Deck

Deck 是 Agent 运行时能调用的工具列表。双模式设计：

- **full 全工具模式**（默认）：Agent 可以使用 config.tools 中的所有工具
- **focus Deck 专注模式**：Agent 只能使用 skill 匹配到的工具 + 基础冗余

## 什么时候该切换

| 场景 | 建议模式 |
|---|---|
| 探索、闲聊、多任务切换 | full |
| 专注执行某个工种（如只用飞书、只写代码） | focus |
| 安全敏感场景（不想让 Agent 读写文件） | focus |

## 操作命令

用 `deck_manage` Tool 或 `sys_terminal wb deck <cmd>` 调用：

```
deck_manage(action="mode")     # 查看当前模式和工具列表
deck_manage(action="full")     # 切换到全工具模式
deck_manage(action="focus")    # 切换到专注模式
deck_manage(action="add", tool_name="fs_write_file")   # 添加工具
deck_manage(action="drop", tool_name="sys_terminal")   # 移除工具
deck_manage(action="reset")    # 重置 Deck，重新 skill 匹配
deck_manage(action="list")     # 列出当前 Deck 工具
deck_manage(action="log")      # 查看使用统计
```

## “做不到”时的回复模板

当你在 focus 模式下因缺少工具而无法完成任务时，按这个格式回复：

```
我做不到：[具体原因，如 "当前 Deck 没有 fs_write_file 工具"]
可行做法：用 deck_manage(action="add", tool_name="<工具名>") 添加工具，或切换到 full 模式。
```

## 注意事项

- 默认是 full 模式，现有用户无需改动
- focus 模式下，无 skill 匹配时使用最小工具集（fs_read_file, fs_search_files, sys_terminal）
- 不用 Deck 功能时，关掉此 skill → deck_manage Tool 不再装填 → 物理隔离
