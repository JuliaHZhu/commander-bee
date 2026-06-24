import sqlite3
import json
import uuid
import threading
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


class SessionDB:
    def __init__(self, db_path="state.db"):
        self.db_path = db_path
        self._local = threading.local()
        try:
            self._init_schema()
        except (sqlite3.DatabaseError, OSError):
            # Likely corrupted database file — archive and start fresh
            corrupted = f"{db_path}.corrupted.{int(time.time())}"
            try:
                os.rename(db_path, corrupted)
            except OSError:
                pass
            # Reset thread-local so _get_conn creates a new connection
            self._local = threading.local()
            self._init_schema()

    def _get_conn(self):
        """Return a connection bound to the current thread."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        return self._local.conn

    def _init_schema(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                created_at TEXT,
                title TEXT,
                purpose TEXT,
                closed_at TEXT,
                wiki_path TEXT
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY,
                session_id TEXT,
                role TEXT,
                content TEXT,
                tool_calls TEXT,
                tags TEXT,
                archived_at TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY,
                session_id TEXT,
                content TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                updated_at TEXT
            );
            -- DEPRECATED: tasks table kept for cron-scheduler compat.
            -- New work should use session purpose + message tags.
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                session_id TEXT,
                content TEXT,
                status TEXT DEFAULT 'todo',
                assigned_to TEXT,
                priority INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT,
                done_at TEXT
            );
        """)
        # Schema migration: add columns if they don't exist (sqlite-friendly)
        self._migrate_schema()
        conn.commit()

    # Whitelist of columns allowed for schema migration (prevents SQL injection
    # via ALTER TABLE — SQLite does not support parameterised column names).
    _SESSION_COLS = {"purpose": "TEXT", "closed_at": "TEXT", "wiki_path": "TEXT"}
    _MESSAGE_COLS = {"tags": "TEXT", "archived_at": "TEXT"}

    def _migrate_schema(self):
        """Add columns that may be missing from older DBs."""
        conn = self._get_conn()
        # Check and add columns to sessions
        cols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()}
        for col, dtype in self._SESSION_COLS.items():
            if col not in cols:
                conn.execute(f"ALTER TABLE sessions ADD COLUMN {col} {dtype}")
        # Check and add columns to messages
        cols = {r[1] for r in conn.execute("PRAGMA table_info(messages)").fetchall()}
        for col, dtype in self._MESSAGE_COLS.items():
            if col not in cols:
                conn.execute(f"ALTER TABLE messages ADD COLUMN {col} {dtype}")
        conn.commit()

    def create_session(self, title="") -> str:
        conn = self._get_conn()
        # Avoid the (theoretical) collision risk of an 8-char UUID prefix.
        # Max 10 attempts — collisions are vanishingly rare; bounding the loop
        # prevents a theoretical infinite loop.
        for _ in range(10):
            sid = str(uuid.uuid4())[:8]
            existing = conn.execute(
                "SELECT 1 FROM sessions WHERE id = ?", (sid,)
            ).fetchone()
            if not existing:
                break
        else:
            # After 10 collisions, fall back to full UUID
            sid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, NULL, NULL, NULL)",
            (sid, datetime.now().isoformat(), title)
        )
        conn.commit()
        return sid

    def set_session_purpose(self, session_id: str, purpose: str):
        conn = self._get_conn()
        conn.execute(
            "UPDATE sessions SET purpose = ? WHERE id = ?",
            (purpose, session_id)
        )
        conn.commit()

    def close_session(self, session_id: str, wiki_path: str | None = None):
        conn = self._get_conn()
        now = datetime.now().isoformat()
        conn.execute(
            "UPDATE sessions SET closed_at = ?, wiki_path = ? WHERE id = ?",
            (now, wiki_path, session_id)
        )
        conn.commit()

    def list_open_sessions(self):
        conn = self._get_conn()
        return conn.execute(
            "SELECT id, created_at, title, purpose FROM sessions WHERE closed_at IS NULL ORDER BY created_at DESC"
        ).fetchall()

    def get_session_meta(self, session_id: str):
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id, created_at, title, purpose, closed_at, wiki_path FROM sessions WHERE id = ?",
            (session_id,)
        ).fetchone()
        if row:
            return {
                "id": row[0], "created_at": row[1], "title": row[2],
                "purpose": row[3], "closed_at": row[4], "wiki_path": row[5]
            }
        return None

    def save_message(self, session_id: str, role: str, content: str, tool_calls: Optional[list] = None, tags: Optional[list] = None):
        conn = self._get_conn()
        tags_json = json.dumps(tags) if tags else None
        conn.execute(
            "INSERT INTO messages (session_id, role, content, tool_calls, tags, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, role, content, json.dumps(tool_calls) if tool_calls else None, tags_json, datetime.now().isoformat())
        )
        conn.commit()

    def get_messages(self, session_id: str, include_archived: bool = False, tags: Optional[list] = None):
        conn = self._get_conn()
        sql = "SELECT id, role, content, tool_calls, tags, archived_at, created_at FROM messages WHERE session_id = ?"
        params = [session_id]
        if not include_archived:
            sql += " AND archived_at IS NULL"
        if tags:
            # Simple JSON substring match for tags (sqlite3 has no native JSON array contains)
            # Escape LIKE wildcards and JSON quotes to prevent pattern injection
            for t in tags:
                sql += " AND tags LIKE ?"
                safe_t = t.replace("\\", "\\\\").replace('"', '\\"').replace("%", "\\%").replace("_", "\\_")
                params.append(f'%"{safe_t}"%')
        sql += " ORDER BY id"
        rows = conn.execute(sql, params).fetchall()
        messages = []
        for msg_id, role, content, tool_calls, tags_json, archived_at, created_at in rows:
            msg = {"id": msg_id, "role": role, "content": content, "created_at": created_at}
            if tool_calls:
                msg["tool_calls"] = json.loads(tool_calls)
            if tags_json:
                msg["tags"] = json.loads(tags_json)
            if archived_at:
                msg["archived_at"] = archived_at
            messages.append(msg)
        return messages

    def tag_message(self, msg_id: int, tag: str):
        conn = self._get_conn()
        row = conn.execute("SELECT tags FROM messages WHERE id = ?", (msg_id,)).fetchone()
        if not row:
            return False
        tags = json.loads(row[0]) if row[0] else []
        if tag not in tags:
            tags.append(tag)
            conn.execute("UPDATE messages SET tags = ? WHERE id = ?", (json.dumps(tags), msg_id))
            conn.commit()
        return True

    def untag_message(self, msg_id: int, tag: str):
        conn = self._get_conn()
        row = conn.execute("SELECT tags FROM messages WHERE id = ?", (msg_id,)).fetchone()
        if not row:
            return False
        tags = json.loads(row[0]) if row[0] else []
        if tag in tags:
            tags.remove(tag)
            conn.execute("UPDATE messages SET tags = ? WHERE id = ?", (json.dumps(tags), msg_id))
            conn.commit()
        return True

    def archive_messages_after(self, session_id: str, msg_id: int):
        """Soft-archive all messages after msg_id in the session."""
        conn = self._get_conn()
        now = datetime.now().isoformat()
        conn.execute(
            "UPDATE messages SET archived_at = ? WHERE session_id = ? AND id > ?",
            (now, session_id, msg_id)
        )
        conn.commit()

    def archive_messages_from(self, session_id: str, msg_id: int):
        """Soft-archive msg_id and all messages after it."""
        conn = self._get_conn()
        now = datetime.now().isoformat()
        conn.execute(
            "UPDATE messages SET archived_at = ? WHERE session_id = ? AND id >= ?",
            (now, session_id, msg_id)
        )
        conn.commit()

    def unarchive_all(self, session_id: str):
        conn = self._get_conn()
        conn.execute(
            "UPDATE messages SET archived_at = NULL WHERE session_id = ?",
            (session_id,)
        )
        conn.commit()

    def list_sessions(self):
        conn = self._get_conn()
        return conn.execute(
            "SELECT id, created_at, title FROM sessions ORDER BY created_at DESC"
        ).fetchall()

    # ── Todos ──
    def add_todo(self, session_id: str, content: str) -> int:
        conn = self._get_conn()
        cur = conn.execute(
            "INSERT INTO todos (session_id, content, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, content, datetime.now().isoformat(), datetime.now().isoformat())
        )
        conn.commit()
        return cur.lastrowid

    def list_todos(self, session_id: str, status: Optional[str] = None):
        conn = self._get_conn()
        sql = "SELECT id, content, status, created_at FROM todos WHERE session_id = ?"
        params = [session_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at"
        return conn.execute(sql, params).fetchall()

    def update_todo_status(self, todo_id: int, status: str):
        conn = self._get_conn()
        conn.execute(
            "UPDATE todos SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.now().isoformat(), todo_id)
        )
        conn.commit()

    def delete_todo(self, todo_id: int):
        conn = self._get_conn()
        conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        conn.commit()

    # ── Tasks ──
    def add_task(self, session_id: str, content: str, assigned_to: Optional[str] = None, priority: int = 0) -> int:
        conn = self._get_conn()
        now = datetime.now().isoformat()
        cur = conn.execute(
            "INSERT INTO tasks (session_id, content, assigned_to, priority, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, content, assigned_to, priority, now, now)
        )
        conn.commit()
        return cur.lastrowid

    def list_tasks(self, session_id: Optional[str] = None, status: Optional[str] = None, assigned_to: Optional[str] = None):
        conn = self._get_conn()
        sql = "SELECT id, session_id, content, status, assigned_to, priority, created_at FROM tasks WHERE 1=1"
        params = []
        if session_id:
            sql += " AND session_id = ?"
            params.append(session_id)
        if status:
            sql += " AND status = ?"
            params.append(status)
        if assigned_to:
            sql += " AND assigned_to = ?"
            params.append(assigned_to)
        sql += " ORDER BY priority DESC, created_at ASC"
        return conn.execute(sql, params).fetchall()

    def update_task_status(self, task_id: int, status: str):
        conn = self._get_conn()
        now = datetime.now().isoformat()
        if status == "done":
            conn.execute(
                "UPDATE tasks SET status = ?, updated_at = ?, done_at = ? WHERE id = ?",
                (status, now, now, task_id)
            )
        else:
            conn.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, task_id)
            )
        conn.commit()

    def assign_task(self, task_id: int, assigned_to: str):
        conn = self._get_conn()
        conn.execute(
            "UPDATE tasks SET assigned_to = ?, updated_at = ? WHERE id = ?",
            (assigned_to, datetime.now().isoformat(), task_id)
        )
        conn.commit()

    def get_pending_tasks_for_job(self, assigned_to: str):
        conn = self._get_conn()
        return conn.execute(
            "SELECT id, content, priority FROM tasks WHERE assigned_to = ? AND status IN ('todo', 'in_progress') ORDER BY priority DESC, created_at ASC",
            (assigned_to,)
        ).fetchall()

    # ── Handoff (auto session continuation) ──
    def save_handoff(self, session_id: str, content: str):
        """Save handoff as a todo with status='handoff'."""
        conn = self._get_conn()
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO todos (session_id, content, status, created_at, updated_at) VALUES (?, ?, 'handoff', ?, ?)",
            (session_id, content, now, now)
        )
        conn.commit()

    def get_handoff(self) -> str | None:
        """Get latest handoff and mark it consumed."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id, content FROM todos WHERE status='handoff' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row:
            conn.execute("UPDATE todos SET status='consumed' WHERE id=?", (row[0],))
            conn.commit()
            return row[1]
        return None

    # ── Batch Handoff Export ──
    def export_handoff(self, session_id: str, out_path: str | None = None) -> str:
        """Export a batch handoff document for session continuation.

        This is NOT a chat summary — it is a work-state snapshot meant for
        the next session to pick up where this one left off (batch pipeline
        handoff style).

        Returns the path to the written Markdown file.
        """
        meta = self.get_session_meta(session_id) or {}
        msgs = self.get_messages(session_id, include_archived=False)
        todos = self.list_todos(session_id)

        # ── Completed work: recent assistant outputs (non-error, deduped) ──
        completed = []
        seen = set()
        for m in reversed(msgs):   # newest first
            if m.get("role") == "assistant":
                text = m.get("content", "").strip()
                if text and not text.startswith("Error:") and not text.startswith("["):
                    key = text[:120]
                    if key not in seen:
                        seen.add(key)
                        completed.append(text[:500])
                if len(completed) >= 5:
                    break
        completed.reverse()  # chronological order

        # ── Recent user context (last 3 non-empty user messages) ──
        recent_user_msgs = []
        for m in msgs:
            if m.get("role") == "user":
                text = m.get("content", "").strip()
                if text:
                    recent_user_msgs.append(text[:300])
        recent_user_msgs = recent_user_msgs[-3:]

        # ── Build handoff Markdown ──
        lines = [
            "# Handoff",
            "",
            f"**Session:** `{session_id}`",
            f"**Exported:** {datetime.now().isoformat()}",
            "",
        ]

        purpose = meta.get("purpose", "")
        if purpose:
            lines.extend(["## Purpose", f"{purpose}", ""])

        if completed:
            lines.extend(["## Completed", ""])
            for item in completed:
                lines.append(f"- {item}")
            lines.append("")

        if todos:
            lines.extend(["## Todos", ""])
            for tid, content, status, _ in todos:
                mark = "[x]" if status == "done" else "[ ]"
                lines.append(f"- {mark} {content}")
            lines.append("")

        if recent_user_msgs:
            lines.extend(["## Context", ""])
            for text in recent_user_msgs:
                lines.append(f"- {text}")
            lines.append("")

            # Next step = last user message
            lines.extend(["## Next Step", f"{recent_user_msgs[-1]}", ""])

        lines.extend([
            "---",
            "",
            "Load this handoff in a new session with `worker-bee --continue <path>`.",
        ])

        content = "\n".join(lines)

        if out_path is None:
            handoffs_dir = Path.home() / ".worker-bee" / "handoffs"
            handoffs_dir.mkdir(parents=True, exist_ok=True)
            out_path = str(handoffs_dir / f"{session_id}.md")

        Path(out_path).write_text(content, encoding="utf-8")
        return out_path
