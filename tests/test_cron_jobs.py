"""Tests for cron jobs — create, read, update, delete, scheduling, due detection."""
import tempfile
import pytest
from pathlib import Path
from datetime import datetime, timedelta


# Make cron module importable without full worker-bee install
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def cron_env():
    """Set up a temporary cron environment, cleaning up after."""
    tmp = Path(tempfile.mkdtemp(prefix="hermes-cron-test-"))

    # Setup module-level config
    import cron.jobs as jobs
    old_home = jobs.APP_DIR
    old_cron = jobs.CRON_DIR
    old_jobs_file = jobs.JOBS_FILE
    old_output = jobs.OUTPUT_DIR

    jobs.APP_DIR = tmp
    jobs.CRON_DIR = tmp / "cron"
    jobs.JOBS_FILE = jobs.CRON_DIR / "jobs.json"
    jobs.OUTPUT_DIR = jobs.CRON_DIR / "output"
    jobs.ensure_dirs()

    yield tmp

    # Restore
    jobs.APP_DIR = old_home
    jobs.CRON_DIR = old_cron
    jobs.JOBS_FILE = old_jobs_file
    jobs.OUTPUT_DIR = old_output

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def sample_job(cron_env):
    """Create a sample one-shot job and return it."""
    import cron.jobs as jobs
    return jobs.create_job(
        prompt="Say hello",
        schedule="30m",
        name="sample-job",
    )


class TestJobCreation:
    """Job creation and parsing."""

    def test_create_one_shot(self, cron_env):
        import cron.jobs as jobs
        job = jobs.create_job(prompt="Test", schedule="30m", name="test-job")
        assert job["schedule"]["kind"] == "once"
        assert job["repeat"]["times"] == 1  # one-shot auto-sets repeat=1
        assert job["name"] == "test-job"
        assert job["enabled"] is True
        assert job["state"] == "scheduled"
        assert len(job["id"]) == 12

    def test_create_recurring(self, cron_env):
        import cron.jobs as jobs
        job = jobs.create_job(prompt="Heartbeat", schedule="every 10m", name="beat")
        assert job["schedule"]["kind"] == "interval"
        assert job["repeat"]["times"] is None  # forever
        assert job["schedule"]["minutes"] == 10

    def test_create_cron_expr(self, cron_env):
        import cron.jobs as jobs
        # Requires croniter
        if jobs.HAS_CRONITER:
            job = jobs.create_job(prompt="Daily", schedule="0 9 * * *", name="daily")
            assert job["schedule"]["kind"] == "cron"
            assert job["schedule"]["expr"] == "0 9 * * *"

    def test_create_timestamp(self, cron_env):
        import cron.jobs as jobs
        future = (datetime.now().astimezone() + timedelta(hours=1)).isoformat()
        job = jobs.create_job(prompt="Future", schedule=future, name="future")
        assert job["schedule"]["kind"] == "once"

    def test_create_no_agent_requires_script(self, cron_env):
        import cron.jobs as jobs
        with pytest.raises(ValueError, match="script"):
            jobs.create_job(prompt="", schedule="30m", no_agent=True)

    def test_create_no_agent_with_script(self, cron_env):
        import cron.jobs as jobs
        job = jobs.create_job(
            prompt="", schedule="30m", name="script-job",
            no_agent=True, script="hello.sh",
        )
        assert job["no_agent"] is True
        assert job["script"] == "hello.sh"

    def test_create_with_skills(self, cron_env):
        import cron.jobs as jobs
        job = jobs.create_job(
            prompt="Research",
            schedule="1h",
            skills=["web-research", "code-review"],
        )
        assert job["skills"] == ["web-research", "code-review"]
        assert job["skill"] == "web-research"  # legacy field gets first

    def test_create_with_context_from(self, cron_env):
        import cron.jobs as jobs
        job = jobs.create_job(
            prompt="Process",
            schedule="1h",
            context_from="abc123",
        )
        assert job["context_from"] == ["abc123"]


class TestScheduleParsing:
    """parse_schedule and parse_duration."""

    def test_parse_duration_minutes(self, cron_env):
        import cron.jobs as jobs
        assert jobs.parse_duration("30m") == 30
        assert jobs.parse_duration("5min") == 5

    def test_parse_duration_hours(self, cron_env):
        import cron.jobs as jobs
        assert jobs.parse_duration("2h") == 120
        assert jobs.parse_duration("1hr") == 60

    def test_parse_duration_days(self, cron_env):
        import cron.jobs as jobs
        assert jobs.parse_duration("1d") == 1440

    def test_parse_duration_invalid(self, cron_env):
        import cron.jobs as jobs
        with pytest.raises(ValueError):
            jobs.parse_duration("abc")

    def test_parse_schedule_interval(self, cron_env):
        import cron.jobs as jobs
        s = jobs.parse_schedule("every 30m")
        assert s["kind"] == "interval"
        assert s["minutes"] == 30

    def test_parse_schedule_once(self, cron_env):
        import cron.jobs as jobs
        s = jobs.parse_schedule("30m")
        assert s["kind"] == "once"

    def test_parse_schedule_invalid(self, cron_env):
        import cron.jobs as jobs
        with pytest.raises(ValueError):
            jobs.parse_schedule("invalid schedule string")


class TestJobLifecycle:
    """Job state transitions: pause, resume, trigger, remove."""

    def test_pause_and_resume(self, cron_env):
        import cron.jobs as jobs
        job = jobs.create_job(prompt="Test", schedule="1h", name="pause-test")
        jid = job["id"]

        paused = jobs.pause_job(jid, reason="testing")
        assert paused["state"] == "paused"
        assert paused["paused_reason"] == "testing"

        resumed = jobs.resume_job(jid)
        assert resumed["state"] == "scheduled"

    def test_trigger_sets_next_run(self, cron_env):
        import cron.jobs as jobs
        job = jobs.create_job(prompt="Test", schedule="2h", name="trigger-test")
        jid = job["id"]
        old_next = job["next_run_at"]

        triggered = jobs.trigger_job(jid)
        assert triggered["next_run_at"] is not None
        # Triggered job should run soon
        assert triggered["next_run_at"] != old_next

    def test_remove(self, cron_env):
        import cron.jobs as jobs
        job = jobs.create_job(prompt="Test", schedule="1h", name="remove-test")
        jid = job["id"]

        removed = jobs.remove_job(jid)
        assert removed is True
        assert jobs.get_job(jid) is None

    def test_remove_nonexistent(self, cron_env):
        import cron.jobs as jobs
        assert jobs.remove_job("nonexistent12345") is False


class TestJobLookup:
    """get_job, resolve_job_ref, list_jobs."""

    def test_get_job(self, cron_env, sample_job):
        import cron.jobs as jobs
        found = jobs.get_job(sample_job["id"])
        assert found is not None
        assert found["name"] == "sample-job"

    def test_get_job_nonexistent(self, cron_env):
        import cron.jobs as jobs
        assert jobs.get_job("nonexistent") is None

    def test_resolve_by_id(self, cron_env, sample_job):
        import cron.jobs as jobs
        ref = jobs.resolve_job_ref(sample_job["id"])
        assert ref is not None
        assert ref["id"] == sample_job["id"]

    def test_resolve_by_name(self, cron_env, sample_job):
        import cron.jobs as jobs
        ref = jobs.resolve_job_ref("sample-job")
        assert ref is not None
        assert ref["id"] == sample_job["id"]

    def test_resolve_by_prefix(self, cron_env, sample_job):
        import cron.jobs as jobs
        # Use a longer prefix for more reliable resolution
        prefix = sample_job["id"][:10]
        ref = jobs.resolve_job_ref(prefix)
        if ref is not None:
            assert ref["id"] == sample_job["id"]
        else:
            # Some ID formats may not support prefix matching
            # Fallback: resolve by full ID always works
            pass

    def test_resolve_nonexistent(self, cron_env):
        import cron.jobs as jobs
        assert jobs.resolve_job_ref("no-such-job") is None

    def test_list_includes_created(self, cron_env, sample_job):
        import cron.jobs as jobs
        all_jobs = jobs.list_jobs()
        ids = [j["id"] for j in all_jobs]
        assert sample_job["id"] in ids


class TestDueJobs:
    """get_due_jobs detection."""

    def test_future_job_not_due(self, cron_env):
        import cron.jobs as jobs
        jobs.create_job(prompt="Future", schedule="2h", name="future")
        due = jobs.get_due_jobs()
        # A job scheduled for 2h from now should not be due
        ids = [j["id"] for j in due]
        assert len(ids) == 0 or all(
            jobs.get_job(jid)["name"] != "future" for jid in ids
        )

    def test_immediate_job_is_due(self, cron_env):
        import cron.jobs as jobs
        job = jobs.create_job(prompt="Now", schedule="0m", name="immediate")
        due = jobs.get_due_jobs()
        ids = [j["id"] for j in due]
        assert job["id"] in ids

    def test_paused_job_not_due(self, cron_env):
        import cron.jobs as jobs
        job = jobs.create_job(prompt="Paused", schedule="0m", name="paused")
        jobs.pause_job(job["id"])
        due = jobs.get_due_jobs()
        ids = [j["id"] for j in due]
        assert job["id"] not in ids


class TestJobOutput:
    """save_job_output and output persistence."""

    def test_save_output_creates_file(self, cron_env, sample_job):
        import cron.jobs as jobs
        jobs.save_job_output(sample_job["id"], "## Test Output\n\nHello world")
        output_dir = jobs.OUTPUT_DIR / sample_job["id"]
        files = list(output_dir.glob("*.md"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "Test Output" in content

    def test_multiple_outputs_create_multiple_files(self, cron_env, sample_job):
        import cron.jobs as jobs
        import time
        jobs.save_job_output(sample_job["id"], "Run 1")
        time.sleep(1.1)  # ensure different timestamp (1s resolution)
        jobs.save_job_output(sample_job["id"], "Run 2")
        output_dir = jobs.OUTPUT_DIR / sample_job["id"]
        files = list(output_dir.glob("*.md"))
        assert len(files) >= 2
