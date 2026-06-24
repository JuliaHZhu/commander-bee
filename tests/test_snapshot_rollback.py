"""Tests for snapshot / rollback mechanism in tools/file.py."""

from tools.file import (
    fs_write_file,
    fs_rollback_file,
    fs_snapshot_list,
    fs_snapshot_diff,
    save_snapshot,
    _snapshot_path,
    _SNAPSHOT_MAX,
)


class TestSnapshot:
    def test_snapshot_created_on_write(self, tmp_path, monkeypatch):
        import tools.file
        monkeypatch.setattr(tools.file, "_SNAPSHOT_DIR", tmp_path / "snapshots")
        monkeypatch.setattr(tools.file, "_WORKSPACE", str(tmp_path))

        target = tmp_path / "doc.txt"
        target.write_text("original")
        fs_write_file(str(target), "modified")
        snap = _snapshot_path(str(target), idx=0)
        assert snap.exists()
        assert snap.read_text() == "original"

    def test_no_snapshot_for_new_file(self, tmp_path, monkeypatch):
        import tools.file
        monkeypatch.setattr(tools.file, "_SNAPSHOT_DIR", tmp_path / "snapshots")
        monkeypatch.setattr(tools.file, "_WORKSPACE", str(tmp_path))

        target = tmp_path / "newfile.txt"
        fs_write_file(str(target), "hello")
        snap = _snapshot_path(str(target), idx=0)
        assert not snap.exists()

    def test_snapshot_rotates_versions(self, tmp_path, monkeypatch):
        """Writing v1 -> v2 -> v3 leaves .bak.0=v2 and .bak.1=v1."""
        import tools.file
        monkeypatch.setattr(tools.file, "_SNAPSHOT_DIR", tmp_path / "snapshots")
        monkeypatch.setattr(tools.file, "_WORKSPACE", str(tmp_path))

        target = tmp_path / "versioned.txt"
        target.write_text("v1")
        fs_write_file(str(target), "v2")
        fs_write_file(str(target), "v3")

        snap0 = _snapshot_path(str(target), idx=0)
        snap1 = _snapshot_path(str(target), idx=1)
        assert snap0.exists()
        assert snap0.read_text() == "v2"
        assert snap1.exists()
        assert snap1.read_text() == "v1"

    def test_save_snapshot_explicit(self, tmp_path, monkeypatch):
        import tools.file
        monkeypatch.setattr(tools.file, "_SNAPSHOT_DIR", tmp_path / "snapshots")

        target = tmp_path / "manual.txt"
        target.write_text("before")
        save_snapshot(str(target))
        snap = _snapshot_path(str(target), idx=0)
        assert snap.exists()
        assert snap.read_text() == "before"

    def test_rotation_respects_max(self, tmp_path, monkeypatch):
        """Only _SNAPSHOT_MAX versions are kept; oldest is dropped."""
        import tools.file
        monkeypatch.setattr(tools.file, "_SNAPSHOT_DIR", tmp_path / "snapshots")
        monkeypatch.setattr(tools.file, "_WORKSPACE", str(tmp_path))

        target = tmp_path / "capped.txt"
        target.write_text("v0")
        for i in range(1, _SNAPSHOT_MAX + 2):
            fs_write_file(str(target), f"v{i}")

        # v0 was rotated out, so oldest should be v1
        oldest = _snapshot_path(str(target), idx=_SNAPSHOT_MAX - 1)
        assert oldest.exists()
        assert oldest.read_text() == "v1"
        # Most recent should be v5 (v0..v6 = 7 versions, 5 kept)
        latest = _snapshot_path(str(target), idx=0)
        assert latest.read_text() == f"v{_SNAPSHOT_MAX}"


class TestRollback:
    def test_rollback_restores_content(self, tmp_path, monkeypatch):
        import tools.file
        monkeypatch.setattr(tools.file, "_SNAPSHOT_DIR", tmp_path / "snapshots")
        monkeypatch.setattr(tools.file, "_WORKSPACE", str(tmp_path))

        target = tmp_path / "doc.txt"
        target.write_text("original")
        fs_write_file(str(target), "modified")
        assert target.read_text() == "modified"

        result = fs_rollback_file(str(target))
        assert "Rolled back" in result
        assert target.read_text() == "original"

    def test_rollback_no_snapshot(self, tmp_path, monkeypatch):
        import tools.file
        monkeypatch.setattr(tools.file, "_SNAPSHOT_DIR", tmp_path / "snapshots")

        target = tmp_path / "nosnap.txt"
        target.write_text("whatever")
        result = fs_rollback_file(str(target))
        assert "No snapshot found" in result

    def test_rollback_creates_parent_dirs(self, tmp_path, monkeypatch):
        import tools.file
        monkeypatch.setattr(tools.file, "_SNAPSHOT_DIR", tmp_path / "snapshots")
        monkeypatch.setattr(tools.file, "_WORKSPACE", str(tmp_path))

        target = tmp_path / "deep" / "nested" / "file.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("deep original")
        fs_write_file(str(target), "deep modified")

        # Delete the file (simulate corruption)
        target.unlink()
        result = fs_rollback_file(str(target))
        assert "Rolled back" in result
        assert target.read_text() == "deep original"

    def test_rollback_steps(self, tmp_path, monkeypatch):
        """Rollback with steps=2 restores .bak.1 (two versions back)."""
        import tools.file
        monkeypatch.setattr(tools.file, "_SNAPSHOT_DIR", tmp_path / "snapshots")
        monkeypatch.setattr(tools.file, "_WORKSPACE", str(tmp_path))

        target = tmp_path / "steps.txt"
        target.write_text("v1")
        fs_write_file(str(target), "v2")
        fs_write_file(str(target), "v3")

        result = fs_rollback_file(str(target), steps=2)
        assert "Rolled back" in result
        assert target.read_text() == "v1"


class TestSnapshotList:
    def test_list_single_file(self, tmp_path, monkeypatch):
        import tools.file
        monkeypatch.setattr(tools.file, "_SNAPSHOT_DIR", tmp_path / "snapshots")
        monkeypatch.setattr(tools.file, "_WORKSPACE", str(tmp_path))

        target = tmp_path / "listed.txt"
        target.write_text("v1")
        fs_write_file(str(target), "v2")

        out = fs_snapshot_list(str(target))
        assert "Snapshot history" in out
        assert "<- latest" in out
        assert "bytes" in out

    def test_list_all(self, tmp_path, monkeypatch):
        import tools.file
        monkeypatch.setattr(tools.file, "_SNAPSHOT_DIR", tmp_path / "snapshots")
        monkeypatch.setattr(tools.file, "_WORKSPACE", str(tmp_path))

        for name in ("a.txt", "b.txt"):
            p = tmp_path / name
            p.write_text("x")
            fs_write_file(str(p), "y")

        out = fs_snapshot_list()
        assert "All snapshot histories" in out
        assert "a.txt" in out
        assert "b.txt" in out

    def test_list_no_snapshots(self, tmp_path, monkeypatch):
        import tools.file
        monkeypatch.setattr(tools.file, "_SNAPSHOT_DIR", tmp_path / "snapshots")

        out = fs_snapshot_list(str(tmp_path / "none.txt"))
        assert "No snapshots found" in out


class TestSnapshotDiff:
    def test_diff_shows_changes(self, tmp_path, monkeypatch):
        import tools.file
        monkeypatch.setattr(tools.file, "_SNAPSHOT_DIR", tmp_path / "snapshots")
        monkeypatch.setattr(tools.file, "_WORKSPACE", str(tmp_path))

        target = tmp_path / "diff.txt"
        target.write_text("line one\nline two\n")
        fs_write_file(str(target), "line one\nline two changed\nline three\n")

        out = fs_snapshot_diff(str(target))
        assert "--- snapshot[0]" in out
        assert "+++ current" in out
        assert "line two changed" in out

    def test_diff_no_changes(self, tmp_path, monkeypatch):
        import tools.file
        monkeypatch.setattr(tools.file, "_SNAPSHOT_DIR", tmp_path / "snapshots")
        monkeypatch.setattr(tools.file, "_WORKSPACE", str(tmp_path))

        target = tmp_path / "same.txt"
        target.write_text("unchanged")
        fs_write_file(str(target), "unchanged")

        out = fs_snapshot_diff(str(target))
        assert "No differences" in out
