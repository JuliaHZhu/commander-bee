---
name: commander-dispatch
description: 派发任务到 Worker Bee 蜂群
triggers:
  - 派发
  - 分配任务
  - dispatch job
  - 分配给
tools:
  - fs_read_file
  - swarm_publish
  - fs_write_file
category: commander
---

# Commander Dispatch Skill

你负责把 `commander-jobs/` 里的任务派发给合适的 Worker Bee。

## 职责

读取 `commander-jobs/` 下的 `created` 状态 job，匹配 Bee 能力，派发。

## 派发规则（纯规则引擎，不用 LLM 猜测）

1. **读 job frontmatter**: `required_skills`
2. **读 bees.json**: 筛选 `skills` 包含 required_skills 的 Bee
3. **筛选在线 Bee**: `status=alive + current_jobs < max_concurrent`
4. **优先级排序**: `last_heartbeat` 最近的（最近活跃优先）
5. **派发**:
   - 写入 job `owner: bee-mac` + `phase: dispatched`
   - NATS 发送 `swarm.task.new-job`:
     ```json
     {
       "job_id": "JOB-047",
       "owner": "bee-mac",
       "meta_path": "~/.commander-bee/commander-jobs/JOB-047/meta.md"
     }
     ```

## 无匹配时

**不要强行派发。** 留在 `created`，等人加 Bee 或加 skill。

记录到 `events.jsonl`:
```json
{
  "timestamp": "2026-06-24T12:00:00Z",
  "event": "dispatch_failed",
  "reason": "no_matching_bee",
  "required_skills": ["hayes-method-reviewer"]
}
```

## 注意事项

- 不要猜测 Bee 能力。只根据 `bees.json` 的 `skills` 字段判断。
- 不要一次派发多个 Bee。一个 job 只派发给一个 Bee。
- 如果 Bee 心跳超时（`last_heartbeat` > 2 分钟），不派发给它。

## 触发方式

- Cronjob 每 120 秒自动运行
- 用户手动说"派发 JOB-047"
