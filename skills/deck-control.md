---
name: deck-control
description: 控制 Worker Bee 的 Deck 模式，在全工具模式和专注模式之间切换
version: 1.0.0
author: Worker Bee
triggers:
  - deck
  - 工具集
  - 切换模式
tools:
  - deck_manage
  - sys_terminal
---

# Deck Control

控制 Worker Bee 的 Deck 模式。

## 什么是 Deck

Deck 是 Worker Bee 的工具边界系统：

- **全工具模式（full）**：加载 config 中的所有工具，适合日常对话和探索性任务
- **专注模式（focus）**：只加载匹配到的 skill 声明的工具 + 3 个冗余槽，适合特定工种任务
- **自动模式（auto，默认）**：无 skill 匹配时用全工具，有匹配时用专注模式

## 何时切换模式

**切换到全工具模式：**
- 用户说"我想随便聊聊"、"帮我查点资料"等探索性请求
- 没有明确的任务边界
- 需要访问所有可能的工具

**切换到专注模式：**
- 用户说"现在只做 X 任务"、"进入 Y 工种模式"
- 明确的任务范围和边界
- 想避免 Agent 使用无关工具

**恢复自动模式：**
- 完成一个明确任务后
- 用户说"恢复正常"、"退出专注模式"

## 使用方法

### 查询当前模式

```python
result = deck_manage(action="status")
print(result["current_mode"])  # auto | full | focus
```

### 切换模式

```python
# 切换到全工具模式
deck_manage(action="set_full")

# 切换到专注模式
deck_manage(action="set_focus")

# 恢复自动模式
deck_manage(action="set_auto")
```

## 重要提示

**模式切换只对下一轮对话生效。** 当前这一轮的 Deck 已经构建好了，无法动态修改。

如果用户要求在专注模式下使用某个工具，但该工具不在当前 Deck 中：

**回复模板：**

```
当前 Deck 不包含 [工具名]。

Deck 专注模式只加载匹配到的 skill 声明的工具。要使用 [工具名]，可以：

1. 切换到全工具模式：`wb deck mode full`（从命令行执行）
2. 或者在下一轮对话中触发包含该工具的 skill

我无法在当前对话中动态添加工具——这是 Deck 的设计约束。
```

## Pitfalls

1. **不要尝试通过 `sys_terminal` 调用 `wb deck mode` 来动态添加工具。** Deck 在对话开始时构建，中途无法改变。

2. **`deck_manage` 工具本身必须在 Deck 中才能使用。** 如果用户在专注模式下没有匹配到 `deck-control` skill，Agent 无法查询或切换模式。这是一个已知限制。

3. **模式切换是全局配置，影响所有后续对话。** 不要频繁切换，除非用户明确要求。

## Examples

### Example 1: 用户想探索

```
User: 我想随便聊聊，不确定要做什么
Agent: [调用 deck_manage(action="set_full")]
好的，已切换到全工具模式。下一轮对话将加载所有工具，方便探索。
```

### Example 2: 用户进入专注任务

```
User: 现在只做文档整理任务，不要分心
Agent: [调用 deck_manage(action="set_focus")]
已切换到专注模式。下一轮对话将只加载文档相关的 skill 工具。
```

### Example 3: 用户在专注模式下要求不支持的工具

```
User: 帮我发个飞书消息
Agent: [调用 deck_manage(action="status") 检查当前模式]
当前 Deck 不包含 lark_send_message。

Deck 专注模式只加载匹配到的 skill 声明的工具。要使用飞书消息功能，可以：

1. 切换到全工具模式：`wb deck mode full`（从命令行执行）
2. 或者在下一轮对话中说"发飞书消息"来触发相关 skill

我无法在当前对话中动态添加工具——这是 Deck 的设计约束。
```

### Example 4: 任务完成，恢复自动

```
User: 文档整理完了，恢复正常模式
Agent: [调用 deck_manage(action="set_auto")]
已恢复自动模式。下一轮对话将根据是否匹配到 skill 自动选择全工具或专注模式。
```
