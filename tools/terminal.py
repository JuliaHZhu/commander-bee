from typing import Union

import fnmatch
import os
import re
import shlex
import subprocess
from worker_bee.registry import registry
from worker_bee.safety import allow_command, is_dangerous_command

# Re-export for backward-compat with tests
_matches_allowlist = allow_command
_is_dangerous = is_dangerous_command


def _run_command(command: Union[str, list], timeout: int, shell: bool) -> str:
    """Execute command and return trimmed output."""
    result = subprocess.run(
        command, shell=shell, capture_output=True,
        text=True, timeout=timeout
    )
    output = result.stdout + result.stderr
    return (output[:5000] + "\n... (truncated)" if len(output) > 5000 else output) or "(no output)"


def sys_terminal(command: str, timeout: int = 30, require_confirmation: bool = True) -> str:
    """Execute a shell command in the workspace.

    Security model:
      1. Allowlist  — common read-only/low-risk commands execute immediately.
      2. Dangerous  — blocked with a clear message (no interactive prompts).
      3. Other      — blocked with a clear message.

      Set require_confirmation=False to also block dangerous/unrecognized
      commands (instead of prompting — for headless/automated contexts).
      Set WORKER_BEE_AUTO_CONFIRM=true to auto-execute unrecognized commands
      (⚠️ only in fully sandboxed environments).

    Any command with shell metacharacters (; && || | $() < > ` { }) bypasses
    the allowlist and falls into category 2 or 3.
    """
    auto_confirm = os.environ.get("WORKER_BEE_AUTO_CONFIRM", "false").lower() == "true"

    # Dangerous check MUST come before allowlist so a mistakenly-added
    # dangerous pattern (e.g. "git push*" in ALLOWLIST) is still blocked.
    if is_dangerous_command(command):
        return (
            f"Blocked: dangerous command pattern detected in: {command}\n"
            f"This command is on the deny list. "
            f"Run it manually in a terminal if you are certain it is safe."
        )
    elif allow_command(command):
        # Fast path: no confirmation needed, use shell=False for safety
        try:
            args = shlex.split(command)
            return _run_command(args, timeout, shell=False)
        except Exception:
            return (
                f"Error: could not parse command with shlex. "
                f"Shell metacharacters or complex quoting may be present. "
                f"Try removing quotes/special characters: {command}"
            )
    else:
        if auto_confirm:
            # Even with auto-confirm, never use shell=True — that's a bypass vector.
            try:
                args = shlex.split(command)
                return _run_command(args, timeout, shell=False)
            except Exception:
                return (
                    f"Blocked: command contains shell metacharacters or "
                    f"unparseable syntax: {command}"
                )
        return (
            f"Blocked: unrecognized command (not in allowlist): {command}\n"
            f"Add it to the allowlist in worker_bee/safety.py ALLOWLIST, "
            f"or set WORKER_BEE_AUTO_CONFIRM=true in sandboxed environments."
        )


registry.register(
    name="sys_terminal",
    description="Execute a shell command in the workspace. Dangerous or unrecognized commands are blocked.",
    parameters={
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
            "require_confirmation": {
                "type": "boolean",
                "description": "If false, block unrecognized/dangerous commands without prompting.",
                "default": True
            }
        },
        "required": ["command"]
    },
    handler=sys_terminal,
    tags=["system", "shell", "execute"],
    category="system"
)
