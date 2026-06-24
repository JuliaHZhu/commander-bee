# 外源信息素格式

> *所有状态必须是人可读的 Markdown。两个物种看同一个文件。*

## 什么是外源信息素？

在 Worker Bee 里，**外源信息素** = 人和 LLM 都可以读写的外部状态文件。

- **外源**：在 LLM 的 context window 外面，在程序的内存外面
- **信息素**：两个物种都能感知和响应的共享信号

比喻：蚂蚁留下信息素路径给其他蚂蚁跟随。Worker Bee 留下 Markdown 路径给下一个 session（或人）拾起来。

## 设计规则

1. **只用 Markdown** — 没有 JSON，没有二进制，没有数据库 schema
2. **两个物种都能读** — LLM 能用 `read_file` 解析，人能用任何文本编辑器打开
3. **尾部添加友好** — 新条目往末尾或新节里放，不用重新编号
4. **人是最终真理** — LLM 和人有冲突，人赢

---

## 格式 1：术语词典

路径：`~/.worker-bee/dict/<project>.md`

使用：**Aristotle Bee**

```markdown
# 术语词典：<项目>

## <术语>
- **Definition**: <准确定义>
- **Variants**: <变体 1> | <变体 2>
- **Context**: Session <id> — 指 <哪个变体>
- **Drift warning**: Session <id> 用了不同意思

## <另一术语>
...
```

### 规则
- 每个术语 = 一个 H2 (`##`)
- 字段 = 带 `**粗体键**` 的列表
- `Drift warning` 非必需，但建议加
- 不需严格排序 — 新术语往末尾追加

---

## 格式 2：架构文档

路径：`~/.worker-bee/arch/<project>.md`

使用：**Architecture Prototype Bee**

```markdown
# Architecture: <项目>

## Goal
<一句话，不可再约简>

## Core Constraints
- [约束 1]: <不能再拆了>
- [约束 2]: <物理边界或用户需求>

## Modules

### <模块 A>
- **Responsibility**: <一句话>
- **Interface**: <输入 → 输出契约>
- **Algorithm**: <名称或草图>
- **Complexity**: <大 O>
- **Dependencies**: <其他模块>

### <模块 B>
...

## Tradeoffs
- 选 X 而非 Y 因为 <原因>
```

### 规则
- Goal 必须一句话。需要两句 = 还没规约到位。
- 约束必须"不可再分"。如果你还能问"为什么？"并得到有意义的答案，继续推。
- 每个模块是 `## Modules` 下的 H3。
- Tradeoffs 是可以被反转的决策。记录下来，以后的你才知道为什么。

---

## 格式 3：项目计划

路径：`~/.worker-bee/pm/<project>.md`

使用：**Project Manager Bee**

```markdown
# Project: <项目>

## Final Artifact
<交付什么？>

## Template
- <部分 1>: <标题> — <大小> — [TBD/Draft/Done]
- <部分 2>: <标题> — <大小> — [状态]

## Tasks
- [ ] <任务> — <负责人> — <截止日> — [blocker: <什么>]

## Contacts
- [<姓名>]: <角色> — <联系顺序> — [状态]

## Risks
- [<风险>]: <缓解方案>
```

### 规则
- `Final Artifact` 是北极星。其他一切都为它服务。
- `Template` 是脚手架。它应该看起来像最终文档，只是有空白。
- `Tasks` 用 `[blocker: X]` 表示依赖。没有阻塞 = 现在就能开始。
- `Contacts` 包括联系顺序（先联系谁、再联系谁...）。
- `Risks` 不是担忧 — 是具体事件加缓解方案。

---

## 格式 4：Handoff 文档

路径：`~/.worker-bee/handoffs/<session_id>.md`

使用：**所有 Bee**（批次继续）

```markdown
# Handoff

**Session:** `<session_id>`
**Exported:** <ISO 时间戳>

## Purpose
<本次 session 想完成什么？>

## Completed
- <完成了什么>

## Todos
- [ ] <剩余工作>

## Context
- <下一次 session 需要的关键信息>

## Next Step
<下一个 session 应该先做什么？>
```

### 规则
- 不是对话摘要。是**工作态快照**。
- `Completed` = 事实，不是解读。
- `Context` = 下一次 session 否则需要重新发现的东西。
- `Next Step` = 一个明确动作，不是选项列表。

---

## 对比

| 格式 | 路径 | 使用者 | 内容 |
|--------|------|--------|------|
| 词典 | `dict/*.md` | Aristotle Bee | 术语定义 + 漂移跟踪 |
| 架构 | `arch/*.md` | Architecture Bee | 模块 + 约束 + tradeoffs |
| 项目计划 | `pm/*.md` | Project Manager Bee | 模板 + 任务 + 联系人 + 风险 |
| Handoff | `handoffs/*.md` | 所有 Bee | 工作态快照用于继续 |
| 数据集 | `worldbee/data/*.md` | WorldBee | 原始数据 + 统计结果 |
| 模型 | `worldbee/models/*.md` | WorldBee | 公式 + 参数 + 基准测试 |
| 规则 | `worldbee/rules/*.md` | WorldBee | 硬约束 + 来源 + 红线 |
