---
name: create-mechanism-skill
description: Use when creating a skill that requires custom Python tooling, state persistence, or data management. For backend-engine skills like job-probe, swarm-listener, or any stateful tool module.
trigger: create mechanism skill, build system skill, skill with state, custom tool skill, persistent data skill, 创建机制skill, 有状态的skill, 底层skill, 带数据持久化的skill
tools:
  - fs_read_file
  - fs_write_file
  - fs_search_files
  - sys_terminal
  - skill_audition
category: skill-authoring
phase: implement
---

# Create Mechanism Skill

> Phase: **implement** — you have decided to build.
>
> Mechanism skill = custom Python backend + state persistence + config-driven

## Pre-Check

**Needs mechanism skill:**
- Custom logic (not just composing existing tools)
- State survives across sessions
- User-configurable categories / quotas / rules

**Does NOT need mechanism skill (use task skill):**
- Search + summarize
- File read + analyze
- Existing tool composition with no custom logic

## Five-Element Checklist

| Element | Must Answer |
|---------|-------------|
| trigger | User says what? Specific enough? |
| kernel | Core mechanism? Data flow? |
| tech stack | Python tool? JSON state? Config file? |
| input | Tool parameters? Action dispatch? |
| output | Plain text? JSON? Table? |
| composability | Depends on other skills? Cron-callable? |

## Workflow

1. **Design data model** — single-file JSON for state + config. No SQLite, no multiple small files.
2. **Create Python tool** — `tools/<skill_name>.py`. Action dispatch, JSON state, config-driven.
3. **Register import** — add to `main.py` to trigger registry registration.
4. **Write skill markdown** — `skills/<skill_name>.md`. Trigger + tools list + workflow description.

## Reference

See `templates/mechanism-skill-reference.md` for code templates, sizing guidelines, and anti-patterns.
