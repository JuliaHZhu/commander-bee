# Autogenesis: A Self-Evolving Agent Protocol

> **arXiv: 2604.15034v4** — [arxiv.org/abs/2604.15034](https://arxiv.org/abs/2604.15034)
> 作者: Wentao Zhang*, Zhe Zhao*, Haibin Wen*, Yingcheng Wu, Cankun Guo, Ming Yin†, Bo An†, Mengdi Wang†
> 机构: NTU, Stanford, Princeton, CityU HK, USTC
> 日期: 2026-04-16 (v4: 2026-05-19)
> 代码: [github.com/DVampire/Autogenesis](https://github.com/DVampire/Autogenesis)
> 分析日期: 2026-06-05

---

## 一句话

AGP 不是进化引擎——是**协议规范**。它定义"agent 内部资源该如何注册、版本化、审计、进化"，填补 MCP/A2A 只管调用不管资源生命周期的空白。

## 双层架构

```
┌──────────────────────────────────────────────────┐
│              AGP (Protocol Spec)                  │
│                                                    │
│  ┌────────────────────────────────────────────┐   │
│  │  SEPL: Self-Evolution Protocol Layer        │   │
│  │  闭环算子接口                                │   │
│  │                                              │   │
│  │  Reflect → Select → Improve → Evaluate → Commit │
│  │  (也可承载 TextGrad / GRPO / Reinforce++)    │   │
│  └──────────────┬─────────────────────────────┘   │
│                 │ 读写                             │
│  ┌──────────────▼─────────────────────────────┐   │
│  │  RSPL: Resource Substrate Protocol Layer    │   │
│  │  资源注册层（被动，不可自修改）               │   │
│  │                                              │   │
│  │  ┌────────┬────────┬──────┬──────┬──────┐  │   │
│  │  │ Prompt │ Agent  │ Tool │ Env  │ Mem  │  │   │
│  │  └────────┴────────┴──────┴──────┴──────┘  │   │
│  │                                              │   │
│  │  基础设施: Model Manager / Version Manager   │   │
│  │           Dynamic Manager / Trace Manager    │   │
│  └────────────────────────────────────────────┘   │
│                                                    │
│  实例化 ↓                                          │
│                                                    │
│  ┌────────────────────────────────────────────┐   │
│  │  AGS: Autogenesis System                    │   │
│  │                                              │   │
│  │  Planning Agent ←→ Agent Bus ←→ Sub-Agents  │   │
│  │       ↓                          ↓           │   │
│  │   plan.md               RSPL 资源注册表      │   │
│  │   (to-do + flowchart +   (prompts/tools/     │   │
│  │    history + result)      agents 版本化)     │   │
│  └────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────┘
```

## 形式化（核心定义）

### RSPL 层

| 符号 | 含义 |
|------|------|
| τ ∈ {Prompt, Agent, Tool, Env, Mem} | 五类资源实体 |
| e_{τ,i} = (name, desc, mapping, evolvability, metadata) | 单个资源实体，evolvability 为 0/1 |
| c_{τ,i} = (e, version, impl, params, exports) | 注册记录：含版本号、实现路径、LLM 可用的导出表示 |
| r_τ = (records, context_mgr, server_interface) | 类型级注册资源：管理平面 + 外部接口 |
| **关键约束** | RSPL 资源是 **passive**——不自带优化逻辑，不可自修改 |

### SEPL 层

| 符号 | 含义 |
|------|------|
| V_evo | 全体可进化变量 = 所有资源实体 ∪ 执行产物 y |
| Θ = {v ∈ V_evo \| g_v = 1} | 可训练参数子空间（由 evolvability mask 控制） |
| f: V_evo × P_in → V_evo' × P_out | SEPL 算子：类型化、可组合 |
| f_n ∘ ... ∘ f_1 | 进化管线：算子串行组合 |

## 五类资源

| 资源类型 | 是什么 | 示例 |
|---------|--------|------|
| **Prompt** | 指令文本 | system prompt、task description |
| **Agent** | 决策策略 | planning agent code、sub-agent 定义 |
| **Tool** | 执行接口 | 本地工具、MCP 工具、agent skills |
| **Env** | 任务/世界动态 | 评测器、沙箱、API 环境 |
| **Mem** | 持久状态 | 对话历史、中间结果、推理轨迹 |

## 核心 Design Decisions

### 1. 协议与实现的分离

AGP 是 spec，AGS 是 instantiations。同一个 AGP 上可以跑不同的进化策略（Reflection / TextGrad / GRPO）。这和 MCP 协议的设计哲学一致——**先定义接口，再各自实现**。

### 2. 资源的被动性（Passivity）

RSPL 资源**不可以自修改**。所有状态变更必须通过 context manager 的受控操作（init/build/update/restore/run）。这是 AGP 与 HyperAgents 和 AEvo 的关键区别——前者把进化逻辑内化到 agent 内部，后者把进化机制放在 harness 里，AGP 把资源和操作完全解耦。

### 3. Evolvability Mask

每个资源实体有一个二进制标记 g_{τ,i} ∈ {0,1}，决定它是否在可训练子空间 Θ 里。这意味着**不是所有资源都能被进化**——可以在注册时锁死关键组件（如 safety checker）。

### 4. 基础设施四件套

| 服务 | 作用 |
|------|------|
| Model Manager | 统一 LLM API，跨 provider 路由+fallback |
| Version Manager | 不可变快照 + lineage，支持 rollback + branching |
| Dynamic Manager | 运行时热替换资源，不重启系统 |
| Trace Manager | 细粒度执行轨迹，用于诊断和回顾优化 |

### 5. Bus 模型（AGS 实例化）

AGS 不靠单体 controller——planning agent 和 sub-agents 都注册到 Agent Bus 上，通过标准化消息通信。sub-agent 并发执行，planning agent 负责收结果 + 重规划。

## 关键结果

### 科学与数学 Benchmarks

| 模型 | GPQA | AIME24 | AIME25 | 策略 |
|------|------|--------|--------|------|
| gemini-3-flash (vanilla) | 88.38 | 83.33 | 83.33 | — |
| gemini-3-flash (PS-Joint-Evo) | **90.40** | **93.33** | **93.33** | Prompt+Solution 联合进化 |
| gpt-4.1 (vanilla) | 65.15 | 23.34 | 20.00 | — |
| gpt-4.1 (PS-Joint-Evo) | 67.67 | **40.00** | **33.33** | 弱模型增益更显著 |

### GAIA（通用 Agent Benchmark）

| 配置 | Validation | Test |
|------|-----------|------|
| Vanilla | 89.70% | 79.07% |
| Agent-Evo | **93.33%** | **89.04%** |
| 最强 baseline | 87.27% (Alita) | 91.69% (openJiuwen*) |

> *openJiuwen 用更强的 backbone model，非协议本身优势。

### Code Agent 自进化（LeetCode 100 题）

| 语言 | Vanilla Pass | +Solution-Evo | 提升 |
|------|-------------|---------------|------|
| Python3 | 79 | 87 | +10.1% |
| C++ | 84 | **99** | +17.9% |
| Java | 84 | **98** | +16.7% |
| Go | 82 | 95 | +15.9% |
| Kotlin | 75 | 95 | +26.7% |

Compile/runtime/answer error 在进化后降到接近零。

## 与 Worker-Bee 的映射

### Worker-Bee 的"写死"不是缺点——是选择

| 维度 | AGP/AGS | Worker-Bee |
|------|---------|------------|
| 抽象层级 | **协议规范**（定义 interface） | **工程系统**（定义 implementation） |
| Agent 复杂度 | Planning agent + 4 种 sub-agent 类型 | **agent 极简**：单一职责，不做重规划 |
| 技能模型 | Tool 是 RSPL 五类资源之一 | **一切皆 skill**：skill 是第一公民 |
| Skill→Tool 关系 | Tool 可以包含 skill | **skill 接 tool 接死**：固定映射，不动态改写 |
| 资源演化 | RSPL 五类资源均可进化 | **只有 skill 层进化**（Darwin Skill），tool 层写死 |
| 版本控制 | RSPL 原生 version lineage + rollback | 无原生版本控制（靠 git） |
| 通信模型 | Agent Bus（标准化消息） | NATS + 文件 mailbox |
| 进化策略 | SEPL 算子代数（可插拔） | WorldBee + Strategic Bee 联合决策 |
| 安全模型 | Version + rollback + evolvability mask | safety.py + audit log |

### 核心差异：协议 vs 惯例

AGP 试图做一个**通用协议规范**——任何人按 RSPL/SEPL 接口实现，就能互相操作。Worker-Bee 走的是另一条路：**用极简惯例取代协议**——agent 极简、一切皆 skill、skill 接 tool 接死。如果 AGP 是 HTTP 规范，Worker-Bee 更像 Unix pipe 哲学——组件简单到不需要规范。

### 可借鉴的点

| AGP 概念 | Worker-Bee 借鉴方向 | 优先级 |
|---------|-------------------|--------|
| RSPL 五类资源抽象 | 把 worker-bee 的资源显式化：Prompt/Agent/Tool 各有注册表 | 中 |
| Evolvability Mask | 给 skill 加 `evolvable: true/false` 标记，锁定核心 safety skill | 高 |
| Version Manager | skill 注册表加版本号 + lineage，支持回滚 | 中 |
| Trace Manager | 增强 WorldBee 的执行轨迹记录，不只是 pheromone | 低 |
| SEPL 算子代数 | Strategic Bee 的决策流程可参考 Reflect→Select→Improve→Evaluate→Commit | 中 |

### 不需要借鉴的

- **Bus 模型**：worker-bee 已经有 NATS，不需要再抽象一层
- **Planning agent 重规划**：和 agent 极简哲学冲突——worker-bee 不要"会规划的胖 agent"
- **五类资源全可进化**：worker-bee 刻意让 tool 层写死，只进化 skill 层——这是架构选择，不是缺失

## 与 AEvo 的关系

| | AEvo | AGP |
|---|------|-----|
| 性质 | 进化**框架** | 进化**协议** |
| 核心操作 | Meta-agent 编辑 Π | SEPL 算子读写 RSPL 资源 |
| 安全机制 | Harness 内的 evaluator 隔离 | 版本化 + rollback + evolvability mask |
| 可组合性 | 单 harness 内 | 协议级互操作 |
| 对 worker-bee 的启发 | WorldBee=Harness, Strategic Bee=Meta-Agent | 资源抽象 + 版本控制 + 安全标记 |

**AGP 和 AEvo 互补**：AGP 定义"资源和进化该长什么样"的规范，AEvo 提供"怎么让 meta-agent 编辑进化机制"的一种具体策略。两者可以叠加——AEvo 的 meta-agent 通过 SEPL 算子接口操作 RSPL 资源。

## 潜在问题

1. **协议重量**：形式化程度高 → 实现门槛高。RSPL 五类资源 + context manager + server interface + SEPL 算子代数 = 大量 boilerplate。
2. **Passivity 约束的实际效果未单独消融**：论文说资源 passive 是核心设计，但没有做"资源可自修改 vs 不可自修改"的对照实验。
3. **Planning Agent 仍是单点**：AGS 的 Bus 模型解耦了 sub-agent，但 planning agent 仍然是唯一能制定 plan.md 的节点。
4. **Env 和 Mem 进化未独立评估**：论文承认这两类资源的进化已实现但未做消融——实际贡献集中在 Prompt/Agent/Tool 三类。
5. **"写死"的代价没讨论**：AGP 假定所有资源都该被版本化管理。但 worker-bee 的经验是：有些东西写死比可进化更稳定。协议应该允许"不可进化"作为一等设计，而不只是用 evolvability mask 关掉。

## Worker-Bee 的差异化定位

| AGP 路径 | Worker-Bee 路径 |
|---------|----------------|
| 协议驱动 → 通用互操作 | 惯例驱动 → 极简可替换 |
| 五类资源抽象 → 统一管理 | 一切皆 skill → skill 接 tool 接死 |
| SEPL 算子代数 → 可插拔进化策略 | WorldBee+Strategic Bee → 双体联合决策 |
| 版本化 + rollback → 安全恢复 | git + safety.py → 外部治理 |
| 目标是**协议标准** | 目标是**蜂群生态** |

**核心判断**：AGP 回答了"如果要做一个通用 self-evolution 协议，它该长什么样"。Worker-Bee 选择不回答这个问题——它回答的是"如果 agent 极简、skill 是第一公民、通信靠 NATS，蜂群该怎么进化"。两条路不冲突，但在"重量 vs 极简"这个轴上，它们是对立的两端。
