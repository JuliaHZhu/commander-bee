"""
Cron job management tool for Worker Bee.

Unified action-oriented tool to avoid schema/context bloat.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

sys.path.insert(0, str(Path(__file__).parent.parent))

from worker_bee.registry import registry
from cron.jobs import (
    AmbiguousJobReference,
    create_job,
    get_job,
    list_jobs,
    pause_job,
    remove_job,
    resolve_job_ref,
    resume_job,
    trigger_job,
    update_job,
)


def _canonical_skills(skill: Optional[str] = None, skills: Optional[Any] = None) -> List[str]:
    if skills is None:
        raw_items = [skill] if skill else []
    elif isinstance(skills, str):
        raw_items = [skills]
    else:
        raw_items = list(skills)

    normalized: List[str] = []
    for item in raw_items:
        text = str(item or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _repeat_display(job: Dict[str, Any]) -> str:
    times = (job.get("repeat") or {}).get("times")
    completed = (job.get("repeat") or {}).get("completed", 0)
    if times is None:
        return "forever"
    if times == 1:
        return "once" if completed == 0 else "1/1"
    return f"{completed}/{times}" if completed else f"{times} times"


def _format_job(job: Dict[str, Any]) -> Dict[str, Any]:
    prompt = str(job.get("prompt") or "")
    skills = _canonical_skills(job.get("skill"), job.get("skills"))
    job_id = str(job.get("id") or "unknown")
    name = str(
        job.get("name")
        or prompt[:50]
        or (skills[0] if skills else "")
        or job_id
        or "cron job"
    )
    result = {
        "job_id": job_id,
        "name": name,
        "skill": skills[0] if skills else None,
        "skills": skills,
        "prompt_preview": prompt[:100] + "..." if len(prompt) > 100 else prompt,
        "model": job.get("model"),
        "provider": job.get("provider"),
        "base_url": job.get("base_url"),
        "schedule": job.get("schedule_display") or "?",
        "repeat": _repeat_display(job),
        "deliver": job.get("deliver", "local"),
        "next_run_at": job.get("next_run_at"),
        "last_run_at": job.get("last_run_at"),
        "last_status": job.get("last_status"),
        "last_error": job.get("last_error"),
        "last_delivery_error": job.get("last_delivery_error"),
        "enabled": job.get("enabled", True),
        "state": job.get("state", "scheduled" if job.get("enabled", True) else "paused"),
        "paused_at": job.get("paused_at"),
        "paused_reason": job.get("paused_reason"),
        "created_at": job.get("created_at"),
    }
    if job.get("script"):
        result["script"] = job["script"]
    if job.get("no_agent"):
        result["no_agent"] = True
    if job.get("enabled_toolsets"):
        result["enabled_toolsets"] = job["enabled_toolsets"]
    if job.get("workdir"):
        result["workdir"] = job["workdir"]
    if job.get("context_from"):
        result["context_from"] = job["context_from"]
    return result


def _tool_error(message: str, success: bool = False) -> str:
    return json.dumps({"success": success, "error": message}, indent=2)


def _normalize_deliver_param(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        parts = [str(p).strip() for p in value if str(p).strip()]
        return ",".join(parts) if parts else None
    text = str(value).strip()
    return text or None


def cronjob(
    action: str,
    job_id: Optional[str] = None,
    prompt: Optional[str] = None,
    schedule: Optional[str] = None,
    name: Optional[str] = None,
    repeat: Optional[int] = None,
    deliver: Optional[str] = None,
    include_disabled: bool = False,
    skill: Optional[str] = None,
    skills: Optional[List[str]] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    reason: Optional[str] = None,
    script: Optional[str] = None,
    context_from: Optional[Union[str, List[str]]] = None,
    enabled_toolsets: Optional[List[str]] = None,
    workdir: Optional[str] = None,
    no_agent: Optional[bool] = None,
) -> str:
    """Unified cron job management tool.

    Actions:
        create  — Create a new cron job (requires schedule).
        list    — List all jobs.
        update  — Update a job (requires job_id).
        pause   — Pause a job (requires job_id).
        resume  — Resume a paused job (requires job_id).
        run / trigger — Schedule a job to run on the next tick (requires job_id).
        remove  — Delete a job (requires job_id).
    """
    try:
        normalized = (action or "").strip().lower()

        if normalized == "create":
            if not schedule:
                return _tool_error("schedule is required for create")
            canonical_skills = _canonical_skills(skill, skills)
            _no_agent = bool(no_agent)
            if _no_agent and not script:
                return _tool_error(
                    "create with no_agent=True requires a script — the script is the job."
                )
            if not prompt and not canonical_skills and not _no_agent:
                return _tool_error(
                    "create requires either prompt or at least one skill"
                )

            # Validate context_from references existing jobs
            if context_from:
                refs = [context_from] if isinstance(context_from, str) else context_from
                for ref_id in refs:
                    if not get_job(ref_id):
                        return _tool_error(
                            f"context_from job '{ref_id}' not found. "
                            f"Use cronjob(action='list') to see available jobs."
                        )

            job = create_job(
                prompt=prompt or "",
                schedule=schedule,
                name=name,
                repeat=repeat,
                deliver=_normalize_deliver_param(deliver),
                origin=None,
                skills=canonical_skills,
                model=model or None,
                provider=provider or None,
                base_url=base_url or None,
                script=script or None,
                context_from=context_from,
                enabled_toolsets=enabled_toolsets or None,
                workdir=workdir or None,
                no_agent=_no_agent,
            )
            return json.dumps(
                {
                    "success": True,
                    "job_id": job["id"],
                    "name": job["name"],
                    "skill": job.get("skill"),
                    "skills": job.get("skills", []),
                    "schedule": job["schedule_display"],
                    "repeat": _repeat_display(job),
                    "deliver": job.get("deliver", "local"),
                    "next_run_at": job["next_run_at"],
                    "job": _format_job(job),
                    "message": f"Cron job '{job['name']}' created.",
                },
                indent=2,
            )

        if normalized == "list":
            jobs = [_format_job(j) for j in list_jobs(include_disabled=include_disabled)]
            return json.dumps({"success": True, "count": len(jobs), "jobs": jobs}, indent=2)

        if not job_id:
            return _tool_error(f"job_id is required for action '{normalized}'")

        try:
            job = resolve_job_ref(job_id)
        except AmbiguousJobReference as exc:
            return json.dumps(
                {
                    "success": False,
                    "error": str(exc),
                    "matches": [
                        {
                            "id": m["id"],
                            "name": m.get("name"),
                            "schedule": m.get("schedule_display"),
                            "next_run_at": m.get("next_run_at"),
                        }
                        for m in exc.matches
                    ],
                },
                indent=2,
            )
        if not job:
            return json.dumps(
                {
                    "success": False,
                    "error": f"Job with ID or name '{job_id}' not found. Use cronjob(action='list') to inspect jobs.",
                },
                indent=2,
            )

        job_id = job["id"]

        if normalized == "remove":
            removed = remove_job(job_id)
            if not removed:
                return _tool_error(f"Failed to remove job '{job_id}'")
            return json.dumps(
                {
                    "success": True,
                    "message": f"Cron job '{job['name']}' removed.",
                    "removed_job": {
                        "id": job_id,
                        "name": job["name"],
                        "schedule": job.get("schedule_display"),
                    },
                },
                indent=2,
            )

        if normalized == "pause":
            updated = pause_job(job_id, reason=reason)
            return json.dumps({"success": True, "job": _format_job(updated)}, indent=2)

        if normalized == "resume":
            updated = resume_job(job_id)
            return json.dumps({"success": True, "job": _format_job(updated)}, indent=2)

        if normalized in {"run", "run_now", "trigger"}:
            updated = trigger_job(job_id)
            return json.dumps({"success": True, "job": _format_job(updated)}, indent=2)

        if normalized == "update":
            updates: Dict[str, Any] = {}
            if prompt is not None:
                updates["prompt"] = prompt
            if name is not None:
                updates["name"] = name
            if deliver is not None:
                updates["deliver"] = _normalize_deliver_param(deliver)
            if skills is not None or skill is not None:
                canonical_skills = _canonical_skills(skill, skills)
                updates["skills"] = canonical_skills
                updates["skill"] = canonical_skills[0] if canonical_skills else None
            if model is not None:
                updates["model"] = model.strip() or None
            if provider is not None:
                updates["provider"] = provider.strip() or None
            if base_url is not None:
                updates["base_url"] = base_url.strip().rstrip("/") or None
            if script is not None:
                updates["script"] = script.strip() or None
            if context_from is not None:
                if isinstance(context_from, str):
                    refs = [context_from.strip()] if context_from.strip() else []
                else:
                    refs = [str(j).strip() for j in context_from if str(j).strip()]
                if refs:
                    for ref_id in refs:
                        if not get_job(ref_id):
                            return _tool_error(
                                f"context_from job '{ref_id}' not found. "
                                f"Use cronjob(action='list') to see available jobs."
                            )
                updates["context_from"] = refs or None
            if enabled_toolsets is not None:
                updates["enabled_toolsets"] = (
                    [str(t).strip() for t in enabled_toolsets if str(t).strip()]
                    if enabled_toolsets else None
                )
            if workdir is not None:
                updates["workdir"] = workdir.strip() or None
            if no_agent is not None:
                updates["no_agent"] = bool(no_agent)
                if bool(no_agent) and not (updates.get("script") or job.get("script")):
                    return _tool_error(
                        "no_agent=True requires a script. Set script first."
                    )

            updated = update_job(job_id, updates)
            if not updated:
                return _tool_error(f"Failed to update job '{job_id}'")
            return json.dumps({"success": True, "job": _format_job(updated)}, indent=2)

        return _tool_error(f"Unknown action: '{action}'. Use create/list/update/pause/resume/run/remove.")

    except ValueError as e:
        return _tool_error(str(e))
    except Exception as e:
        return _tool_error(f"Cron tool error: {e}")


registry.register(
    name="cronjob",
    description="Manage cron jobs (create, list, update, pause, resume, run, remove).",
    parameters={
        "properties": {
            "action": {
                "type": "string",
                "description": "Action to perform",
                "enum": ["create", "list", "update", "pause", "resume", "run", "remove"]
            },
            "job_id": {
                "type": "string",
                "description": "Job ID or name (required for update/pause/resume/run/remove)"
            },
            "prompt": {
                "type": "string",
                "description": "The task prompt for the agent"
            },
            "schedule": {
                "type": "string",
                "description": "Schedule expression: '30m' (once), 'every 30m' (recurring), '0 9 * * *' (cron), or ISO timestamp"
            },
            "name": {"type": "string", "description": "Human-readable name"},
            "repeat": {"type": "integer", "description": "Number of times to run. Omit for infinite."},
            "deliver": {
                "type": "string",
                "description": "Delivery target: 'local', 'origin', 'feishu', 'discord', 'all', or comma-separated list"
            },
            "include_disabled": {"type": "boolean", "description": "Include paused jobs in list"},
            "skill": {"type": "string", "description": "Single skill to load (legacy)"},
            "skills": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of skills to load before running"
            },
            "model": {"type": "string", "description": "Override model for this job"},
            "provider": {"type": "string", "description": "Override provider for this job"},
            "base_url": {"type": "string", "description": "Override base URL for this job"},
            "reason": {"type": "string", "description": "Reason for pausing"},
            "script": {"type": "string", "description": "Path to a script to run instead of an agent"},
            "context_from": {
                "oneOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}}
                ],
                "description": "Upstream job ID(s) whose output is injected as context"
            },
            "enabled_toolsets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tool names to enable for this job"
            },
            "workdir": {"type": "string", "description": "Working directory for script execution"},
            "no_agent": {"type": "boolean", "description": "Run script directly without an LLM agent"}
        },
        "required": ["action"]
    },
    handler=cronjob,
    tags=["cron", "infra"],
    category="infra"
)
