"""Integration tests for cron scheduler — tick() with no_agent scripts."""
import os
import tempfile
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def cron_scheduler_env():
    """Set up cron environment with temp workspace."""
    tmp = Path(tempfile.mkdtemp(prefix="hermes-cron-sched-"))

    import cron.jobs as jobs
    imported_scheduler = __import__('cron.scheduler', fromlist=['scheduler'])
    sched = imported_scheduler

    old_home = jobs.APP_DIR
    old_cron = jobs.CRON_DIR
    old_jobs_file = jobs.JOBS_FILE
    old_output = jobs.OUTPUT_DIR

    jobs.APP_DIR = tmp
    jobs.CRON_DIR = tmp / "cron"
    jobs.JOBS_FILE = jobs.CRON_DIR / "jobs.json"
    jobs.OUTPUT_DIR = jobs.CRON_DIR / "output"
    jobs.ensure_dirs()

    # Mock config for the tick
    mock_cfg = {
        "model": "test-model",
        "provider": "test",
        "api_key": "***",
        "base_url": "https://example.com",
        "max_iterations": 5,
        "system_prompt": "test",
        "tools": [],
    }

    yield tmp, mock_cfg, sched, jobs

    # Restore
    jobs.APP_DIR = old_home
    jobs.CRON_DIR = old_cron
    jobs.JOBS_FILE = old_jobs_file
    jobs.OUTPUT_DIR = old_output

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


class TestSchedulerNoAgent:
    """End-to-end: no_agent cron job execution."""

    def test_no_agent_script_runs_and_writes_output(self, cron_scheduler_env, monkeypatch):
        tmp, config, sched, jobs = cron_scheduler_env

        # Create a script INSIDE the workspace
        script_path = tmp / "test.sh"
        script_path.write_text("#!/bin/bash\necho 'Hello from cron test script'\necho 'Line 2'")
        os.chmod(script_path, 0o755)

        # Patch the scheduler module-level _CRON_WORKSPACE
        monkeypatch.setattr(sched, "_CRON_WORKSPACE", str(tmp))

        # Create a no_agent job with immediate schedule
        job = jobs.create_job(
            prompt="",
            schedule="0m",
            name="scheduler-e2e",
            no_agent=True,
            script=str(script_path),
            deliver="local",
        )

        # Run tick
        count = sched.tick(config)
        assert count >= 1

        # Check output saved
        output_dir = jobs.OUTPUT_DIR / job["id"]
        files = sorted(output_dir.glob("*.md"))
        assert len(files) >= 1
        content = files[0].read_text(encoding="utf-8")
        assert "Hello from cron test script" in content

    def test_no_agent_script_outside_workspace_blocked(self, cron_scheduler_env):
        tmp, config, sched, jobs = cron_scheduler_env

        # Script outside workspace
        outside_script = Path("/tmp/hermes-cron-test-outside.sh")
        outside_script.write_text("#!/bin/bash\necho 'outside'")
        os.chmod(outside_script, 0o755)

        os.environ["WORKER_BEE_WORKSPACE"] = str(tmp)

        try:
            jobs.create_job(
                prompt="",
                schedule="0m",
                name="outside-test",
                no_agent=True,
                script=str(outside_script),
                deliver="local",
            )

            count = sched.tick(config)
            # Should not crash, the job should just fail gracefully
            assert count >= 1
        finally:
            del os.environ["WORKER_BEE_WORKSPACE"]
            try:
                outside_script.unlink()
            except OSError:
                pass

    def test_no_agent_missing_script(self, cron_scheduler_env):
        tmp, config, sched, jobs = cron_scheduler_env

        os.environ["WORKER_BEE_WORKSPACE"] = str(tmp)

        try:
            jobs.create_job(
                prompt="",
                schedule="0m",
                name="missing-script",
                no_agent=True,
                script="/nonexistent/script.sh",
                deliver="local",
            )

            count = sched.tick(config)
            # Should not crash
            assert count >= 1
        finally:
            del os.environ["WORKER_BEE_WORKSPACE"]
