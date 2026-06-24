"""Tests for fault resilience: state.json corruption, state.db corruption, backups."""
import json
import os
import tempfile
from pathlib import Path

import pytest

from worker_bee.memory import SessionDB
from todo_ball_machine.engine import Engine


class TestTodoBallMachineStateResilience:
    """#2 — state.json corruption detection, backup recovery, corrupted archive."""

    @pytest.fixture
    def tbm_dir(self):
        with tempfile.TemporaryDirectory(prefix="tbm-") as d:
            path = Path(d)
            # Minimal config and balls
            (path / "config.json").write_text(
                json.dumps({"cycle_name": "Test", "cycle_start": "2026-01-01", "cycle_end": "2026-12-31"}),
                encoding="utf-8",
            )
            (path / "balls.json").write_text(
                json.dumps({
                    "boxes": {
                        "Work": {"emoji": "💼", "balls": [{"id": "w1", "content": "Task 1", "difficulty": "medium"}]}
                    }
                }),
                encoding="utf-8",
            )
            yield path

    def test_load_corrupted_state_archives_and_falls_back_to_init(self, tbm_dir):
        state_path = tbm_dir / "state.json"
        state_path.write_text("NOT JSON{{{", encoding="utf-8")
        eng = Engine(tbm_dir)
        # Should have recovered via _init (no backup exists yet)
        assert "cycle" in eng.state
        assert eng.state["cycle"]["name"] == "Test"
        # Corrupted file should be archived
        corrupted_files = list(tbm_dir.glob("state.json.corrupted.*"))
        assert len(corrupted_files) == 1

    def test_load_corrupted_state_recovers_from_backup(self, tbm_dir):
        state_path = tbm_dir / "state.json"
        good_state = {
            "cycle": {"name": "Backup", "start": "2026-01-01", "end": "2026-12-31"},
            "boxes": {"Work": {"emoji": "💼", "stack": ["w1"], "used": []}},
            "days": {},
        }
        state_path.write_text(json.dumps(good_state, ensure_ascii=False), encoding="utf-8")
        # Trigger a backup save
        eng1 = Engine(tbm_dir)
        eng1._save()
        # Verify backup exists
        backup = state_path.with_suffix(".json.bak")
        assert backup.exists()
        # Corrupt the current state
        state_path.write_text("GARBAGE", encoding="utf-8")
        # New engine should recover from backup
        eng2 = Engine(tbm_dir)
        assert eng2.state["cycle"]["name"] == "Backup"
        # Corrupted file archived
        corrupted_files = list(tbm_dir.glob("state.json.corrupted.*"))
        assert len(corrupted_files) == 1

    def test_save_rotates_backup(self, tbm_dir):
        state_path = tbm_dir / "state.json"
        eng = Engine(tbm_dir)
        eng._save()  # First save creates state.json (no prior backup yet)
        assert state_path.exists()
        # Second save should rotate backup
        eng.state["days"]["2026-05-24"] = {"morning": {"box": "Work", "content": "T", "status": "planned", "ball_id": "w1"}}
        eng._save()
        backup = state_path.with_suffix(".json.bak")
        assert backup.exists()
        # Backup should contain the state from the first save (days empty)
        backup_data = json.loads(backup.read_text(encoding="utf-8"))
        assert "2026-05-24" not in backup_data.get("days", {})


class TestSessionDBCorruption:
    """#4 — state.db corruption detection and archive+rebuild."""

    def test_corrupted_db_is_archived_and_rebuilt(self):
        with tempfile.TemporaryDirectory(prefix="db-") as d:
            db_path = Path(d) / "state.db"
            # Write garbage to simulate corruption
            db_path.write_bytes(b"THIS IS NOT A SQLITE FILE")
            # Should not raise — archive and rebuild
            db = SessionDB(str(db_path))
            # Basic operation should work on fresh db
            sid = db.create_session()
            assert len(sid) == 8
            # Corrupted file should be archived
            corrupted = list(Path(d).glob("state.db.corrupted.*"))
            assert len(corrupted) == 1

    def test_normal_db_unchanged(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        db = SessionDB(db_path)
        sid = db.create_session(title="Normal")
        meta = db.get_session_meta(sid)
        assert meta["title"] == "Normal"
        os.unlink(db_path)
