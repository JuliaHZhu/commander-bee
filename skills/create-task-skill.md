---
name: create-task-skill
description: Use when creating a lightweight skill for information retrieval, summarization, or workflow guidance. No custom code needed — just tool composition and prompt design.
trigger: create task skill, lightweight skill, search summary skill, workflow skill, information skill, 创建任务skill, 轻量skill, 搜索总结skill, 工作流skill
tools:
  - fs_read_file
  - fs_write_file
  - fs_search_files
  - skill_audition
category: skill-authoring
phase: implement
---

# Create Task Skill

> Phase: **implement** — you have decided to build.
>
> Task skill = precise trigger + tool composition + fixed workflow + defined output format

## Pre-Check

**Fits task skill:**
- Information retrieval + summarization
- File analysis + recommendation
- Workflow guidance
- Search + formatted output

**Does NOT fit (use mechanism skill):**
- Custom Python logic needed
- State persistence needed
- User-configurable data structures needed

## Five-Element Checklist

| Element | Must Answer |
|---------|-------------|
| trigger | User says what? Concrete or abstract? |
| kernel | Core workflow? Fixed steps? |
| input | What does the user provide? |
| output | Plain text / table / diff / checklist? |
| composability | Recommended pairings with other skills? |

## Workflow

1. **Design trigger** — specific > abstract, multi-word > single-word. Each word triggers independently.
2. **Select tools** — check `registry.list_tools()`. 2-4 tools optimal. Deck adds 3 redundant base tools.
3. **Design workflow** — numbered steps, each names a specific tool and what to do with results.
4. **Define output format** — be explicit in skill body. Format drives consistency.
5. **Write skill markdown** — frontmatter + body. Keep under 100 lines.

## Reference

See `templates/task-skill-reference.md` for trigger patterns, tool selection guide, and anti-patterns.
