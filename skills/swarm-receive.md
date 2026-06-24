---
name: swarm-receive
description: 读取蜂群发来的消息（从 mailbox/inbox/），分类处理
trigger: 收消息, 看消息, 蜂群消息, 收件箱, 有没有新消息, 检查邮件, check inbox, check mailbox
tools:
  - fs_read_file
  - fs_write_file
category: swarm
---

# 蜂群接收协议

蜂群消息由 `swarm_listener` 后台进程写入 `mailbox/inbox/`。你来读取和处理。

## 步骤

1. **列出新消息**
   读 `mailbox/inbox/` 目录，按文件名排序（时间戳在文件名里）

2. **逐个处理**（每次最多处理 20 条，防 token 爆炸）
   每条消息是 JSON：`{subject, reply_to, data, timestamp, sender}`

3. **按 subject 前缀分类处理**：

   | subject 前缀 | 含义 | 处理方式 |
   |-------------|------|---------|
   | `swarm.task.*` | 任务派发 | 检查 data.owner，是给自己则执行 |
   | `swarm.event.*` | 事件通知 | 提取摘要，通知用户 |
   | `swarm.heartbeat.*` | 心跳 | 更新存活记录（可跳过） |
   | `swarm.result.*` | 任务结果 | 关联到对应 job，记录完成 |
   | `swarm.query.*` | 查询请求 | 忽略——走 request/reply，不经过 mailbox |
   | 其他 | 未知 | 报告用户，不做处理 |

4. **处理完的消息移动**
   用 `fs_write_file` 写到 `mailbox/read/`，然后手动删除 inbox 原文件（或依赖后续 cron 清理）

## 约束

- 只在 inbox/ 里读，不要读 read/（已处理过的）
- 一次不要处理超过 20 条——超过时告诉用户"还有 N 条未读"
- 不要删除消息——移动或保留
- 处理间隔建议 5 分钟以上，不要每次对话都检查
