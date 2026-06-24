# Task Skill Reference

> This is a reference document, NOT a skill. It contains detailed patterns for creating task-type skills.
> For the actual skill creation workflow, see `create-task-skill`.

## Minimal Skeleton

```yaml
---
name: <skill-name>
description: Use when ...
trigger: ...
tools:
  - tool_a
  - tool_b
category: ...
---

# <Title>

## Workflow

1. Step one
2. Step two
```

> **Note on Input/Output sections**: The sections below are reference format, NOT mandatory. Worker Bee does not perform automatic parameter validation. The skill is a function call protocol — the user is responsible for providing correct parameters.

## Input

- What the user provides

## Output

- What the skill returns
```

## Trigger Design

**Principle: specific > abstract, multi-word > single-word**

```yaml
# ✅ Good: specific, multi-word, hard to misfire
trigger: search, look up, research, find online, what is

# ❌ Bad: too broad
trigger: web

# ✅ Good: action verbs
trigger: review, code review, check code, review this
```

Each word triggers independently via substring match.

## Tool Selection Guide

| Scenario | Tools |
|----------|-------|
| Web research | net_web_search, net_web_extract |
| Code review | fs_read_file, fs_search_files, fs_write_file |
| Release flow | sys_terminal, fs_read_file, fs_search_files |
| Analysis | fs_read_file, fs_search_files |

**Principle: 2-4 tools. Deck auto-adds 3 redundant base tools.**

## Workflow Rules

1. Numbered steps, each names a specific tool
2. Each step states what to do with the result
3. Next step is explicit

**Anti-pattern**: "search, then analyze, then output" (no tool names)

## Output Format

Define in skill body:
```markdown
## Output

- Summary with citations
- Action checklist
- Code diff (if applicable)
```

## Anti-Patterns

1. Trigger too broad → misfires, interferes with normal chat
2. Tool list too long → Deck bloat, context waste
3. Workflow steps vague → LLM improvises, inconsistent results
4. No output format defined → style varies per run
5. Duplicates existing skill → check `skills/` first
6. Description is feature spec → should be trigger condition: "Use when..."
