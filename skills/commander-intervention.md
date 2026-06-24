---
name: commander-intervention
description: 处理 Worker Bee 的 blocked 消息
triggers:
  - blocked
  - 卡住了
  - intervention
  - 介入
  - 处理阻塞
tools:
  - fs_read_file
  - fs_write_file
  - swarm_publish
  - send_message
category: commander
---

# Commander Intervention Skill

你负责处理 Worker Bee 的 `blocked` 消息，决定介入策略。这是 **LLM 驱动** 的 Skill。

## 职责

读 Worker 发来的 `swarm.event.blocked`，决定介入策略。

## 输入

Worker Bee 发送的 blocked 消息：

```json
{
  "subject": "swarm.event.blocked",
  "payload": {
    "job_id": "JOB-048",
    "bee_id": "bee-mac",
    "reason": "缺少原文 PDF，无法进行论文拆解",
    "timestamp": "2026-06-24T12:00:00Z"
  }
}
```

## 介入决策（LLM）

读取：
1. **blocked reason**（Worker 报告的原因）
2. **job meta**（任务的 frontmatter 和描述）
3. **当前环境**（是否有其他 Bee 有能力处理？依赖的 job 完成了吗？）

然后判断：

### 1. 重新派发

**适用场景**:
- reason: "Bee 能力不足，需要 hayes-method-reviewer skill"
- 当前 Bee 确实没有这个 skill

**操作**:
- 清空 `owner` → `phase: created`
- 等更强的 Bee 接单

### 2. 等人工

**适用场景**:
- reason: "缺少原文 PDF"
- reason: "acceptance 标准不清晰，无法判断完成"
- reason: "需要人类决策：保留哪个版本"

**操作**:
- `phase: blocked`
- 发消息通知用户（`send_message` 或 NATS）
- 记录到 `events.jsonl`

### 3. 修改 job

**适用场景**:
- reason: "acceptance 标准太宽泛，不知道写多少字"
- reason: "required_skills 字段缺失"

**操作**:
- 建议用户修改 job meta
- 标记 `phase: blocked`

### 4. 自动补救

**适用场景**:
- reason: "依赖的 JOB-046 还没完成"
- reason: "临时文件被清理，重新生成需要 10 分钟"

**操作**:
- 如果依赖 job 已经完成 → 清空 `owner` + `phase: created`（重新派发）
- 如果依赖 job 还没完成 → 等依赖完成后自动重派（设置 Cronjob）

## 输出格式

写入 `commander-jobs/JOB-048/intervention.md`:

```markdown
## 介入记录: JOB-048

### Blocked 原因
缺少原文 PDF，无法进行论文拆解

### 决策
等人工处理

### 理由
原文 PDF 是任务的必要输入，Commander 无法自动获取。已通知用户上传 PDF 到 `artifacts/source.pdf`。

### 后续
用户上传 PDF 后，手动将 job 重置为 `phase: created`，重新派发。

---
Timestamp: 2026-06-24T12:05:00Z
```

同时更新 job `phase`:

- 重新派发 → `phase: created`
- 等人工 → `phase: blocked`
- 修改 job → `phase: blocked`
- 自动补救 → `phase: waiting`（设置 Cronjob 定期检查）

## NATS 通知

介入完成后，发送 NATS 消息：

```json
{
  "subject": "swarm.event.intervention",
  "payload": {
    "job_id": "JOB-048",
    "decision": "wait_human",
    "message": "缺少原文 PDF，已通知用户"
  }
}
```

## 触发方式

- Worker 发送 `swarm.event.blocked` 后自动触发
- 用户手动说"介入 JOB-048"

## 注意事项

- **不要猜测**。如果 blocked reason 模糊，标记为 `reason_unclear`，让用户澄清。
- **不要强行推进**。如果真的需要人工，就等人工，不要绕过问题。
- 记录介入决策，方便后续审查。
