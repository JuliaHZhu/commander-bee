---
name: lark-drive
description: 飞书文件操作 — 上传、下载、分享，以及和消息的衔接
trigger: 上传文件, 下载文件, 传文件, 分享文档, 云文档, 附件, drive, file, upload, download, 云空间
tools:
  - feishu_lark
category: feishu
---

# Lark Drive — 文件操作

上传、下载、分享。核心是：**文件不是孤立存在的，最终要落到某个人或某个群。**

## 什么时候触发

- "把这个文件传到飞书"
- "把群里的文件下载下来"
- "分享这个文档给团队"
- "上传附件"

## 上传 — 决策流程

### 第 1 步：确认文件路径

- 用户给了本地路径 → 检查文件是否存在
- 用户没说路径 → 问文件在哪

### 第 2 步：确认上传到哪儿

| 目标 | 命令 |
|------|------|
| 个人云空间（默认） | `drive +upload --path /local/file.pdf` |
| 指定文件夹 | `drive +upload --path /local/file.pdf --parent folder_token` |

### 第 3 步：拿到 token 后分享

上传成功会返回 `file_token`。接下来：

| 用户要做什么 | 下一步 |
|-------------|--------|
| "发给张三" | `feishu_lark` 执行 `im +messages-send --file-token xxx` |
| "分享到群里" | `feishu_lark` 执行 `im +messages-send` 带 file-token |
| "只上传，不分享" | 告诉用户上传完成，token 是什么 |

**ponytail:** 当前版本 file_token 的透传方式依赖 lark-cli 具体实现，如果消息发文件失败，退化为发文件链接。

## 下载 — 决策流程

### 用户有 file_token
→ `drive +download --token file_xxx --path /local/dest.pdf`

### 用户在消息里提到文件
→ `feishu_lark` 执行 `im +messages-list` 拉消息历史，从消息体里提取 file_token，再下载。

### 路径确认

- 用户给了保存路径 → 用用户的
- 用户没说 → 默认 `~/Downloads/` 或当前工作目录，先确认再写

## 分享链接

如果用户只要链接、不要发消息：
- `drive +share --token file_xxx`（如果 lark-cli 支持）
- 否则下载后由用户自行处理

## 组合流程

**“把 report.pdf 传给张三”**
1. 确认本地文件存在：`report.pdf`
2. `feishu_lark` 执行 `drive +upload --path report.pdf` → 拿 `file_token`
3. `feishu_lark` 执行 `contact +search-user` → 搜“张三”拿 `open_id`
4. `feishu_lark` 执行 `im +messages-send --user-id ou_xxx --file-token xxx`（或带链接的文本消息）

**“把群里那个 Excel 下载下来”**
1. `feishu_lark` 执行 `im +chat-search` → 搜群名拿 `chat_id`
2. `feishu_lark` 执行 `im +messages-list --chat-id xxx --limit 20` → 找含文件的消息
3. 提取 `file_token`
4. `feishu_lark` 执行 `drive +download --token xxx --path ./download/`

## 约束

- 上传前检查文件大小，超大文件（>100MB）提示可能超时
- 下载时确认目标路径不会覆盖已有文件
- 不要上传敏感/机密文件到公开群，除非用户明确确认
- `lark_allow_write: true` 要求同上
