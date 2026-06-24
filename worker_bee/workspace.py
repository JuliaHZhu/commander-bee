"""Workspace resolution — single source of truth for worker-bee boundaries.

Import-safe: no external dependencies beyond stdlib.
"""

import os
from pathlib import Path


def get_workspace() -> Path:
    """Return the worker-bee workspace root.

    Priority:
      1. ``WORKER_BEE_WORKSPACE`` environment variable (expanded, resolved)
      2. Default ``~/workspace/`` (auto-created if absent)

    This is the single source of truth — all other callers should import it.
    """
    env = os.environ.get("WORKER_BEE_WORKSPACE", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    default = Path.home() / "workspace"
    default.mkdir(parents=True, exist_ok=True)
    return default
