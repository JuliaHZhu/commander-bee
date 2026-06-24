"""Skill manager — load, match, and inject skill markdown files.

Caches:
  - In-process LRU cache keyed by (path, mtime, size)
  - Disk snapshot .skills_cache.json keyed by mtime/size manifest
"""
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional


def _parse_yamlish(text: str) -> dict:
    """Parse simple YAML frontmatter: scalars and lists only."""
    meta = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("-"):
            i += 1
            continue
        if ":" not in stripped:
            i += 1
            continue
        key, rest = stripped.split(":", 1)
        key = key.strip()
        val = rest.strip()
        if val:
            meta[key] = val
            i += 1
            continue
        j = i + 1
        items = []
        while j < len(lines):
            next_line = lines[j]
            if not next_line.strip():
                j += 1
                continue
            if next_line.strip().startswith("-"):
                item = next_line.strip()[1:].strip()
                items.append(item)
                j += 1
                continue
            break
        if items:
            meta[key] = items
            i = j
        else:
            meta[key] = ""
            i += 1
    return meta


class SkillManager:
    """Load, cache, and match skill markdown files."""

    def __init__(self, skills_dir: str = None):
        if skills_dir is not None:
            self.skills_dir = Path(skills_dir)
        else:
            # Try package-internal skills first (works for pip installs)
            internal = Path(os.path.join(os.path.dirname(__file__), "skills"))
            # Fallback to repo-root skills (editable/dev installs)
            external = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills"))
            if internal.exists() and list(internal.glob("*.md")):
                self.skills_dir = internal
            elif external.exists() and list(external.glob("*.md")):
                self.skills_dir = external
            else:
                self.skills_dir = internal  # default to internal, will create if missing
        self._skills: Dict[str, dict] = {}

        # In-process LRU cache: key=(path_str, mtime_ns, size)
        self._parse_cache: Dict[tuple, dict] = {}
        self._cache_lock = threading.Lock()
        self._cache_max_size = 32

        # Disk snapshot path
        self._snapshot_path = self.skills_dir / ".skills_cache.json"

    def load_all(self) -> list:
        """Load all .md skill files from skills_dir, using cache when valid."""
        loaded = []
        if not self.skills_dir.exists():
            self.skills_dir.mkdir(parents=True, exist_ok=True)
            return loaded

        # Try disk snapshot first
        disk_snapshot = self._load_disk_snapshot()
        if disk_snapshot:
            self._skills = disk_snapshot
            return list(self._skills.keys())

        # Cold path: scan filesystem
        for path in sorted(self.skills_dir.glob("*.md")):
            name = path.stem
            skill = self._load_skill_file(path)
            if skill:
                self._skills[name] = skill
                loaded.append(name)

        # Write disk snapshot for next time
        self._write_disk_snapshot()
        return loaded

    def _load_skill_file(self, path: Path) -> Optional[dict]:
        """Load a single skill file with in-process caching."""
        stat = path.stat()
        cache_key = (str(path), stat.st_mtime_ns, stat.st_size)

        with self._cache_lock:
            cached = self._parse_cache.get(cache_key)
            if cached is not None:
                return cached

        content = path.read_text(encoding="utf-8")
        skill = self._parse_skill(path.stem, content, str(path))

        with self._cache_lock:
            self._parse_cache[cache_key] = skill
            while len(self._parse_cache) > self._cache_max_size:
                self._parse_cache.pop(next(iter(self._parse_cache)))

        return skill

    def _parse_skill(self, name: str, content: str, path: str) -> dict:
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if m:
            frontmatter_text = m.group(1)
            body = content[m.end():].strip()
            meta = _parse_yamlish(frontmatter_text)
        else:
            frontmatter_text = ""
            body = content.strip()
            meta = {}

        tools = meta.get("tools", [])
        if isinstance(tools, str):
            tools = [t.strip() for t in tools.split(",") if t.strip()]

        triggers = meta.get("trigger", meta.get("triggers", ""))
        if isinstance(triggers, str):
            triggers = [t.strip() for t in triggers.split(",") if t.strip()]
        elif isinstance(triggers, list):
            triggers = [str(t).strip() for t in triggers]

        return {
            "name": name,
            "description": meta.get("description", meta.get("name", "")),
            "triggers": triggers,
            "tools": tools,
            "category": meta.get("category", ""),
            "composability": meta.get("composability", ""),
            "input": meta.get("input", ""),
            "output": meta.get("output", ""),
            "_path": path,
            "_frontmatter": frontmatter_text,
            "_body": body,
            "_raw": content,
            "_mtime": Path(path).stat().st_mtime_ns if Path(path).exists() else 0,
            "_size": Path(path).stat().st_size if Path(path).exists() else 0,
        }

    def _build_manifest(self) -> dict:
        """Build a manifest of current skill files: {path: [mtime_ns, size]}."""
        manifest = {}
        for path in sorted(self.skills_dir.glob("*.md")):
            st = path.stat()
            rel = str(path.relative_to(self.skills_dir))
            manifest[rel] = [st.st_mtime_ns, st.st_size]
        return manifest

    def _load_disk_snapshot(self) -> Optional[dict]:
        """Try loading from .skills_cache.json if manifest matches."""
        if not self._snapshot_path.exists():
            return None
        try:
            snapshot = json.loads(self._snapshot_path.read_text(encoding="utf-8"))
            current_manifest = self._build_manifest()
            if snapshot.get("manifest") != current_manifest:
                return None
            skills = {}
            for name, data in snapshot.get("skills", {}).items():
                skills[name] = data
            return skills
        except (json.JSONDecodeError, OSError):
            return None

    def _write_disk_snapshot(self) -> None:
        """Write current skills + manifest to .skills_cache.json."""
        try:
            snapshot = {
                "manifest": self._build_manifest(),
                "skills": self._skills,
                "version": 1,
                "timestamp": time.time(),
            }
            self._snapshot_path.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def invalidate_cache(self) -> None:
        """Clear all caches and remove disk snapshot."""
        with self._cache_lock:
            self._parse_cache.clear()
        self._skills.clear()
        try:
            if self._snapshot_path.exists():
                self._snapshot_path.unlink()
        except OSError:
            pass

    def list_skills(self) -> Dict[str, dict]:
        return {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
                for k, v in self._skills.items()}

    def get_skill(self, name: str) -> Optional[dict]:
        return self._skills.get(name)

    def match_skills(self, user_input: str) -> List[str]:
        matched = []
        ui_lower = user_input.lower()
        for name, meta in self._skills.items():
            for trigger in meta.get("triggers", []):
                if trigger.lower() in ui_lower:
                    matched.append(name)
                    break
        return matched

    def get_tools_for_skills(self, skill_names: List[str]) -> List[str]:
        tools = set()
        for sn in skill_names:
            skill = self._skills.get(sn)
            if skill:
                for t in skill.get("tools", []):
                    tools.add(t)
        return list(tools)

    def build_context_for_skills(self, skill_names: List[str]) -> str:
        parts = []
        for sn in skill_names:
            skill = self._skills.get(sn)
            if not skill:
                continue
            body = skill["_body"]
            snippet = body[:2000]
            if len(body) > 2000:
                snippet += "\n..."
            parts.append(f"## Skill: {sn}\n{snippet}")
        if not parts:
            return ""
        return "Matched Skills:\n" + "\n\n".join(parts)
