"""Subagent tools — single, parallel, and cross-validation delegation."""
import os
import json
import concurrent.futures
from typing import List, Dict, Optional
from agent.registry import registry


def _make_agent_config(
    model: Optional[str] = None,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    tools: Optional[List[str]] = None,
    max_iterations: int = 10,
    system_prompt: str = "",
) -> dict:
    """Build an AIAgent config dict, falling back to environment variables."""
    # Basic api_key validation when explicitly provided
    if api_key is not None and (not api_key or not api_key.strip()):
        raise ValueError("Invalid api_key: must be a non-empty string")
    # Provider resolution
    prov = provider or os.environ.get("LITE_PROVIDER", "anthropic")
    # API key resolution — try provider-specific env vars first
    key = api_key
    if not key:
        if prov == "openai":
            key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ARKCODE_API_KEY", "")
        else:
            key = os.environ.get("ARKCODE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
    # Base URL resolution
    base = base_url
    if not base:
        if prov == "openai":
            base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        else:
            base = os.environ.get("ARKCODE_BASE_URL", "https://ark.cn-beijing.volces.com/api/coding")
    # Model resolution
    mdl = model or os.environ.get("LITE_MODEL", "kimi-k2.6")

    default_system = (
        "You are a focused sub-agent working on a specific subtask. "
        "Work independently and return a concise final answer."
    )
    return {
        "model": mdl,
        "provider": prov,
        "api_key": key,
        "base_url": base,
        "max_iterations": max_iterations,
        "system_prompt": system_prompt or default_system,
        "tools": tools or [],
    }


def _run_single_agent(config: dict, messages: List[Dict]) -> str:
    """Instantiate AIAgent and run one-shot."""
    from agent.agent import AIAgent
    agent = AIAgent(config)
    return agent.run(messages)


# ───────────────────────────────────────────────────────────────
# 1. Single sub-agent (serial)
# ───────────────────────────────────────────────────────────────
def agent_delegate_task(
    goal: str,
    context: str = "",
    tools: Optional[list] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    max_iterations: int = 10
) -> str:
    """Delegate an independent subtask to a child agent.

    The child agent gets a fresh context (no access to parent conversation).
    It can use a subset of tools and returns a final summary.
    """
    config = _make_agent_config(
        model=model, provider=provider, api_key=api_key, base_url=base_url,
        tools=tools, max_iterations=max_iterations
    )
    if context:
        messages = [{"role": "user", "content": f"Context: {context}\n\nTask: {goal}"}]
    else:
        messages = [{"role": "user", "content": goal}]
    return _run_single_agent(config, messages)


# ───────────────────────────────────────────────────────────────
# 2. Parallel sub-agents
# ───────────────────────────────────────────────────────────────
def agent_delegate_parallel(
    tasks: list,
    max_workers: int = 3
) -> str:
    """Spawn multiple child agents in parallel.

    Each entry in `tasks` is a dict with keys:
      - goal (required)
      - context (optional)
      - tools (optional)
      - model (optional)
      - provider (optional)
      - api_key (optional)
      - base_url (optional)
      - max_iterations (optional, default 10)

    Returns a JSON string mapping task index → result string.
    """
    def _run_one(idx: int, task: dict) -> tuple:
        goal = task["goal"]
        ctx = task.get("context", "")
        config = _make_agent_config(
            model=task.get("model"),
            provider=task.get("provider"),
            api_key=task.get("api_key"),
            base_url=task.get("base_url"),
            tools=task.get("tools"),
            max_iterations=task.get("max_iterations", 10),
        )
        if ctx:
            messages = [{"role": "user", "content": f"Context: {ctx}\n\nTask: {goal}"}]
        else:
            messages = [{"role": "user", "content": goal}]
        try:
            result = _run_single_agent(config, messages)
        except Exception as e:
            result = f"DELEGATE_ERROR: {e}"
        return idx, result

    results: Dict[int, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_run_one, i, t): i for i, t in enumerate(tasks)}
        for fut in concurrent.futures.as_completed(futures):
            idx, res = fut.result()
            results[idx] = res

    # Preserve task order
    ordered = {str(i): results[i] for i in range(len(tasks))}
    return json.dumps(ordered, ensure_ascii=False, indent=2)


# ───────────────────────────────────────────────────────────────
# 3. Cross-validation — same task, multiple models
# ───────────────────────────────────────────────────────────────
def agent_cross_validate(
    goal: str,
    context: str = "",
    models: Optional[list] = None,
    tools: Optional[list] = None,
    judge: bool = True,
    max_iterations: int = 10
) -> str:
    """Run the same task through multiple models and return a comparison.

    Args:
        goal: The task to perform.
        context: Additional context.
        models: List of model identifiers, e.g. ["kimi-k2.6", "gpt-4o"].
                Defaults to a single run with the default model.
        tools: Tool names available to each sub-agent.
        judge: If True, a final judge agent summarises agreements / disagreements.
        max_iterations: Max tool-use iterations per sub-agent.

    Returns:
        JSON string with keys:
          - results: dict {model_name: answer}
          - judge_summary: str (empty if judge=False)
    """
    models = models or [os.environ.get("LITE_MODEL", "kimi-k2.6")]
    tasks = []
    for m in models:
        tasks.append({
            "goal": goal,
            "context": context,
            "tools": tools,
            "model": m,
            "max_iterations": max_iterations,
        })

    parallel_result = agent_delegate_parallel(tasks, max_workers=len(models))
    raw = json.loads(parallel_result)

    # Map index -> model name for readability
    results = {}
    for i, m in enumerate(models):
        results[m] = raw.get(str(i), "")

    judge_summary = ""
    if judge and len(models) > 1:
        judge_prompt = (
            "You are an impartial judge. Multiple models were asked the same question.\n\n"
            f"Question: {goal}\n\n"
            + "\n\n".join(f"--- {m} ---\n{ans}" for m, ans in results.items())
            + "\n\nPlease summarize:\n"
            "1. Where do the answers agree?\n"
            "2. Where do they disagree or show different emphases?\n"
            "3. Which answer seems most accurate or complete, and why?\n"
            "Keep it concise."
        )
        judge_config = _make_agent_config(max_iterations=5)
        judge_config["system_prompt"] = "You are a critical evaluator comparing multiple AI outputs."
        try:
            judge_summary = _run_single_agent(judge_config, [{"role": "user", "content": judge_prompt}])
        except Exception as e:
            judge_summary = f"Judge error: {e}"

    return json.dumps({
        "results": results,
        "judge_summary": judge_summary
    }, ensure_ascii=False, indent=2)


# ───────────────────────────────────────────────────────────────
# Registry registration
# ───────────────────────────────────────────────────────────────
registry.register(
    name="agent_delegate_task",
    description=(
        "Delegate an independent subtask to a child agent. "
        "Use for parallelizable work or when the main task can be broken into smaller pieces. "
        "The sub-agent has a fresh context and does not see the parent conversation."
    ),
    parameters={
        "properties": {
            "goal": {"type": "string", "description": "Clear description of what the sub-agent should accomplish"},
            "context": {"type": "string", "description": "Additional context the sub-agent needs", "default": ""},
            "tools": {"type": "array", "items": {"type": "string"}, "description": "List of tool names the sub-agent may use", "default": []},
            "model": {"type": "string", "description": "Override model for this sub-agent", "default": ""},
            "provider": {"type": "string", "description": "Override provider (anthropic|openai)", "default": ""},
            "api_key": {"type": "string", "description": "Override API key", "default": ""},
            "base_url": {"type": "string", "description": "Override base URL", "default": ""},
            "max_iterations": {"type": "integer", "description": "Max tool-use iterations", "default": 10}
        },
        "required": ["goal"]
    },
    handler=agent_delegate_task,
    tags=["agent", "delegate", "subtask"],
    category="agent"
)

registry.register(
    name="agent_delegate_parallel",
    description=(
        "Delegate multiple independent subtasks to child agents in parallel. "
        "Each task runs in its own thread with a fresh context. "
        "Returns a JSON map of task index → result."
    ),
    parameters={
        "properties": {
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "goal": {"type": "string"},
                        "context": {"type": "string", "default": ""},
                        "tools": {"type": "array", "items": {"type": "string"}, "default": []},
                        "model": {"type": "string", "default": ""},
                        "provider": {"type": "string", "default": ""},
                        "api_key": {"type": "string", "default": ""},
                        "base_url": {"type": "string", "default": ""},
                        "max_iterations": {"type": "integer", "default": 10}
                    },
                    "required": ["goal"]
                },
                "description": "List of task dicts"
            },
            "max_workers": {"type": "integer", "description": "Max parallel threads", "default": 3}
        },
        "required": ["tasks"]
    },
    handler=agent_delegate_parallel,
    tags=["agent", "delegate", "parallel", "subtask"],
    category="agent"
)

registry.register(
    name="agent_cross_validate",
    description="Run the same task through multiple LLMs and compare their answers.",
    parameters={
        "properties": {
            "goal": {"type": "string", "description": "The task to validate"},
            "context": {"type": "string", "description": "Additional context", "default": ""},
            "models": {"type": "array", "items": {"type": "string"}, "description": "List of model names to compare", "default": []},
            "tools": {"type": "array", "items": {"type": "string"}, "description": "Tool names available to sub-agents", "default": []},
            "judge": {
                "type": "boolean",
                "description": (
                    "If true, a judge agent summarises agreement and disagreement across outputs. "
                    "Useful for filtering hallucinations or getting a second opinion."
                ),
                "default": True
            },
            "max_iterations": {"type": "integer", "description": "Max iterations per sub-agent", "default": 10}
        },
        "required": ["goal"]
    },
    handler=agent_cross_validate,
    tags=["agent", "cross-validate", "judge", "hallucination-filter"],
    category="agent"
)
