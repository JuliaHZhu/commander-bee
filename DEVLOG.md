# Worker Bee 开发笔记

> 从 hermes-lite 到 worker-bee 的完整提交历史，按阶段整理。

---

## 阶段一：地基（2026-05-21）

| 提交 | 改了哪 |
|------|--------|
| `414ce5a` Initial commit: hermes-lite | 项目骨架：agent/loop/protocols/registry，~1,700行 Python |
| `035814e` nanobot-style CLI | setup / ping / 交互式 onboarding |
| `7c7b0ea` Deck architecture | Deck 工具边界——运行时按 skill 需求装配工具集 |
| `c4e9a3d` DESIGN.md | 从 Hermes 好奇心到 Deck 架构的演化文档 |
| `50111a7` 中英文 README 分拆 | 纯 EN + 纯 ZH，不再混写 |
| `d99b54d` minimal README | 只写和 Hermes 的差异 + 快速开始 |

## 阶段二：核心功能（2026-05-21 ~ 05-23）

| 提交 | 改了哪 |
|------|--------|
| `2bbc4a0` TODO Ball Machine + cron + subagent + skills | 四大件集成：任务机、定时调度、子代理、skill 系统（来自 Hermes Curiosity 分支） |
| `6ecf3fe` parallel subagents + cross-validation | agent_delegate_parallel（并行）/ agent_cross_validate（多模型交叉验证） |
| `0f6a31b` allowlist security | 终端白名单 + 确认模型，去掉 Python -c 硬编码，修 SQL 注入 |
| `0adfc0b` critical code audit fixes | 代码审计发现的严重问题批量修复 |
| `2f85508` 212 tests | 首个完整测试套件，100% 通过 |
| `670a54d` gstack integration | 浏览守护进程 + 5 个适配 skill（review/cso/investigate/ship/browse） |
| `3df8eaa` ruff lint | 34 文件全通过 ruff 检查，零违规 |

## 阶段三：Skill 生态建设（2026-05-22 ~ 05-24）

| 提交 | 改了哪 |
|------|--------|
| `b148643` skill authoring guides | mechanism-skill + task-skill 创作器 |
| `58bef1f` creator-is-you skill | 设计指南 + 审查教练 |
| `a6a2589` trigger 审计 | 去重、加 phase 标记、修复重叠 substring |
| `85e5f32` 动态上下文注入 | skill 创作器支持运行时注入 + skill_test 校验 |
| `26efd3e` /goal → /task | 用 tagged session 机制替代指令式 goal |
| `93dc976` strip templates | skill body 抽离模板到 templates/ |
| `3eb8acb` skill_audition CLI | 替代 skill-creating-trainer，CLI 形式 linter |
| `76d485c` podcast_agent.py | NotebookLM 风格脚本生成器 |
| `131928e` NotebookLM x Hermes playbook | 完整工作流文档 |
| `d93c7df` runtime-fault fixes | 损坏恢复、import 隔离、错误语义修复 |
| `99835ee` job supervisor | agent 工作追踪 job board |
| `9687790` supervisor 集成测试 | 完整 job 生命周期测试 |
| `01e8dee` README rewrite | 以 job-supervisor 为核心叙事重写 |

## 阶段四：品牌化（2026-05-24 ~ 05-25）

| 提交 | 改了哪 |
|------|--------|
| `29bcc2e` code-decision-guidelines | 产品规划者的编码决策辅助 skill |
| `9455616` 全英文 trigger | 全球分发，trigger 统一英文 |
| `0fd3b52` hermes-lite → worker-bee | 项目改名 |
| `8006bdf` 补漏 rename | 所有 hermes/hermes-lite 引用改为 worker-bee |
| `ddd2e4b` worker_bee/ namespace | 所有模块打包到 worker_bee/ 下 |
| `b601a08` Bing 搜索 | 从 DuckDuckGo 切换到 Bing |

## 阶段五：蜂群架构（2026-05-26 ~ 06-01）

| 提交 | 改了哪 |
|------|--------|
| `1db8bbd` pip-installable | 可 pip 安装 + 对话就绪 |
| `6e0a4e6` batch handoff + 三 Bee fork | 批量交接 + Aristotle/Architecture/PM Bee |
| `5784cc4` PM Bee 原子组合 | 7 skill 原子化 + 栈编排 |
| `9047f6c` WorldBee | 环境引擎——现实检查 |
| `097c8a2` 清理 | 删除过时代码和孤儿文件 |
| `9c3f04a` Feishu App Bot API | send_message 升级到飞书应用机器人 API |
| `5deb636` 飞书 HTTP webhook | `wb lark --port 8080` 独立机器人 |

## 阶段六：内核升级 + 清理（2026-05-31 ~ 06-05）

| 提交 | 改了哪 |
|------|--------|
| `acf0b6e` sync hermes-lite | 从上游同步安全和协议修复 |
| `15fd673` 采用 hermes-lite kernel | protocols.py + loop.py 原样复用 |
| `401d247` skills 移出 worker_bee/ | 从 worker_bee/skills/ → 仓库根 skills/ |
| `03537de` 批量删除 | 移除 docs/、notebooklm-playbook、cron 旧模块 |
| `7bd56a5` 删除 Bee skills | 移除 architect/aristotle/project-manager/worldbee |
| `cbecbe6` 删除 job_supervisor | 移除旧版 job supervisor，后续用 probe 替代 |

## 阶段七：Job Probe + NATS + CLI（2026-06-05）

| 提交 | 改了哪 |
|------|--------|
| `bcee3a1` job-probe 系统 | 后台监控——扫描 session、检查阈值、自动摘要。木偶绳子系统 |
| `3cc621b` probe 集成 cron | probe_tick 嵌入 cron 调度器 |
| `4eeab19` 上下文限制放宽 | 60→90 轮，probe 阈值 50/55→80/85 |
| `a0e35d2` wb CLI | 统一 job + todo 命令行 |
| `17852ab` agent.md/soul.md 注入 | 启动时注入到 system prompt |
| `2365ab4` NATS swarm | 蜂群通信：tools + skills + listener |
| `ca8ca4f` wb swarm CLI | swarm listen/status 命令 |
| `253128e` workspace 解析 | cron 脚本的工作区边界 |

## 阶段八：Arch 分析 Skills（2026-06-06 ~ 06-07）

| 提交 | 改了哪 |
|------|--------|
| `663180e` arch-atomic-analysis | 原子化→打标签→看统计 |
| `bec2ba6` arch-novel-split + arch-novel-tag | 小说原子切割（场景×主题）+ 引擎标签 Deck 10 张牌 |
| `30ea0e8` 删除 arch-batch-split | 冗余，被 arch-novel-split 覆盖 |
| `bc0cfc4` arch-collection-split | 短篇集拆分（福尔摩斯等），逐篇→novel-split |
| `0bf2173` arch-novel-tag 14 标签 | 10 基础 + 4 对白扩展（矛盾/留白/表演/审讯） |
| `a9e624e` 双 atom 模型 | 道尔（场景×主题）vs 克里斯蒂（对白回合） |

## 阶段九：安全加固（2026-06-14 ~ 06-15）

| 提交 | 改了哪 |
|------|--------|
| `d9a5f8b` 4 层安全护栏 | 文件写拒绝、危险命令硬阻塞、git 自动快照、自我修改锁 |
| `57a61f4` 战术修复 | terminal 加固、跨进程锁、SQL 注入修复 |
| `46002bc` review 修复 | 安全模型优先级、消息截断、线程重复修复、类型注解 |
| `a36f21c` audit fixes | 死代码删除、UUID 循环加边界、审计日志、api_key 校验 |
| `cc46fa5` gstack audit | 审计日志脱敏 + 权限修整、循环错误消毒 |

## 阶段十：飞书/Lark 集成（2026-06-16）

| 提交 | 改了哪 |
|------|--------|
| `7aade17` lark-cli wrapper tool + skill | feishu_lark tool + lark.md skill |
| `7518777` _lark → feishu_lark | 命名清晰化 |
| `695c0ca` 简化 lark tool | 去掉 40 行前缀白名单，改用 config.json 一个布尔值 |
| `c3af0a9` wb lark CLI | who/chats/send——名字直输，不用记 oc_xxx |
| `db9acb6` wb lark inbox | 拉最近消息，同样名字直输 |
| `fd3ab5f` lark skill 拆 4 个 | contact / messaging / drive 场景驱动拆分 |
| `dd20087` five-story factory README | 五层工厂架构 + Skill/Tool/CLI 三层分离文档 |
| `99f756e` trigger-matching 测试 | 3 个 lark skill 的中文触发词测试 |
| `cd5b87d` 收紧写保护 | _READ_SUBCOMMANDS frozenset 白名单 + CLI 精确匹配安全 |
| `946809e` 路径/截断/去重修复 | lark-cli 路径解析、消息截断、读命令去重 |
| `27bd3ec` import/lint/空消息修复 | import 顺序、空消息保护、路径统一 |
| `827dadd` CLI/tool 写保护统一 | CLI 加 lark_allow_write 检查 + 路径 fallback 统一 |

---

## 统计

- **总提交数**: 131
- **时间跨度**: 2026-05-21 ~ 2026-06-16（27 天）
- **当前测试**: 326 passed
- **当前行数**: ~11,600 行 Python
