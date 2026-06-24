"""Tests for SessionDB — session creation, messages, todos, tags, archive, close."""
import pytest
import tempfile
from pathlib import Path

from agent.memory import SessionDB


@pytest.fixture
def db():
    """In-memory SessionDB for isolated tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    sdb = SessionDB(path)
    yield sdb
    try:
        Path(path).unlink()
    except OSError:
        pass


class TestSessions:
    """Session CRUD."""

    def test_create_session(self, db):
        sid = db.create_session()
        assert len(sid) == 8
        assert isinstance(sid, str)

    def test_create_session_with_title(self, db):
        db.create_session(title="My Test")
        sessions = db.list_sessions()
        titles = {s[2] for s in sessions}
        assert "My Test" in titles

    def test_list_sessions_empty(self, db):
        sessions = db.list_sessions()
        assert sessions == []

    def test_list_sessions_order(self, db):
        db.create_session(title="First")
        db.create_session(title="Second")
        sessions = db.list_sessions()
        # Most recent first
        assert sessions[0][2] == "Second"
        assert sessions[1][2] == "First"

    def test_session_meta_and_purpose(self, db):
        sid = db.create_session(title="Test Meta")
        db.set_session_purpose(sid, "Design state machine")
        meta = db.get_session_meta(sid)
        assert meta["purpose"] == "Design state machine"
        assert meta["title"] == "Test Meta"

    def test_close_session(self, db):
        sid = db.create_session()
        db.close_session(sid, wiki_path="/tmp/wiki/session-abc.md")
        meta = db.get_session_meta(sid)
        assert meta["closed_at"] is not None
        assert meta["wiki_path"] == "/tmp/wiki/session-abc.md"

    def test_list_open_sessions(self, db):
        db.create_session(title="Open")
        closed_sid = db.create_session(title="Closed")
        db.close_session(closed_sid)
        open_sessions = db.list_open_sessions()
        assert len(open_sessions) == 1
        assert open_sessions[0][2] == "Open"


class TestMessages:
    """Message save and retrieval."""

    def test_save_and_get_message(self, db):
        sid = db.create_session()
        db.save_message(sid, "user", "hello")
        db.save_message(sid, "assistant", "hi there")

        msgs = db.get_messages(sid)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hello"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "hi there"

    def test_message_with_tool_calls(self, db):
        sid = db.create_session()
        tool_calls = [{"id": "tc1", "name": "fs_read_file", "arguments": {"path": "test.txt"}}]
        db.save_message(sid, "assistant", "I'll read that", tool_calls=tool_calls)

        msgs = db.get_messages(sid)
        assert msgs[0]["tool_calls"] == tool_calls

    def test_get_messages_empty_session(self, db):
        sid = db.create_session()
        assert db.get_messages(sid) == []

    def test_messages_isolated_per_session(self, db):
        sid1 = db.create_session()
        sid2 = db.create_session()
        db.save_message(sid1, "user", "a")
        db.save_message(sid2, "user", "b")

        assert len(db.get_messages(sid1)) == 1
        assert len(db.get_messages(sid2)) == 1
        assert db.get_messages(sid1)[0]["content"] == "a"
        assert db.get_messages(sid2)[0]["content"] == "b"


class TestTags:
    """Tagging messages."""

    def test_save_message_with_tags(self, db):
        sid = db.create_session()
        db.save_message(sid, "user", "hello", tags=["#design", "#question"])
        msgs = db.get_messages(sid)
        assert msgs[0]["tags"] == ["#design", "#question"]

    def test_tag_and_untag_message(self, db):
        sid = db.create_session()
        db.save_message(sid, "user", "hello")
        msg = db.get_messages(sid)[0]
        mid = msg["id"]

        db.tag_message(mid, "#coding")
        db.tag_message(mid, "#bug")
        msgs = db.get_messages(sid)
        assert set(msgs[0]["tags"]) == {"#coding", "#bug"}

        db.untag_message(mid, "#bug")
        msgs = db.get_messages(sid)
        assert msgs[0]["tags"] == ["#coding"]

    def test_get_messages_filter_by_tags(self, db):
        sid = db.create_session()
        db.save_message(sid, "user", "design idea", tags=["#design"])
        db.save_message(sid, "assistant", "implementation", tags=["#coding"])
        db.save_message(sid, "user", "another design", tags=["#design"])

        design_msgs = db.get_messages(sid, tags=["#design"])
        assert len(design_msgs) == 2
        assert all("#design" in m.get("tags", []) for m in design_msgs)


class TestArchive:
    """Soft-archive (rewind) messages."""

    def test_archive_after(self, db):
        sid = db.create_session()
        db.save_message(sid, "user", "msg1")
        db.save_message(sid, "assistant", "msg2")
        db.save_message(sid, "user", "msg3")
        db.save_message(sid, "assistant", "msg4")

        msgs = db.get_messages(sid, include_archived=True)
        mid = msgs[1]["id"]  # archive after msg2

        db.archive_messages_after(sid, mid)
        active = db.get_messages(sid, include_archived=False)
        assert len(active) == 2
        assert active[0]["content"] == "msg1"
        assert active[1]["content"] == "msg2"

        all_msgs = db.get_messages(sid, include_archived=True)
        assert len(all_msgs) == 4
        assert all_msgs[2].get("archived_at") is not None
        assert all_msgs[3].get("archived_at") is not None

    def test_archive_from(self, db):
        sid = db.create_session()
        db.save_message(sid, "user", "msg1")
        db.save_message(sid, "assistant", "msg2")
        db.save_message(sid, "user", "msg3")

        msgs = db.get_messages(sid, include_archived=True)
        mid = msgs[1]["id"]  # archive from msg2 onward

        db.archive_messages_from(sid, mid)
        active = db.get_messages(sid, include_archived=False)
        assert len(active) == 1
        assert active[0]["content"] == "msg1"

    def test_unarchive_all(self, db):
        sid = db.create_session()
        db.save_message(sid, "user", "msg1")
        db.save_message(sid, "assistant", "msg2")
        mid = db.get_messages(sid)[0]["id"]
        db.archive_messages_after(sid, mid)
        assert len(db.get_messages(sid, include_archived=False)) == 1

        db.unarchive_all(sid)
        assert len(db.get_messages(sid, include_archived=False)) == 2


class TestTodos:
    """Todo CRUD."""

    def test_add_and_list_todos(self, db):
        sid = db.create_session()
        tid = db.add_todo(sid, "Write tests")
        assert isinstance(tid, int)
        assert tid > 0

        todos = db.list_todos(sid)
        assert len(todos) == 1
        assert todos[0][1] == "Write tests"
        assert todos[0][2] == "pending"

    def test_update_todo_status(self, db):
        sid = db.create_session()
        tid = db.add_todo(sid, "Do thing")
        db.update_todo_status(tid, "done")

        done = db.list_todos(sid, status="done")
        assert len(done) == 1
        assert done[0][0] == tid

        pending = db.list_todos(sid, status="pending")
        assert len(pending) == 0

    def test_delete_todo(self, db):
        sid = db.create_session()
        tid = db.add_todo(sid, "Delete me")
        db.delete_todo(tid)

        assert db.list_todos(sid) == []

    def test_list_todos_filter_by_status(self, db):
        sid = db.create_session()
        db.add_todo(sid, "Task 1")
        tid2 = db.add_todo(sid, "Task 2")
        db.update_todo_status(tid2, "done")

        assert len(db.list_todos(sid, status="pending")) == 1
        assert len(db.list_todos(sid, status="done")) == 1


class TestTasks:
    """Task management — DEPRECATED but kept for cron-scheduler compat."""

    def test_add_and_list_task(self, db):
        sid = db.create_session()
        db.add_task(sid, "Migrate auth module")
        tasks = db.list_tasks(session_id=sid)
        assert len(tasks) == 1
        assert tasks[0][2] == "Migrate auth module"
        assert tasks[0][3] == "todo"

    def test_list_by_status(self, db):
        sid = db.create_session()
        db.add_task(sid, "Task A")
        tid = db.add_task(sid, "Task B")
        db.update_task_status(tid, "done")
        todos = db.list_tasks(session_id=sid, status="todo")
        dones = db.list_tasks(session_id=sid, status="done")
        assert len(todos) == 1
        assert len(dones) == 1

    def test_status_flow(self, db):
        sid = db.create_session()
        tid = db.add_task(sid, "Flow test")
        db.update_task_status(tid, "in_progress")
        tasks = db.list_tasks(session_id=sid, status="in_progress")
        assert tasks[0][2] == "Flow test"
        db.update_task_status(tid, "done")
        tasks = db.list_tasks(session_id=sid, status="done")
        assert len(tasks) == 1

    def test_cancel_task(self, db):
        sid = db.create_session()
        tid = db.add_task(sid, "Cancel me")
        db.update_task_status(tid, "cancelled")
        tasks = db.list_tasks(session_id=sid, status="cancelled")
        assert len(tasks) == 1

    def test_assign_and_filter(self, db):
        sid = db.create_session()
        db.add_task(sid, "Morning report", assigned_to="morning-brief")
        db.add_task(sid, "Evening cleanup", assigned_to="evening-brief")
        db.add_task(sid, "Unassigned task")
        morning = db.list_tasks(assigned_to="morning-brief")
        assert len(morning) == 1
        assert morning[0][2] == "Morning report"

    def test_get_pending_tasks_for_job(self, db):
        sid = db.create_session()
        db.add_task(sid, "Do X", assigned_to="job-1")
        tid = db.add_task(sid, "Do Y", assigned_to="job-1")
        db.update_task_status(tid, "done")
        db.add_task(sid, "Do Z", assigned_to="job-1")
        pending = db.get_pending_tasks_for_job("job-1")
        assert len(pending) == 2  # Do X (todo) + Do Z (todo); Do Y is done

    def test_assign_task(self, db):
        sid = db.create_session()
        tid = db.add_task(sid, "Reassign me")
        db.assign_task(tid, "job-2")
        tasks = db.list_tasks(assigned_to="job-2")
        assert len(tasks) == 1
        assert tasks[0][2] == "Reassign me"

    def test_empty_task_list(self, db):
        sid = db.create_session()
        tasks = db.list_tasks(session_id=sid)
        assert tasks == []
