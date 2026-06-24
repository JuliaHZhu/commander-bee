---
name: lark-contact
description: 飞书找人、找群 — 名字与 open_id / chat_id 的解析与匹配
trigger: 找人, 找群, 搜用户, 搜群, 查通讯录, 名字转ID, open_id, chat_id, contact, user, group, 成员
tools:
  - feishu_lark
category: feishu
---

# Lark Contact — 找人找群

所有飞书交互的第一步：**把人名/群名解析成机器 ID**。没有 ID 就无法发消息、无法拉群历史。

## 什么时候触发

- 用户说人名或群名（"发给张三"、"技术群"）
- 用户要查某人的 open_id
- 消息/文件操作的目标不是明确的 `oc_xxx` / `ou_xxx`

## 解析策略

### 1. 用户给了确切 ID
ID 特征：
- 用户 open_id：`ou_` 开头
- 群 chat_id：`oc_` 开头
- 文档 token：`doc_` / `wiki_` 开头

→ 直接用，不需要 search。

### 2. 用户给了名字
→ 先 search，再精确匹配。

**步骤：**
1. `contact +search-user --query "名字"`（找人）或 `im +chat-search --query "名字"`（找群）
2. 看返回结果：
   - **只有一个匹配** → 直接用
   - **有精确匹配**（name 完全相等）→ 用精确匹配项
   - **多个模糊匹配** → 列出前 5 个让用户选，**不要自己猜**
   - **没结果** → 告诉用户搜不到，建议换个关键词

### 3. 重名处理
如果 search 返回多个同名用户：
- 列出姓名 + 部门 + email（如果有）
- 让用户指定："有两个张三，研发部的还是财务部的？"
- **绝不默认选第一个**

## 缓存复用

同一轮对话里，已经解析过的名字→ID 可以记住，不用重复 search。但不要跨 session 假设 ID 还有效。

## 常见组合流程

这些场景本 skill 只负责 ID 解析部分，后续操作由 Deck 根据用户完整意图加载对应 skill：

| 场景 | 你做什么 | 下一步（Deck 决定） |
|------|---------|-------------------|
| "发给张三 hello" | `contact +search-user` 拿 open_id | messaging skill 接手发消息 |
| "看看技术群最近说了什么" | `im +chat-search` 拿 chat_id | messaging skill 接手拉历史 |
| "把文件传给设计组" | `im +chat-search` 拿 chat_id | drive + messaging skill 协作 |

## 约束

- `contact +get-user` 需要已知 user_id/open_id，不要拿名字直接查
- 群名可能变化，search 时允许模糊匹配
- 隐私：不要主动列出全部通讯录，只在用户明确请求时 search
