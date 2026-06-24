---
name: lark-messaging
description: 飞书收发消息 — 私聊、群聊、历史消息拉取与摘要
trigger: 发消息, 发给, 发送, 通知, 私信, 群聊, 聊天记录, 最近消息, 看看群里, 回复, messaging, send message, inbox
tools:
  - feishu_lark
category: feishu
---

# Lark Messaging — 收发消息

教 agent 怎么发消息、怎么读消息，以及什么时候该用 CLI  shortcut。

## 什么时候触发

- "通知团队"、"发给张三"、"回复李四"
- "看看群里最近说了什么"、"拉一下聊天记录"
- "摘要一下今天的消息"

## 发消息 — 决策流程

### 第 1 步：确认目标

| 用户表达 | 目标类型 | 你需要先做什么 |
|---------|---------|--------------|
| "发给张三" | 私聊 | `feishu_lark` 执行 `contact +search-user` 拿 open_id |
| "发到技术群" | 群聊 | `feishu_lark` 执行 `im +chat-search` 拿 chat_id |
| "回复这条消息" | 同一会话 | 拿原消息的 chat_id / user_id |

**不知道私聊还是群聊 → 问用户。**

### 第 2 步：选择发送方式

- 普通文字 → `feishu_lark` 执行 `im +messages-send --text "内容"`
- 富文本/卡片 → `feishu_lark` 执行 `im +messages-send --content '{"text":"..."}'`（用户明确要格式时才用）
- 带文件 → 先 `feishu_lark` 执行 `drive +upload` 拿到 token，再发消息带文件

### 第 3 步：内容检查

- 消息超过 2000 字 → 提示用户是否要分段，或改用文档发送
- 包含敏感命令/代码 → 确认用户真的要发
- 发给群且 @所有人 → 确认（避免误操作）

## 收消息 — 决策流程

### 用户有明确 ID
→ `im +messages-list --chat-id oc_xxx --limit N`

### 用户只有名字
→ 优先用 `wb lark inbox` CLI（它内部做了名字解析），或先 `feishu_lark` 执行 `contact +search-user` 拿 ID 再拉消息。

**优先用 CLI：** `wb lark inbox --from 张三 --limit 10`，因为它已经封装了名字→ID 的解析，比 agent 分两步更稳。

### 消息摘要

拉回来的消息列表：
1. 按时间顺序排列（最新的在最后，方便阅读）
2. 每条显示：`[时间] 发送者: 内容前 200 字`
3. 超过 20 条 → 问用户要摘要还是看全部

## 组合流程

**“通知团队项目上线了”**
1. `feishu_lark` 执行 `im +chat-search` → 搜“项目群”拿 chat_id
2. 确认：“发到【项目群】对吗？”
3. `feishu_lark` 执行 `im +messages-send --chat-id xxx --text "项目已上线"`

**“把会议纪要发给参会的人”**
1. 问用户：纪要内容是什么 / 文件在哪
2. 如果是文字 → 直接发；如果是文件 → `feishu_lark` 执行 `drive +upload` 上传后再发
3. `feishu_lark` 执行 `contact +search-user` 确认收件人名单

## 约束

- 发消息是写操作，需要 `lark_allow_write: true`，否则 tool 会拒绝
- 不要在没有确认的情况下发消息给大群
- 历史消息里可能包含敏感信息，不要随意转述给第三方
- 用户说"帮我回一下"但没给内容 → 问用户回复什么
