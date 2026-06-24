---
name: swarm-send
description: 通过 NATS 向蜂群其他 Worker-bee 发送消息或发起查询
trigger: 通知, 广播, 发给 bee, 问其他 bee, 问一下其他, 蜂群发送, 派发任务, 通知蜂群, swarm publish, 问问别的
tools:
  - swarm_publish
  - swarm_request
  - fs_write_file
category: swarm
---

# 蜂群发送协议

向蜂群中的其他 Worker-bee 发送消息。NATS 负责路由，你只对 subject 说话。

## 模式选择

| 场景 | 用哪个 | subject 示例 |
|------|--------|-------------|
| 通知事件（构建完成） | `swarm_publish` | `swarm.event.deck-done` |
| 派发任务 | `swarm_publish` | `swarm.task.deck-build` |
| 心跳/存活确认 | `swarm_publish` | `swarm.heartbeat.bee-01` |
| 查询信息（等回复） | `swarm_request` | `swarm.query.vector-search` |
| 状态查询 | `swarm_request` | `swarm.query.status` |

## 步骤

1. 确认 subject 格式：`swarm.{类别}.{动作}`
   - 类别：task / event / heartbeat / query / result
   - 只用小写字母、数字、连字符和点
2. 按上表选择 `swarm_publish` 或 `swarm_request`
3. payload 必须可 JSON 序列化（dict，不要嵌套过深）
4. 重要消息同步写 `mailbox/sent/` 留副本（用 fs_write_file）

## 约束

- 不要用 `swarm_request` 发不需要回复的消息（浪费等待）
- `swarm_request` 默认60秒超时，失败自动重试3次，都失败则返回错误告知用户
- `swarm_publish` 是 fire-and-forget，返回成功只代表 NATS 收到，不代表对端处理完
- 每条消息自动包含 message_id + sequence + sender(bee_id) + timestamp
