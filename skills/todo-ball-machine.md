---
name: todo-ball-machine
description: Todo Ball Machine — 人生任务管理系统，基于抽球机制的日常场次管理
version: 2.0
triggers:
  - todo_ball_machine
  - Todo Ball Machine
  - todo ball
  - draw ball
  - session
  - today plan
  - box quota
  - morning report
tools:
  - todo_ball_machine
---

# Todo Ball Machine v2.0

## 核心概念

装填 → 抽取 → 完成

- **装填 (Fill)**：shuffle 后彩球入栈，单文件 `state.json` 持久化
- **抽取 (Draw)**：random.choice + pop，一场一球
- **重抽 (Redraw)**：push 回栈顶 → 再抽
- **完成 (Done)**：status 标记，完成率可统计

## 默认盒子（可自定义）

| 盒子 | emoji | 配额 |
|------|-------|------|
| 学习 | 📚   | 21   |
| 工作 | 💼   | 21   |
| 运动 | 🏃   | 15   |
| 治愈 | 🧘   | 14   |
| 社交 | 🎉   | 7    |
| 家务 | 🧹   | 6    |

改分类、改配额、改球内容 → 编辑 `balls.json` + `config.json` 即可，无需改代码。

## Tool: `todo_ball_machine`

### 操作清单

| action | session | content | 说明 |
|--------|---------|---------|-----|
| `dashboard` | — | — | 仪表盘：今日安排 + 盒子剩余 + 周期进度 |
| `today` | — | — | 今日 4 场详情 |
| `draw` | morning/afternoon/evening/overtime | — | 抽取指定场次 |
| `quick_draw` | — | — | 快速抽取三场（排除已抽） |
| `complete` | morning/... | — | 标记完成 |
| `redraw` | morning/... | — | 重抽：旧球返回栈顶 → 新抽 |
| `edit` | morning/... | 新内容 | 修改场次内容 |
| `box_list` | — | — | 盒子配额列表 |
| `cycle_status` | — | — | 周期名称、起止、完成度 |
| `new_cycle` | — | 周期名（可省略） | 开启新周期（重新装填） |
| `history` | — | N天（默认7） | 历史记录 |
| `day` | — | 日期（默认今天） | 指定日期详情 |
| `stats` | — | N天（默认7） | 统计报告：盒子完成率 + 每日趋势 + 连续天数 |
| `help` | — | — | 帮助文字 |

### 常用示例

```
# 今日快照
todo_ball_machine(action="today")

# 快速抽取三场
todo_ball_machine(action="quick_draw")

# 抽取上午场
todo_ball_machine(action="draw", session="morning")

# 完成上午场
todo_ball_machine(action="complete", session="morning")

# 重抽下午场
todo_ball_machine(action="redraw", session="afternoon")

# 统计报告（最近 14 天）
todo_ball_machine(action="stats", content="14")

# 查 2026-05-10 那天的安排
todo_ball_machine(action="day", content="2026-05-10")

# 开启新周期
todo_ball_machine(action="new_cycle", content="2026年06月周期")
```

## 工作流

1. **每日早报**：cron 每天 8:00 自动推送：今日安排 + 盒子剩余 + 昨日回顾 + 连续完成天数
2. **清晨**：用 `quick_draw` 抽取三场
3. **执行**：完成后 `complete` 标记
4. **傍晚**：用 `stats` 看本周趋势
5. **周期结束**：`cycle_status` 检查 → `new_cycle` 开新周期

## 约束

- 30 天一周期，抽完的球从栈中移除（不重复）
- `重抽` 将旧球退回栈顶，保证瞬间不抽到同一个
- 所有状态存于单文件 `state.json`，不依赖外部数据库
- 盒子分类由 `balls.json` 配置驱动，代码不硬编码任何分类
