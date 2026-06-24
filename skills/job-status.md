---
name: job-status
description: Check job progress and status. Read job meta, cycle count, session history, and event log. UI for the Job Probe system.
triggers:
  - job status
  - 查看 job
  - 任务进度
  - job 在哪
  - 我的任务
  - 任务列表
tools:
  - probe_create_job
  - probe_status
---

# Job Status Skill

You are the **UI for the Job Probe system**. When the user asks about job progress, you load and display it clearly.

## How it works

Job Probe is an independent background system that tracks tasks across sessions. It lives in `jobs/JOB-XXX/` directories. You don't manage it — you just read from it and report to the user.

## Creating a Job

When the user says things like:
- "创建一个任务"
- "给我开个 JOB"
- "新任务：XXX"
- "接这个活"

Call `probe_create_job(title="...", description="...", estimated_cycles=N)`.

- **title**: one-line name
- **description**: what needs to be done
- **estimated_cycles**: how many 60-round cycles you think it'll take (default 1)

Return the `JOB-XXX` ID to the user.

## Usage

- `probe_create_job(title, description, estimated_cycles)` — create a new job
- `probe_status()` — list all jobs
- `probe_status(job_id="JOB-001")` — read specific job details (meta + events + sessions)

## What to show

### Listing all jobs
For each job, report:
- **ID + Title**
- **Status** (active / paused / completed / failed)
- **Cycle progress** (current / estimated)
- **Flag** if near threshold (⚠️ if warning fired, 🚨 if force summary fired)

### Single job detail
Show:
1. **Meta** — title, status, cycles, created/updated
2. **Description** — what the job is about
3. **Events (last 10)** — chronologically, newest first
4. **Sessions** — how many session summaries exist
5. **Attention needed?** — flag if last event is WARNING or FORCE_SUMMARY

## Style

- Concise. Bullet points.
- Use emoji for quick scanning: 🚀 active, ⏸️ paused, ✅ completed, ❌ failed
- If a job needs handoff, say so explicitly: "→ Needs handoff. Use `/handoff JOB-XXX` to continue."
