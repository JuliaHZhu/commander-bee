# AEvo: Harnessing Agentic Evolution

> **arXiv: 2605.13821** — [arxiv.org/abs/2605.13821](https://arxiv.org/abs/2605.13821)
> 作者: Jiayi Zhang, Yongfeng Gu, Jianhao Ruan, Maojia Song, Yiran Peng, Zhiguang Han, Jinyu Xiang, Zhitao Wang, Caiyin Yang, Yixi Ouyang, Bang Liu, Chenglin Wu†, Yuyu Luo†
> 机构: DeepWisdom, HKUST(GZ), SUTD, NTU, SJTU, Tsinghua, UdeM & Mila
> 日期: 2026-05-13
> 分析日期: 2026-06-05

---

## 一句话

把 agentic evolution 本身建模成交互式环境——meta-agent 不直接产生候选，而是编辑控制未来搜索的机制。

## 核心架构

```
┌─────────────────────────────────────────────┐
│                  AEvo Loop                    │
│                                               │
│  ┌─────────────┐       ┌──────────────────┐  │
│  │ Meta-Editing │──────▶│ Evolution Segment │  │
│  │   Phase      │       │  (多轮候选生成)    │  │
│  │              │◀──────│                   │  │
│  │ 编辑 Π_r →   │       │ Π_r 下跑 N 轮     │  │
│  │ Π_{r+1}     │       │ 累积 C_r          │  │
│  └─────────────┘       └──────────────────┘  │
│         ▲                       │             │
│         │     ┌─────────────────┘             │
│         │     ▼                               │
│  ┌──────────────────────────────┐            │
│  │         Harness               │            │
│  │  · 统一 workspace            │            │
│  │  · 受保护 evaluator（隔离）   │            │
│  │  · 候选历史（可搜索）         │            │
│  │  · 可恢复 CLI                │            │
│  └──────────────────────────────┘            │
└─────────────────────────────────────────────┘
```

## 形式化（简化）

| 符号 | 含义 |
|------|------|
| C_r | 累积进化上下文（候选 + 反馈 + 轨迹 + 失败 + 成本） |
| Π_r | 第 r 轮的进化机制（procedure 或 agent context） |
| s_r = (r, C_r) | 环境状态 |
| o_r = Φ(s_r) | meta-agent 观测（进度/重复失败/无效尝试/成本/冗余方向） |
| a_r = M(o_r) | meta-action：编辑 Π_r → Π_{r+1} + run plan |
| c_{r+1} = Π_{r+1}(C_r) | 新机制下继续搜索 |

## 两类实例化

| 维度 | Procedure-Based | Agent-Based |
|------|----------------|-------------|
| Π_r 是什么 | 显式搜索流程代码 | Agent 运行上下文 |
| meta-action 改什么 | selection / optimization / feedback summary / budget / update rules | skills / goals / tools / feedback format / notes / execution context |
| 候选生成者 | 固定流程 | 通用 agent（不受 meta-agent 直接控制） |
| AEvo 的角色 | 改流程代码 | 改 agent 运行的条件 |

## 关键结果

### 标准 Benchmark（Avg@3）

| Benchmark | AEvo | 最强 Baseline | 差距 |
|-----------|------|-------------|------|
| Terminal-Bench | **53.8** | 44.3 (DGM/AFlow) | +21% |
| ARC-AGI-2 | **47.0** | 36.0 (ADAS) | +31% |
| 平均相对提升 | — | — | **+26%** |

### 开放优化任务（Best@3, 100 轮）

| 任务 | AEvo 最佳 | 说明 |
|------|----------|------|
| Circle Packing 26 | 2.6359（并列最优） | 第 2-17 轮即达最优 |
| Autocorrelation | **0.9459** | 超过所有 baseline |
| Kernel Optimization | **1138 cycles** | 自称同预算下 best reported |

### 消融实验（Kernel 任务）

| 配置 | Reward Hack | 最佳 Cycles |
|------|------------|------------|
| Full AEvo | 0/3 | **1138** |
| 去掉 Meta-Agent Skills | 0/3 | 1407（弱化） |
| 去掉 Evolution Harness | **2/3** | N/A（reward hack） |

> **结论**: Harness = 安全边界，Skills = 持续有效的干预能力。两者正交但都需要。

## Design Decisions（值得借鉴的点）

### 1. Coarse-Grained Intervention

Meta-agent 不每轮干预。产出一个 run plan（迭代预算 + 停止条件），evolution segment 在不受打扰的情况下跑多轮。segment 结束或检测到停滞才切回 meta-editing。

**收益**: 干预成本和收益平衡。太频繁→成本高；太稀疏→漂移。

### 2. 故意简单的初始化

初始 procedure 故意设得很弱——best-valid selection + 单一 LLM rewrite。初始 agent 也是最小 ReAct。理由：**让后续 meta-edit 更容易归因**。如果种子已经很复杂，分不清改进来自 meta-edit 还是种子本身。

→ 对应 worker-bee 的「冰核雪球」哲学。

### 3. Evaluator 隔离

Evaluator 既不对 evolution agent 暴露，也不对 meta-agent 暴露。agent 只能 submit candidate，不能 inspect evaluator internals、访问隐藏 benchmark artifacts、或直接写分数。

**与 worker-bee 的对应**: `safety.py` 的 write-safety 检查 + audit log。

### 4. 失败候选不丢弃

失败的候选变成过程级证据。Case study 中 P0→P6 共 7 次 meta-intervention，P5/P6 回退了——但论文坦率展示，这些失败帮助 meta-agent 决定后续方向。

## 与 Worker-Bee 的映射

| AEvo 概念 | Worker-Bee 对应 | 差异 |
|-----------|----------------|------|
| Harness（工作区 + evaluator 隔离） | WorldBee（状态观测 + 环境边界） | WorldBee 还承担更多——pheromone 广播、跨 agent 状态同步 |
| Meta-Agent（机制编辑决策） | Strategic Bee | Strategic Bee 更偏战略层决策，不直接改代码 |
| Evolution Context C_r | NATS 消息历史 + 文件 mailbox | worker-bee 的 context 天然分布式，AEvo 是单机 harness |
| Procedure-Based | 无直接对应 | worker-bee 全是 agent-based |
| Agent-Based | 工蜂本体 | worker-bee agent 不走 harness 内的 candidate 循环 |

### 核心差异

| | AEvo | Worker-Bee |
|---|------|------------|
| 元决策者 | **单体** meta-agent | **双体联合**: WorldBee（观测）+ Strategic Bee（决策） |
| 进化对象 | 单个任务（benchmark/优化问题） | 整个蜂群生态（agent + skill + tool） |
| 安全模型 | Harness 内 evaluator 隔离 | 每 agent 内置 safety.py + 外部 audit log |
| 干预粒度 | Meta-editing phase 产 run plan，segment 跑 N 轮 | 更粗——cron job 间隔 + handoff 触发 |

### 可直接借鉴的点

1. **Evaluator 隔离 → WorldBee 加 evaluation firewall**: 让 WorldBee 成为唯一有权访问评测结果的 Bee，其他 agent 只收反馈摘要
2. **Coarse-grained intervention → Strategic Bee 的干预频率设计**: 不每轮决策，设置"进化段"后再审视
3. **Harness CLI → WorldBee CLI 增强**: 可恢复、可查询状态的命令行接口

## 潜在问题

1. **Meta-agent 能力瓶颈**: 论文用 Claude-Opus-4.7 / GPT-5.4。弱 meta-agent 下框架是否成立？未讨论。
2. **3 倍成本换 26%**: 是否值得取决于边际收益曲线。但开放任务上成本可控（prompt caching 生效时 $0.32-1.40/R）。
3. **Procedure vs Agent 不对称**: Agent-based 的编辑空间（prompts/skills/notes/tools）远大于 procedure-based（几个函数），实际部署时这个不对称更显著。
4. **Harness 是新的单点**: Evaluator 设计缺陷无法被框架本身检测——只能防篡改，不能防设计错误。

## 与相关工作的定位

| 工作 | 定位 | 与 AEvo 关系 |
|------|------|------------|
| HyperAgents | 自修改 agent 程序，meta-improvement 内化 | AEvo 外部化——meta-agent 在 harness 外 |
| DGM (Darwin Gödel Machine) | 固定 procedure 进化 | AEvo 的 procedure-based baseline |
| CORAL | 多 agent 协作进化 | AEvo 仍然是单 meta-agent |
| MemEvolve / ALMA | 元进化 agent memory 设计 | AEvo 改的是更广的机制，不只是 memory |
| AFlow / ADAS | Agent workflow 自动设计 | AEvo 的固定 procedure baseline |
| **Worker-Bee** | 蜂群 agent 生态 + skill 进化 | AEvo 的单任务 harness 模式 vs worker-bee 的分布式蜂群 |

## 对 Worker-Bee 进化的启发

用户判断：**"进化任务"由 WorldBee + Strategic Bee 联合决策**。

这个映射是精准的：
- **WorldBee** = 状态观测 + harness 边界（对应 AEvo 的 Harness role）——观测全局状态、累积 pheromone、检测停滞/重复失败
- **Strategic Bee** = 机制编辑决策（对应 AEvo 的 Meta-Agent role）——决定改什么 skill/tool/agent 配置、不改什么

与 AEvo 的单体 meta-agent 不同，这个双体设计更符合蜂群架构的去中心化原则——观测和决策分开，各自独立演化和替换。
