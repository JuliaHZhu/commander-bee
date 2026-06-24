---
name: commander-report
description: 汇总蜂群状态，生成人类可读报告
triggers:
  - 汇报
  - 周报
  - status report
  - 看看进度
  - 蜂群状态
tools:
  - fs_read_file
  - fs_search_files
category: commander
---

# Commander Report Skill

你负责汇总蜂群状态，生成人类可读的报告。这是 **LLM 驱动** 的 Skill。

## 职责

读 `bees.json` + `commander-jobs/` 所有 job，生成汇总报告。

## 报告格式

### 蜂群状态
- **在线 Bee**: N 台（bee-mac, bee-linux...）
- **繁忙 Bee**: M 台（正在执行任务）
- **离线 Bee**: K 台（心跳超时 > 2 分钟）

### 任务进度
- **待派发**: X 个（phase: created）
- **执行中**: Y 个（phase: executing）
- **已完成**: Z 个（phase: done）
- **阻塞中**: W 个（phase: blocked）
- **待修改**: V 个（phase: revision）

### 最近完成（Top 5）
按完成时间倒序，列出最近完成的 5 个任务：

```
- JOB-047: 拆解论文 #047 · ✅ 2026-06-24 12:30 · bee-mac
- JOB-046: 战略案例 #046 · ✅ 2026-06-24 10:15 · bee-linux
- ...
```

### 需要注意
如果有异常情况，列出来：

```
- JOB-048: 超时 4 小时，已介入回收
- bee-linux: 心跳丢失 10 分钟，可能停机
- JOB-049: blocked 原因 "缺原文 PDF"，需人工处理
```

### 效率统计
计算今日/本周的效率指标：

- **平均完成时间**: 从 dispatched 到 done 的平均时长
- **成功率**: Pass 数量 / 总完成数量
- **最繁忙 Bee**: 完成任务最多的 Bee

## 示例输出

```markdown
## 蜂群状态报告
**生成时间**: 2026-06-24 18:00

### 蜂群状态
- 在线 Bee: 3 台（bee-mac, bee-linux, bee-cloud）
- 繁忙 Bee: 1 台（bee-mac 正在执行 JOB-050）
- 离线 Bee: 0 台

### 任务进度
- 待派发: 5 个
- 执行中: 1 个
- 已完成: 47 个
- 阻塞中: 2 个
- 待修改: 1 个

### 最近完成（Top 5）
- JOB-047: 拆解论文 #047 · ✅ 2026-06-24 12:30 · bee-mac
- JOB-046: 战略案例 #046 · ✅ 2026-06-24 10:15 · bee-linux
- JOB-045: 直觉泵分析 · ✅ 2026-06-23 22:00 · bee-mac
- JOB-044: 量表整理 · ✅ 2026-06-23 18:30 · bee-cloud
- JOB-043: 课程拆分 · ✅ 2026-06-23 15:00 · bee-mac

### 需要注意
- JOB-049: blocked 原因 "缺原文 PDF"，已通知用户
- JOB-051: revision 状态，等 Worker 补充博弈还原

### 效率统计
- 平均完成时间: 2.3 小时
- 成功率: 89%（42 Pass / 47 完成）
- 最繁忙 Bee: bee-mac（23 个任务）
```

## 触发方式

- **用户问"看看进度"** → 即时生成
- **Cronjob 每天 9:00** 自动发送周报

## 注意事项

- **简洁直接**。人类想快速了解全局，不要冗长分析。
- 如果没有异常，"需要注意"部分可以省略。
- 效率统计只计算最近 24 小时或 7 天，不要算全部历史。
