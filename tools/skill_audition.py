"""skill-audition — IDE-style linter for skill markdown files.

Usage:
    python tools/skill_audition.py <skill_name>      # audit one skill
    python tools/skill_audition.py --all              # audit all skills
    python tools/skill_audition.py <name> --json      # machine-readable output

Validates:
    - Frontmatter (name, description, trigger, tools, category)
    - Trigger quality (no single-word, no too-broad)
    - Tool existence in registry
    - Body structure (non-empty)
    - Trigger conflicts across skills
    - Match simulation (--verbose)
"""
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SKILLS_DIR = Path(__file__).parent.parent / "skills"

# ── Frontmatter parser (delegates to skills.py for consistency) ─────
# Guard for CLI entry: tools/ is not on sys.path when run directly
_sys_path_guard = str(Path(__file__).parent.parent)
if _sys_path_guard not in sys.path:
    sys.path.insert(0, _sys_path_guard)
from agent.skills import _parse_yamlish  # noqa: E402

# ── Import tools to trigger registration (needed for registry check) ─
# When running standalone, tool modules haven't been imported yet, so registry
# is empty. We pre-load all tools/ modules so check_tool_existence() works.
import importlib  # noqa: E402
import pkgutil  # noqa: E402

_tools_dir = str(Path(__file__).parent)
for _, _mod_name, _ in pkgutil.iter_modules([_tools_dir]):
    if not _mod_name.startswith("_"):
        try:
            importlib.import_module(f"tools.{_mod_name}")
        except Exception:
            pass  # silently skip tools that fail to load

def _parse_frontmatter(content: str) -> Tuple[Optional[dict], str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not m:
        return None, content
    meta = _parse_yamlish(m.group(1))
    return meta, content[m.end():].strip()


def _get_triggers(meta: dict) -> List[str]:
    triggers = meta.get("trigger", meta.get("triggers", []))
    if isinstance(triggers, str):
        triggers = [t.strip() for t in triggers.split(",") if t.strip()]
    return triggers


def _get_tools(meta: dict) -> List[str]:
    tools = meta.get("tools", [])
    if isinstance(tools, str):
        tools = [t.strip() for t in tools.split(",") if t.strip()]
    return tools


# ── Checks ──────────────────────────────────────────────────────────

def check_frontmatter(meta: dict) -> List[str]:
    """Return list of frontmatter errors (empty = pass)."""
    errors = []
    required = ["name", "description", "trigger", "tools", "category"]
    for key in required:
        if key not in meta:
            errors.append(f"missing required field: '{key}'")

    name = meta.get("name", "")
    if name:
        if not re.match(r"^[a-z0-9-]+$", name):
            errors.append(f"invalid name '{name}': must be [a-z0-9-]")
        if len(name) > 64:
            errors.append(f"name too long: {len(name)} chars (max 64)")

    desc = meta.get("description", "")
    if desc:
        if len(desc) > 1024:
            errors.append(f"description too long: {len(desc)} chars (max 1024)")
        if not desc.lower().startswith("use when"):
            errors.append("description should start with 'Use when...'")

    triggers = _get_triggers(meta)
    if not triggers:
        errors.append("no triggers defined")
    for t in triggers:
        words = t.split()
        if len(words) < 2 and len(t) < 4:
            errors.append(f"trigger too short: '{t}' (use multi-word)")

    tools = _get_tools(meta)
    if len(tools) > 5:
        errors.append(f"too many tools: {len(tools)} (recommend 2-4)")

    return errors


def check_trigger_conflicts(all_skills: Dict[str, dict]) -> List[str]:
    """Check trigger substring overlaps between different skills."""
    conflicts = []
    skill_triggers = {}
    for name, meta in all_skills.items():
        skill_triggers[name] = [t.lower() for t in _get_triggers(meta)]

    names = sorted(skill_triggers.keys())
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for ta in skill_triggers[a]:
                for tb in skill_triggers[b]:
                    if ta in tb or tb in ta:
                        if ta != tb:
                            conflicts.append(
                                f"trigger overlap: '{a}' → '{ta}'  vs  '{b}' → '{tb}'"
                            )
    return conflicts


def check_tool_existence(tools: List[str]) -> List[str]:
    """Check if declared tools exist in registry. Graceful if no registry."""
    try:
        from agent.registry import registry
        missing = []
        for t in tools:
            if not registry.has_tool(t):
                missing.append(f"tool not in registry: '{t}'")
        return missing
    except ImportError:
        return []  # skip when running standalone without registry


def simulate_matches(all_skills: Dict[str, dict], samples: List[str]) -> Dict[str, List[str]]:
    results = {}
    for sample in samples:
        matched = []
        sample_lower = sample.lower()
        for name, meta in all_skills.items():
            for trig in _get_triggers(meta):
                if trig.lower() in sample_lower:
                    matched.append(name)
                    break
        results[sample] = matched
    return results


# ── Core audit function ─────────────────────────────────────────────

def audit(target: str = "all", verbose: bool = False) -> dict:
    """Audit skill(s). Returns dict with 'errors', 'warnings', 'score', 'details'.

    Args:
        target: skill name (without .md) or "all"
        verbose: include match simulation
    """
    if not SKILLS_DIR.exists():
        return {"errors": ["skills/ directory not found"], "warnings": [], "score": 0, "details": {}}

    # Load all skills
    skill_files = {}
    for path in sorted(SKILLS_DIR.glob("*.md")):
        if path.name.startswith("."):
            continue
        content = path.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(content)
        skill_files[path.stem] = {
            "path": str(path),
            "meta": meta or {},
            "body": body,
            "has_frontmatter": meta is not None,
        }

    if target != "all" and target not in skill_files:
        return {"errors": [f"skill '{target}' not found"], "warnings": [], "score": 0, "details": {}}

    targets = [target] if target != "all" else sorted(skill_files.keys())
    all_skills = {name: data["meta"] for name, data in skill_files.items()}

    all_errors = []
    all_warnings = []
    details = {}

    for name in targets:
        data = skill_files[name]
        errors = []
        warnings = []

        if not data["has_frontmatter"]:
            errors.append("no YAML frontmatter")
            details[name] = {"errors": errors, "warnings": warnings}
            all_errors.append(f"{name}: no frontmatter")
            continue

        meta = data["meta"]

        # Frontmatter checks
        for e in check_frontmatter(meta):
            errors.append(e)
            all_errors.append(f"{name}: {e}")

        # Body check
        if not data["body"]:
            errors.append("body empty")
            all_errors.append(f"{name}: body empty")

        # Tool existence
        tools = _get_tools(meta)
        for e in check_tool_existence(tools):
            errors.append(e)
            all_errors.append(f"{name}: {e}")

        # Phase check (warning)
        if "phase" not in meta:
            warnings.append("no 'phase' field (recommend: design / implement / review)")
            all_warnings.append(f"{name}: no phase")

        details[name] = {"errors": errors, "warnings": warnings}

    # Global trigger conflicts
    for c in check_trigger_conflicts(all_skills):
        all_warnings.append(c)

    # Score (single target: errors only; all: errors + 1 per conflict)
    if target != "all":
        issue_count = sum(len(d["errors"]) for d in details.values())
        score = max(0, 10 - issue_count)
    else:
        issue_count = sum(len(d["errors"]) for d in details.values()) + len(check_trigger_conflicts(all_skills))
        score = max(0, 10 - issue_count)

    result = {
        "errors": all_errors,
        "warnings": all_warnings,
        "score": score,
        "details": details,
        "skills_checked": len(targets),
    }

    if verbose:
        samples = [
            "create mechanism skill",
            "create task skill",
            "audit skill",
            "search something online",
            "review my code",
        ]
        result["match_simulation"] = simulate_matches(all_skills, samples)

    return result


# ── Output formatters ───────────────────────────────────────────────

def format_human(result: dict) -> str:
    """IDE-linter style output."""
    lines = []
    status = "PASS" if result["score"] >= 8 else "WARN" if result["score"] >= 5 else "FAIL"
    lines.append(f"  skill-audition  [{status}]  score={result['score']}/10  files={result['skills_checked']}")

    if result["errors"]:
        lines.append("")
        for e in result["errors"]:
            lines.append(f"  ✗ error  {e}")
    if result["warnings"]:
        for w in result["warnings"]:
            lines.append(f"  ⚠ warn   {w}")

    if "match_simulation" in result:
        lines.append("")
        lines.append("  --- match simulation ---")
        for sample, matched in result["match_simulation"].items():
            mt = ", ".join(matched) if matched else "(none)"
            lines.append(f"  '{sample}' → {mt}")

    lines.append("")
    if result["score"] == 10:
        lines.append("  ✓ all checks passed")
    else:
        lines.append(f"  {len(result['errors'])} error(s), {len(result['warnings'])} warning(s)")
    return "\n".join(lines)


# ── CLI entry point ─────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="skill-audition: linter for skill markdown files")
    parser.add_argument("target", nargs="?", default="all", help="skill name or 'all' (default)")
    parser.add_argument("--verbose", "-v", action="store_true", help="include match simulation")
    parser.add_argument("--json", "-j", action="store_true", help="machine-readable JSON output")
    args = parser.parse_args()

    result = audit(target=args.target, verbose=args.verbose)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_human(result))

    sys.exit(0 if result["score"] >= 8 else 1)


# ── Registry tool registration ──────────────────────────────────────

def skill_audition(target: str = "all", verbose: bool = False) -> str:
    """Validate skill markdown files. Returns human-readable report."""
    result = audit(target=target, verbose=verbose)
    return format_human(result)


# Auto-register when imported
try:
    from agent.registry import registry
    registry.register(
        name="skill_audition",
        description=(
            "Audit skill markdown files for frontmatter errors, trigger conflicts, "
            "tool existence, and body structure. Like an IDE linter for skills."
        ),
        parameters={
            "properties": {
                "target": {
                    "type": "string",
                    "description": 'Skill name (without .md) or "all"',
                    "default": "all",
                },
                "verbose": {
                    "type": "boolean",
                    "description": "Include match simulation",
                    "default": False,
                },
            },
            "required": [],
        },
        handler=skill_audition,
        tags=["skill", "audit", "lint", "validation"],
        category="skill-authoring",
    )
except ImportError:
    pass  # standalone mode, no registry available


if __name__ == "__main__":
    main()
