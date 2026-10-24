import asyncio
import click
import json
import os
from pathlib import Path
import uuid as _uuid
import logging
import statistics as stats # Used internally by ResearchManager, ModelRouterOptimizer
from typing import Optional, List, Any

# --- Core Components ---
# from quentin.config.settings import Settings # Settings might still be used by AgentRuntime, though not directly in new CL
# from quentin.runtime.agent_runtime import AgentRuntime # Removed as new CL is standalone

from quentin.cognitive.loop import CognitiveLoop, CognitiveTask, CognitiveResult
from quentin.traces.execution_trace import ExecutionTrace, ExecutionTraceStore

# --- LLM Related ---
from quentin.models.router import ModelRouter # New ModelRouter
from quentin.llm.router_optimize import ModelRouterOptimizer # New ModelRouterOptimizer
# from quentin.llm.multi_council import MultiAICouncil # Used by various components' default init, not directly in CLI handlers
# from quentin.llm.client import call_llm # Assuming this is available, but not directly used in CLI handlers

# --- Memory & Research ---
from quentin.memory.fabric import MemoryFabric # New MemoryFabric
from quentin.memory.models import MemoryQuery, MemoryTier
try:
    from quentin.l3.research.experiments import ResearchManager  # New ResearchManager
except Exception:
    class ResearchManager:  # Fallback stub to unblock CLI basics
        def __init__(self, *a, **k): pass
        def list_experiments(self): return []
        def list_runs(self, *a, **k): return []
        def compare_variants(self, *a, **k): return []
        def export_results(self, *a, **k): return None

try:
    from quentin.self_programming.engine import SelfProgrammingEngine, PatchTaskSpec, PatchResult  # New SelfProgrammingEngine
except Exception:
    class PatchTaskSpec:
        def __init__(self, *a, **k): pass
    class PatchResult:
        def __init__(self, *a, **k): pass
    class SelfProgrammingEngine:
        def __init__(self, *a, **k): pass
        async def run_patch_pipeline(self, *a, **k): return None
        async def run_cycle_for_gap(self, *a, **k): return None
from quentin.self_programming.legacy_selfprog.registry import FileBackedPatchRegistry
from quentin.self_programming.legacy_selfprog.apply import PatchApplier
from quentin.blueprint.tracker import BlueprintGapTracker, BlueprintScanReport
from quentin.blueprint.auto_patcher import BlueprintGapAutoPatcher # New BlueprintGapAutoPatcher
from quentin.self_programming.skill_impl import (
    SkillImplementationEngine,
    SkillImplementationRequest,
)
from quentin.cli.commands_pg import pg_group
from quentin.llm.client import call_llm as _call_llm
from quentin.runtime.brain_daemon import brain_daemon_from_env
from quentin.runtime.task_queue import TaskQueue, TaskQueueItem
from quentin.runtime.task_sources import run_task_sources_once
from quentin.runtime.silent_protocol import is_silent_reply
from quentin.runtime.system_events import SystemEventQueue
from quentin.runtime.output_projection import visible_output_from_brain_events

# --- Skills ---
from quentin.skills.manager import SkillManager, SkillSpec, SKILL_STATUS_CANDIDATE, SKILL_STATUS_ACTIVE, SKILL_STATUS_DEPRECATED # New SkillManager
from quentin.skills.registry import FileBackedSkillRegistry # Note: This is now SkillRegistry (not FileBackedSkillRegistry) and its schema is different
# from quentin.skills.evolution import SkillEvolutionEngine # New SkillEvolutionEngine - used by sleep_loop

# --- Policy & Budget ---
from quentin.kernel.policy import PolicyEngine, ActionRequest, PolicyDecision # New PolicyEngine
from quentin.kernel.budget import BudgetController, BudgetDecision # New BudgetController
# from quentin.kernel.safety import SafetyKernel, GuardResult # SafetyKernel is used internally by SelfProgEngine/PolicyEngine

# --- Loops ---
from quentin.loops.immune_loop import ImmuneLoop, ImmuneConfig # New ImmuneLoop from loops directory
try:
    from quentin.loops.sleep_loop import SleepLoop, SleepConfig # New SleepLoop from loops directory
except Exception:
    class SleepConfig:
        def __init__(self, *a, **k): pass
    class SleepLoop:
        def __init__(self, *a, **k): pass
        def run_once(self): return {}

# --- Goals & Done ---
from quentin.goals.done_definition import GoalDoneManager, GoalSpec, DoneCheckContext, DoneCheckResult # New Goal/Done


logger = logging.getLogger(__name__)

# --- Dummy call_llm if not explicitly defined yet ---
# This is needed by CognitiveLoop and other components, but not directly in CLI handlers.
# It should be defined in quentin.llm.client.py. For the CLI to run, we assume it's available.
# We will not redefine it here.


@click.group()
def cli():
    """
    Project Quentin CLI for self-evolving agent management.
    """
    pass
cli.add_command(pg_group)


# --- Task Management ---

@cli.command("run-task")
@click.option("--input-text", type=str, required=True, help="Natural language description of the task.")
@click.option("--task-id", type=str, default="", help="Optional explicit task_id (if empty, a UUID will be generated).")
@click.option("--session-id", type=str, default="", help="Optional session_id to serialize tasks within the same session lane.")
@click.option("--domain", type=str, default="core", help="Domain of the task (default: core).")
@click.option("--environment", type=str, default="sandbox", help="Environment (default: sandbox).")
@click.option("--goal-title", type=str, default=None, help="Optional short title for the goal.")
@click.option("--goal-description", type=str, default=None, help="Optional detailed description for the goal.")
@click.option("--success-criteria", type=str, multiple=True, help="Success criteria (can be repeated).")
@click.option("--hard-constraints", type=str, multiple=True, help="Hard constraints (can be repeated).")
@click.option("--soft-preferences", type=str, multiple=True, help="Soft preferences (can be repeated).")
def cmd_run_task(
    input_text: str,
    task_id: str,
    session_id: str,
    domain: str,
    environment: str,
    goal_title: Optional[str],
    goal_description: Optional[str],
    success_criteria: tuple[str, ...],
    hard_constraints: tuple[str, ...],
    soft_preferences: tuple[str, ...],
) -> None:
    """
    Run a generic task through the Cognitive Loop.
    """
    import sys
    import time
    
    task_id = task_id or str(_uuid.uuid4())

    task = CognitiveTask(
        input_text=input_text,
        task_id=task_id,
        domain=domain,
        environment=environment,
        goal_title=goal_title,
        goal_description=goal_description,
        success_criteria=list(success_criteria),
        hard_constraints=list(hard_constraints),
        soft_preferences=list(soft_preferences),
        metadata={"session_id": session_id} if session_id else {},
    )

    # Use the DI container so CLI always runs the canonical wiring (loops/managers/policies).
    from quentin.bootstrap.container import Container

    container = Container()
    loop = container.cognitive_loop

    async def run_and_wait():
        from quentin.infra.concurrency.lanes import enqueue, resolve_session_lane

        lane = resolve_session_lane(session_id or "cli")

        async def _run() -> Any:
            return await asyncio.to_thread(loop.run_task, task)

        return await enqueue(lane, _run, global_lane="main")

    async def main_with_heartbeat():
        task_coro = asyncio.create_task(run_and_wait())
        while not task_coro.done():
            # Heartbeat to prevent tool timeout
            sys.stderr.write(".")
            sys.stderr.flush()
            await asyncio.sleep(15.0)
        sys.stderr.write("\n")
        return await task_coro

    result = asyncio.run(main_with_heartbeat())

    print(f"Task ID     : {result.task_id}")
    print(f"Goal ID     : {result.goal_id}")
    print(f"Is Done     : {result.done}")
    print(f"Confidence  : {result.done_confidence:.3f}")
    print(f"Plan summary:\n{result.plan_summary}")
    print(f"Actions summary:\n{result.actions_summary}")
    print("\nFinal output:\n")
    queue = SystemEventQueue(repo_root=".")
    stream_text = visible_output_from_brain_events(
        queue.list_brain_events(session_id=session_id or task_id, limit=500),
        turn_id=task_id,
    )
    if stream_text and not is_silent_reply(stream_text):
        print(stream_text)
    print("\nDone Council Reasons:")
    for r in result.done_result.reasons:
        print(f"- {r}")
    if result.done_result.violated_constraints:
        print("\nViolated constraints:")
        for vc in result.done_result.violated_constraints:
            print(f"- {vc}")
    if result.done_result.improvement_suggestions:
        print("\nImprovement suggestions:")
        for s in result.done_result.improvement_suggestions:
            print(f"- {s}")
    return


@cli.command("llm-smoke")
@click.option("--provider", type=str, default="", help="Provider override (openai|gemini|deepseek|openrouter|ollama). Defaults to env/provider inference.")
@click.option("--model", type=str, default="", help="Model override (defaults to env LLM_MODEL).")
@click.option("--system", type=str, default="You are a helpful assistant.", help="System prompt.")
@click.option("--prompt", type=str, required=True, help="User prompt.")
def cmd_llm_smoke(provider: str, model: str, system: str, prompt: str) -> None:
    """
    Smoke test LLM execution via the canonical `quentin.llm.client.call_llm`.

    This can run against local Ollama or remote providers (opt-in via env).
    """
    model_id = model.strip() or os.getenv("LLM_MODEL", "").strip()
    if not model_id:
        raise click.ClickException("Missing model: pass --model or set env LLM_MODEL")
    prov = provider.strip().lower() or None
    out = _call_llm(
        model_id,
        user_prompt=prompt,
        system_prompt=system,
        provider=prov,
        model_name=model_id,
        actor="qctl_llm_smoke",
        domain=os.getenv("QUENTIN_DOMAIN", "core"),
        environment=os.getenv("QUENTIN_ENV", "sandbox"),
        risk_level=os.getenv("QUENTIN_RISK", "medium"),
        action_metadata={"topic": "llm_smoke"},
    )
    click.echo(out)


@cli.command("brain-run")
@click.option("--input-text", type=str, required=True, help="Task input text to run each iteration.")
@click.option("--max-iterations", type=int, default=1, help="0 means forever; default 1.")
def cmd_brain_run(input_text: str, max_iterations: int) -> None:
    """
    Run the minimal "brain runs itself" loop:
    CognitiveLoop -> (optional) SleepLoop -> (optional) ImmuneLoop.

    Configure via env:
    - `LLM_STUB=1` for offline deterministic runs
    - `LLM_PROVIDER` + keys for real external LLM
    - `QUENTIN_TRACES_DIR`, `QUENTIN_AUDIT_PATH`, `QUENTIN_POLICY_DECISIONS_PATH` for isolated outputs
    """
    daemon = brain_daemon_from_env()
    if max_iterations == 1:
        out = daemon.run_once(input_text=input_text, metadata={"source": "qctl_brain_run"})
        click.echo(json.dumps(out, ensure_ascii=False, indent=2))
        return
    daemon.run_forever(input_text=input_text, max_iterations=int(max_iterations))


@cli.command("bench-tool-adaptation")
@click.option("--repo-root", type=str, default=".", help="Repository root (default: .).")
@click.option(
    "--output",
    type=str,
    default="generated/benchmarks/tool_adaptation_benchmark_report.json",
    help="Output report path.",
)
@click.option(
    "--previous",
    type=str,
    default="generated/benchmarks/tool_adaptation_benchmark_prev.json",
    help="Previous report path.",
)
@click.option(
    "--history",
    type=str,
    default="generated/benchmarks/tool_adaptation_benchmark_history.jsonl",
    help="History JSONL path.",
)
@click.option("--domain-bucket", type=str, default="global", help="Calibration domain bucket label.")
@click.option("--min-score", type=float, default=0.70, help="Minimum quality score threshold.")
@click.option("--moving-window", type=int, default=5, help="Trend guard moving-average window.")
@click.option("--trend-drop-tolerance", type=float, default=0.05, help="Allowed drop below moving average.")
@click.option("--ci-mode", is_flag=True, default=False, help="Enable deterministic CI mode.")
@click.option("--enforce-schema/--no-enforce-schema", default=True, help="Whether schema validation gates pass/fail.")
@click.option("--case-timeout-ms", type=int, default=6500, help="Per-case timeout budget in milliseconds.")
@click.option("--strict-timeouts/--soft-timeouts", default=True, help="Whether timeout budget failures fail benchmark.")
@click.option(
    "--schema-file",
    type=str,
    default="quentin/benchmarks/schemas/tool_adaptation_report.schema.json",
    help="JSON schema path used for strict report validation.",
)
@click.option("--deterministic-fixtures/--no-deterministic-fixtures", default=True, help="Enable deterministic fixture mode.")
@click.option("--auto-tune-weights/--no-auto-tune-weights", default=True, help="Enable history-driven weight autotuning.")
@click.option(
    "--trend-ndjson-output",
    type=str,
    default="generated/benchmarks/tool_adaptation_trend.ndjson",
    help="Append trend row to NDJSON path.",
)
def cmd_bench_tool_adaptation(
    repo_root: str,
    output: str,
    previous: str,
    history: str,
    domain_bucket: str,
    min_score: float,
    moving_window: int,
    trend_drop_tolerance: float,
    ci_mode: bool,
    enforce_schema: bool,
    case_timeout_ms: int,
    strict_timeouts: bool,
    schema_file: str,
    deterministic_fixtures: bool,
    auto_tune_weights: bool,
    trend_ndjson_output: str,
) -> None:
    """
    Benchmark tool management & adaptation:
    plugins/skills discovery, governance gates, memory writeback, cache.
    """
    from quentin.benchmarks.tool_adaptation import run_benchmark as _run_tool_bench

    report = _run_tool_bench(
        repo_root=Path(repo_root),
        output=Path(output),
        previous=Path(previous) if previous else None,
        history=Path(history) if history else None,
        min_score=float(min_score),
        domain_bucket=str(domain_bucket or "global"),
        moving_window=int(moving_window),
        trend_drop_tolerance=float(trend_drop_tolerance),
        ci_mode=bool(ci_mode),
        enforce_schema=bool(enforce_schema),
        case_timeout_ms=int(case_timeout_ms),
        strict_timeouts=bool(strict_timeouts),
        schema_file=Path(schema_file) if schema_file else None,
        deterministic_fixtures=bool(deterministic_fixtures),
        auto_tune_weights=bool(auto_tune_weights),
        trend_ndjson_output=Path(trend_ndjson_output) if trend_ndjson_output else None,
    )
    click.echo(
        json.dumps(
            {
                "quality_score": report.get("quality_score"),
                "min_score": report.get("min_score"),
                "pass": report.get("pass"),
                "improved_vs_previous": report.get("improved_vs_previous"),
                "previous_score": report.get("previous_score"),
                "top_issue_keys": [str(x.get("key") or "") for x in (report.get("issues") or [])[:8]],
                "top_weaknesses": report.get("top_weaknesses"),
                "trend_guard": report.get("trend_guard"),
                "schema_ok": ((report.get("schema_validation") or {}).get("ok")),
                "timeout_summary": report.get("timeout_summary"),
                "regression": report.get("regression_explain"),
                "remediation_queue_size": len(report.get("remediation_queue") or []),
                "replay": report.get("replay"),
                "weight_tuning": report.get("weight_tuning"),
                "output": str(output),
            },
            ensure_ascii=False,
        )
    )
    if not bool(report.get("pass")):
        raise click.ClickException("tool adaptation benchmark failed")


@cli.command("task-enqueue")
@click.option("--input-text", type=str, required=True, help="Task input text.")
@click.option("--domain", type=str, default="core", help="Domain (default: core).")
@click.option("--environment", type=str, default="sandbox", help="Environment (default: sandbox).")
@click.option("--session-id", type=str, default="", help="Optional session id.")
@click.option("--priority", type=int, default=0, help="Higher runs first.")
def cmd_task_enqueue(input_text: str, domain: str, environment: str, session_id: str, priority: int) -> None:
    q = TaskQueue(repo_root=".")
    item = TaskQueueItem.new(
        input_text=input_text,
        domain=domain,
        environment=environment,
        session_id=session_id,
        priority=priority,
        metadata={"source": "qctl_task_enqueue"},
    )
    q.append(item)
    click.echo(item.task_id)


@cli.command("task-run-queue")
@click.option("--max-tasks", type=int, default=1, help="0 means run forever; default 1.")
@click.option("--worker-id", type=str, default="", help="Worker id to claim tasks.")
def cmd_task_run_queue(max_tasks: int, worker_id: str) -> None:
    daemon = brain_daemon_from_env()
    wid = worker_id.strip() or os.getenv("QUENTIN_WORKER_ID", "qctl-worker")
    daemon.run_queue_forever(worker_id=wid, max_tasks=int(max_tasks))


@cli.command("task-source-run")
@click.option("--max-blueprint-tasks", type=int, default=25, help="Max tasks from blueprint gap source.")
def cmd_task_source_run(max_blueprint_tasks: int) -> None:
    """
    Run task sources once and enqueue maintenance tasks.

    Configure via env:
    - `QUENTIN_TASK_SOURCE_BLUEPRINT=0|1` (default 1)
    - `QUENTIN_TASK_SOURCE_OBS=0|1` (default 1)
    """
    import asyncio
    r = asyncio.run(run_task_sources_once(repo_root=".", max_blueprint_tasks=int(max_blueprint_tasks)))
    click.echo(json.dumps(r.to_dict(), ensure_ascii=False, indent=2))


@cli.command("wake")
@click.option("--session-id", type=str, default="global", help="Session id for wake event routing.")
@click.option("--text", type=str, required=True, help="Wake message text.")
@click.option("--event-type", type=str, default="background_task_done", help="Event type.")
@click.option("--source", type=str, default="qctl", help="Event source label.")
def cmd_wake(session_id: str, text: str, event_type: str, source: str) -> None:
    """
    Emit a wake event into SystemEventQueue for async/background task callbacks.
    """
    raw = (os.getenv("QUENTIN_WAKE_ENABLED", "true") or "").strip().lower()
    if raw not in ("1", "true", "yes", "on"):
        click.echo(json.dumps({"ok": False, "error": "wake_disabled"}, ensure_ascii=False))
        return
    q = SystemEventQueue(repo_root=".")
    event = q.enqueue_event(
        session_id=str(session_id or "global"),
        event_type=str(event_type or "background_task_done"),
        payload={"message": str(text or "").strip(), "status": "done"},
        source=str(source or "qctl"),
    )
    click.echo(json.dumps({"ok": True, "event_id": event.event_id, "session_id": event.session_id, "event_type": event.event_type}, ensure_ascii=False))


# --- Skill Management ---

# cmd_skill_list_candidates is deprecated due to schema changes.
@cli.command("skill-list-candidates")
def cmd_skill_list_candidates_deprecated() -> None:
    """
    List mined SkillCandidates (Deprecated: uses old schema).
    """
    print("DEPRECATED: This command uses an outdated SkillCandidate schema.")
    print("Use 'skills-sync' to merge candidates into the new registry and then 'skills-list'.")

# cmd_skill_show_candidate is deprecated due to schema changes.
@cli.command("skill-show-candidate")
@click.option("--candidate-id", type=str, required=True, help="ID of the SkillCandidate to show.")
def cmd_skill_show_candidate_deprecated(candidate_id: str) -> None:
    """
    Show details of a SkillCandidate by ID (Deprecated: uses old schema).
    """
    print("DEPRECATED: This command uses an outdated SkillCandidate schema.")
    print("Please inspect the data/skills.jsonl file directly for raw candidates if needed.")

# cmd_skill_mine_from_goal is deprecated due to schema changes.
@cli.command("skill-mine-from-goal")
@click.option("--goal", type=str, required=True, help="Goal to run and mine skill from.")
@click.option("--domain", type=str, default="general", help="Domain of the goal (default: general).")
def cmd_skill_mine_from_goal_deprecated(goal: str, domain: str) -> None:
    """
    Run a goal once through CognitiveLoop and mine a SkillCandidate from it (Deprecated: uses old schema).
    """
    print("DEPRECATED: This command is deprecated due to outdated CognitiveLoop and SkillCandidate schemas.")
    print("The skill mining process is now integrated into SleepLoop's 'skills_extraction'.")

# cmd_skill_list (old) is deprecated, replaced by skills-list
# @cli.command("skill-list")
# def cmd_skill_list_deprecated() -> None:
#     """
#     List registered Skills (SkillDefinition) (Deprecated: uses old schema).
#     """
#     print("WARNING: This command is deprecated. Use 'skills-list' instead.")

# cmd_skill_promote_candidate is deprecated due to schema changes.
@cli.command("skill-promote-candidate")
@click.option("--candidate-id", type=str, required=True, help="ID of the SkillCandidate to promote.")
@click.option("--auto", is_flag=True, help="Mark this promotion as auto (for research metrics).")
def cmd_skill_promote_candidate_deprecated(candidate_id: str, auto: bool) -> None:
    """
    Promote a SkillCandidate to SkillDefinition using SkillPromotionEngine (Deprecated: uses old schema).
    """
    print("DEPRECATED: This command uses outdated SkillCandidate/SkillDefinition schemas.")
    print("Skill promotion is now part of SleepLoop's automated process via SkillEvolutionEngine.")


# cmd_skill_run (old) still valid, but using new SkillManager/FileBackedSkillRegistry
@cli.command("skill-run")
@click.option("--skill-id", type=str, required=True, help="ID of the Skill to run.")
@click.option("--input-json", type=str, required=True, help='Input JSON string, e.g. \'{\"text\": \"hello\"}\'')
@click.option("--text-output", is_flag=True, help="If set, do not force JSON output parsing.")
def cmd_skill_run(skill_id: str, input_json: str, text_output: bool) -> None:
    """
    Run a registered Skill with JSON input via MultiAICouncil.
    (Note: This command uses the updated SkillManager and registry, but the execution logic might need more integration.)
    """
    mgr = SkillManager() # This now uses the new SkillManager
    skill = mgr.registry.get(skill_id) # Using new registry .get()
    if not skill:
        print(f"Skill not found: {skill_id}")
        return

    try:
        input_payload = json.loads(input_json)
    except Exception as e:
        print(f"Failed to parse input-json: {e}")
        return

    # SkillManager.run_skill does not exist in the new SkillManager
    # This command needs to be re-evaluated for how it runs a skill
    print("WARNING: 'skill-run' command is under refactoring. Direct skill execution is not yet exposed via this CLI.")
    # For now, this is a placeholder. A proper implementation would invoke a CognitiveLoop run with the skill.


@cli.command("skill-evolve-once")
def cmd_skill_evolve_once_deprecated() -> None:
    """
    Run the Skill Evolution loop once (Deprecated: uses old schema).
    """
    print("DEPRECATED: Skill evolution is now integrated into SleepLoop.")


@cli.command("skills-sync")
def cmd_skills_sync() -> None:
    """
    Sync skills from SleepLoop candidates into the skill registry.
    """
    mgr = SkillManager()
    changed = mgr.sync_from_candidates()
    print(f"Skills synced from candidates. Changed/created: {changed}")


@cli.command("skills-list")
@click.option("--status", type=str, default=None, help="Filter by status: candidate/active/deprecated")
@click.option("--domain", type=str, default=None, help="Filter by domain (core/desktop/legal/trading/...) ")
@click.option("--implemented", type=str, default=None, help="Filter by implemented flag: true/false")
def cmd_skills_list(status: Optional[str], domain: Optional[str], implemented: Optional[str]) -> None:
    """
    List skills in the registry.
    """
    implemented_bool: Optional[bool] = None
    if implemented is not None:
        v = implemented.strip().lower()
        if v in ("true", "1", "yes"):
            implemented_bool = True
        elif v in ("false", "0", "no"):
            implemented_bool = False

    mgr = SkillManager()
    skills = mgr.list_skills(
        status=status,
        domain=domain,
        implemented=implemented_bool,
    )
    print(f"Total skills: {len(skills)}")
    for sk in skills:
        impl_flag = "Y" if sk.is_implemented else "N"
        print(
            f"- {sk.skill_id[:8]} | {sk.status:10s} | impl={impl_flag} | "
            f"{sk.domain:8s} | {sk.title}"
        )


@cli.command("skills-suggest")
@click.argument("text", type=str)
@click.option("--domain", type=str, default=None, help="Domain of task: core/desktop/legal/trading/...")
@click.option("--top-k", type=int, default=5, help="Max number of skills to return.")
def cmd_skills_suggest(text: str, domain: Optional[str], top_k: int) -> None:
    """
    Suggest relevant skills for a given task text.
    """
    mgr = SkillManager()
    suggestions = mgr.suggest_for_task(
        task_text=text,
        domain=domain,
        top_k=top_k,
        include_candidates=True,
    )
    print(f"Suggested skills for domain={domain or '*'} text='{text[:40]}...':")
    for s in suggestions:
        print(
            f"- {s['skill_id'][:8]} | score={s['score']:.2f} | "
            f"{s['status']:10s} | impl={s['implemented']} | {s['title']}"
        )


# --- Self-programming (New) ---

@cli.command("selfprog-patch")
@click.option("--target", type=str, required=True, help="Target Python file path, relative to repo root (e.g. 'quentin/cognitive/loop_impl.py').")
@click.option("--reason", type=str, required=True, help="Reason for patch (natural language).")
@click.option("--domain", type=str, default="core", help="Domain label, e.g. core/desktop/legal/trading (default: core).")
@click.option("--environment", type=str, default="sandbox", help="Execution environment: sandbox/staging/prod (default: sandbox).")
@click.option("--risk-level", type=str, default="high", help="Risk level: low/medium/high/critical (default: high).")
@click.option("--context-snippet", type=str, default="", help="Optional context snippet for the LLM.")
def cmd_selfprog_patch(target: str, reason: str, domain: str, environment: str, risk_level: str, context_snippet: str) -> None:
    """
    Run a self-programming patch attempt on a target Python file.
    """
    engine = SelfProgrammingEngine()
    task = PatchTaskSpec(
        target_path=target,
        reason=reason,
        domain=domain,
        environment=environment,
        risk_level=risk_level,
        context_snippet=context_snippet,
    )
    result = engine.propose_and_apply_patch(task)

    print(f"Task ID    : {result.task_id}")
    print(f"Target     : {result.target_path}")
    print(f"Success    : {result.success}")
    print(f"Applied    : {result.applied}")
    print(f"Guard      : {result.guard.reason}")
    print(f"Policy ok? : {result.guard.policy_decision.allow}")
    print(f"Budget ok? : {result.guard.budget_decision.allow}")
    if result.test_result:
        print(f"Tests pass : {result.test_result.passed}")
    if result.gate_result:
        print(f"Gate appr? : {result.gate_result.approved}")
        print(f"Gate summary:\n{result.gate_result.council_summary}\n")

    if result.error:
        print("Error:")
        print(result.error)
    else:
        print("\nNew code preview (first 20 lines):\n")
        print(result.new_code_preview)


# --- Old Self-programming commands (Deprecated or Replaced by selfprog-patch) ---

@cli.command("patch-propose")
@click.option("--target-path", type=str, required=True, help="Repo-relative path to the target file.")
@click.option("--problem", type=str, required=True, help="Description of the problem or improvement goal.")
@click.option("--change-type", type=str, default="refactor", help="Change type, e.g. bugfix/refactor/optimize.")
@click.option("--target-symbol", type=str, default=None, help="Optional function/class name to focus on.")
def cmd_patch_propose_deprecated(target_path: str, problem: str, change_type: str, target_symbol: Optional[str]) -> None:
    """
    Propose a self-programming patch (Deprecated: use 'selfprog-patch').
    """
    print("DEPRECATED: 'patch-propose' is deprecated. Use 'selfprog-patch' for the new workflow.")

@cli.command("patch-list")
@click.option("--status", type=str, default=None, help="Filter by status: proposed/evaluated/approved/rejected/applied.")
def cmd_patch_list(status: Optional[str]) -> None:
    """
    List known patches in the registry.
    """
    registry = FileBackedPatchRegistry()
    patches = registry.list_patches(status=status)
    if not patches:
        print("No patches found.")
        return

    print(f"Found {len(patches)} patches:")
    for p in patches:
        print(
            f"- {p.patch_id} | {p.status} | risk={p.risk_level} | "
            f"{p.target_path}::{p.target_symbol or ''}"
        )


@cli.command("patch-show")
@click.option("--patch-id", type=str, required=True, help="ID of the patch to show.")
def cmd_patch_show(patch_id: str) -> None:
    """
    Show details of a specific patch.
    """
    registry = FileBackedPatchRegistry()
    patch = registry.get_patch(patch_id)
    if not patch:
        print(f"Patch not found: {patch_id}")
        return

    print(f"Patch {patch.patch_id}")
    print(f"- target_path : {patch.target_path}")
    print(f"- target_sym  : {patch.target_symbol}")
    print(f"- change_type : {patch.change_type}")
    print(f"- status      : {patch.status}")
    print(f"- risk_level  : {patch.risk_level}")
    print(f"- created_by  : {patch.created_by}")
    print(f"- created_at  : {patch.created_at}")
    print(f"- updated_at  : {patch.updated_at}")
    print(f"- intent      : {patch.intent}\n")

    print("=== PATCH TEXT (truncated) ===")
    print(patch.patch_text[:4000])

    print("\n=== TESTS (truncated) ===")
    print(patch.tests[:2000])

    if patch.eval_report:
        er = patch.eval_report
        print("\n=== EVAL REPORT ===")
        print(f"- ok         : {er.ok}")
        print(f"- score      : {er.score}")
        print(f"- risk_level : {er.risk_level}")
        if er.issues:
            print("- issues:")
            for i in er.issues:
                print(f"  * {i}")
        if er.warnings:
            print("- warnings:")
            for w in er.warnings:
                print(f"  * {w}")


@cli.command("patch-eval")
@click.option("--patch-id", type=str, required=True, help="ID of the patch to evaluate.")
def cmd_patch_eval_deprecated(patch_id: str) -> None:
    """
    Run static evaluation for a patch (Deprecated: now part of selfprog-patch workflow).
    """
    print("DEPRECATED: 'patch-eval' is deprecated as standalone. Evaluation is part of 'selfprog-patch' workflow.")
    # The new SelfProgrammingEngine.propose_and_apply_patch already does evaluation internally.
    # If a standalone evaluation is needed, it would require significant refactor of eval logic.


@cli.command("patch-gate")
@click.option("--patch-id", type=str, required=True, help="ID of the patch to review.")
@click.option("--env", type=str, default="staging", help="Requested environment: staging or prod (default: staging).")
def cmd_patch_gate_deprecated(patch_id: str, env: str) -> None:
    """
    Run multi-AI gate council for a patch (Deprecated: now part of selfprog-patch workflow).
    """
    print("DEPRECATED: 'patch-gate' is deprecated. Gating is part of 'selfprog-patch' workflow.")


@cli.command("patch-apply")
@click.option("--patch-id", type=str, required=True, help="ID of the patch to apply.")
@click.option("--env", type=str, default="staging", help="Environment for apply: staging or prod (default: staging).")
@click.option("--no-gate", is_flag=True, help="If set, do not require gate_decision=approve (for manual experiments).")
def cmd_patch_apply_deprecated(patch_id: str, env: str, no_gate: bool) -> None:
    """
    Apply an approved patch to the codebase (Deprecated: now part of selfprog-patch workflow).
    """
    print("DEPRECATED: 'patch-apply' is deprecated. Application is part of 'selfprog-patch' workflow.")


@cli.command("patch-rollback")
@click.option("--patch-id", type=str, required=True, help="ID of the patch to rollback.")
def cmd_patch_rollback_deprecated(patch_id: str) -> None:
    """
    Rollback an applied patch using its backup file (Deprecated: now part of selfprog-patch workflow).
    """
    print("DEPRECATED: 'patch-rollback' is deprecated. Rollback is part of 'selfprog-patch' workflow.")


# --- Blueprint Management ---

@cli.command("blueprint-scan")
@click.option("--blueprint-path", type=str, default="blueprint/spec_v3.json", help="Path to blueprint JSON spec (default: blueprint/spec_v3.json).")
@click.option("--emit-evidence", is_flag=True, help="Emit deterministic offline evidence (traces + baseline experiments) before scanning.")
def cmd_blueprint_scan(blueprint_path: str, emit_evidence: bool) -> None:
    """
    Scan repo against blueprint spec_v3 and show completion summary.
    """
    if emit_evidence:
        from quentin.blueprint.evidence_emitter import emit_blueprint_spec_v3_evidence

        emit_blueprint_spec_v3_evidence(repo_root=".", spec_path=blueprint_path)
    tracker = BlueprintGapTracker(spec_path=blueprint_path)
    report = tracker.scan()

    print(f"Blueprint version : {report.version}")
    print(f"Scanned at        : {report.scanned_at}")
    print(f"Total items       : {report.total_items}")
    print(f"Average score     : {report.avg_score:.3f}")
    print("")
    print("Items:")
    for it in report.items:
        item_status = str(getattr(it, "status", "") or "").strip().lower() or ("done" if it.score >= 0.99 else "partial")
        status_flag = "✅" if item_status == "done" else ("❌" if item_status == "missing" else "⚠️")
        print(
            f"{status_flag} {it.spec.id:<30} "
            f"layer={it.spec.layer:<18} "
            f"phase={it.spec.phase:<24} "
            f"status={item_status:<8} "
            f"score={it.score:.2f} "
            f"[files={it.file_implemented}, traces={it.has_traces}, exp={it.has_experiments}]"
        )


@cli.command("blueprint-item")
@click.argument("item_id", type=str)
@click.option("--blueprint-path", type=str, default="blueprint/spec_v3.json", help="Path to blueprint JSON spec (default: blueprint/spec_v3.json).")
def cmd_blueprint_item(item_id: str, blueprint_path: str) -> None:
    """
    Show detailed status for a specific blueprint item ID.
    """
    tracker = BlueprintGapTracker(spec_path=blueprint_path)
    status = tracker.find_item(item_id)
    if not status:
        print(f"No blueprint item found with id: {item_id}")
        return

    it = status
    print(f"ID         : {it.spec.id}")
    print(f"Name       : {it.spec.name}")
    print(f"Layer      : {it.spec.layer}")
    print(f"Phase      : {it.spec.phase}")
    print(f"Category   : {it.spec.category}")
    print(f"Status     : {getattr(it, 'status', 'unknown')}")
    print(f"Confidence : {getattr(it, 'confidence', it.score):.2f}")
    print(f"Score      : {it.score:.2f}")
    print(f"Files      : {it.file_implemented}")
    print(f"Traces     : {it.has_traces} (expected={getattr(it, 'expects_traces', True)})")
    print(f"Experiments: {it.has_experiments} (expected={getattr(it, 'expects_experiments', True)})")
    print("")
    print("Description:")
    print(it.spec.description)
    print("")
    print("Required capabilities:")
    for cap in it.spec.required_capabilities:
        print(f"- {cap}")
    print("")
    print("Hints:")
    for k, v in (it.spec.hints or {{}}).items():
        print(f"- {k}: {v}")


@cli.command("blueprint-autopatch")
@click.option("--blueprint-path", type=str, default="blueprint/spec_v3.json", help="Path to blueprint JSON spec (default: blueprint/spec_v3.json).")
@click.option("--status", type=str, default="missing,partial", help="Comma-separated statuses to target, e.g. 'missing,partial' or 'partial'.")
@click.option("--eval", "auto_eval", is_flag=True, help="If set, run static evaluation for each proposed patch.")
@click.option("--run-selfprog", is_flag=True, help="If set, run SelfProgrammingEngineV2 for targeted gaps (no auto-apply).")
@click.option("--json", is_flag=True, help="Output full report as JSON.")
def cmd_blueprint_autopatch(blueprint_path: str, status: str, auto_eval: bool, run_selfprog: bool, json: bool) -> None:
    """
    Auto-propose patches for missing/partial capabilities from the blueprint.
    """
    statuses = [s.strip() for s in status.split(",") if s.strip()]
    autopatcher = BlueprintGapAutoPatcher(
        blueprint_path=blueprint_path,
    )
    report = autopatcher.propose_patches_for_gaps(
        status_filter=statuses,
        auto_eval=auto_eval,
        run_selfprog=bool(run_selfprog),
    )
    data = report.to_dict()

    if json:
        import json as _json
        print(_json.dumps(data, ensure_ascii=False, indent=2))
        return

    print(f"Blueprint: {data['blueprint_path']}")
    print(
        f"Gaps targeted: {data['total_gaps']} | "
        f"proposed={data['proposed']} | skipped={data['skipped']}"
    )
    print("\nDetails:")
    for d in data["details"]:
        print(
            f"- cap={d['capability_id']} | status_before={d['status_before']} | "
            f"action={d['action']} | patch_id={d['patch_id']} | reason={d['reason']}"
        )


# --- Immune Loop ---

@cli.command("immune-process-trace")
@click.option("--trace-file", type=str, required=True, help="Path to a JSON file containing one ExecutionTrace object.")
def cmd_immune_process_trace(trace_file: str) -> None:
    """
    Process a single ExecutionTrace JSON file via ImmuneLoop.
    """
    import json as _json
    from pathlib import Path as _Path

    p = _Path(trace_file)
    if not p.exists():
        print(f"Trace file not found: {p}")
        return

    try:
        raw = _json.loads(p.read_text(encoding="utf-8") or "{{}}")
    except Exception as e:
        print(f"Failed to parse trace JSON: {e}")
        return

    try:
        trace = ExecutionTrace(
            trace_id=raw.get("trace_id", ""), # Default empty string if not found
            task_id=raw.get("task_id", ""),
            component_id=raw.get("component_id", ""),
            blueprint_capability_id=raw.get("blueprint_capability_id"),
            target_module=raw.get("target_module"),
            target_symbol=raw.get("target_symbol"),
            success=bool(raw.get("success", True)),
            error_type=raw.get("error_type"),
            error_message=raw.get("error_message"),
            start_time=raw.get("start_time") or "",
            end_time=raw.get("end_time") or "",
            metrics=raw.get("metrics") or {{}},
            tags=raw.get("tags") or {{}},
        )
    except Exception as e:
        print(f"Failed to construct ExecutionTrace: {e}")
        return

    _immune_loop = ImmuneLoop()
    immune_case, patch = _immune_loop.process_trace(trace)

    if not immune_case:
        print("No anomaly detected by ImmuneLoop. No ImmuneCase created.")
        return

    print("ImmuneCase created:")
    print(f"- case_id      : {immune_case.case_id}")
    print(f"- component_id : {immune_case.component_id}")
    print(f"- severity     : {immune_case.severity}")
    print(f"- action_type  : {immune_case.action_type}")
    print(f"- summary      : {immune_case.summary}")
    print(f"- reason       : {immune_case.reason}")

    if patch:
        print("\nPatch proposed by ImmuneLoop:")
        print(f"- patch_id     : {patch.patch_id}")
        print(f"- target_path  : {patch.target_path}")
        print(f"- target_sym   : {patch.target_symbol}")
        print(f"- status       : {patch.status}")
        print(f"- risk_level   : {patch.risk_level}")


@cli.command("immune-run")
@click.option("--window-minutes", type=int, default=60, help="Time window (minutes) to analyze traces (default: 60).")
@click.option("--enable-self-fix", is_flag=True, help="Enable automatic self-fix via SelfProgrammingEngine.")
def cmd_immune_run(window_minutes: int, enable_self_fix: bool) -> None:
    """
    Run ImmuneLoop once to detect anomalies and optionally trigger self-fix.
    """
    cfg = ImmuneConfig(
        window_minutes=window_minutes,
        enable_self_fix=bool(enable_self_fix),
        component_to_module={
            "cognitive_loop": "quentin/cognitive/loop_impl.py",
            "immune_loop": "quentin/loops/immune_loop.py",
            "sleep_loop": "quentin/loops/sleep_loop.py",
            "goal_done_definition": "quentin/goals/done_definition.py",
            "self_programming_engine": "quentin/selfprog/engine.py",
            "model_router": "quentin/llm/router.py",
            "memory_fabric": "quentin/memory/fabric.py",
        },
    )
    loop = ImmuneLoop(config=cfg)
    cases = loop.run_once()

    print(f"ImmuneLoop finished. Detected {len(cases)} anomaly cases.")
    for c in cases:
        print(
            f"- case_id={c.case_id} component={c.component_id} "
            f"error_rate={c.error_rate:.2f} severity={c.severity} "
            f"action={c.suggested_action}"
        )


# --- Sleep Loop (New) ---

@cli.command("sleep-run")
@click.option("--hours", type=int, default=24, help="Trace window (hours) for sleep consolidation (default: 24).")
@click.option("--disable-blueprint", is_flag=True, help="Disable blueprint gap scan and patch in this run.")
@click.option("--use-postgres", is_flag=True, help="Force Postgres memory store (else auto-detect by env).")
def cmd_sleep_run(hours: int, disable_blueprint: bool, use_postgres: bool) -> None:
    """
    Run SleepLoop once for memory consolidation and blueprint gap patches.
    """
    # Use DI container so CLI runs canonical SleepLoop wiring.
    from quentin.bootstrap.container import Container

    container = Container()
    loop = container.sleep_loop
    report = asyncio.run(loop.run_once()) if asyncio.iscoroutinefunction(loop.run_once) else loop.run_once()
    if hasattr(report, "to_dict"):
        report = report.to_dict()

    print("SleepLoop finished.")
    print(f"- consolidated_traces   : {report.get('consolidated_traces')}")
    print(f"- procedural_memories   : {report.get('procedural_memories')}")
    print(f"- training_pairs        : {report.get('training_pairs')}")
    print(f"- skill_candidates      : {report.get('skill_candidates')}")
    print(f"- duration_ms           : {report.get('duration_ms')}")
    print(f"- tokens_est            : {report.get('tokens_est')}")


@cli.command("memory-batch-run")
@click.option(
    "--batch",
    type=click.Choice(["nightly", "weekly", "manual"], case_sensitive=False),
    default="nightly",
    help="Batch name to run (default: nightly).",
)
@click.option("--max-records", type=int, default=200, help="Max records to promote/decay in this run.")
@click.option("--max-duration-ms", type=int, default=60_000, help="Max wall time for the batch run.")
@click.option("--max-tokens-est", type=int, default=200_000, help="Max estimated tokens budget.")
@click.option("--no-consolidation", is_flag=True, help="Disable SleepLoop consolidation part for this run.")
def cmd_memory_batch_run(
    batch: str,
    max_records: int,
    max_duration_ms: int,
    max_tokens_est: int,
    no_consolidation: bool,
) -> None:
    """
    Run continual memory automation batch:
    - (optional) consolidation via SleepLoop
    - promotion (STS->MTS, MTS->LTS)
    - decay (STS/MTS TTL)
    """
    from quentin.bootstrap.container import Container
    from quentin.memory.batch_runner import MemoryBatchConfig, MemoryConsolidationBatchRunner

    container = Container()
    runner = MemoryConsolidationBatchRunner(
        fabric=container.memory_fabric,
        config=MemoryBatchConfig(
            enabled=True,
            batch_name=str(batch).lower(),
            max_records=int(max_records or 200),
            max_duration_ms=int(max_duration_ms or 60_000),
            max_tokens_est=int(max_tokens_est or 200_000),
            enable_consolidation=not bool(no_consolidation),
        ),
        sleep_loop=container.sleep_loop if not bool(no_consolidation) else None,
    )

    report = runner.run_once()
    print("Memory batch finished.")
    print(f"- batch_id      : {report.batch_id}")
    print(f"- batch_name    : {report.batch_name}")
    print(f"- promoted      : {report.promoted}")
    print(f"- decayed       : {report.decayed}")
    print(f"- consolidated  : {report.consolidated}")
    print(f"- duration_ms   : {report.duration_ms}")
    print(f"- tokens_est    : {report.tokens_est}")
    print(f"- stopped_reason: {report.stopped_reason}")
    print(f"- errors        : {report.errors}")


@cli.command("memory-export")
@click.option("--output-dir", type=str, default="data/memory_markdown", help="Directory to save markdown files.")
def cmd_memory_export(output_dir: str) -> None:
    """
    Export MemoryFabric records to Markdown files for inspection.
    """
    from quentin.bootstrap.container import Container
    container = Container()
    res = container.memory_fabric.export_to_markdown(output_dir=output_dir)
    print(json.dumps(res, indent=2))


@cli.command("memory-recall")
@click.option("--text", required=True, help="Query text for recall.")
@click.option(
    "--tier",
    type=click.Choice(["STS", "MTS", "LTS", ""], case_sensitive=False),
    default="",
    help="Optional memory tier filter (STS/MTS/LTS).",
)
@click.option("--top-k", type=int, default=5, help="How many records to return.")
@click.option("--domain", type=str, default="", help="Optional domain filter (supports cross-domain by default).")
@click.option("--use-vector/--no-vector", default=True, help="Force vector recall (or force text-only recall).")
def cmd_memory_recall(text: str, tier: str, top_k: int, domain: str, use_vector: bool) -> None:
    """
    Recall memories from MemoryFabric, optionally forcing vector-based retrieval.
    """
    from quentin.bootstrap.container import Container

    container = Container()
    fabric: MemoryFabric = container.memory_fabric

    tier_val = None
    t = (tier or "").strip().upper()
    if t == "STS":
        tier_val = MemoryTier.STS
    elif t == "MTS":
        tier_val = MemoryTier.MTS
    elif t == "LTS":
        tier_val = MemoryTier.LTS

    q = MemoryQuery(
        text=text,
        tier=tier_val,
        top_k=int(top_k or 5),
        domain=(domain.strip() or None),
        include_cross_domain=True,
    )

    if not use_vector:
        # Explicitly disable vector recall for this query.
        saved = getattr(fabric, "embedding_client", None)
        try:
            setattr(fabric, "embedding_client", None)
            records = fabric.recall(q)
        finally:
            setattr(fabric, "embedding_client", saved)
    else:
        # Explicitly request vector recall (if embedding client is available).
        try:
            if getattr(fabric, "embedding_client", None) and q.text:
                q.vector = fabric.embedding_client.embed_text(q.text)  # type: ignore[union-attr]
        except Exception:
            pass
        records = fabric.recall(q)

    print(f"Recall results: {len(records)}")
    for r in records[: int(top_k or 5)]:
        print(f"- id={r.id} tier={r.tier.value} kind={getattr(r, 'kind', '')} domain={getattr(r, 'domain', None)}")
        print(f"  tags={getattr(r, 'tags', [])}")
        print(f"  content={str(getattr(r, 'content', ''))[:200]}")


# --- Policy & Budget (New) ---

@cli.command("policy-show")
@click.option("--decisions-tail", type=int, default=5, help="How many recent decisions to show (default: 5).")
def cmd_policy_show(decisions_tail: int) -> None:
    """
    Show current constitution config and a few recent policy decisions.
    """
    engine = PolicyEngine()
    path = engine.constitution_path
    print(f"Constitution file: {path}")
    if path.exists():
        print(path.read_text(encoding="utf-8"))
    else:
        print("<no constitution file; using in-code defaults>")

    # 再显示几条最新的决策
    dec_path = engine.decision_log_path
    print(f"\nRecent decisions from: {dec_path}")
    if not dec_path.exists():
        print("<no decisions logged yet>")
        return

    lines = dec_path.read_text(encoding="utf-8").splitlines()
    tail = lines[-decisions_tail:] if decisions_tail > 0 else lines
    for line in tail:
        print(line)


@cli.command("budget-show")
def cmd_budget_show() -> None:
    """
    Show budget profiles and current usage state.
    """
    bc = BudgetController()
    print("Budget profiles:")
    for pid, profile in bc._profiles.items():
        print(f"- profile_id : {pid}")
        print(f"  daily_token_limit   : {profile.daily_token_limit}")
        print(f"  monthly_token_limit : {profile.monthly_token_limit}")
        print(f"  daily_usd_limit     : {profile.daily_usd_limit}")
        print(f"  monthly_usd_limit   : {profile.monthly_usd_limit}")
        print(f"  hard_stop           : {profile.hard_stop}")
        print("")

    print("Routing rules:")
    for k, v in bc._routing.items():
        print(f"- {k} -> profile '{v}'")

    print("\nCurrent usage state:")
    if not bc._usage:
        print("<no usage recorded yet>")
        return
    for pid, usage in bc._usage.items():
        print(f"- profile_id : {pid}")
        print(f"  day        : {usage.day}")
        print(f"  month      : {usage.month}")
        print(f"  tokens_today / month : {usage.tokens_today} / {usage.tokens_month}")
        print(f"  usd_today    / month : {usage.usd_today:.4f} / {usage.usd_month:.4f}")
        print("")


# --- Research Management (New) ---

@cli.command("exp-list")
def cmd_exp_list() -> None:
    """
    List all experiments registered in ResearchManager.
    """
    rm = ResearchManager()
    exps = rm.list_experiments()
    if not exps:
        print("No experiments found.")
        return
    print("Experiments:")
    for e in exps:
        print(f"- id={e.experiment_id}")
        print(f"  name        : {e.name}")
        print(f"  purpose     : {e.purpose}")
        print(f"  capability  : {e.capability}")
        print(f"  requirement : {e.requirement_id}")
        print(f"  tags        : {', '.join(e.tags)}")
        print("")


@cli.command("exp-runs")
@click.option("--experiment-id", type=str, required=True, help="Experiment ID.")
def cmd_exp_runs(experiment_id: str) -> None:
    """
    List runs of a given experiment.
    """
    rm = ResearchManager()
    runs = rm.list_runs(experiment_id)
    if not runs:
        print(f"No runs found for experiment {experiment_id}")
        return
    print(f"Runs for experiment {experiment_id}:")
    for r in runs:
        print(f"- run_id   : {r.run_id}")
        print(f"  variant  : {r.variant_id}")
        print(f"  created  : {r.created_at}")
        print(f"  metrics  : {r.metrics}")
        print(f"  context  : {r.context}")
        print("")


@cli.command("exp-compare")
@click.option("--experiment-id", type=str, required=True)
@click.option("--metric", type=str, required=True, help="Metric name.")
@click.option("--top-k", type=int, default=5, help="Number of top variants to show (default: 5).")
@click.option("--higher-is-better", is_flag=True, help="If set, larger metric value is considered better (default: False).")
def cmd_exp_compare(experiment_id: str, metric: str, top_k: int, higher_is_better: bool) -> None:
    """
    Compare variants for an experiment on a given metric.
    """
    rm = ResearchManager()
    results = rm.compare_variants(
        experiment_id=experiment_id,
        metric_name=metric,
        top_k=top_k,
        higher_is_better=bool(higher_is_better),
    )
    if not results:
        print("No variant summaries found for the given metric.")
        return

    print(f"Top {len(results)} variants for experiment={experiment_id}, metric={metric}:")
    for s in results:
        print(f"- variant={s.variant_id}")
        print(f"  count : {s.count}")
        print(f"  mean  : {s.mean:.4f}")
        print(f"  std   : {s.std:.4f}")
        print(f"  min   : {s.min:.4f}")
        print(f"  max   : {s.max:.4f}")
        print("")


@cli.command("exp-export")
@click.option("--experiment-id", type=str, required=True)
@click.option("--output", type=str, required=True, help="Destination JSON file path.")
def cmd_exp_export(experiment_id: str, output: str) -> None:
    """
    Export a full experiment (meta + runs + summaries) to a JSON file.
    """
    rm = ResearchManager()
    try:
        rm.export_results(experiment_id, dest_path=output)
    except Exception as e:
        print(f"Failed to export experiment: {e}")
        return
    print(f"Experiment {experiment_id} exported to {output}")


# --- Router Optimization (New) ---

@cli.command("router-optimize")
@click.option("--weight-latency", type=float, default=0.1, help="Weight for latency penalty in effective score (default: 0.1).")
def cmd_router_optimize(weight_latency: float) -> None:
    """
    Optimize ModelRouter policies based on collected stats.
    """
    opt = ModelRouterOptimizer(weight_latency=weight_latency)
    policies = opt.optimize()
    if not policies:
        print("No policies produced (maybe no stats yet).")
        return

    print("Optimized router policies:")
    for key, p in policies.items():
        print(f"- route      : {p.mode}::{p.task_type}")
        print(f"  model      : {p.model} ({p.provider})")
        print(f"  metric     : {p.metric}")
        print(f"  score      : {p.score:.4f}")
        print(f"  success_rt : {p.success_rate:.3f}")
        print(f"  avg_latency: {p.avg_latency_ms:.1f} ms")
        print(f"  avg_score  : {p.avg_model_score:.3f}")
        print("")


@cli.command("router-show")
def cmd_router_show() -> None:
    """
    Show current ModelRouter rules (from config/model_router_rules.json).
    """
    router = ModelRouter()
    # Directly access internal _rules (CLI tool, acceptable)
    rules = getattr(router, "_rules", {})
    if not rules:
        print("No explicit rules found. Router will use default hardcoded strategies.")
        return
    print("Current ModelRouter rules:")
    for key, r in rules.items():
        print(f"- route  : {key}")
        print(f"  model  : {r.get('model')}")
        print(f"  provider: {r.get('provider')}")
        print(f"  metric : {r.get('metric')}")
        print(f"  score  : {r.get('score')}")
        print("")


@cli.command("mobile-start")
@click.option("--telegram-token", type=str, help="Telegram Bot Token (overrides env)")
@click.option("--discord-token", type=str, help="Discord Bot Token (overrides env)")
@click.option("--slack-tokens", type=str, help="Slack tokens 'app:bot' (overrides env)")
def cmd_mobile_start(telegram_token: Optional[str], discord_token: Optional[str], slack_tokens: Optional[str]) -> None:
    """
    Start the mobile control bridge (Telegram, Discord, Slack, iMessage).
    """
    import asyncio
    from quentin.bootstrap.container import Container
    from quentin.infra.channels.telegram import TelegramAdapter
    from quentin.infra.channels.discord_adapter import DiscordAdapter
    from quentin.infra.channels.slack_adapter import SlackAdapter
    from quentin.infra.channels.imessage_adapter import IMessageAdapter
    from quentin.infra.channels.bridge import ChannelBridge
    
    adapters = []

    # 1. Telegram
    tg_token = telegram_token or os.getenv("TELEGRAM_BOT_TOKEN")
    if tg_token:
        print("Enable: Telegram")
        adapters.append(TelegramAdapter(tg_token))

    # 2. Discord
    dc_token = discord_token or os.getenv("DISCORD_BOT_TOKEN")
    if dc_token:
        print("Enable: Discord")
        adapters.append(DiscordAdapter(dc_token))

    # 3. Slack
    sl_app_token = os.getenv("SLACK_APP_TOKEN")
    sl_bot_token = os.getenv("SLACK_BOT_TOKEN")
    if slack_tokens:
        parts = slack_tokens.split(":")
        if len(parts) == 2:
            sl_app_token, sl_bot_token = parts
    
    if sl_app_token and sl_bot_token:
        print("Enable: Slack")
        adapters.append(SlackAdapter(app_token=sl_app_token, bot_token=sl_bot_token))

    # 4. iMessage (MacOS only)
    if platform.system() == "Darwin":
        # Check if enabled explicitly or by default
        if os.getenv("IMESSAGE_ENABLE", "0") == "1":
            print("Enable: iMessage (Send-only)")
            adapters.append(IMessageAdapter())

    if not adapters:
        print("Error: No channels enabled. Set TELEGRAM_BOT_TOKEN, DISCORD_BOT_TOKEN, or SLACK_APP/BOT_TOKEN in .env")
        return

    container = Container()
    bridge = ChannelBridge(container.cognitive_loop, adapters)
    
    print(f"Starting Mobile Bridge with {len(adapters)} channels... Press Ctrl+C to stop.")
    try:
        asyncio.run(bridge.start())
        # Keep alive
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping Bridge...")
        asyncio.run(bridge.stop())


@cli.command("mobile-approve")
@click.argument("code")
def cmd_mobile_approve(code: str) -> None:
    """
    Approve a mobile pairing code.
    """
    from quentin.infra.channels.pairing import PairingManager
    pm = PairingManager()
    sender_id = pm.approve_code(code)
    if sender_id:
        print(f"Successfully approved sender: {sender_id}")
    else:
        print(f"Error: Invalid or expired code: {code}")


@cli.command("mobile-gateway-start")
@click.option("--host", default="0.0.0.0", help="Binding host")
@click.option("--port", default=8888, help="Binding port")
def cmd_mobile_gateway_start(host: str, port: int) -> None:
    """
    Start the ACP Gateway for direct mobile device control (Android/iOS).
    This enables skills like photo taking, GPS, and UI automation.
    """
    import asyncio
    from quentin.infra.acp.server import ACPServer
    
    server = ACPServer(host=host, port=port)
    print(f"Starting ACP Gateway on {host}:{port}... Waiting for nodes to connect.")
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\nStopping Gateway...")


@cli.command("canvas-start")
@click.option("--host", default="0.0.0.0", help="Binding host")
@click.option("--port", default=8889, help="Binding port")
def cmd_canvas_start(host: str, port: int) -> None:
    """
    Start the Canvas Visual Dashboard.
    Opens a real-time window into what the brain sees and does.
    """
    from quentin.infra.canvas.server import start_canvas_server
    print(f"Starting Canvas Visual Dashboard on {host}:{port}...")
    print(f"Access the UI via: http://{host}:{port}/dashboard")
    try:
        start_canvas_server(host=host, port=port)
    except KeyboardInterrupt:
        print("\nStopping Canvas Dashboard...")


@cli.command("gate-approve")
@click.argument("request_id")
def cmd_gate_approve(request_id: str) -> None:
    """
    Approve a pending sensitive action request.
    """
    from quentin.infra.security.approval import approval_gate
    approval_gate.resolve_request(request_id, True)
    print(f"Request {request_id} APPROVED.")

@cli.command("gate-reject")
@click.argument("request_id")
def cmd_gate_reject(request_id: str) -> None:
    """
    Reject a pending sensitive action request.
    """
    from quentin.infra.security.approval import approval_gate
    approval_gate.resolve_request(request_id, False)
    print(f"Request {request_id} REJECTED.")

@cli.command("browser-node-start")
@click.option("--visible", is_flag=True, help="Run browser in visible mode (default is headless)")
def cmd_browser_node_start(visible: bool) -> None:
    """
    Start the Automated Browser Node (Playwright).
    Enables Quentin to browse the web and interact with websites.
    """
    import asyncio
    from quentin.infra.browser.manager import browser_manager
    
    browser_manager.headless = not visible
    print(f"Starting Browser Node (Headless={not visible})...")
    
    async def run():
        await browser_manager.start()
        # Keep alive
        while True:
            await asyncio.sleep(1)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nStopping Browser Node...")


@cli.command("desktop-node-start")
def cmd_desktop_node_start() -> None:
    """
    Start the Local Desktop Node.
    Mirrors your screen to Canvas and allows AI to control your computer.
    """
    import asyncio
    from quentin.infra.desktop.manager import desktop_manager
    
    print("Starting Desktop Node... Warning: This allows AI to see and control your screen.")
    
    async def run():
        await desktop_manager.start()
        while True:
            await asyncio.sleep(1)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nStopping Desktop Node...")


def cmd_skill_impl(args: click.Context) -> None: # Using click context wrapper style from before not strictly enforcing namespace here but standard args
    # Note: the Click framework passes parameters directly to the function, 
    # but our main dispatch uses set_defaults(func=...) which expects a Namespace object if using argparse.
    # However, since this file uses click.group() and decorators, we need to adapt.
    # Wait, the previous code structure in this file seems to be a mix of click decorators and argparse pattern 
    # because of how I implemented it previously (using subparser add_parser manually inside a click command? No, wait).
    # 
    # Correction: The existing code uses `click` decorators for commands, BUT inside `cli()` it doesn't seem to use `argparse` explicitly 
    # EXCEPT for the logic I added in previous steps which seemed to rely on `argparse` namespace style in `set_defaults`.
    # 
    # ACTUALLY, checking the file content again:
    # The file uses `@cli.command(...)` decorators.
    # My previous REPLACE blocks added `subparsers.add_parser` logic which is ARGPARSE specific, 
    # but the file uses `click`. 
    # 
    # I made a mistake in the previous step by injecting `argparse` logic into a `click` CLI.
    # I need to FIX this by adding standard `@cli.command` definitions for these new commands, 
    # instead of the `subparsers` logic which won't work with `click`.
    pass

@cli.command("skill-impl")
@click.argument("skill_id", type=str)
@click.option("--dry-run", is_flag=True, help="If set, only generate code without writing to file.")
def cmd_skill_impl(skill_id: str, dry_run: bool) -> None:
    """
    Implement a single skill by skill_id using the self-programming engine.
    """
    engine = SkillImplementationEngine()
    req = SkillImplementationRequest(skill_id=skill_id, dry_run=dry_run)
    res = engine.implement_skill(req)
    print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))


@cli.command("skill-impl-next")
@click.option("--domain", type=str, default=None, help="Optional domain filter.")
@click.option("--dry-run", is_flag=True, help="Dry run for the selected skill.")
def cmd_skill_impl_next(domain: Optional[str], dry_run: bool) -> None:
    """
    Pick a candidate skill and implement it automatically.
    """
    mgr = SkillManager()
    # Find a candidate skill
    candidates = mgr.list_skills(
        status=SKILL_STATUS_CANDIDATE,
        domain=domain,
        implemented=False,
    )
    if not candidates:
        print("No candidate skills found for implementation.")
        return

    # Pick the first one
    sk = candidates[0]
    print(f"Selected candidate skill: {sk.skill_id} | {sk.title} (domain={sk.domain})")

    engine = SkillImplementationEngine()
    req = SkillImplementationRequest(skill_id=sk.skill_id, dry_run=dry_run)
    res = engine.implement_skill(req)
    print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
