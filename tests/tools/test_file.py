"""Tests for file tools — workspace guard, sensitive file blocking, read/write/search."""
import os

import tools.file as file_mod


class TestSensitiveDetection:
    """_is_sensitive path filtering."""

    def test_env_is_sensitive(self):
        assert file_mod._is_sensitive("/home/user/.env")

    def test_ssh_key_is_sensitive(self):
        assert file_mod._is_sensitive("/home/user/.ssh/id_rsa")

    def test_authorized_keys_is_sensitive(self):
        assert file_mod._is_sensitive("/home/user/.ssh/authorized_keys")

    def test_config_json_is_sensitive(self):
        assert file_mod._is_sensitive("/app/config.json")

    def test_etc_passwd_is_sensitive(self):
        assert file_mod._is_sensitive("/etc/passwd")

    def test_etc_shadow_is_sensitive(self):
        assert file_mod._is_sensitive("/etc/shadow")

    def test_regular_file_not_sensitive(self):
        assert not file_mod._is_sensitive("/home/user/project/readme.md")

    def test_normal_txt_not_sensitive(self):
        assert not file_mod._is_sensitive("/tmp/test.txt")

    def test_env_like_filename_not_sensitive(self):
        """my.env.py should NOT be flagged just because it contains '.env'."""
        assert not file_mod._is_sensitive("/home/user/project/my.env.py")
        assert not file_mod._is_sensitive("/app/settings.env.json")


class TestWorkspaceGuard:
    """_is_inside_workspace boundary enforcement."""

    def test_file_in_workspace(self, temp_dir, monkeypatch):
        monkeypatch.setattr(file_mod, "_WORKSPACE", str(temp_dir))
        path = temp_dir / "file.txt"
        assert file_mod._is_inside_workspace(str(path))

    def test_file_in_subdir(self, temp_dir, monkeypatch):
        monkeypatch.setattr(file_mod, "_WORKSPACE", str(temp_dir))
        subdir = temp_dir / "subdir" / "file.txt"
        subdir.parent.mkdir(parents=True, exist_ok=True)
        assert file_mod._is_inside_workspace(str(subdir))

    def test_file_outside_workspace(self, temp_dir, monkeypatch):
        monkeypatch.setattr(file_mod, "_WORKSPACE", str(temp_dir))
        assert not file_mod._is_inside_workspace("/etc/passwd")

    def test_workspace_root_itself(self, temp_dir, monkeypatch):
        monkeypatch.setattr(file_mod, "_WORKSPACE", str(temp_dir))
        assert file_mod._is_inside_workspace(str(temp_dir))

    def test_symlink_escape(self, temp_dir, monkeypatch):
        monkeypatch.setattr(file_mod, "_WORKSPACE", str(temp_dir))
        symlink = temp_dir / "escape"
        os.symlink("/etc/passwd", str(symlink))
        try:
            assert not file_mod._is_inside_workspace(str(symlink))
        finally:
            os.unlink(str(symlink))


class TestGuardPath:
    """_guard_path validation for reads and writes."""

    def test_write_inside_workspace_ok(self, temp_dir, monkeypatch):
        monkeypatch.setattr(file_mod, "_WORKSPACE", str(temp_dir))
        err = file_mod._guard_path(str(temp_dir / "output.txt"), write=True)
        assert err == ""

    def test_write_outside_workspace_blocked(self, temp_dir, monkeypatch):
        monkeypatch.setattr(file_mod, "_WORKSPACE", str(temp_dir))
        err = file_mod._guard_path("/etc/cron.d/bad", write=True)
        assert "outside workspace" in err

    def test_write_sensitive_blocked(self, temp_dir, monkeypatch):
        monkeypatch.setattr(file_mod, "_WORKSPACE", str(temp_dir))
        err = file_mod._guard_path(str(temp_dir / ".env"), write=True)
        assert "sensitive" in err

    def test_read_outside_workspace_ok(self, temp_dir, monkeypatch):
        monkeypatch.setattr(file_mod, "_WORKSPACE", str(temp_dir))
        err = file_mod._guard_path("/tmp/README.md", write=False)
        assert err == ""


class TestReadFile:
    """fs_read_file functionality."""

    def test_read_existing_file(self, temp_dir):
        path = temp_dir / "test.txt"
        path.write_text("line1\nline2\nline3")
        result = file_mod.fs_read_file(str(path))
        assert "line1" in result

    def test_read_with_offset(self, temp_dir):
        path = temp_dir / "lines.txt"
        path.write_text("a\nb\nc\nd\ne")
        result = file_mod.fs_read_file(str(path), offset=3)
        lines = result.splitlines()
        assert lines[0] == "c"

    def test_read_with_limit(self, temp_dir):
        path = temp_dir / "many.txt"
        path.write_text("\n".join(str(i) for i in range(20)))
        result = file_mod.fs_read_file(str(path), limit=5)
        assert len(result.splitlines()) == 5

    def test_read_nonexistent(self, temp_dir):
        result = file_mod.fs_read_file(str(temp_dir / "nope.txt"))
        assert "Error" in result


class TestWriteFile:
    """fs_write_file with workspace guard."""

    def test_write_inside_workspace(self, temp_dir, monkeypatch):
        monkeypatch.setattr(file_mod, "_WORKSPACE", str(temp_dir))
        path = temp_dir / "output.txt"
        result = file_mod.fs_write_file(str(path), "hello world")
        assert "Written" in result
        assert path.exists()

    def test_write_creates_parent_dirs(self, temp_dir, monkeypatch):
        monkeypatch.setattr(file_mod, "_WORKSPACE", str(temp_dir))
        path = temp_dir / "deep" / "nested" / "file.txt"
        result = file_mod.fs_write_file(str(path), "deep content")
        assert "Written" in result
        assert path.exists()

    def test_write_outside_workspace_blocked(self, temp_dir, monkeypatch):
        monkeypatch.setattr(file_mod, "_WORKSPACE", str(temp_dir))
        result = file_mod.fs_write_file("/tmp/should_not_exist_test.txt", "bad")
        assert "disallowed" in result.lower()

    def test_write_sensitive_blocked(self, temp_dir, monkeypatch):
        monkeypatch.setattr(file_mod, "_WORKSPACE", str(temp_dir))
        path = temp_dir / ".env"
        result = file_mod.fs_write_file(str(path), "SECRET=123")
        assert "sensitive" in result.lower()


class TestSearchFiles:
    """fs_search_files with workspace guard."""

    def test_search_finds_content(self, temp_dir, monkeypatch):
        monkeypatch.setattr(file_mod, "_WORKSPACE", str(temp_dir))
        (temp_dir / "a.txt").write_text("hello world")
        (temp_dir / "b.txt").write_text("goodbye world")
        result = file_mod.fs_search_files("hello", path=str(temp_dir))
        assert "a.txt" in result or "hello world" in result

    def test_search_with_file_glob(self, temp_dir, monkeypatch):
        monkeypatch.setattr(file_mod, "_WORKSPACE", str(temp_dir))
        (temp_dir / "a.txt").write_text("needle")
        (temp_dir / "b.py").write_text("needle")
        result = file_mod.fs_search_files("needle", path=str(temp_dir), file_glob="*.py")
        assert "b.py" in result or "needle" in result

    def test_search_outside_workspace_blocked(self, temp_dir, monkeypatch):
        monkeypatch.setattr(file_mod, "_WORKSPACE", str(temp_dir))
        result = file_mod.fs_search_files("root", path="/root")
        assert "disallowed" in result.lower()

    def test_search_nonexistent_dir(self, temp_dir):
        result = file_mod.fs_search_files("x", path=str(temp_dir / "nope"))
        assert "Error" in result
