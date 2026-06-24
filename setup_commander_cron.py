#!/usr/bin/env python3
"""Setup CommanderBee cronjobs.

Creates 4 cronjobs:
  1. heartbeat-monitor — every 60s
  2. dispatch-scan — every 120s
  3. timeout-check — every 300s
  4. daily-report — 0 9 * * *
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cron.jobs import create_job, load_jobs, save_jobs


def setup():
    jobs = load_jobs()

    # Remove existing commander jobs
    jobs = [j for j in jobs if not j.get("id", "").startswith("cmdr-")]

    new_jobs = [
        create_job(
            prompt="Run monitor_tick() to check bee heartbeats and job timeouts.",
            schedule="every 1m",
            name="[CB] Heartbeat Monitor",
            skills=["commander-monitor"],
        ),
        create_job(
            prompt="Run dispatch_scan() to auto-dispatch created jobs to matching Worker Bees.",
            schedule="every 2m",
            name="[CB] Dispatch Scan",
            skills=["commander-dispatch"],
        ),
        create_job(
            prompt="Run monitor_tick() for timeout checks (accept + execute timeouts).",
            schedule="every 5m",
            name="[CB] Timeout Check",
            skills=["commander-monitor"],
        ),
        create_job(
            prompt="Run report_generate() and send daily status report to user.",
            schedule="0 9 * * *",
            name="[CB] Daily Report",
            skills=["commander-report"],
        ),
    ]

    # create_job returns a dict; we need to add ids
    for j, jid in zip(new_jobs, ["cmdr-heartbeat", "cmdr-dispatch", "cmdr-timeout", "cmdr-daily"]):
        j["id"] = jid

    jobs.extend(new_jobs)
    save_jobs(jobs)
    print(f"Created {len(new_jobs)} CommanderBee cronjobs.")
    for j in new_jobs:
        print(f"  - {j['id']}: {j['name']} ({j.get('schedule_display', '?')})")


if __name__ == "__main__":
    setup()
