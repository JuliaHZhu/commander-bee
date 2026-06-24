---
name: skill-creator-is-you
description: Use when the user wants to create a skill but has not started writing yet. Guides design decisions before any code or markdown is produced.
trigger: skill构思, 从零设计skill, skill idea, 想写个skill, 要不要做skill, skill规划, skill设计
tools:
  - fs_read_file
  - fs_search_files
  - skill_audition
category: skill-authoring
phase: design
---

# Skill Creator Is You

> Phase: **design** — before writing anything.
>
> You are the designer. I am the mirror.

## Gate 1: Do you actually need a skill?

| Situation | Verdict |
|-----------|---------|
| One-off task, never again | **No skill.** Just do it. |
| Reusable pattern across sessions | **Yes.** Create a task-type skill. |
| Custom logic with state persistence | **Yes.** Create a mechanism-type skill. |
| Unclear if reusable | **No.** Use it three times first, then decide. |

## Gate 2: Mechanism or Task?

| Signal | Type |
|--------|------|
| Needs custom Python, JSON state, user config | **Mechanism** |
| Just composes existing tools | **Task** |

If mechanism → load `create-mechanism-skill`
If task → load `create-task-skill`

## Gate 3: The Five-Element Draft

Answer each in one sentence:

| Element | Question |
|---------|----------|
| trigger | What exact words would the user say? |
| kernel | What is the ONE thing this skill does? |
| input | What does the user hand over? |
| output | What does the user receive back? |
| composability | Which other skills does this one call or get called by? |

If any answer is longer than one sentence, it is too big. Split it.

## Gate 4: Trigger Sanity Check

- Would "help" or "web" accidentally fire this skill? → Too broad.
- Would a normal chat about cooking trigger it? → Too broad.
- Does it contain at least one action verb? (search, review, check, draw) → Good.

## Output

A one-page design brief:
- Name
- Type (mechanism / task)
- Trigger list
- Five-element summary
- First draft of the skill markdown skeleton
