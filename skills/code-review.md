---
name: code-review
description: Review code for quality, bugs, and style issues
trigger: review, code review, check code, review this, look at this code
tools:
  - fs_read_file
  - fs_search_files
  - fs_write_file
category: development
---

# Code Review Skill

When the user asks to review code:

1. Read the relevant file(s) with `fs_read_file`
2. Search for related files if needed with `fs_search_files`
3. Analyze for:
   - Bugs and logic errors
   - Style consistency
   - Performance issues
   - Security concerns
4. Provide specific line-by-line feedback
5. If appropriate, suggest a fixed version using `fs_write_file`

## Input
- File path(s) to review
- Specific concerns (optional)

## Output
- Written review with actionable suggestions
- Fixed code file (if user agrees)
