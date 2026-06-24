import datetime
import fnmatch
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from worker_bee.registry import registry
from worker_bee.safety import is_write_denied, is_self_modify_target

# Re-export for backward-compat with tests
_is_sensitive = is_write_denied


# ── Snapshot / Rollback ─────────────────────────────────────────────

_SNAPSHOT_DIR = Path.home() / ".worker-bee" / "snapshots"
_SNAPSHOT_MAX = 5  # ponytail: keep last 5 versions. Ceiling: O(N) rotation, N small.


def _snapshot_path(path: str, idx: int = 0) -> Path:
    """Return the snapshot file path for a given target file.

    idx=0      -> most recent (.bak.0)
    idx>0      -> older versions (.bak.1, .bak.2, ...)
    idx=-1     -> legacy flat .bak (backward compat)
    """
    key = Path(path).expanduser().resolve().as_posix()
    h = hashlib.sha256(key.encode()).hexdigest()[:16]
    if idx < 0:
        return _SNAPSHOT_DIR / f"{h}.bak"
    return _SNAPSHOT_DIR / f"{h}.bak.{idx}"


def _update_meta(path: str, h: str) -> None:
    """Update the metadata JSON describing all snapshots for a file."""
    meta_path = _SNAPSHOT_DIR / f"{h}.meta"
    abs_path = str(Path(path).expanduser().resolve())
    snapshots = []

    for i in range(_SNAPSHOT_MAX):
        snap = _SNAPSHOT_DIR / f"{h}.bak.{i}"
        if snap.exists():
            stat = snap.stat()
            snapshots.append({
                "idx": i,
                "timestamp": datetime.datetime.fromtimestamp(
                    stat.st_mtime, tz=datetime.timezone.utc
                ).isoformat(),
                "size": stat.st_size,
            })

    data = {
        "path": abs_path,
        "snapshots": snapshots,
    }
    meta_path.write_text(json.dumps(data, indent=2))


def save_snapshot(path: str) -> None:
    """Save a snapshot of the file before overwriting. No-op if file doesn't exist."""
    src = Path(path).expanduser()
    if not src.exists():
        return
    _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    h = hashlib.sha256(
        Path(path).expanduser().resolve().as_posix().encode()
    ).hexdigest()[:16]

    # Rotate existing indexed snapshots: .bak.3 -> .bak.4, ..., .bak.0 -> .bak.1
    for i in range(_SNAPSHOT_MAX - 2, -1, -1):
        old = _SNAPSHOT_DIR / f"{h}.bak.{i}"
        if old.exists():
            old.rename(_SNAPSHOT_DIR / f"{h}.bak.{i + 1}")

    # Migrate legacy flat .bak into the rotation chain if present
    legacy = _SNAPSHOT_DIR / f"{h}.bak"
    if legacy.exists():
        legacy.rename(_SNAPSHOT_DIR / f"{h}.bak.{_SNAPSHOT_MAX - 1}")

    # Save newest snapshot
    dst = _SNAPSHOT_DIR / f"{h}.bak.0"
    shutil.copy2(src, dst)
    _update_meta(path, h)


def fs_rollback_file(path: str, steps: int = 1) -> str:
    """Rollback a file to a previous snapshot. steps=1 = most recent."""
    idx = steps - 1
    src = _snapshot_path(path, idx)
    if not src.exists():
        # Fallback to legacy .bak for steps=1
        if idx == 0:
            legacy = _snapshot_path(path, -1)
            if legacy.exists():
                src = legacy
            else:
                return f"No snapshot found for {path}"
        else:
            return f"No snapshot found for {path} (steps={steps})"
    dst = Path(path).expanduser()
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return f"Rolled back {path} from snapshot [{idx}]"


def fs_git_rollback(path: str) -> str:
    """Restore the working tree from the most recent auto-stash checkpoint."""
    from worker_bee.safety import git_rollback
    repo_dir = str(Path(path).expanduser().parent)
    return git_rollback(repo_dir)


def fs_snapshot_list(path: str | None = None) -> str:
    """List snapshot history for a file, or all files with snapshots."""
    if path:
        h = hashlib.sha256(
            Path(path).expanduser().resolve().as_posix().encode()
        ).hexdigest()[:16]
        lines = [f"Snapshot history for {Path(path).expanduser().resolve()}:"]

        for i in range(_SNAPSHOT_MAX):
            snap = _SNAPSHOT_DIR / f"{h}.bak.{i}"
            if snap.exists():
                stat = snap.stat()
                ts = datetime.datetime.fromtimestamp(
                    stat.st_mtime, tz=datetime.timezone.utc
                ).strftime("%Y-%m-%d %H:%M:%S")
                marker = "  <- latest" if i == 0 else ""
                lines.append(f"  [{i}] {ts}  {stat.st_size:>8} bytes{marker}")

        legacy = _SNAPSHOT_DIR / f"{h}.bak"
        if legacy.exists() and not (_SNAPSHOT_DIR / f"{h}.bak.0").exists():
            stat = legacy.stat()
            ts = datetime.datetime.fromtimestamp(
                stat.st_mtime, tz=datetime.timezone.utc
            ).strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"  [legacy] {ts}  {stat.st_size:>8} bytes  <- latest")

        if len(lines) == 1:
            return f"No snapshots found for {path}"
        return "\n".join(lines)

    if not _SNAPSHOT_DIR.exists():
        return "No snapshots yet."
    metas = sorted(_SNAPSHOT_DIR.glob("*.meta"))
    if not metas:
        return "No snapshots yet."

    lines = ["All snapshot histories:"]
    for meta in metas:
        try:
            data = json.loads(meta.read_text())
            snapshots = data.get("snapshots", [])
            p = data.get("path", "?")
            if snapshots:
                latest = snapshots[0]
                lines.append(
                    f"  {p} \u2014 {len(snapshots)} version(s), latest {latest['timestamp'][:19]}"
                )
            else:
                lines.append(f"  {p} \u2014 (empty)")
        except Exception:
            pass
    return "\n".join(lines)


def fs_snapshot_diff(path: str, steps: int = 1) -> str:
    """Show unified diff between current file and a snapshot."""
    idx = steps - 1
    src = _snapshot_path(path, idx)
    if not src.exists():
        if idx == 0:
            legacy = _snapshot_path(path, -1)
            if legacy.exists():
                src = legacy
            else:
                return f"No snapshot found for {path}"
        else:
            return f"No snapshot found for {path} (steps={steps})"

    dst = Path(path).expanduser()
    if not dst.exists():
        return f"File not found: {path}"

    try:
        import difflib
        old_lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
        new_lines = dst.read_text(encoding="utf-8", errors="replace").splitlines()
        diff = list(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"snapshot[{idx}]",
                tofile="current",
                lineterm="",
            )
        )
        if not diff:
            return "No differences between snapshot and current file."
        out = "\n".join(diff)
        if len(out) > 8000:
            out = out[:8000] + "\n...(truncated)"
        return out
    except Exception as e:
        return f"Error generating diff: {e}"


# ── Workspace guard ─────────────────────────────────────────────────

_WORKSPACE = os.environ.get("WORKER_BEE_WORKSPACE", str(Path.cwd().resolve()))


def _is_inside_workspace(path: str) -> bool:
    """Return True if path resolves inside the configured workspace."""
    try:
        target = Path(path).resolve()
        root = Path(_WORKSPACE).resolve()
        # Allow the root itself and any child
        return target == root or root in target.parents
    except Exception:
        return False


def _guard_path(path: str, write: bool = False) -> str:
    """Return error string if path is disallowed, else empty string."""
    try:
        p = Path(path).expanduser()
    except Exception as e:
        return f"Error: invalid path '{path}': {e}"

    if write and not _is_inside_workspace(str(p)):
        return (
            f"Error: write outside workspace disallowed. "
            f"Target: {p} | Workspace: {_WORKSPACE}"
        )

    if write and is_write_denied(str(p)):
        return f"Error: writing to sensitive path disallowed: {p}"

    if write and is_self_modify_target(str(p)):
        return (
            f"Error: self-modification blocked. "
            f"Writing to worker-bee source code is disallowed. "
            f"Set WORKER_BEE_ALLOW_SELF_MODIFY=true to override."
        )

    return ""


def fs_read_file(path: str, offset: int = 1, limit: int = 100) -> str:
    """Read a text file with pagination."""
    try:
        p = Path(path).expanduser()
        err = _guard_path(str(p), write=False)
        if err:
            return err
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[offset - 1:offset - 1 + limit])
    except Exception as e:
        return f"Error: {e}"


def fs_write_file(path: str, content: str) -> str:
    """Write text to a file (creates parent directories)."""
    err = _guard_path(path, write=True)
    if err:
        return err
    try:
        p = Path(path).expanduser()
        # Save snapshot before overwriting
        save_snapshot(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Written {len(content)} chars to {path}"
    except Exception as e:
        return f"Error: {e}"


def fs_search_files(pattern: str, path: str = ".", file_glob: str = "*") -> str:
    """Search file contents with regex. file_glob selects which files to inspect (default: all)."""
    results = []
    search_root = Path(path).expanduser()
    # Prevent escaping workspace via relative paths
    if not _is_inside_workspace(str(search_root)):
        return (
            f"Error: search outside workspace disallowed. "
            f"Target: {search_root} | Workspace: {_WORKSPACE}"
        )
    for root, _, files in os.walk(search_root):
        for f in files:
            if not fnmatch.fnmatch(f, file_glob):
                continue
            fp = os.path.join(root, f)
            if is_write_denied(fp):
                continue
            try:
                content = Path(fp).read_text(encoding="utf-8", errors="replace")
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(pattern, line):
                        results.append(f"{fp}:{i}: {line.strip()}")
                        if len(results) >= 30:
                            return "\n".join(results) + "\n... (truncated)"
            except Exception:
                pass
    return "\n".join(results) or "No matches"


registry.register(
    name="fs_read_file",
    description="Read a text file with line numbers and pagination. Use this instead of shell cat/head.",
    parameters={
        "properties": {
            "path": {"type": "string", "description": "Absolute or relative file path"},
            "offset": {"type": "integer", "description": "Start line (1-indexed)", "default": 1},
            "limit": {"type": "integer", "description": "Max lines to read", "default": 100}
        },
        "required": ["path"]
    },
    handler=fs_read_file,
    tags=["filesystem", "read"],
    category="filesystem"
)

registry.register(
    name="fs_write_file",
    description="Write text to a file. Creates parent directories automatically. Overwrites existing content.",
    parameters={
        "properties": {
            "path": {"type": "string", "description": "Target file path"},
            "content": {"type": "string", "description": "Full text content to write"}
        },
        "required": ["path", "content"]
    },
    handler=fs_write_file,
    tags=["filesystem", "write"],
    category="filesystem"
)

registry.register(
    name="fs_search_files",
    description="Search file contents with regex. Returns matching lines with file paths. Optionally filter by file glob (e.g. '*.py').",
    parameters={
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search"},
            "path": {"type": "string", "description": "Directory to search in", "default": "."},
            "file_glob": {"type": "string", "description": "File glob pattern to filter files (e.g. '*.py')", "default": "*"}
        },
        "required": ["pattern"]
    },
    handler=fs_search_files,
    tags=["filesystem", "search"],
    category="filesystem"
)

registry.register(
    name="fs_rollback_file",
    description="Rollback a file to a previous snapshot. steps=1 = most recent, steps=2 = the one before that, etc.",
    parameters={
        "properties": {
            "path": {"type": "string", "description": "File path to rollback"},
            "steps": {"type": "integer", "description": "How many versions back (1=most recent)", "default": 1}
        },
        "required": ["path"]
    },
    handler=fs_rollback_file,
    tags=["filesystem", "rollback"],
    category="filesystem"
)

registry.register(
    name="fs_snapshot_list",
    description="List snapshot history for a file (pass path) or all files with snapshots (omit path).",
    parameters={
        "properties": {
            "path": {"type": "string", "description": "File path to inspect (omit for all)", "default": None}
        },
        "required": []
    },
    handler=fs_snapshot_list,
    tags=["filesystem", "snapshot", "list"],
    category="filesystem"
)

registry.register(
    name="fs_snapshot_diff",
    description="Show unified diff between current file and a snapshot.",
    parameters={
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "steps": {"type": "integer", "description": "How many versions back (1=most recent)", "default": 1}
        },
        "required": ["path"]
    },
    handler=fs_snapshot_diff,
    tags=["filesystem", "snapshot", "diff"],
    category="filesystem"
)
