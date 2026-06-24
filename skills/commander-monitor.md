---
name: commander-monitor
description: 监控 Bee 心跳和 job 超时
triggers:
  - 监控
  - check status
  - monitor bees
  - 检查心跳
tools:
  - fs_read_file
  - fs_write_file
  - swarm_publish
category: commander
---

# Commander Monitor Skill

你负责监控 Bee 心跳和 job 超时。纯规则驱动，不需要 LLM 判断。

## 职责

扫描 `bees.json` + `commander-jobs/`，检测超时和阻塞。

## 检测规则

### 1. Bee 心跳超时（默认 2 分钟）

```
if (now - last_heartbeat) > 120s:
    status = "silent"
    if current_jobs > 0:
        # 回收 job：清空 owner
        for job_id in assigned_jobs:
            job.owner = null
            job.phase = "created"
            log_event("job_recovered", job_id, "bee_silent")
```

### 2. Job accept 超时（默认 10 分钟）

```
if job.phase == "dispatched" and (now - dispatched_at) > 600s:
    # Worker 可能收不到消息或停机
    job.owner = null
    job.phase = "created"
    log_event("accept_timeout", job_id)
```

### 3. Job execute 超时（默认 4 小时）

```
if job.phase == "executing" and (now - started_at) > 14400s:
    # Worker 可能卡住了
    swarm_publish("swarm.command.rescind", {
        "job_id": job_id,
        "reason": "execute_timeout"
    })
    log_event("execute_timeout", job_id)
```

## 输出格式

每次扫描后，写入 `~/.commander-bee/monitor.log`:

```json
{
  "timestamp": "2026-06-24T12:00:00Z",
  "bees_alive": 3,
  "bees_silent": 1,
  "jobs_recovered": 2,
  "jobs_timeout": 0
}
```

## 触发方式

Cronjob 每 60 秒自动运行。

## 注意事项

- **不要问 LLM**。这是纯规则引擎。
- 超时阈值可以在 `~/.commander-bee/config.json` 配置。
- 回收 job 时，记得清空 `owner` 和 `phase`。
