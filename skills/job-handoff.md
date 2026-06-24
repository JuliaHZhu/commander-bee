---
name: job-handoff
description: Prepare or execute a job handoff — continuation across sessions. Generate handoff package from Job Probe system.
triggers:
  - handoff
  - 续跑
  - 继续任务
  - job continue
  - 接着做
  - 接力
tools:
  - probe_handoff
  - probe_status
---

# Job Handoff Skill

You help the user **continue a job across sessions**. The Job Probe system has already prepared session summaries and tracked progress. You just surface the handoff package.

## When to use

- User says "继续做 JOB-001"
- User says "接着上次的"
- A job hit the 60-round threshold and needs a new session
- User wants to know "上次做到哪了"

## Usage

1. `probe_handoff(job_id="JOB-001")` — generate fresh handoff package
2. `probe_status(job_id="JOB-001")` — read full history if needed

## What you show the user

1. **Job summary** — what was accomplished so far
2. **Key decisions made** — from session summaries
3. **Open todos** — what's still pending
4. **Copy-paste ready opening message** for the next session

### Opening message template

```
Continue JOB-XXX: [one-line summary of where we left off]

Context:
- [key decision 1]
- [key decision 2]

Next: [specific next step]
```

## Style

- Action-oriented. No fluff.
- Give the user a **ready-to-use** opening message. Don't make them think.
- If handoff package is empty or job has no sessions, say so clearly.
