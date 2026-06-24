"""Audit logging — optional tool-call record for operational traceability.

Enabled via WORKER_BEE_AUDIT_LOG (path to JSONL file, e.g., ~/.worker-bee/audit.jsonl).
Each line is a JSON object: {ts, tool, args, status, duration_ms, error}.
Args are truncated to 500 chars to keep logs compact.
Sensitive keys (api_key, password, token, etc.) are redacted to ***.
"""
from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path
from typing import Any, Dict, Optional


# Keys whose values are redacted in audit logs to avoid credential leakage.
_SENSITIVE_KEYS = frozenset({"api_key", "password", "token", "secret", "key", "credential"})


def _audit_path() -> Optional[Path]:
    p = os.environ.get("WORKER_BEE_AUDIT_LOG", "").strip()
    if not p:
        return None
    return Path(p).expanduser()


_MAX_ARG_LEN = 500


def _truncate(s: str, max_len: int = _MAX_ARG_LEN) -> str:
    if len(s) <= max_len:
        return s
    return s[:max_len] + "…"


def _redact_args(arguments: Dict[str, Any]) -> Dict[str, str]:
    """Serialise and truncate args; redact values for sensitive keys."""
    return {
        k: "***" if k.lower() in _SENSITIVE_KEYS else _truncate(json.dumps(v, default=str))
        for k, v in arguments.items()
    }

def log_tool_call(
    tool_name: str,
    arguments: Dict[str, Any],
    result: str,
    duration_ms: float,
    error: bool = False,
) -> None:
    """Record a tool invocation to the audit log (no-op if not configured)."""
    path = _audit_path()
    if path is None:
        return

    # Redact sensitive arguments before logging
    args_safe = _redact_args(arguments)

    entry = {
        "ts": time.time(),
        "tool": tool_name,
        "args": args_safe,
        "status": "error" if error else "ok",
        "duration_ms": round(duration_ms, 1),
    }
    if error:
        entry["error"] = _truncate(result, 200)

    # Ensure parent directory exists (idempotent)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    # Restrict log file to owner-only read/write
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
