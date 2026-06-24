---
name: mail-to-job
description: 将蜂群收件箱里的新消息转化为 job，通知用户
trigger: 新消息, 收工单, 收到任务, 查邮件, 处理 inbox, mail to job, 消息转 job
tools:
  - fs_read_file
  - fs_write_file
  - fs_search_files
  - probe_create_job
  - probe_status
category: swarm
---

# Mail → Job 转换协议

读取 `mailbox/inbox/` 里的新消息，为每条消息创建一个 job，然后通知用户。

## 步骤

1. **列出新消息**
   读 `mailbox/inbox/` 目录，按 `sequence` 排序（数字大的在后）

2. **过滤**
   - 跳过 `swarm.heartbeat.*`（心跳不需要转 job）
   - 跳过已处理过的 message_id（检查 `mailbox/jobs/` 下是否已有对应记录）

3. **逐个处理** 每条消息：
   - 用 `probe_create_job` 创建 job
     - title: `蜂群消息: {subject}`
     - description: 消息 data 内容的摘要
   - 写记录到 `mailbox/jobs/{message_id}.json`，包含 job_id 和状态
   - 通知用户: "收到新消息，已创建 job {job_id}: {title}"

4. **移动消息**
   处理完后移入 `mailbox/read/`（不删除，保留 3 个月）

## 约束

- 每次最多处理 20 条消息
- 不要处理自己发出的消息（sender == 自己的 bee_id）
- `swarm.task.*` 消息优先处理（可能是 CommanderBee 派发的工单）
- 如果消息已有 `job_id` 字段，说明已被其他 bee 处理，跳过
