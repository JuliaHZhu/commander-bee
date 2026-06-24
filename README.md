# Commander Bee

> 监工 · 派发 · 验收 · 协调 — 基于 Worker Bee 五层架构

---

## 一句话

**Commander Bee = Worker Bee + 监工 Skill 集合**

共享相同的五层工厂架构，但专注于蜂群协调：派发任务、验收成果、监控心跳、介入阻塞。

---

## 核心定位

Commander Bee 是一个**完整的 Worker Bee**，不是独立框架。通过不同的 Skill 集合和 Cronjob 配置，实现监工职能：

| 维度 | Worker Bee | Commander Bee |
|------|-----------|---------------|
| 架构 | 五层工厂 | 五层工厂（复用） |
| 配置目录 | `~/.worker-bee/` | `~/.commander-bee/` |
| 主要职能 | 执行任务 | 派发任务 + 验收成果 |
| LLM 用途 | 推理 + 工具调用 | 验收判断 + 汇总汇报 |
| NATS 角色 | 接收 `swarm.task.*` | 发送 `swarm.task.*` |
| Skill 集合 | lark-messaging, code-review... | commander-dispatch, commander-acceptance... |

---

## 架构：五层工厂（与 Worker Bee 完全相同）

```
五层：蜂群装备（NATS + Cron + Job Probe + SessionDB）
  ↓
四层：Agent 外壳（~/.commander-bee/ 配置）
  ↓
三层：协议内核（protocols.py + loop.py）
  ↓
二层：工具边界（Deck + Registry + Skills）
  ↓
一层：工具实现（swarm, file, terminal...）
```

---

## 专属 Skill 清单

1. **commander-dispatch** — 派发任务到 Worker Bee 蜂群
2. **commander-monitor** — 监控 Bee 心跳和 job 超时
3. **commander-acceptance** — 验收 Worker Bee 提交的成果（LLM）
4. **commander-report** — 汇总蜂群状态，生成人类可读报告（LLM）
5. **commander-intervention** — 处理 Worker Bee 的 blocked 消息（LLM）

---

## LLM 使用边界

Commander Bee 是**规则为主、LLM 为辅**：

| 场景 | 用什么 | 示例 |
|------|--------|------|
| Skill 匹配 | 纯规则 | `required_skills: [hayes-method]` → 查 `bees.json` |
| Bee 筛选 | 纯规则 | `status=alive + current_jobs < max_concurrent` |
| 超时回收 | 纯规则 | `job_accept 超时` → 清空 owner |
| 成果验收 | **LLM** | 读 `acceptance` 标准 + artifacts → 判断是否合格 |
| 多任务汇总 | **LLM** | 100 个 job → 生成周报 |
| blocked 介入 | **LLM** | Worker 说"缺 PDF" → 判断：重派/等人工/修改 job |
| 字数硬阈值 | 纯规则 | 字数 < 一半 → 自动重派（不问 LLM） |

**分界线：**凡是能写成 `if-else` 的，用规则。凡是需要"理解语义"的，用 LLM。

---

## Cronjob 配置

Commander Bee 依赖 Cronjob 实现自动化监控：

```json
{
  "heartbeat-monitor": "every 60s",   // 检查 Bee 心跳
  "dispatch-scan": "every 120s",      // 扫描 created job 自动派发
  "timeout-check": "every 300s",      // 检查超时 job 介入回收
  "daily-report": "0 9 * * *"         // 每日周报
}
```

---

## NATS 消息协议

| 方向 | subject | payload | 用途 |
|------|---------|---------|------|
| CB → WB | `swarm.task.new-job` | `{job_id, owner, meta_path}` | 派发新任务 |
| CB → WB | `swarm.command.rescind` | `{job_id, reason}` | 超时回收 |
| WB → CB | `swarm.event.job-started` | `{job_id, bee_id}` | Worker 开始干活 |
| WB → CB | `swarm.event.job-done` | `{job_id, bee_id, summary}` | Worker 完成任务 |
| WB → CB | `swarm.event.blocked` | `{job_id, bee_id, reason}` | Worker 遇到阻塞 |
| WB → CB | `swarm.heartbeat.<bee-id>` | `{status, current_jobs, skills}` | 心跳 + 能力上报 |

---

## 目录结构

```
~/.commander-bee/
├── config.json              # 同 Worker Bee 格式
├── agent.md                 # 监工人格
├── soul.md                  # 公正裁判语气
├── bees.json                # Bee 名录（心跳自动维护）
├── commander-jobs/          # 派单池
│   ├── JOB-047/
│   │   ├── meta.md          # frontmatter: required_skills, acceptance...
│   │   ├── events.jsonl     # 派发/回收/介入记录
│   │   └── artifacts/       # Worker 交付物
│   └── JOB-048/
├── cron/
│   └── jobs.json            # Cronjob 配置
└── mailbox/
    ├── inbox/               # NATS listener 写入
    └── sent/                # 发出的重要消息副本
```

---

## 快速开始

```bash
# 1. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 2. 安装
pip install -e .

# 3. 初始化配置
commander-bee setup

# 4. 启动 NATS listener（后台）
python swarm/listener.py &

# 5. 启动 Commander Bee（交互式）
commander-bee

# 6. 或者让 Cronjob 自动运行
commander-bee cron start
```

---

## 实施路径

### Phase 1: 最小可用版本（MVP）
- [x] 复制 Worker Bee 架构
- [ ] 写 3 个 Skill: `commander-dispatch`, `commander-monitor`, `commander-acceptance`
- [ ] 实现 `bees.json` 心跳注册逻辑
- [ ] 配置 2 个 Cronjob: 心跳监控 + 派发扫描
- [ ] 手动测试：创建 job → Commander 派发 → Worker 执行 → Commander 验收

### Phase 2: 自动化介入
- [ ] 实现 `commander-intervention` Skill
- [ ] 超时回收逻辑（job_accept / job_execute）
- [ ] blocked 消息处理

### Phase 3: 人类友好界面
- [ ] 实现 `commander-report` Skill
- [ ] 每日周报 Cronjob
- [ ] Web dashboard（可选，后期）

### Phase 4: WorldBee 接管
- [ ] WorldBee 负责 job 文件的物理投放
- [ ] CommanderBee 只发敲门铃（subject + job_id）
- [ ] 信息素驱动的自动派发

---

## 关键设计原则

| 原则 | 含义 |
|------|------|
| **架构复用** | CommanderBee = Worker Bee + 不同的 Skill 集合 |
| **规则为主** | 能写 if-else 的不用 LLM |
| **LLM 为辅** | 验收、汇总、介入决策用 LLM |
| **唯一派单口** | 只有 Commander 能发 `swarm.task.new-job` |
| **Cronjob 驱动** | 不需要 daemon，用 Cronjob 周期性唤醒 |
| **Markdown 状态** | 所有状态在文件里，人可读可编辑 |
| **NATS 解耦** | Commander 和 Worker 只通过 NATS 通信 |

---

## 与 Worker Bee 的关系

Commander Bee 不是 Worker Bee 的替代品，而是**协同工作的角色分工**：

- **Worker Bee** — 日结工，接单干活，容器销毁后记忆归零
- **Commander Bee** — 代理店长，派发任务、验收成果、维护手册墙

人类是顾客，只看柜台（交付仓库）。蜂群基础设施是 Bee 们自己的"车间"，顾客不进车间。

---

## 文档

完整设计文档：[CommanderBee 完整设计 v2](https://github.com/JuliaHZhu/commander-bee/wiki)

---

## License

MIT License — 同 Worker Bee

---

## 致谢

基于 [Worker Bee](https://github.com/JuliaHZhu/worker-bee) 架构构建。
