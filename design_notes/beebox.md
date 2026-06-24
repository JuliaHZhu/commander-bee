# BeeBox 架构笔记

> 蜂群系统的设计思考——随分析积累，每次有新认知就追记。
> 不是设计文档，是认知轨迹。读的顺序不重要，每一段自包含。

---

## 2026-06-05: AGP 版本化 → Deck Snapshot 版本化

**触发**: 读 Autogenesis (AGP) 论文，喜欢其 RSPL 资源版本化 + rollback 的设计，但审视 worker-bee 现状后认为不该走中心化注册表路线。

**三个输入的合成**:

| 输入 | 内容 |
|------|------|
| AGP 的 RSPL | 五类资源（Prompt/Agent/Tool/Env/Mem）注册表 + version lineage + rollback |
| Worker-Bee 现状 | 专机专能 + 多机集群 + Deck 机制 |
| 黄超的判断 | agent 就是个 tool-calling loop |

**合成结论**: 版本化不需要 RSPL 那样的中心化注册表。Deck 本身就是一种轻量版本化机制——每个 atom 有来源、有标签、有归属轮次，一次 Deck snapshot 就是"那一时刻的知识版本"。专机专能的 agent 无状态，只管跑 tool-calling loop，状态在 Deck 和 NATS 消息里。

**版本化路径**: 不是加 RSPL，而是让 Deck 的 snapshot 机制更显式——
- 每次进化后自动记一个 Deck version
- 回滚 = 切 Deck snapshot
- agent 永远无状态，只读当前 Deck + 收 NATS 消息

---

## 2026-06-05: AEvo → WorldBee + Strategic Bee 双体联合

**触发**: 读 AEvo 论文，其核心是 meta-agent 编辑进化机制 Π，而非直接产生候选。

**映射**:
- **WorldBee** = AEvo 的 Harness 角色（状态观测 + 环境边界）
- **Strategic Bee** = AEvo 的 Meta-Agent 角色（机制编辑决策）

**与 AEvo 的关键差异**: AEvo 的 meta-agent 是单体的，Worker-Bee 是双体联合——观测和决策分开，各自独立演化和替换。更符合蜂群去中心化原则。

---

## 2026-06-05: 三篇论文的定位关系

| 维度 | AEvo | AGP | Worker-Bee |
|------|------|-----|------------|
| 性质 | 进化框架 | 协议规范 | 蜂群系统 |
| 资源模型 | 无统一抽象 | 五类资源 + 被动约束 | Skill/Tool/Agent 三类 |
| 版本控制 | Harness 内 candidate history | RSPL 原生 version lineage | Deck snapshot（无原生版本控制） |
| 进化机制 | Meta-agent 编辑 Π | SEPL 算子代数 | WorldBee + Strategic Bee 联合 |
| 安全模型 | Evaluator 隔离 | 每次变更版本化+可回滚 | safety.py + audit log |
| 通信模型 | 单机 harness | Bus 模型（AGS） | NATS + mailbox |

**Worker-Bee 的差异化**: 惯例驱动（非协议驱动），agent 极简（非胖 agent），一切皆 skill（非五类抽象），skill 接 tool 接死（非动态改写）。

---

## 2026-06-05: worker-bee 的"写死"是选择，不是缺失

AGP 和 AEvo 都假定"越可进化越好"。Worker-Bee 刻意在多个层级写死：

| 层级 | 写死的 | 可进化的 | 理由 |
|------|--------|---------|------|
| Tool | ✅ 写死 | — | 工具是基础设施，稳定 > 灵活 |
| Skill | — | ✅ Darwin Skill | 进化发生在技能层 |
| Agent | ✅ 写死（极简 loop） | — | 专机专能，换机不换 agent 逻辑 |
| 通信 | ✅ 写死（NATS） | — | 协议层稳定，内容层灵活 |
| 知识 | — | ✅ Deck atom + tag | 知识是唯一该持续进化的层 |

这和 AGP 的"所有五类资源都该可版本化"是对立的设计哲学。不是谁对谁错——是两条路。

---

## 2026-06-05: 专机专用 × 一体一机 × ToolCall Loop（三个递进约束）

**触发**: 把 AGP/AEvo 的启发放进 worker-bee 实际架构里走了一遍，发现三个约束层层收紧，恰好解释了为什么我们不需要 AGP 的大部分重量。

### 约束 1: 专机专用

写作 Agent 就只干写作。它不需要复杂的 Memory 版本管理——一个 Writer Bee 的"历史"不是记忆版本，而是**Procedure 的迭代轨迹**：上次用的什么 prompt 模板、选了哪些 atom、产出被 Julia 怎么改的。

→ Memory 版本化不适用。适用的是 Procedure 版本化——每个 Writing Bee 的 procedure 就是它的进化对象。

### 约束 2: 一体一机

一个 Agent = 一台 Computer。十几台 Computer 在跑，但大家都跑在同一个 Ubuntu 上。不需要 environment 抽象层去适配异构环境——没有异构。

→ AGP 的 Environment 资源类型不适用。Worker-Bee 的"环境"就是 Ubuntu + NATS，写死在基础设施层。

### 约束 3: ToolCall Loop

黄超的判断：agent 就是个 tool-calling loop。Loop 的核心是**连续的 tool-call 动作序列**——不是"规划-执行-反思"的重型循环，是 call tool → 收结果 → call next tool。

结合前面两篇论文：
- **WorldBee** 跟踪的是整个 BeeBox 的进化过程——哪台机产出了什么、哪些 skill 被更新了、Deck 变化轨迹
- **Strategic Bee** 做的是进化决策——什么时候该启动一次进化任务

### 进化的正确打开方式

进化**不是自发的**。不是说 agent 跑着跑着自己就进化了。进化是一个**特定时刻显式启动的任务**：

```
Julia 或 Strategic Bee 启动进化任务
  → WorldBee 把最近干的活理一遍（产出和反馈）
  → Strategic Bee 判断：Writer Bee 的 procedure 哪里该改
  → 改完 → 新的 procedure 版本 → Writer Bee 下次用新版
```

**Writer Bee 的进化方向是"更好的 Writer Bee"**。它不会变成 Director Bee，不会变成 Architect Bee。专机专用 = 进化有方向约束，不是 open-ended。

### 为什么这三个约束恰好消解了 AGP 的重量

| AGP 需要的 | Worker-Bee 为什么不需要 |
|-----------|----------------------|
| 五类资源统一管理 | 只有 Skill 和 Procedure 需要版本化，其他写死 |
| Environment 资源类型 | 一体一机，统一 Ubuntu |
| Memory 版本化 | 专机专用——"历史"是 Procedure 迭代轨迹，不是通用记忆 |
| 中心化注册表 | 蜂群去中心化——每台机的 procedure 版本存在自己的 Deck 里 |
| SEPL 算子代数 | 进化是显式任务，不是持续闭环——WorldBee + Strategic Bee 联合决策即可 |
| 持续自进化 | 进化是事件驱动 + 人工启动，不是后台常驻进程 |

---

## 2026-06-05: Strategic Bee + WorldBee 的 Pair 逻辑

**触发**: 对 Strategic Bee 的定位做了进一步澄清——为什么它必须和 WorldBee 成对出现。

**核心**: 战略工作本质上是**常规搜索研究工作**。Strategic Bee 平时就在不断搜索、研究、积累——这个过程中产生的研究要点、搜索结论、对比分析，平时是"存货"。当特定问题出现时，这些存货变成资源，被 WorldBee 调用来支持问题解决。

> 外部印证：战略情报领域——情报分析人员平时的工作就是做研究。不是在危机爆发时才启动，而是日常积累 depth，危机时才有东西可以调。

```
Strategic Bee（常规搜索研究）         WorldBee（全局状态跟踪）
        │                                    │
        │  持续产出：研究要点                   │
        │  对比分析                            │
        │  搜索结论                            │
        │  架构洞察                            │
        │                                    │
        ▼                                    │
    ┌───────────────────────────────────────┐
    │          共享知识池（Deck）             │
    │                                       │
    │  问题出现时：存货 → 资源               │
    │  WorldBee 检索相关研究要点              │
    │  → 支撑 Strategic Bee 做具体决策       │
    └───────────────────────────────────────┘
```

**与 AEvo/A G P 的对比**: AEvo 的 meta-agent 和 AGP 的 SEPL 都是"事件触发型"——进化只在检测到停滞时才启动。Strategic Bee 不同——它是**持续运行的常规工作**，不是只在出问题时才动。这和"进化是显式启动任务"不矛盾——启动的是**决策**（基于存量做判断），积累是**持续的**（日常搜索研究）。

**为什么必须是 Pair**: Strategic Bee 没有 WorldBee 就不知道当前全局状态（哪台机产出什么、哪个 skill 被更新了、Deck 变化轨迹）。WorldBee 没有 Strategic Bee 就只是一个被动观测器——拿到全局状态但不知道针对什么问题该怎么做。两者合在一起才是"知道发生了什么 + 知道该怎么办"。
