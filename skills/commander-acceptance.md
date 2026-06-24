---
name: commander-acceptance
description: 验收 Worker Bee 提交的成果
triggers:
  - 验收
  - 审查结果
  - check deliverables
  - 检查成果
tools:
  - fs_read_file
  - fs_search_files
  - swarm_publish
  - fs_write_file
category: commander
---

# Commander Acceptance Skill

你负责验收 Worker Bee 提交的成果。这是 **LLM 驱动** 的 Skill。

## 职责

读 job 的 `acceptance` 标准，检查 Worker 提交的 artifacts，判断是否合格。

## 验收步骤

### 1. 读取标准

从 job `meta.md` 的 frontmatter 读取 `acceptance` 字段：

```yaml
acceptance: |
  三页互链完整（lesson.html + notes.html + 博弈还原.html）
  论证链清晰，独立解读与原文分离
  lesson 页包含主旨 + 写作手法 + 论证结构
```

### 2. 检查文件

列出 `commander-jobs/JOB-047/artifacts/` 目录下的所有文件：

```bash
ls -la commander-jobs/JOB-047/artifacts/
```

### 3. 读取关键文件

读取提交的核心文件（如 `lesson.html`, `notes.html`, `博弈还原.html`）。

### 4. 判断合格性

根据 `acceptance` 标准，判断：

- ✅ **Pass**: 完全符合 acceptance 标准
- ⚠️ **Needs work**: 缺少部分内容，可补救（给出具体建议）
- ❌ **Incomplete**: 严重不符，需重做

## 硬阈值（不问 LLM，直接判断）

在读文件之前，先检查硬阈值：

- **字数 < 一半** → 自动 ❌ + 重派
- **文件缺失**（约定 3 个文件，只有 1 个）→ 自动 ❌

如果硬阈值不通过，不需要读文件内容，直接标记为 `Incomplete`。

## 输出格式

写入 `commander-jobs/JOB-047/review.md`:

```markdown
## 验收报告: JOB-047

### 文件清单
- [x] lesson.html (3,200 字)
- [x] notes.html (1,800 字)
- [ ] 博弈还原.html (缺失)

### 判断
⚠️ Needs work

### 理由
- lesson 页内容完整，主旨和论证结构清晰
- notes 页论证链完整，但独立解读部分较少
- **缺少博弈还原.html**

### 建议
补充博弈还原.html，按照五工具链流水线完整分析。

---
Reviewer: CommanderBee  
Timestamp: 2026-06-24T12:00:00Z
```

同时更新 job `phase`:

- ✅ Pass → `phase: done`
- ⚠️ Needs work → `phase: revision`（Worker 会收到通知）
- ❌ Incomplete → `phase: failed`（重新派发）

## NATS 通知

验收完成后，发送 NATS 消息：

```json
{
  "subject": "swarm.event.job-reviewed",
  "payload": {
    "job_id": "JOB-047",
    "verdict": "needs_work",
    "suggestions": "补充博弈还原.html"
  }
}
```

## 触发方式

- Worker 发送 `swarm.event.job-done` 后自动触发
- 用户手动说"验收 JOB-047"

## 注意事项

- **公正但严格**。不要因为 Worker 干了很久就放水。
- 如果标准不清晰，标记为 `acceptance_unclear`，让人类修改 job。
- 记录验收理由，让 Worker 知道为什么没通过。
