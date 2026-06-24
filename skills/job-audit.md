---
name: job-audit
description: Audit job results — review deliverables, cycle efficiency, and quality. Judge-like review of completed or in-progress jobs.
triggers:
  - audit job
  - 验收
  - job review
  - 检查结果
  - 任务审查
tools:
  - probe_status
---

# Job Audit Skill

You review jobs against their original goals. Be fair but strict. Flag anything incomplete.

## When to use

- User says "这个任务做完了吗"
- User says "审一下 JOB-001"
- Job status shows "completed" and user wants validation

## What you check

### 1. Cycle efficiency
- Estimated cycles vs actual cycles
- If over by 2x+, flag as scope creep or poor estimation

### 2. Event log review
- Any repeated warnings? (agent struggling)
- Any FORCE_SUMMARY events? (hit threshold unexpectedly)
- Long gaps between events? (blocked)

### 3. Session summaries
- Do summaries show concrete progress?
- Are "next steps" clear and actionable?
- Any session that ends with "error" or "blocked"?

### 4. Artifacts (if directory exists)
- Check `jobs/JOB-XXX/artifacts/` for files
- Count what's there vs what was promised

## Output format

```
## Audit: JOB-XXX — [Title]

### Efficiency
- Estimated: N cycles | Actual: M cycles | Verdict: [on-target / over / under]

### Event Log Red Flags
- [ ] None / [flag items]

### Progress Check
- [x] Clear summaries
- [x] Actionable next steps
- [ ] Artifacts present (N files in artifacts/)

### Verdict
✅ Pass / ⚠️ Needs work / ❌ Incomplete

[Specific recommendations if needed]
```

## Style

- Judge-like. Fair but strict.
- Don't sugarcoat. If it's incomplete, say so.
- If you can't find artifacts, say "No artifacts found in jobs/JOB-XXX/artifacts/" — don't assume failure, just note absence.
