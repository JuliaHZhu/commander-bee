# Design Notes

本目录包含 Worker Bee fork 的设计文档 — 基于同一套核心 shell 的专业化认知工具。

| 文件 | 说明 |
|------|------|
| [01-aristotle-bee.md](01-aristotle-bee.md) | 定义大师 — 术语守护 |
| [02-architecture-bee.md](02-architecture-bee.md) | 结构规约器 — 从模糊想法到不可再分约束 |
| [03-project-manager-bee.md](03-project-manager-bee.md) | 编排优化器 — 现实材料分解与排期 |
| [04-worldbee.md](04-worldbee.md) | 环境引擎 — 现实检查、数据验证 |
| [05-commander-worker-io.md](05-commander-worker-io.md) | CommanderBee + WorkerBee：代理店长与日结工 |
| [06-worldbee-pheromone.md](06-worldbee-pheromone.md) | WorldBee：信息素与全局感知 |
| [07-full-agent-ecosystem.md](07-full-agent-ecosystem.md) | 全 Agent 蜂群：分层架构与双仓库 |
| [exogenous-pheromone-formats.md](exogenous-pheromone-formats.md) | 每个 fork 的外部状态 Markdown 格式 |
| [beebox.md](beebox.md) | 蜂群架构认知轨迹——随分析积累，每次追记 |

## 外部架构研究

[architecture-study/](architecture-study/) — 外部架构论文与系统的对比拆解，用于参考设计和定位 Worker-Bee 的差异化。

| 文件 | 说明 |
|------|------|
| [aevo-harnessing-agentic-evolution.md](architecture-study/aevo-harnessing-agentic-evolution.md) | AEvo: 把进化建模成交互式环境，meta-agent 编辑搜索机制而非产生候选 |
| [autogenesis-self-evolving-agent-protocol.md](architecture-study/autogenesis-self-evolving-agent-protocol.md) | AGP: 双层自进化协议——RSPL 资源注册层 + SEPL 闭环算子层，填补 MCP/A2A 的资源管理空白 |

## 核心架构

见仓库根目录的 [DESIGN.md](../DESIGN.md) — Deck、Registry、Skill 系统、Batch Handoff。
