import asyncio
import json
import os
from pathlib import Path
import typer
from rich.console import Console
from rich.panel import Panel

from app.config import settings
from app.models import ProjectState
from app.observability.logger import setup_logging
from app.observability.tracer import setup_tracing
from app.dashboard import build_dashboard_snapshot, run_dashboard_server
from app.evidence import EvidenceStore
from app.evidence import EventStore
from app.metrics import (
    build_policy_tuning_dataset,
    calibrate_auto_review_policy,
    read_runner_health,
    write_system_hardening_report,
)
from app.control import load_failure_router_policy, route_recovery_action
from app.control import ShutdownManager, write_terminal_event_once
from app.review import (
    evaluate_auto_review,
    evaluate_governance_review,
    latest_human_review,
    list_human_reviews,
    resolve_human_review,
)

from typing import Annotated

app = typer.Typer()
console = Console()
try:
    from app.temporal.mock_worker import MockTemporalWorker
except Exception:
    MockTemporalWorker = None


def get_main_status() -> str:
    return "ok"


def _runner_session_id(runner_type: str) -> str:
    mapping = {
        "codex": settings.codex_session_id,
        "gemini": settings.gemini_session_id,
        "claude": settings.claude_session_id,
    }
    value = str(mapping.get(runner_type, "")).strip()
    if value and any(token in value.lower() for token in ("your-", "<", ">", "session-id", "session_id")):
        return ""
    return value


def _apply_profile(profile: str) -> None:
    if not profile.strip():
        return
    normalized_profile = profile.strip().lower()
    if normalized_profile not in {"dev", "prod"}:
        console.print(f"[red]Unknown profile: {normalized_profile}. Use dev or prod.[/red]")
        raise typer.Exit(1)
    settings.execution_profile = normalized_profile


def _normalize_project_root() -> None:
    current_root = Path.cwd().resolve()
    configured_root = settings.project_root.resolve()
    if configured_root != current_root:
        console.print(
            f"[yellow]PROJECT_ROOT override detected ({configured_root}); using cwd ({current_root})[/yellow]"
        )
        settings.project_root = current_root


def _normalize_runner_configuration() -> None:
    current_runner = settings.agent_runner_type
    profile = settings.execution_profile
    if current_runner == "codex":
        settings.apply_codex_timeout_profile()
    if profile == "prod" and current_runner == "mock":
        console.print("[red]prod profile forbids mock runner[/red]")
        raise typer.Exit(2)
    if current_runner in {"claude"} and not _runner_session_id(current_runner).strip():
        if profile == "prod":
            console.print(
                f"[red]{current_runner} runner requires session id in prod profile[/red]"
            )
            raise typer.Exit(2)
        console.print(
            f"[yellow]{current_runner} runner has no session id configured; falling back to mock[/yellow]"
        )
        settings.agent_runner_type = "mock"


def _validate_prd_path(prd_path: str) -> str:
    prd_file = Path(prd_path)
    if not prd_file.is_absolute():
        prd_file = Path.cwd() / prd_file
    if not prd_file.exists() or not prd_file.is_file():
        console.print(f"[red]PRD file not found:[/red] {prd_file}")
        raise typer.Exit(1)
    return str(prd_file)


def _validate_mode_profile_constraints(mode: str) -> None:
    if mode == "temporal" and settings.execution_profile == "prod" and settings.temporal_mock_mode:
        console.print("[red]prod profile requires real Temporal mode (set TEMPORAL_MOCK_MODE=false)[/red]")
        raise typer.Exit(2)


def _collect_preflight_issues(mode: str, prd_path: str) -> list[str]:
    issues: list[str] = []
    prd_file = Path(prd_path)
    if not prd_file.is_absolute():
        prd_file = Path.cwd() / prd_file
    if not prd_file.exists() or not prd_file.is_file():
        issues.append(f"PRD file not found: {prd_file}")

    if mode not in {"graph", "temporal"}:
        issues.append(f"Unsupported mode: {mode}")

    if settings.execution_profile == "prod":
        if settings.agent_runner_type == "mock":
            issues.append("prod profile forbids mock runner")
        if settings.agent_runner_type in {"claude"} and not _runner_session_id(
            settings.agent_runner_type
        ).strip():
            issues.append(f"{settings.agent_runner_type} runner requires session id in prod profile")
        if mode == "temporal" and settings.temporal_mock_mode:
            issues.append("prod profile requires real Temporal mode")

    return issues


def _load_existing_failure_context(*, project_id: str, phase_id: str) -> dict:
    summary_file = settings.runtime_dir / "evidence" / project_id / phase_id / "execution_summary.json"
    if not summary_file.exists():
        return {}
    try:
        return json.loads(summary_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _has_execution_summary(*, project_id: str, phase_id: str) -> bool:
    summary_file = settings.runtime_dir / "evidence" / project_id / phase_id / "execution_summary.json"
    return summary_file.exists()


RUNNER_HEALTH_KEYS: tuple[str, ...] = (
    "state_db_fallback_count",
    "session_degraded_count",
    "execution_timeout_count",
    "probe_failure_count",
    "usage_limit_count",
)


def _runner_health_snapshot() -> dict[str, int]:
    payload = read_runner_health()
    return {key: int(payload.get(key, 0) or 0) for key in RUNNER_HEALTH_KEYS}


def _runner_health_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    delta: dict[str, int] = {}
    for key in RUNNER_HEALTH_KEYS:
        value = int(after.get(key, 0)) - int(before.get(key, 0))
        if value > 0:
            delta[key] = value
    return delta


def _runner_health_signals_from_delta(delta: dict[str, int]) -> list[str]:
    mapping = {
        "state_db_fallback_count": "STATE_DB_DEGRADED",
        "session_degraded_count": "AGENT_RUNNER_SESSION_DEGRADED",
        "usage_limit_count": "RUNNER_USAGE_LIMIT",
    }
    return [signal for key, signal in mapping.items() if int(delta.get(key, 0)) > 0]


def _apply_runner_health_delta_gate(
    *,
    project_id: str,
    phase_id: str,
    before: dict[str, int],
    after: dict[str, int],
) -> dict:
    summary_file = settings.runtime_dir / "evidence" / project_id / phase_id / "execution_summary.json"
    if not summary_file.exists():
        return {}
    try:
        payload = json.loads(summary_file.read_text(encoding="utf-8"))
    except Exception:
        return {}

    delta = _runner_health_delta(before, after)
    degraded_signals = _runner_health_signals_from_delta(delta)
    degraded = bool(degraded_signals)
    timeout_delta_count = int(delta.get("execution_timeout_count", 0))
    payload["runner_health_before"] = before
    payload["runner_health_after"] = after
    payload["runner_health_delta"] = delta
    payload["runner_health_degraded_run"] = degraded
    payload["runner_health_timeout_delta_count"] = timeout_delta_count

    signals = degraded_signals
    if signals:
        existing_signals = [str(item) for item in payload.get("runner_health_signals", []) if str(item).strip()]
        payload["runner_health_signals"] = list(dict.fromkeys(existing_signals + signals))
        acceptance_status = str(payload.get("acceptance_status", "")).strip().lower()
        if acceptance_status == "passed":
            non_blocking = [str(item) for item in payload.get("non_blocking_signals", []) if str(item).strip()]
            payload["non_blocking_signals"] = list(dict.fromkeys(non_blocking + signals))
        else:
            secondary = [str(item) for item in payload.get("secondary_failure_types", []) if str(item).strip()]
            payload["secondary_failure_types"] = list(dict.fromkeys(secondary + signals))

    summary_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    marker_file = summary_file.with_name("runner_health_delta.json")
    marker_payload = {
        "project_id": project_id,
        "phase_id": phase_id,
        "runner_health_before": before,
        "runner_health_after": after,
        "runner_health_delta": delta,
        "runner_health_degraded_run": degraded,
        "runner_health_timeout_delta_count": timeout_delta_count,
        "runner_health_signals": signals,
    }
    marker_file.write_text(json.dumps(marker_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return marker_payload


def _derive_shutdown_failure_context(*, project_id: str, phase_id: str) -> dict:
    existing = _load_existing_failure_context(project_id=project_id, phase_id=phase_id)
    if existing:
        return {
            "primary_failure_type": str(existing.get("primary_failure_type", "")).strip(),
            "secondary_failure_types": [
                str(item) for item in existing.get("secondary_failure_types", []) if str(item).strip()
            ],
            "first_failure_at": str(existing.get("first_failure_at", "")).strip(),
            "first_failure_event_id": str(existing.get("first_failure_event_id", "")).strip(),
            "final_status_label": str(existing.get("final_status_label", "")).strip(),
            "recovery_action": str(existing.get("recovery_action", "")).strip(),
            "terminal_state": str(existing.get("terminal_state", "")).strip(),
        }

    events = EventStore().read(project_id, phase_id)
    if not events:
        return {}

    from app.temporal.workflow import _derive_failure_diagnostics, _derive_terminal_state

    diagnostics = _derive_failure_diagnostics(
        results={},
        test_results={"status": "failed", "acceptance_status": "rejected"},
        failed_modules=[],
        events=events,
    )
    recommended_action = route_recovery_action(
        status="failed",
        acceptance_status="rejected",
        failed_modules=[],
        replan_rounds=0,
        reviewer_codes=[],
        failure_type=str(diagnostics.get("primary_failure_type", "")),
        first_failure_stage=str(diagnostics.get("first_failure_stage", "")),
        failure_signature_count=1,
    )
    terminal_state = _derive_terminal_state(
        acceptance_status="rejected",
        recommended_action=recommended_action,
        failure_diagnostics=diagnostics,
    )
    return {
        "primary_failure_type": str(diagnostics.get("primary_failure_type", "")).strip(),
        "secondary_failure_types": [
            str(item) for item in diagnostics.get("secondary_failure_types", []) if str(item).strip()
        ],
        "first_failure_at": str(diagnostics.get("first_failure_at", "")).strip(),
        "first_failure_event_id": str(diagnostics.get("first_failure_event_id", "")).strip(),
        "final_status_label": str(diagnostics.get("final_status_label", "")).strip(),
        "recovery_action": str(recommended_action).strip(),
        "terminal_state": str(terminal_state).strip(),
    }


def _write_shutdown_terminal_fallback(*, project_id: str, phase_id: str, termination_reason: str) -> None:
    existing = _derive_shutdown_failure_context(project_id=project_id, phase_id=phase_id)
    primary_failure_type = str(existing.get("primary_failure_type", "")).strip()
    secondary = [str(item) for item in existing.get("secondary_failure_types", []) if str(item).strip()]
    first_failure_at = str(existing.get("first_failure_at", "")).strip()
    terminal_state = str(existing.get("terminal_state", "")).strip().upper() or "ABORTED"
    final_status_label = str(existing.get("final_status_label", "")).strip()
    recommended_action = str(existing.get("recovery_action", "")).strip() or "escalate_to_human"
    external_timeout_forced = os.environ.get("AUTOLOOP_TIMEOUT_TERMINATES_AS_GLOBAL_TIMEOUT", "").strip() == "1"
    if external_timeout_forced and termination_reason == "signal_sigterm":
        if primary_failure_type in {"", "BUSINESS_REJECTION_UNMAPPED", "UNCLASSIFIED_EXECUTION_FAILURE"}:
            primary_failure_type = "GLOBAL_TIMEOUT"
            terminal_state = "TIMEOUT"
            final_status_label = "GLOBAL_TIMEOUT"
            recommended_action = "replan_from_spec"
    failure_events = []
    if first_failure_at:
        failure_events.append(
            {
                "event_id": str(existing.get("first_failure_event_id", "")).strip(),
                "event_time": first_failure_at,
                "stage": "workflow",
                "actor": "workflow",
                "attempt": 1,
                "cause_type": primary_failure_type,
                "cause_class": "execution",
                "is_primary_candidate": True,
            }
        )
    write_terminal_event_once(
        project_id=project_id,
        phase_id=phase_id,
        terminal_state=terminal_state,
        final_status_label=final_status_label or ("ABORTED_BY_SIGNAL" if terminal_state == "ABORTED" else terminal_state),
        recommended_action=recommended_action,
        acceptance_status="rejected",
        primary_failure_type=primary_failure_type,
        secondary_failure_types=secondary,
        failure_events=failure_events,
        termination_reason=termination_reason,
        trace_id=f"{project_id}:{phase_id}",
    )


@app.command()
def run(
    prd_path: str = typer.Argument(..., help="Path to PRD markdown file"),
    project_id: str = typer.Option("autoloop-project", help="Project ID"),
    mode: str = typer.Option("graph", help="Execution mode: graph or temporal"),
    profile: str = typer.Option("", help="Execution profile: dev or prod"),
):
    _apply_profile(profile)
    _normalize_project_root()
    _normalize_runner_configuration()
    resolved_prd_path = _validate_prd_path(prd_path)
    _validate_mode_profile_constraints(mode)
    settings.ensure_dirs()
    setup_logging()
    setup_tracing()

    console.print(Panel.fit("🚀 AutoLoop Multi-Agent Orchestration System", style="bold green"))
    console.print(f"[cyan]Project ID:[/cyan] {project_id}")
    console.print(f"[cyan]PRD Path:[/cyan] {resolved_prd_path}")
    console.print(f"[cyan]Mode:[/cyan] {mode}")
    console.print(f"[cyan]Profile:[/cyan] {settings.execution_profile}")
    console.print(f"[cyan]Agent Runner:[/cyan] {settings.agent_runner_type}")
    if settings.agent_runner_type == "codex":
        console.print(
            f"[cyan]Codex Timeout Profile:[/cyan] {settings.codex_timeout_profile} "
            f"(attempt={settings.codex_attempt_timeout_seconds}s total={settings.agent_total_timeout_seconds}s)"
        )

    runner_health_before = _runner_health_snapshot()
    shutdown_manager = ShutdownManager()
    shutdown_manager.install()
    fallback_written = False
    try:
        if mode == "graph":
            asyncio.run(run_langgraph(project_id, resolved_prd_path))
        elif mode == "temporal":
            asyncio.run(run_temporal(project_id, resolved_prd_path))
        else:
            console.print(f"[red]Unknown mode: {mode}[/red]")
            raise typer.Exit(1)
    except KeyboardInterrupt:
        _write_shutdown_terminal_fallback(
            project_id=project_id,
            phase_id="phase_01",
            termination_reason=shutdown_manager.state.termination_reason or "signal_interrupt",
        )
        fallback_written = True
        console.print("\n[red]Interrupted by signal; graceful shutdown completed[/red]")
        raise typer.Exit(130)
    finally:
        if (
            shutdown_manager.state.shutdown_requested
            and not fallback_written
            and not _has_execution_summary(project_id=project_id, phase_id="phase_01")
        ):
            _write_shutdown_terminal_fallback(
                project_id=project_id,
                phase_id="phase_01",
                termination_reason=shutdown_manager.state.termination_reason or "signal_interrupt",
            )
        if mode == "temporal":
            runner_health_after = _runner_health_snapshot()
            marker = _apply_runner_health_delta_gate(
                project_id=project_id,
                phase_id="phase_01",
                before=runner_health_before,
                after=runner_health_after,
            )
            if marker.get("runner_health_degraded_run"):
                console.print(
                    f"[yellow]Runner degraded during run:[/yellow] {marker.get('runner_health_delta', {})}"
                )
        shutdown_manager.restore()


@app.command()
def doctor(
    prd_path: str = typer.Argument(..., help="Path to PRD markdown file"),
    mode: str = typer.Option("graph", help="Execution mode to validate"),
    profile: str = typer.Option("", help="Execution profile: dev or prod"),
):
    _apply_profile(profile)
    _normalize_project_root()
    issues = _collect_preflight_issues(mode, prd_path)

    console.print(Panel.fit("🩺 AutoLoop Preflight Doctor", style="bold cyan"))
    console.print(f"[cyan]Project Root:[/cyan] {settings.project_root}")
    console.print(f"[cyan]Mode:[/cyan] {mode}")
    console.print(f"[cyan]Profile:[/cyan] {settings.execution_profile}")
    console.print(f"[cyan]Runner:[/cyan] {settings.agent_runner_type}")
    if settings.agent_runner_type in {"codex", "claude"}:
        session_state = "set" if _runner_session_id(settings.agent_runner_type).strip() else "missing"
        suffix = " (optional for codex)" if settings.agent_runner_type == "codex" else ""
        console.print(f"[cyan]Runner Session:[/cyan] {session_state}{suffix}")
    evidence_path, evidence = EvidenceStore(settings.runtime_dir / "evidence").latest_record()
    recent_evidence = EvidenceStore(settings.runtime_dir / "evidence").recent_records(limit=3)
    if evidence_path and evidence:
        console.print(f"[cyan]Latest Evidence:[/cyan] {evidence_path}")
        console.print(f"[cyan]Evidence Acceptance:[/cyan] {evidence.acceptance_status}")
        console.print(f"[cyan]Evidence Test Status:[/cyan] {evidence.test_status}")
        if evidence.first_failure_stage:
            console.print(f"[yellow]First Failure Stage:[/yellow] {evidence.first_failure_stage}")
        if evidence.owner_agent:
            console.print(f"[yellow]Failure Owner:[/yellow] {evidence.owner_agent}")
        if evidence.failure_signature:
            console.print(f"[yellow]Failure Signature:[/yellow] {evidence.failure_signature}")
        if evidence.trace_id:
            console.print(f"[yellow]Trace ID:[/yellow] {evidence.trace_id}")
        if evidence.missing_required_tests:
            console.print(
                f"[yellow]Missing Required Tests:[/yellow] {', '.join(evidence.missing_required_tests)}"
            )
    if recent_evidence:
        signatures = [record.failure_signature for _, record in recent_evidence if record.failure_signature]
        if signatures:
            console.print(f"[yellow]Recent Failure Signatures:[/yellow] {', '.join(signatures)}")
    review = latest_human_review()
    if review:
        console.print(f"[red]Human Review Required:[/red] {review.get('hook_file', 'unknown')}")
        console.print(f"[red]Human Review Acceptance:[/red] {review.get('acceptance_status', 'unknown')}")
        if review.get("trace_id"):
            console.print(f"[red]Human Review Trace:[/red] {review.get('trace_id')}")

    if issues:
        console.print("\n[red]Preflight checks failed:[/red]")
        for issue in issues:
            console.print(f" - {issue}")
        raise typer.Exit(1)

    console.print("\n[green]Preflight checks passed[/green]")


async def run_langgraph(project_id: str, prd_path: str):
    console.print("\n[yellow]Running in LangGraph mode...[/yellow]\n")
    from app.graph import create_autoloop_graph

    graph = create_autoloop_graph()

    initial_state = ProjectState(project_id=project_id, prd_path=prd_path)

    raw_result = await graph.ainvoke(initial_state)
    result = (
        ProjectState.model_validate(raw_result)
        if isinstance(raw_result, dict)
        else raw_result
    )

    console.print("\n[green]✓ LangGraph execution completed[/green]")
    console.print(f"[cyan]Final status:[/cyan] {'Completed' if result.is_completed else 'Failed'}")
    console.print(f"[cyan]Current phase:[/cyan] {result.current_phase}")

    if result.phases:
        latest_phase = result.phases[-1]
        console.print(f"[cyan]Phase status:[/cyan] {latest_phase.status}")
        console.print(
            f"[cyan]Tasks assigned:[/cyan] {len(latest_phase.tasks_assigned) if latest_phase.tasks_assigned else 0}"
        )

    console.print(f"\n[green]Check results in:[/green] {settings.phases_dir}")
    console.print(f"[green]Check logs in:[/green] {settings.logs_dir}")


async def run_temporal(project_id: str, prd_path: str):
    if settings.temporal_mock_mode:
        console.print("\n[yellow]Running in Mock Temporal mode...[/yellow]\n")
        if MockTemporalWorker is None:
            raise RuntimeError("MockTemporalWorker unavailable")
        worker = MockTemporalWorker()
        result = await worker.run_workflow(project_id, prd_path)
    else:
        console.print("\n[yellow]Running in Real Temporal mode...[/yellow]\n")
        from temporalio.client import Client
        from app.temporal.workflow import RunProjectWorkflow

        client = await Client.connect(
            settings.temporal_host, namespace=settings.temporal_namespace
        )

        result = await client.execute_workflow(
            RunProjectWorkflow.run,
            args=[project_id, prd_path],
            id=f"{project_id}-workflow",
            task_queue=settings.temporal_task_queue,
        )

    console.print("\n[green]✓ Temporal workflow completed[/green]")
    console.print(f"[cyan]Project ID:[/cyan] {result.get('project_id', project_id)}")
    console.print(f"[cyan]Phase ID:[/cyan] {result.get('phase_id', 'unknown')}")
    console.print(f"[cyan]Status:[/cyan] {result.get('status', 'unknown')}")
    console.print(f"[cyan]Acceptance:[/cyan] {result.get('acceptance_status', 'unknown')}")
    console.print(f"[cyan]Recovery Action:[/cyan] {result.get('recommended_action', 'unknown')}")
    if result.get("evidence_file"):
        console.print(f"[cyan]Evidence:[/cyan] {result.get('evidence_file')}")
    if result.get("human_review_hook"):
        console.print(f"[red]Human Review Hook:[/red] {result.get('human_review_hook')}")
    console.print(f"[cyan]Report:[/cyan] {result.get('phase_report', 'N/A')}")
    await _maybe_auto_review_resume(
        project_id=project_id,
        prd_path=prd_path,
        result=result,
        auto_resume_depth=0,
    )


async def _maybe_auto_review_resume(
    *,
    project_id: str,
    prd_path: str,
    result: dict,
    auto_resume_depth: int,
) -> None:
    if not settings.auto_review_enabled:
        return
    if auto_resume_depth >= settings.auto_review_max_auto_resumes:
        return
    phase_id = str(result.get("phase_id", "")).strip()
    hook_path = str(result.get("human_review_hook", "")).strip()
    if not phase_id or not hook_path:
        return

    evaluation = evaluate_auto_review(phase_id=phase_id)
    decision = str(evaluation.get("decision", "rejected")).strip().lower()
    confidence = float(evaluation.get("confidence", 0.0))
    notes = str(evaluation.get("notes", "")).strip()
    risk_signals = evaluation.get("risk_signals", [])
    console.print(
        f"[cyan]Default auto-review:[/cyan] decision={decision} confidence={confidence:.2f} phase={phase_id}"
    )
    if risk_signals:
        console.print(f"[yellow]Auto-review risks:[/yellow] {', '.join(str(item) for item in risk_signals)}")

    if decision != "approved" or confidence < settings.auto_review_min_confidence:
        console.print("[yellow]Auto-review did not pass threshold[/yellow]")
        await _maybe_governance_review_resume(
            project_id=project_id,
            prd_path=prd_path,
            phase_id=phase_id,
            auto_resume_depth=auto_resume_depth,
        )
        return

    resolution = resolve_human_review(
        phase_id=phase_id,
        decision=decision,
        reviewer="auto_review_default_flow",
        notes=notes,
        policy_version=str(evaluation.get("policy_version", "auto_review_policy_v1")),
    )
    console.print(f"[green]Auto-review resolved:[/green] {resolution['resolution_file']}")
    console.print(
        f"[yellow]Default flow auto-resume temporal run[/yellow] phase={phase_id} project={project_id}"
    )

    next_result = await _execute_temporal_workflow(project_id=project_id, prd_path=prd_path)

    console.print(f"[cyan]Auto-resume status:[/cyan] {next_result.get('status', 'unknown')}")
    console.print(f"[cyan]Auto-resume acceptance:[/cyan] {next_result.get('acceptance_status', 'unknown')}")


async def _maybe_governance_review_resume(
    *,
    project_id: str,
    prd_path: str,
    phase_id: str,
    auto_resume_depth: int,
) -> None:
    if not settings.governance_review_enabled:
        console.print("[yellow]Governance review disabled; keep human-review required[/yellow]")
        return
    if auto_resume_depth >= settings.auto_review_max_auto_resumes:
        console.print("[yellow]Governance auto-resume depth exceeded; keep human-review required[/yellow]")
        return

    evaluation = evaluate_governance_review(phase_id=phase_id)
    decision = str(evaluation.get("decision", "rejected")).strip().lower()
    confidence = float(evaluation.get("confidence", 0.0))
    notes = str(evaluation.get("notes", "")).strip()
    risk_signals = evaluation.get("risk_signals", [])
    console.print(
        f"[cyan]Governance review:[/cyan] decision={decision} confidence={confidence:.2f} phase={phase_id}"
    )
    if risk_signals:
        console.print(f"[yellow]Governance risks:[/yellow] {', '.join(str(item) for item in risk_signals)}")

    resolution = resolve_human_review(
        phase_id=phase_id,
        decision=decision,
        reviewer="governance_review_agent",
        notes=notes,
        policy_version=str(evaluation.get("policy_version", "governance_review_policy_v1")),
    )
    console.print(f"[green]Governance review resolved:[/green] {resolution['resolution_file']}")
    if decision != "approved" or not settings.governance_review_auto_resume:
        return

    next_result = await _execute_temporal_workflow(project_id=project_id, prd_path=prd_path)
    console.print(f"[cyan]Governance auto-resume status:[/cyan] {next_result.get('status', 'unknown')}")
    console.print(
        f"[cyan]Governance auto-resume acceptance:[/cyan] {next_result.get('acceptance_status', 'unknown')}"
    )


async def _execute_temporal_workflow(*, project_id: str, prd_path: str) -> dict:
    if settings.temporal_mock_mode:
        if MockTemporalWorker is None:
            raise RuntimeError("MockTemporalWorker unavailable")
        worker = MockTemporalWorker()
        return await worker.run_workflow(project_id, prd_path)
    from temporalio.client import Client
    from app.temporal.workflow import RunProjectWorkflow

    client = await Client.connect(
        settings.temporal_host, namespace=settings.temporal_namespace
    )
    return await client.execute_workflow(
        RunProjectWorkflow.run,
        args=[project_id, prd_path],
        id=f"{project_id}-workflow",
        task_queue=settings.temporal_task_queue,
    )


@app.command()
def sessions(
    runner_type: Annotated[str, typer.Option(help="Runner type: codex, gemini, or claude")] = "codex",
    cleanup: bool = typer.Option(False, "--cleanup", help="Cleanup old sessions (keep latest 5)"),
):
    import asyncio
    from app.runners.session_manager import SessionManager

    console.print(Panel.fit(f"📋 Session Manager - {runner_type}", style="bold cyan"))

    manager = SessionManager(runner_type)

    if cleanup:
        asyncio.run(manager.cleanup_old_sessions())
        console.print(f"\n[green]✓ Cleaned up old {runner_type} sessions[/green]")

    sessions = asyncio.run(manager.list_sessions())

    if not sessions:
        console.print(f"\n[yellow]No {runner_type} sessions found[/yellow]")
        console.print("\n[cyan]Sessions will be created automatically on first use[/cyan]")
        return

    console.print(f"\n[bold]Stored Sessions ({len(sessions)}):[/bold]\n")

    from rich.table import Table

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Agent", style="cyan")
    table.add_column("Phase", style="green")
    table.add_column("Session ID", style="yellow")
    table.add_column("Created", style="blue")

    for key, data in sessions.items():
        table.add_row(
            data.get("agent_role", "N/A"),
            data.get("phase_id", "N/A"),
            data.get("session_id", "N/A")[:40] + "...",
            data.get("created_at", "N/A")[:19],
        )

    console.print(table)


@app.command()
def health():
    import asyncio
    from app.runners import health_check_all_runners

    console.print(Panel.fit("🏥 Agent Runner Health Check", style="bold cyan"))

    results = asyncio.run(health_check_all_runners())

    console.print("\n[bold]Available Runners:[/bold]\n")
    for runner_type, is_healthy in results.items():
        status = "[green]✓ Available[/green]" if is_healthy else "[red]✗ Not Available[/red]"
        console.print(f"  {runner_type:15} {status}")

    console.print(f"\n[cyan]Current runner:[/cyan] {settings.agent_runner_type}")

    healthy_count = sum(1 for v in results.values() if v)
    console.print(f"\n[green]{healthy_count}/4 runners available[/green]")


@app.command()
def reviews():
    _normalize_project_root()
    rows = list_human_reviews()
    console.print(Panel.fit("🧭 Human Review Queue", style="bold yellow"))
    if not rows:
        console.print("[green]No pending human-review hooks[/green]")
        return
    console.print(f"[cyan]Pending:[/cyan] {len(rows)}")
    for item in rows[:10]:
        console.print(f"- [red]{item.get('phase_id', 'unknown')}[/red] {item.get('hook_file', 'unknown')}")
        console.print(
            f"  acceptance={item.get('acceptance_status', 'unknown')} failed_modules={item.get('failed_modules', [])}"
        )


@app.command()
def review(
    phase_id: Annotated[str, typer.Option(help="Phase id to review")] = "",
    decision: Annotated[str, typer.Option(help="approved or rejected")] = "approved",
    notes: Annotated[str, typer.Option(help="Review notes")] = "",
    reviewer: Annotated[str, typer.Option(help="Reviewer name")] = "lead_integrator",
    resume: bool = typer.Option(True, "--resume/--no-resume", help="Auto resume run after approved"),
    prd_path: Annotated[str, typer.Option(help="PRD path for resume run")] = "",
    project_id: Annotated[str, typer.Option(help="Project id for resume run")] = "",
):
    _normalize_project_root()
    selected_phase_id = phase_id.strip()
    target_hook = latest_human_review()
    if not selected_phase_id:
        if not target_hook:
            console.print("[yellow]No pending human-review hook found[/yellow]")
            raise typer.Exit(1)
        selected_phase_id = str(target_hook.get("phase_id", "")).strip()
    if not selected_phase_id:
        console.print("[red]Unable to resolve phase_id for review[/red]")
        raise typer.Exit(1)

    resolution = resolve_human_review(
        phase_id=selected_phase_id,
        decision=decision,
        reviewer=reviewer,
        notes=notes,
        policy_version="manual_review_v1",
    )
    console.print(f"[green]Resolved human review for {selected_phase_id}[/green]")
    console.print(f"[cyan]Decision:[/cyan] {resolution['decision']}")
    console.print(f"[cyan]Resolution file:[/cyan] {resolution['resolution_file']}")
    console.print(f"[cyan]Archived hook:[/cyan] {resolution['archived_required_hook']}")

    if resolution["decision"] != "approved" or not resume:
        return

    resume_prd_path = prd_path.strip()
    if not resume_prd_path:
        resume_prd_path = str((target_hook or {}).get("prd_path", "")).strip()
    if not resume_prd_path:
        console.print("[yellow]Review approved but PRD path missing, skip auto-resume[/yellow]")
        return

    resume_project_id = project_id.strip() or str((target_hook or {}).get("project_id", "autoloop-project"))
    resume_prd_path = _validate_prd_path(resume_prd_path)
    _validate_mode_profile_constraints("temporal")
    settings.ensure_dirs()
    setup_logging()
    setup_tracing()
    console.print(
        f"[yellow]Auto-resume temporal run[/yellow] phase={selected_phase_id} project={resume_project_id}"
    )
    asyncio.run(run_temporal(resume_project_id, resume_prd_path))


@app.command("auto-review")
def auto_review(
    phase_id: Annotated[str, typer.Option(help="Phase id to auto review")] = "",
    reviewer: Annotated[str, typer.Option(help="Auto reviewer name")] = "auto_review_agent",
    resume: bool = typer.Option(True, "--resume/--no-resume", help="Auto resume run after approved"),
    prd_path: Annotated[str, typer.Option(help="PRD path override for resume")] = "",
    project_id: Annotated[str, typer.Option(help="Project id override for resume")] = "",
):
    _normalize_project_root()
    evaluation = evaluate_auto_review(phase_id=phase_id)
    hook = evaluation.get("hook") or {}
    if not hook:
        console.print("[yellow]No pending human-review hook found[/yellow]")
        raise typer.Exit(1)

    selected_phase_id = str(hook.get("phase_id", "")).strip()
    decision = str(evaluation.get("decision", "rejected")).strip().lower()
    notes = str(evaluation.get("notes", "")).strip()
    repair_template = str(evaluation.get("repair_template", "")).strip()
    confidence = float(evaluation.get("confidence", 0.0))
    risk_signals = evaluation.get("risk_signals", [])

    console.print(
        f"[cyan]Auto review decision:[/cyan] {decision} confidence={confidence:.2f} phase={selected_phase_id}"
    )
    if risk_signals:
        console.print(f"[yellow]Risk signals:[/yellow] {', '.join(str(item) for item in risk_signals)}")
    if repair_template:
        console.print(f"[yellow]Repair template:[/yellow] {repair_template}")

    resolution = resolve_human_review(
        phase_id=selected_phase_id,
        decision=decision,
        reviewer=reviewer,
        notes=notes,
        policy_version=str(evaluation.get("policy_version", "auto_review_policy_v1")),
    )
    console.print(f"[green]Resolved by auto-review:[/green] {selected_phase_id}")
    console.print(f"[cyan]Resolution file:[/cyan] {resolution['resolution_file']}")

    if decision != "approved" or not resume:
        return

    resume_prd_path = prd_path.strip() or str(hook.get("prd_path", "")).strip()
    if not resume_prd_path:
        console.print("[yellow]Auto-approved but PRD path missing, skip auto-resume[/yellow]")
        return
    resume_project_id = project_id.strip() or str(hook.get("project_id", "autoloop-project"))
    resume_prd_path = _validate_prd_path(resume_prd_path)
    _validate_mode_profile_constraints("temporal")
    settings.ensure_dirs()
    setup_logging()
    setup_tracing()
    console.print(
        f"[yellow]Auto-review resume temporal run[/yellow] phase={selected_phase_id} project={resume_project_id}"
    )
    asyncio.run(run_temporal(resume_project_id, resume_prd_path))


@app.command("governance-review")
def governance_review(
    phase_id: Annotated[str, typer.Option(help="Phase id to govern")] = "",
    reviewer: Annotated[str, typer.Option(help="Reviewer name")] = "governance_review_agent",
    resume: bool = typer.Option(True, "--resume/--no-resume", help="Auto resume run after approved"),
    prd_path: Annotated[str, typer.Option(help="PRD path override for resume")] = "",
    project_id: Annotated[str, typer.Option(help="Project id override for resume")] = "",
):
    _normalize_project_root()
    evaluation = evaluate_governance_review(phase_id=phase_id)
    hook = evaluation.get("hook") or {}
    if not hook:
        console.print("[yellow]No pending human-review hook found[/yellow]")
        raise typer.Exit(1)
    selected_phase_id = str(hook.get("phase_id", "")).strip()
    decision = str(evaluation.get("decision", "rejected")).strip().lower()
    confidence = float(evaluation.get("confidence", 0.0))
    notes = str(evaluation.get("notes", "")).strip()
    risk_signals = evaluation.get("risk_signals", [])
    console.print(
        f"[cyan]Governance review decision:[/cyan] {decision} confidence={confidence:.2f} phase={selected_phase_id}"
    )
    if risk_signals:
        console.print(f"[yellow]Risk signals:[/yellow] {', '.join(str(item) for item in risk_signals)}")
    resolution = resolve_human_review(
        phase_id=selected_phase_id,
        decision=decision,
        reviewer=reviewer,
        notes=notes,
        policy_version=str(evaluation.get("policy_version", "governance_review_policy_v1")),
    )
    console.print(f"[green]Resolved by governance-review:[/green] {selected_phase_id}")
    console.print(f"[cyan]Resolution file:[/cyan] {resolution['resolution_file']}")
    if decision != "approved" or not resume:
        return
    resume_prd_path = prd_path.strip() or str(hook.get("prd_path", "")).strip()
    if not resume_prd_path:
        console.print("[yellow]Approved but PRD path missing, skip auto-resume[/yellow]")
        return
    resume_project_id = project_id.strip() or str(hook.get("project_id", "autoloop-project"))
    resume_prd_path = _validate_prd_path(resume_prd_path)
    _validate_mode_profile_constraints("temporal")
    settings.ensure_dirs()
    setup_logging()
    setup_tracing()
    asyncio.run(run_temporal(resume_project_id, resume_prd_path))


@app.command()
def init(
    project_dir: Annotated[str, typer.Option(help="Project directory to initialize")] = ".",
):
    console.print(Panel.fit("🔧 Initializing AutoLoop Project", style="bold blue"))

    project_path = Path(project_dir)
    settings.project_root = project_path.absolute()
    settings.ensure_dirs()

    (project_path / "prd.md").write_text(
        """# Project PRD

## Overview
This is a sample project for AutoLoop.

## Requirements
- Implement feature A
- Implement feature B
- Test all functionality

## Acceptance Criteria
- All tests pass
- Code follows best practices
"""
    )

    console.print(f"[green]✓ Project initialized at:[/green] {project_path}")
    console.print(f"[cyan]Edit prd.md and run:[/cyan] python -m app.main run prd.md")


@app.command()
def dashboard(
    host: Annotated[str, typer.Option(help="Dashboard host")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Dashboard port")] = 8765,
    snapshot_only: bool = typer.Option(False, "--snapshot-only", help="Print snapshot JSON and exit"),
):
    _normalize_project_root()
    if snapshot_only:
        console.print_json(data=build_dashboard_snapshot())
        return
    console.print(Panel.fit(f"📊 AutoLoop Dashboard on http://{host}:{port}", style="bold cyan"))
    run_dashboard_server(host=host, port=port)


@app.command("system-metrics-report")
def system_metrics_report():
    _normalize_project_root()
    report_file = write_system_hardening_report()
    console.print(f"[green]System hardening report written:[/green] {report_file}")


@app.command("calibrate-auto-review-policy")
def calibrate_policy(
    policy_file: Annotated[str, typer.Option(help="Source policy file path")] = "",
    output_file: Annotated[str, typer.Option(help="Calibrated policy output path")] = "",
    apply_to_default: bool = typer.Option(
        False,
        "--apply-to-default",
        help="Replace default auto-review policy",
    ),
):
    _normalize_project_root()
    source = Path(policy_file).resolve() if policy_file.strip() else None
    target = Path(output_file).resolve() if output_file.strip() else None
    calibrated_path = calibrate_auto_review_policy(
        policy_file=source,
        output_file=target,
    )
    dataset = build_policy_tuning_dataset()
    console.print(f"[green]Calibrated policy written:[/green] {calibrated_path}")
    console.print(f"[cyan]Sample size:[/cyan] {dataset.get('sample_size', 0)}")
    console.print(f"[cyan]Passed:[/cyan] {dataset.get('passed_count', 0)}")
    console.print(f"[cyan]Rejected:[/cyan] {dataset.get('rejected_count', 0)}")
    if apply_to_default:
        default_policy = settings.project_root / "policies" / "auto_review_policy.json"
        default_policy.parent.mkdir(parents=True, exist_ok=True)
        default_policy.write_text(calibrated_path.read_text(encoding="utf-8"), encoding="utf-8")
        console.print(f"[green]Default policy updated:[/green] {default_policy}")


@app.command("diagnose-recovery")
def diagnose_recovery(
    status: Annotated[str, typer.Option(help="Workflow status")] = "failed",
    acceptance_status: Annotated[str, typer.Option(help="Acceptance status")] = "rejected",
    failure_type: Annotated[str, typer.Option(help="Failure type")] = "",
    first_failure_stage: Annotated[str, typer.Option(help="First failure stage")] = "",
    failed_modules: Annotated[str, typer.Option(help="Comma-separated failed modules")] = "",
    reviewer_codes: Annotated[str, typer.Option(help="Comma-separated reviewer codes")] = "",
    replan_rounds: Annotated[int, typer.Option(help="Current replan rounds")] = 0,
    failure_signature_count: Annotated[int, typer.Option(help="Failure signature repeat count")] = 0,
):
    _normalize_project_root()
    policy = load_failure_router_policy()
    failed_module_list = [item.strip() for item in failed_modules.split(",") if item.strip()]
    reviewer_code_list = [item.strip() for item in reviewer_codes.split(",") if item.strip()]
    action = route_recovery_action(
        status=status,
        acceptance_status=acceptance_status,
        failed_modules=failed_module_list,
        replan_rounds=replan_rounds,
        reviewer_codes=reviewer_code_list,
        failure_type=failure_type,
        first_failure_stage=first_failure_stage,
        failure_signature_count=failure_signature_count,
        max_review_loops=settings.max_review_loops_per_module,
        policy=policy,
    )
    console.print_json(
        data={
            "inputs": {
                "status": status,
                "acceptance_status": acceptance_status,
                "failure_type": failure_type,
                "first_failure_stage": first_failure_stage,
                "failed_modules": failed_module_list,
                "reviewer_codes": reviewer_code_list,
                "replan_rounds": replan_rounds,
                "failure_signature_count": failure_signature_count,
            },
            "recommended_action": action,
            "policy_snapshot": {
                "max_repeat_before_replan": policy.get("max_repeat_before_replan"),
                "non_retryable_failure_types": policy.get("non_retryable_failure_types", []),
            },
        }
    )


if __name__ == "__main__":
    app()
