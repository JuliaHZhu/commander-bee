# Worker Bee

> 一个 Agent，一块板。够了。

---

## 一句话

**Worker Bee = Hermes Lite 内核 + 蜂群扩展层。**

保持相同的极简架构 — 注册表、Deck、协议抽象、协议无关循环 — 在此基础上增加了真正需要的东西：session、定时任务、标签、平台感知、NATS 蜂群通信、skill 生态。

不需要 Symphony，不需要多 Agent 编排，不需要 daemon。Agent 自己读板、自己派活、自己留下信息素。人随时打开文件就能看到全貌。

---

## 为什么一个 Agent 就够了

多 Agent 框架的默认假设：任务复杂到需要分工，所以要有 orchestrator、worker pool、agent 间通信协议。

Worker Bee 的假设不同：

> **Agent 自己就是 dispatcher。** Deck 架构已经解决了工具分发 — 每次任务只暴露相关的工具。Agent 不需要"被调度"，它只需要"被激活"。

```
用户说 "搜索论文"
    │
    ▼
trigger 匹配 web-research skill
    │
    ▼
Deck 加载搜索工具
    │
    ▼
Agent 搜索 -> 抽取 -> 汇报 -> 停止
```

Agent 一次只做一件事，但**一件事可以很复杂** — 读多个 job、评估质量、生成报告。复杂不等于需要多个 agent。

---

## 架构：五层工厂

把 Worker Bee 想象成一座五层工厂。每层只做一件事，原料（数据）从下往上流。Agent 住在顶层，它从不操心地下室发生了什么。

```
+────────────────────────────────────────────────┐
│  五层：蜂群装备                          │
│  - NATS 消息总线（跨机器说话）            │
│  - Cron 调度器（后台探头）                │
│  - Job Probe（jobs/ 的巡逻兵）            │
│  - SessionDB（SQLite 持久化）             │
+────────────────────────────────────────────────┘
│  四层：Agent 外壳                        │
│  - 配置加载器（~/.worker-bee/）           │
│  - Schema 缓存 + agent.md/soul.md 注入   │
+────────────────────────────────────────────────┘
│  三层：协议内核（Hermes Lite）            │
│  - protocols.py（Anthropic / OpenAI）     │
│  - loop.py（协议无关对话循环）            │
+────────────────────────────────────────────────┘
│  二层：工具边界（Deck + Registry）        │
│  - registry.py（线程安全工具仓库）        │
│  - deck.py（运行时工具边界）              │
│  - skills.py（Markdown 技能匹配引擎）     │
+────────────────────────────────────────────────┘
│  一层：工具实现                          │
│  - lark.py, file.py, terminal.py, ...    │
│  - 导入即注册。零配置。                   │
+────────────────────────────────────────────────┘
```

**这意味着什么**：如果 Hermes Lite 修复了协议 bug 或新增了一个 provider，Worker Bee 只要复制 `protocols.py` 和 `loop.py` 就能白劫。零合并冲突，零漂移。

---

## 一次请求的生命周期

假设你说：**“发给张三 project 上线了”**

```
用户输入："发给张三 project 上线了"
    │
    ▼
┌─────────────────┐
│ skills.py       │  trigger 匹配："发给"命中 lark-messaging skill
│ （匹配引擎）     │  "张三"也可能命中 lark-contact
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ deck.py         │  采购（Procure）：把 skill 声明的工具压进 Deck
│ （工具边界）     │  lark-messaging 声明：[feishu_lark]
│                 │  + 3 个冗余基础工具（读文件、搜文件、执行 shell）
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ loop.py         │  进入对话循环。LLM 只能看到 Deck 里的工具
│ （对话循环）     │  看不到 cronjob，看不到 swarm_publish
│                 │  只能看到 feishu_lark + 文件操作
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ registry.py     │  LLM 说："用 feishu_lark 执行 contact +search-user --query 张三"
│ （工具分发）     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ tools/lark.py   │  薄执行层：subprocess.run(["lark-cli", ...])
│ （执行引擎）     │  安全门：lark_allow_write？读操作直接过，写操作要开关
└────────┬────────┘
         │
         ▼
    返回结果 -> loop 塞回上下文 -> 继续循环或直接结束
```

**关键洞察**：Deck 是运行时边界。LLM 不可能幻觉出 Deck 里没有的工具。如果一个 skill 没有声明 `swarm_publish`，agent 字面意义上无法调用它 — 不是因为权限错误，而是因为当前上下文中这个工具根本不存在。

---

## Skill / Tool / CLI：三层，零重叠

Worker Bee 强制职责分离。最近的例子是 Lark（飞书）集成：

| 层级 | 文件 | 职责 | 举例 |
|------|------|------|------|
| **Skill** | `skills/lark-*.md` | **WHEN / HOW / WHAT-TO-AVOID** — 教 agent 决策流、边界、反模式 | "发送前先确认目标。对人名，先搜索再匹配；禁止猜 ID。" |
| **Tool** | `tools/lark.py` | **薄执行** — 安全调用 `lark-cli`。一个布尔门 (`lark_allow_write`) | `subprocess.run(["lark-cli", "im", "+messages-send", ...])` |
| **CLI** | `cli.py` | **人类捷径** — 绕过 agent 循环直接执行 | `wb lark send "张三" "上线了"` |

**Skill 从不教命令语法**（那是 Tool schema 的事）。**Tool 从不教决策逻辑**（那是 Skill 的事）。**CLI 是给人类用的，不是给 agent 用的**。

核心公理：**Skill = 推理手册。Tool = 执行引擎。零重复。**

---

## 快速开始

```bash
# 1. 创建虚拟环境（Ubuntu/Debian 必须）
python3 -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate

# 2. 安装
pip install git+https://github.com/JuliaHZhu/worker-bee.git

# 3. 初始化 — 配置 API key
worker-bee setup
# 或直接编辑 ~/.worker-bee/config.json

# 4. 测试模型连通
worker-bee -m "hello"

# 5. 测试渠道（可选）
export FEISHU_WEBHOOK_URL=...
worker-bee -c "hello"

# 6. 启动交互会话
worker-bee
```

没有 daemon，没有 orchestrator。一个 CLI 入口。

**或者用 `wb` 直接执行命令：**

```bash
# Job 管理
wb job create "重构支付模块" "把 Stripe 集成抽成独立 service"
wb job ls
wb job status JOB-001
wb job run JOB-001          # 自动检测 skill，搜索/抽取，写入产出物
wb job tick                 # 手动触发后台 probe

# 蜂群
wb swarm status
wb swarm listen

# 飞书 Lark
wb lark who 张三             # 按名字搜索用户 → open_id
wb lark chats               # 列出最近会话
wb lark send --to 张三 hello # 按人名发消息
wb lark inbox --from 张三   # 拉取最近消息
```

---

## 项目结构

```
worker-bee/
├─── agent/           # 核心 agent + CLI
│   ├─── main.py           # CLI 入口（setup / ping / session / lark）
│   ├─── cli.py            # wb 命令行接口（job + todo + swarm + lark）
│   ├─── agent.py          # Agent 外壳（配置、schema 缓存、agent.md/soul.md 注入）
│   ├─── loop.py           # 协议无关运行循环（Hermes 内核）
│   ├─── protocols.py      # Anthropic / OpenAI 协议适配（Hermes 内核）
│   ├─── registry.py       # 工具注册表（线程安全、LRU 缓存、generation counter）
│   ├─── deck.py           # 工具边界（Deck 装填）
│   ├─── skills.py         # Skill 匹配引擎（Markdown 契约、trigger 匹配）
│   ├─── memory.py         # Session DB（SQLite，持久化）
│   ├─── infra_toolsets.py # 平台检测（Linux / 飞书 / Discord）
│   ├─── lark_cli.py       # 独立飞书 Lark Bot（HTTP webhook）
│   └─── skills/           # Markdown skill 契约
│       ├─── lark-contact.md
│       ├─── lark-messaging.md
│       ├─── lark-drive.md
│       ───── code-review.md
│       ───── swarm-send.md
│       ───── swarm-receive.md
│       ───── ...
├─── tools/                # 工具实现（自动注册到 registry）
│   ├─── lark.py           # 飞书 Lark CLI 封装（feishu_lark 工具）
│   ├─── send_message.py   # 飞书 App Bot API / Webhook / Discord
│   ├─── terminal.py       # 执行 shell 命令
│   ├─── file.py           # 读写/搜索文件
│   ├─── web.py            # 网页搜索/抽取
│   ├─── subagent.py       # 委派子 agent
│   ├─── cronjob.py        # 定时任务管理
│   ├─── job_probe.py      # 后台 job 监控 + probe tick
│   ├─── swarm.py          # NATS 蜂群发布/请求
│   └─── ...
├─── swarm/                # NATS 蜂群通信
│   ├─── server.conf       # NATS 服务配置（单机/集群）
│   └─── listener.py       # 后台监听：NATS → mailbox/inbox/
├─── cron/                 # 后台定时器
│   ├─── scheduler.py      # 每 60s tick 循环（集成 job probe）
│   └─── jobs.py           # Job 定义
├─── jobs/                 # Job 存储（Markdown + YAML frontmatter）
│   └─── JOB-XXX/
│       ├─── meta.md
│       ├─── sessions/
│       └─── artifacts/
│─── tests/                # pytest 测试套件
│─── design_notes/         # 架构设计文档
│─── templates/            # Skill 编写模板 + agent.md/soul.md 示例
```

---

## Text as Model

Job 的真实状态不在内存里，不在数据库里，在 `jobs/JOB-XXX/` 目录的 frontmatter 里。

**人 `cat` 一下就能看懂，LLM 读一遍就能操作，git diff 能追踪变更。**

一个完整的 Job 文件：

```markdown
---
id: JOB-001
title: 重构 auth 模块
owner: agent-001
reviewer: human
skills: [code-review, refactor]
deliverables:
  - auth/sso.py
  - tests/test_sso.py
  - migration_guide.md
acceptance:
  - 向后兼容
  - 测试覆盖率>80%
  - 不改 public API
state: Done
phase: done
created: 2026-05-24T14:00:00Z
updated: 2026-05-24T14:55:00Z
---

## 任务描述
将 SSO 逻辑拆分成独立模块，保持向后兼容。

## 交付物
- [x] auth/sso.py
- [x] tests/test_sso.py
- [x] migration_guide.md

## 验收标准
- [x] 向后兼容
- [x] 测试覆盖率>80%
- [x] 不改 public API

## 事件流 (append-only)

- [14:00] created — state=Todo
- [14:05] checkpoint — phase=confirmed, who=agent-001, note=理解了任务和交付标准
- [14:10] checkpoint — phase=planned, who=agent-001, note=方案：先迁移函数，再补测试
- [14:15] checkpoint — phase=planned, who=human, note=方案通过，执行
- [14:20] state_change — Todo → Running
- [14:30] log — 创建 auth/sso.py
- [14:35] log — 测试通过，覆盖率 85%
- [14:40] self_check — deliverables 3/3, acceptance 3/3
- [14:45] eval — design-alignment: Pass
- [14:50] checkpoint — phase=reviewed, who=human, note=验收通过
- [14:55] checkpoint — phase=done, who=system
- [14:55] state_change — Running → Done
```

**这就是全部。** 没有隐藏状态，没有数据库，没有 ORM。一个 Markdown 文件 = 一个完整的工作记录。

---

## 交付质量四要素

每个 job 天然包含：

| 要素 | 字段 | 含义 |
|------|------|------|
| **What** | `title` + `description` + `skills` | 任务内容和所需能力 |
| **Who** | `owner` + `reviewer` | 责任链：谁执行，谁确认 |
| **Deliverables** | `deliverables` checklist | 交付什么产出物 |
| **Acceptance** | `acceptance` checklist | 质量门槛是什么 |

---

## 七阶段生命周期

```
created → confirmed → planned → executing → self_checked → reviewed → done
```

| Phase | 意思 | 谁确认 | 产出 |
|-------|------|--------|------|
| `created` | 刚创建 | 系统 | job 文件 |
| `confirmed` | 责任人确认理解 | owner | 理解摘要 |
| `planned` | 方案提交并通过 | reviewer | 方案批准 |
| `executing` | 执行中 | owner | 代码/文档 |
| `self_checked` | 责任人自检 | owner | checklist 结果 |
| `reviewed` | 评估人复核 | reviewer | 评估结论 |
| `done` | 归档 | 系统 | 完整历史 |

每个关卡迁移都是 **checkpoint** 事件，记录：谁、什么关卡、什么结论、时间。

---

## 与 Symphony 的区别

| | **Symphony** | **Worker Bee** |
|---|---|---|
| **核心假设** | 任务需要多个 worker 分工 | 一个 agent 可以序列处理多个任务 |
| **调度** | 硬代码 orchestrator（`while/for/sleep`） | agent 自己读板、自己决策 |
| **并发** | 内部管理多个 agent 实例 | 顺序执行，简单可预测 |
| **状态存哪** | 内存 / 数据库 / JSON | **Markdown 文件**（人可读） |
| **人怎么干预** | 改配置重启 | **直接改 job 文件** |
| **形态** | 工厂流水线（自动化） | 工单板（可管理） |

> **Symphony 是"机器自己跟着流水线跑"。Worker Bee 是"机器跟着人的板子走"。**

---

## 还有别的吗？

有。这些是现有的 skill，都走同一套 Deck 架构：

| Skill | 做什么 | Trigger |
|-------|--------|---------|
| **lark-contact** | 人名/群名→ID 解析 | 找人、找群、search user |
| **lark-messaging** | 收发消息 | 发消息、发送、通知、私信、inbox |
| **lark-drive** | 上传/下载/分享文件 | 上传、下载、文件、附件 |
| **code-review** | 代码审查 | code review |
| **job-status** | Job board 监控 | job, status |
| **job-handoff** | 导出 job 状态以保持连续性 | handoff |
| **job-audit** | 审查交付物 vs 验收标准 | audit |
| **web-research** | 网页搜索与内容抽取 | search, research, 搜索 |
| **swarm-send** | 通过 NATS 向蜂群发布/请求 | 通知、广播、派发任务 |
| **swarm-receive** | 读取蜂群消息（从 mailbox） | 收消息、看邮件、check inbox |
| **wiki** | 本地知识库操作 | wiki, note |
| **pm-bee** | 项目管理助手 | plan, schedule, milestone |
| **skill-creator-is-you** | Skill 创作教练 | write skill, create skill |
| **code-decision-guidelines** | 编码决策辅助 | tech decision, stack choice |

添加新 skill 只需要：写一个 `skills/xxx.md` 契约 + 一个 `tools/xxx.py` handler。零核心侵入。

---

## `wb` CLI

`wb` 是直接命令行接口 — 不走 agent 循环，不占上下文窗口，直接执行：

```bash
# Job probe 命令
wb job create "标题" "描述" --cycles 2
wb job ls
wb job status JOB-001
wb job handoff JOB-001
wb job audit JOB-001
wb job run JOB-001          # 自动检测 skill，搜索/抽取，写入产出物
wb job tick                 # 手动触发后台 probe

# 蜂群命令
wb swarm status
wb swarm listen

# 飞书命令
wb lark who 张三
wb lark chats
wb lark send --to 张三 hello
wb lark inbox --from 张三 --limit 10
```

`wb` 和交互式 `worker-bee` 共享同一个 `jobs/` 目录和 `state.db`。自动化用 `wb`，开放交流用 `worker-bee`。

---

## Job Probe 系统

后台监控器定期扫描 `jobs/` ，不需要人去轮询：

```
每 60 秒（cron tick）：
  ├── 扫描 jobs/ 的活跃 job
  ├── 检查 cycle 截止日期
  ├── 提示超期 / 阻塞的 job
  └── 如果达到上下文阈值，触发 handoff
```

Probe 阈值可配置（默认：80 rounds 警告，85 rounds handoff）。

Skill 响应 probe 状态：
- `job-status` → 读取 probe 输出，汇报简洁仪表盘
- `job-handoff` → 导出 job 状态 + 产出物树，保持连续性
- `job-audit` → 审查交付物 vs 验收标准

---

## 蜂群通信（NATS）

不同服务器上的 Worker Bee 通过 NATS 通信 — 一个轻量的 pub/sub 消息总线。每台 bee 连接本地的 NATS server；多台 server 组成集群，消息自动跨服务器路由。

```
Agent 说 "通知蜂群 deck 构建完成"
    │
    ▼
匹配 swarm-send skill → Deck 装填 swarm_publish
    │
    ▼
Agent 调用 swarm_publish("swarm.event.deck-done", payload)
    │
    ▼
NATS 路由 → swarm_listener 后台进程写入 mailbox/inbox/
    │
    ▼
Agent 说 "查收件箱" → swarm-receive skill → 读 mailbox → 分类处理
```

- **发送**：`swarm_publish`（广播，不等回复）或 `swarm_request`（请求回复）
- **接收**：后台 `swarm/listener.py` 订阅 NATS → 写入 `~/.worker-bee/mailbox/inbox/`
- **CLI**：`wb swarm status`（检查状态）、`wb swarm listen`（启动监听）

Agent 不直接 subscribe NATS。它读 mailbox — 和 Job Board 一样：所有状态在文件里。

---

## 批次交接 (Session Handoff)

Session 变长后，不压缩历史，导出 handoff 开新 session：

```bash
# 会话中
> /export
Handoff exported to: ~/.worker-bee/handoffs/a1b2c3d4.md

# 退出时自动导出
> /exit
[Handoff] exported to ~/.worker-bee/handoffs/a1b2c3d4.md
```

新 session 加载：
```bash
worker-bee --continue ~/.worker-bee/handoffs/a1b2c3d4.md
```

Handoff 是工作态快照（Purpose / Completed / Todos / Context / Next Step），不是对话摘要。

---

## 设计笔记

Aristotle Bee、Architecture Bee、Project Manager Bee、WorldBee 等历史 fork 概念，以及完整的 agent 生态系统设计，均存档于 `design_notes/` 。它们说明了同一个内核如何穿上不同的 skill 外衣。

运营规范（信息素格式、mechanism vs task skill 区别）见 `design_notes/exogenous-pheromone-formats.md`。

最近的架构研究：
- **BeeBox**（`design_notes/beebox.md`） — 三个收紧约束，探索 agentic 硬件
- **AEvo**（`design_notes/architecture-study/aevo-harnessing-agentic-evolution.md`） — 利用 agentic 进化
- **Autogenesis**（`design_notes/architecture-study/autogenesis-self-evolving-agent-protocol.md`） — 自我进化的 agent 协议

---

## 设计原则

| 原则 | 含义 |
|-----------|---------|
| **复用内核** | `protocols.py` + `loop.py` 从 Hermes Lite 原样复用。零漂移。 |
| **一个 Agent 就够** | 不要多 Agent，不要 orchestrator，不要 daemon |
| **Text as Model** | 所有状态都在 Markdown 里，人可读、可直接编辑 |
| **Append-Only** | 事件流永不覆盖，历史永不丢失 |
| **Deck 修剪** | 每个任务只暴露相关工具，不越界 |
| **Checkpoint 驱动** | 任务不是 "Todo->Done"；它们是 7 个确认节点 |
| **Skill != Tool** | Skill = 推理手册 (WHEN/HOW/WHAT to avoid)。Tool = 薄执行引擎。零重复。 |

---

## 自定义 Agent（agent.md + soul.md）

想改变 agent 的行为？写两个 Markdown 文件 — 不需要改代码。

```
~/.worker-bee/
├── agent.md    # Agent 行为：规则、偏好、工具使用模式
└── soul.md     # Agent 人设：语气、风格、身份
```

启动时，Worker Bee 读取这两个文件并追加到系统提示词。每个文件都包裹在自己的标题下：

```
--- AGENT.MD ---
[contents of agent.md]

--- SOUL.MD ---
[contents of soul.md]
```

**原理**（来自 `agent/agent.py`）：

```python
def _load_prompt_files() -> str:
    base = Path.home() / ".worker-bee"
    for filename in ("agent.md", "soul.md"):
        path = base / filename
        if path.exists():
            parts.append(f"\n\n--- {filename.upper()} ---\n\n{path.read_text()}")
    return "".join(parts)

# In AIAgent.__init__:
self.system_prompt = f"{base_prompt}{injection}"
```

**结论**：编辑文件 -> agent 行为改变。不需要重启，不需要配置，不需要代码。

---

> 你有一个 Agent。
>
> 你有一块板。
>
> 这两个东西始终在对话。
>
> 你可以随时拍它肩膀问："这个进度怎么样？"
>
> 它会指着板子上的记录给你看。
>
> 这就够了。
