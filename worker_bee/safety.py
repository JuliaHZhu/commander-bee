"""Safety guardrails — single source of truth for worker-bee security policy.

Four layers (user-mandated order):
  1. File write denylist + optional safe_write_root sandbox.
  2. Dangerous-command hardline blocklist (unconditional).
  3. Auto git checkpoint before mutating operations.
  4. Agent self-modify lock (default deny writes to own source).
"""
from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

# ── Layer 1: Write-path denylist ────────────────────────────────────

_SENSITIVE_PATHS: tuple[str, ...] = (
    "/etc/passwd", "/etc/shadow", "/etc/sudoers",
    "/etc/hosts", "/etc/resolv.conf", "/etc/fstab",
    "/etc/ssh/sshd_config", "/etc/crontab",
    "/proc", "/sys", "/dev",
    ".ssh/authorized_keys", ".ssh/id_rsa", ".ssh/id_ed25519",
    ".ssh/known_hosts", ".ssh/config",
    ".env", ".env.local", ".env.production",
    "config.json", "secrets.json", "credentials.json",
    ".pypirc", ".netrc", ".git-credentials",
    "~/.bashrc", "~/.zshrc", "~/.profile",
)

# Short filenames that must match exactly to avoid false positives
# (e.g. "my.env.py" should NOT be blocked just because it contains ".env")
_BASENAME_EXACT: frozenset[str] = frozenset({
    ".env", ".env.local", ".env.production",
    ".bashrc", ".zshrc", ".profile",
})

def is_write_denied(path: str) -> bool:
    """Return True if *path* must never be written to."""
    expanded = Path(path).expanduser().resolve()
    norm = str(expanded)
    lowered = norm.lower()
    basename = Path(norm).name.lower()

    # Block well-known sensitive files
    for frag in _SENSITIVE_PATHS:
        frag_lower = frag.lower()
        if frag_lower in _BASENAME_EXACT:
            if basename == frag_lower:
                return True
        else:
            frag_expanded = str(Path(frag).expanduser())
            if frag_expanded.lower() in lowered or norm.endswith(frag_expanded):
                return True

    # Broad directory guards: anything under these dirs is sensitive
    if "/.ssh/" in lowered or lowered.rstrip("/").endswith("/.ssh"):
        return True
    if "/proc/" in lowered or lowered.rstrip("/").endswith("/proc"):
        return True
    if "/sys/" in lowered or lowered.rstrip("/").endswith("/sys"):
        return True
    if "/dev/" in lowered or lowered.rstrip("/").endswith("/dev"):
        return True

    # Optional safe-root sandbox
    safe_root_env = os.environ.get("WORKER_BEE_WRITE_SAFE_ROOT", "").strip()
    if safe_root_env:
        safe = Path(safe_root_env).expanduser().resolve()
        try:
            expanded.relative_to(safe)
        except ValueError:
            return True

    return False


# ── Layer 2: Dangerous-command hardline blocklist ───────────────────

_HARDLINE_RE = re.compile(
    r"""
    (?:^|;)\s*
    (?:
        rm\s+-[a-zA-Z]*rf?\s+(?:/|~|\$HOME|/boot|/etc|/usr|/var|/home|/root)
      | rm\s+-[a-zA-Z]*rf?\s+/.*\b
      | mkfs\.
      | mkfs\s+
      | mkswap\s+
      | fdisk\s+
      | parted\s+
      | dd\s+if=.+of=/dev/
      | shutdown\s+| reboot\s+| halt\s+| poweroff\s+
      | systemctl\s+(poweroff|reboot|halt|suspend|hibernate)
      | init\s+0\b
      | telinit\s+0\b
      | :\(\)\{\s*:\|:&\s*\};:
      | eval\s*\(
      | exec\s*\(
      | curl\s+.*\|\s*sh\b
      | wget\s+.*\|\s*sh\b
      | curl\s+.*\|\s*bash\b
      | wget\s+.*\|\s*bash\b
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Standalone commands that are always blocked
_HARDLINE_COMMANDS: set[str] = {
    "rm", "rmdir", "mkfs", "mkswap", "fdisk", "parted",
    "shutdown", "reboot", "halt", "poweroff",
    "systemctl", "init", "telinit",
}

# Allowlist for sys_terminal — commands that run immediately without confirmation.
# Patterns are fnmatch globs.  Commands with shell metacharacters always bypass.
ALLOWLIST: list[str] = [
    "head*", "tail*", "less*", "more*",
    "ls*", "ll*", "pwd", "id", "uname*", "whoami",
    "echo*", "printf*", "which*", "whereis*", "stat*", "file*",
    "wc*", "ps*", "top*", "df*", "du*", "free", "uptime",
    "date", "cal", "hostname",
    "grep*", "find*", "locate*",
    "git status*", "git log*", "git diff*", "git show*", "git branch*",
    "git remote*", "git config --list", "git --version",
    "python --version", "python3 --version", "pip list*", "pip3 list*",
    "python -m pytest --collect-only*",
    # file reading
    "cat*", "bat*", "tac*", "nl*", "od*",
    # lint / test (read-only nature)
    "pytest*", "python -m pytest*",
    "black --check*", "ruff check*", "mypy*", "flake8*",
    "pylint*", "bandit*", "vulture*",
    # git (read-only + safe writes only)
    "git add*", "git commit*", "git fetch*",
    # build tools
    "make*", "cmake*", "cargo*", "go build*", "go test*", "go run*",
    "npm*", "pnpm*", "yarn*", "npx*",
    # docker read-only
    "docker ps*", "docker images*", "docker logs*", "docker inspect*",
    "docker network*", "docker volume*",
    # archive (low risk)
    "tar*", "zip*", "unzip*", "gzip*", "gunzip*",
    # file ops (non-destructive)
    "mkdir*", "touch*", "cp*", "mv*", "rename*",
    "chmod*", "chown*",  # dangerous list blocks -R variants
    "ln*", "readlink*",
    # text processing
    "sort*", "uniq*", "cut*", "awk*", "sed*",
    "tr*", "rev*", "base64*", "md5sum*", "sha256sum*",
    "diff*", "cmp*", "comm*",
    "tree*", "fd*", "rg*", "ag*",
    "xargs*", "parallel*",
    # network probes (read-only)
    "curl -I*", "curl --head*", "wget --spider*",
    # misc common
    "time*", "timeout*", "nice*",
    "ssh-keygen*", "ssh-keyscan*",
    "type*", "command*",
    "printenv*", "env*", "export*", "set*",
]

# Dangerous substrings: presence blocks command unconditionally.
DANGEROUS: list[str] = [
    "rm -rf", "rm -fr", "rm -r /", "rmdir /",
    "sudo", "su -", "doas",
    "chmod -R", "chown -R", "chmod 777",
    "mkfs", "mkswap", "swapon",
    "dd if=", "dd of=",
    "> /dev", "< /dev", "/dev/sd", "/dev/hd", "/dev/nvme",
    "curl *|*sh", "wget *|*sh", "curl *|*bash", "wget *|*bash",
    ":(){ :|:& };:",  # fork bomb
    "eval(", "exec(", "__import__('os').system",
    "git push", "git reset", "git rebase", "git stash drop",
    "python -c", "python3 -c", "python -m", "python3 -m",
]

# Shell metacharacters that break simple allowlist matching
_SHELL_META_RE = re.compile(r'[;&|<>$`\(\)\{\}]')


def allow_command(command: str) -> bool:
    """True if command matches ALLOWLIST and contains no shell metacharacters."""
    if _SHELL_META_RE.search(command):
        return False
    for pattern in ALLOWLIST:
        if fnmatch.fnmatch(command, pattern):
            return True
    return False


def is_dangerous_command(command: str) -> bool:
    """True if command contains any dangerous substring or matches hardline."""
    lowered = command.lower()
    for d in DANGEROUS:
        if "*" in d or "?" in d:
            if fnmatch.fnmatch(lowered, d.lower()):
                return True
        elif d.lower() in lowered:
            return True

    blocked, _ = detect_hardline_command(command)
    return blocked


def detect_hardline_command(command: str) -> tuple[bool, Optional[str]]:
    """Return (blocked, reason) for commands on the unconditional blocklist."""
    stripped = command.strip()
    lowered = stripped.lower()

    # Redirect overwrite to /dev/ is always dangerous
    if ">/dev/" in lowered.replace(" ", "") or ">/dev/" in lowered:
        return True, "redirect to block device"

    # Regex-based complex patterns
    if _HARDLINE_RE.search(lowered):
        if "rm" in lowered and ("/" in stripped or "~" in stripped or "$home" in lowered):
            return True, "rm targeting filesystem root or home directory"
        if "mkfs" in lowered:
            return True, "mkfs filesystem formatting command"
        if "dd" in lowered and "of=/dev/" in lowered:
            return True, "dd writing to block device"
        if ":(){ :|:& };:" in lowered or "fork bomb" in lowered:
            return True, "fork bomb"
        if "|" in lowered and ("sh" in lowered or "bash" in lowered):
            return True, "piped curl/wget into shell"
        if any(w in lowered for w in ("shutdown", "reboot", "halt", "poweroff", "init", "telinit")):
            return True, "shutdown/reboot/halt/poweroff/init/telinit system control command"
        return True, "matches unconditional blocklist pattern"

    # Simple prefix match for obviously destructive standalone commands
    first_word = stripped.split()[0].lower() if stripped else ""
    if first_word in _HARDLINE_COMMANDS:
        # Heuristic: block if it targets rootfs or no specific safe target
        if "/" in stripped or "~" in stripped or "$HOME" in stripped:
            return True, f"'{first_word}' targeting filesystem root"
        if first_word in ("shutdown", "reboot", "halt", "poweroff", "init", "telinit"):
            return True, "shutdown/reboot/halt/poweroff/init/telinit system control command"

    return False, None


def hardline_block_message(reason: str) -> str:
    return (
        f"BLOCKED (hardline): Command is on the unconditional blocklist. "
        f"Reason: {reason}. No override available."
    )


# ── Layer 4: Self-modify lock ──────────────────────────────────────

WORKER_BEE_ROOT = Path(__file__).resolve().parent


def is_self_modify_target(path: str) -> bool:
    """Return True if *path* points inside the worker-bee package itself."""
    if os.environ.get("WORKER_BEE_ALLOW_SELF_MODIFY", "").lower() == "true":
        return False
    target = Path(path).expanduser().resolve()
    try:
        target.relative_to(WORKER_BEE_ROOT)
        return True
    except ValueError:
        return False


# ── Layer 3: Auto git checkpoint / rollback ────────────────────────

def git_checkpoint(repo_dir: str, description: str = "auto-checkpoint") -> str:
    """Stash current working-tree changes before a mutating operation.

    Returns a human-readable status string.
    """
    repo = Path(repo_dir).expanduser().resolve()
    git_dir = repo / ".git"
    if not git_dir.is_dir():
        return "(not a git repo — no checkpoint)"

    # Check whether there is anything to stash
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return "(no local changes — no checkpoint)"

    stash_result = subprocess.run(
        ["git", "stash", "push", "--include-untracked", "-m", f"worker-bee-{description}"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if stash_result.returncode == 0:
        return f"checkpoint created: worker-bee-{description}"
    return f"checkpoint failed: {stash_result.stderr.strip() or 'unknown error'}"


def git_rollback(repo_dir: str) -> str:
    """Pop the most recent stash to restore working-tree changes."""
    repo = Path(repo_dir).expanduser().resolve()
    git_dir = repo / ".git"
    if not git_dir.is_dir():
        return "(not a git repo — nothing to rollback)"

    # Check whether there is a stash to pop
    stash_list = subprocess.run(
        ["git", "stash", "list"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if stash_list.returncode != 0 or not stash_list.stdout.strip():
        return "(no stash to restore — nothing to rollback)"

    pop_result = subprocess.run(
        ["git", "stash", "pop"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if pop_result.returncode == 0:
        return "Rolled back to pre-checkpoint state."
    return f"Rollback failed: {pop_result.stderr.strip() or 'unknown error'}"
