# Mechanism Skill Reference

> This is a reference document, NOT a skill. It contains detailed templates and patterns for creating mechanism-type skills.
> For the actual skill creation workflow, see `create-mechanism-skill`.

## Pattern: Action-Dispatch Tool

```python
import json
import os
from registry import registry

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "<skill_name>_data")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

def _load_json(path, default=None):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}

def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def <skill_name>(action: str, ...):
    state = _load_json(STATE_FILE, {})
    config = _load_json(CONFIG_FILE, {})
    # ... dispatch logic ...
    _save_json(STATE_FILE, state)
    return result

registry.register(
    name="<skill_name>",
    description="...",
    parameters={...},
    handler=<skill_name>,
    tags=[...],
    category="..."
)
```

## State + Config Layout

```
<skill_name>_data/
  state.json     # runtime state (auto read/write)
  config.json    # user-editable config (categories, quotas, rules)
```

## Config-Driven Example

```json
{
  "categories": ["学习", "工作", "运动"],
  "quotas": {"学习": 21, "工作": 21, "运动": 15}
}
```

## Import Registration

Add to `main.py`:
```python
from tools.<skill_name> import <skill_name>  # noqa: F401
```

## Sizing Guideline

- Python tool: ~100-300 lines
- Skill markdown: ~50-100 lines
- JSON state: single file
- JSON config: single file

## Anti-Patterns

1. Hard-coded categories / quotas → user cannot customize
2. SQLite for simple config → unnecessary complexity
3. Multiple small state files → harder to manage
4. Non-atomic writes → crash corrupts state.json (use temp file + rename)
5. if-elif chains with >5 actions → use dict dispatch instead
