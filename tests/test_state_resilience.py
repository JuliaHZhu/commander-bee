"""Tests for fault resilience: state.db corruption, backups."""
import json
import os
import tempfile
from pathlib import Path

import pytest

from agent.memory import SessionDB


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
