from __future__ import annotations

import contextlib
import gzip
import json
import os
import tempfile
import time
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional


REPORT_SCHEMA_VERSION = "2.0.0"
DEFAULT_SCHEMA_FILE = (Path(__file__).resolve().parent / "schemas" / "tool_adaptation_report.schema.json").resolve()


@contextlib.contextmanager
def _benchmark_warning_filters(enabled: bool) -> Iterable[None]:
    if not enabled:
        yield
        return
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*Pydantic V1 style `@root_validator`.*")
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"pydantic(\.|$)")
        yield


def _now_utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def _clamp01(x: float) -> float:
    try:
        v = float(x)
    except Exception:
        v = 0.0
    return float(max(0.0, min(1.0, v)))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _model_to_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        try:
            out = value.model_dump()
            return out if isinstance(out, dict) else {"value": out}
        except Exception:
            pass
    if hasattr(value, "dict"):
        try:
            out = value.dict()
            return out if isinstance(out, dict) else {"value": out}
        except Exception:
            pass
    return {"value": str(value)}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        try:
            return _jsonable(value.model_dump())
        except Exception:
            pass
    if hasattr(value, "dict"):
        try:
            return _jsonable(value.dict())
        except Exception:
            pass
    return str(value)


@contextlib.contextmanager
def _temp_environ(patch: Dict[str, str]) -> Iterable[None]:
    old: Dict[str, Optional[str]] = {k: os.environ.get(k) for k in patch.keys()}
    try:
        for k, v in patch.items():
            os.environ[str(k)] = str(v)
        yield
    finally:
        for k, prev in old.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[str(k)] = str(prev)


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    title: str
    passed: bool
    score: float
    details: Dict[str, Any]
    issues: List[Dict[str, Any]]


def _issue(*, case_id: str, key: str, severity: str, message: str, evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "case_id": str(case_id),
        "key": str(key),
        "severity": str(severity),
        "message": str(message),
        "evidence": _jsonable(dict(evidence or {})),
    }


def _resolve_repo_root(repo_root: str | Path) -> Path:
    root = Path(repo_root).resolve()
    if (root / "pyproject.toml").exists() and (root / "quentin").exists():
        return root
    for parent in root.parents:
        if (parent / "pyproject.toml").exists() and (parent / "quentin").exists():
            return parent
    return root


def _scratch_env(*, repo_root: Path, scratch_root: Path, ci_mode: bool) -> Dict[str, str]:
    plugin_tools_dir = (repo_root / "extensions" / "tools").resolve()
    plugin_skills_dir = (repo_root / "extensions" / "skills").resolve()
    env = {
        "MEM_EMBED_PROVIDER": "disabled",
        "QUENTIN_MEMORY_EMBED_CACHE_ENABLE": "0",
        "QUENTIN_TOOL_CACHE_PATH": str((scratch_root / "tool_cache.db").resolve()),
        "QUENTIN_TOOL_PLUGINS_ENABLED": "1",
        "QUENTIN_TOOL_PLUGINS_DIRS": str(plugin_tools_dir),
        "QUENTIN_EXEC_SKILLS_ENABLED": "1",
        "QUENTIN_EXEC_SKILLS_DIRS": str(plugin_skills_dir),
        "QUENTIN_MEMORY_STORE": "sqlite",
        "QUENTIN_BENCHMARK_FIXTURE_MODE": "1",
        "TZ": "UTC",
    }
    if ci_mode:
        env.update(
            {
                "PYTHONHASHSEED": "0",
                "QUENTIN_TOOL_PLUGINS_LAZY_RELOAD": "0",
                "QUENTIN_PLUGIN_RUNTIME_ISOLATION": "1",
            }
        )
    return env


async def _call_tool(tool_manager: Any, *, tool_name: str, payload: Dict[str, Any]) -> Any:
    from quentin.tools.manager import ToolCallContext
    from quentin.tools.schemas import ToolCallRequest

    ctx = ToolCallContext(metadata={"actor": "tool_adaptation_benchmark", "session_id": "bench"})
    return await tool_manager.call_tool(ToolCallRequest(tool_name=tool_name, payload=dict(payload or {})), ctx=ctx)


def _extract_bench_payload(tool_result: Any) -> Dict[str, Any]:
    payload = _model_to_dict(getattr(tool_result, "output", tool_result))
    current = payload if isinstance(payload, dict) else {}
    # Unwrap common nesting patterns from ToolCallResult + plugin wrappers:
    # {"result": {...}}, {"cached": true, "result": {"result": {...}}}, etc.
    for _ in range(3):
        if not isinstance(current, dict):
            break
        if "mode" in current or "tool" in current:
            break
        nxt = current.get("result")
        if isinstance(nxt, dict):
            current = nxt
            continue
        break
    return current if isinstance(current, dict) else {}


def _read_trace_events(traces_dir: Path) -> List[Dict[str, Any]]:
    path = traces_dir / "events.jsonl.gz"
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    out.append(obj)
    except Exception:
        return []
    return out


def _case_container_sees_tool_plugins(*, repo_root: Path, scratch_root: Path, ci_mode: bool) -> CaseResult:
    case_id = "container_tool_plugins_visible"
    title = "Container默认 wiring 能看到 extensions/tools"
    issues: List[Dict[str, Any]] = []

    from quentin.bootstrap.container import Container

    with _temp_environ(_scratch_env(repo_root=repo_root, scratch_root=scratch_root, ci_mode=ci_mode)):
        c = Container(repo_root=scratch_root)
        tm = c.tool_manager
        names = tm.list_tool_names()
        ok = "bench.screwdriver" in set(names)
        if not ok:
            issues.append(
                _issue(
                    case_id=case_id,
                    key="bench_tool_missing",
                    severity="fail",
                    message="Container.tool_manager 未加载 tool plugin（bench.screwdriver 缺失）",
                    evidence={"tool_names_sample": names[:20]},
                )
            )
        help_obj = tm.get_tool_schema_help("bench.screwdriver") if ok else {"status": "skipped"}
        if ok and str(help_obj.get("status") or "") != "ok":
            ok = False
            issues.append(
                _issue(
                    case_id=case_id,
                    key="tool_help_failed",
                    severity="fail",
                    message="Tool schema help 不可用（bench.screwdriver）",
                    evidence={"help": help_obj},
                )
            )

    return CaseResult(
        case_id=case_id,
        title=title,
        passed=bool(ok),
        score=1.0 if ok else 0.0,
        details={"help": _jsonable(help_obj)},
        issues=issues,
    )


def _case_requires_env_gate(*, repo_root: Path, scratch_root: Path, ci_mode: bool) -> CaseResult:
    import asyncio

    case_id = "plugin_requires_env_gate"
    title = "插件 requires_env 在隔离模式下 fail-closed"
    issues: List[Dict[str, Any]] = []

    from quentin.bootstrap.container import Container

    env = dict(_scratch_env(repo_root=repo_root, scratch_root=scratch_root, ci_mode=ci_mode))
    env["QUENTIN_PLUGIN_RUNTIME_ISOLATION"] = "1"
    with _temp_environ(env):
        c = Container(repo_root=scratch_root)
        tm = c.tool_manager
        try:
            res = asyncio.run(_call_tool(tm, tool_name="test_isolated_tool", payload={"ping": "pong"}))
        except Exception as exc:
            res = {"success": False, "error": repr(exc), "output": None, "meta": {}}

    result_dict = _model_to_dict(res)
    err = str(result_dict.get("error") or "")
    ok = "missing_required_env:SECRET_KEY_REQUIRED" in err
    if not ok:
        issues.append(
            _issue(
                case_id=case_id,
                key="requires_env_not_enforced",
                severity="fail",
                message="requires_env 未被正确拦截（应返回 missing_required_env:SECRET_KEY_REQUIRED）",
                evidence={"error": err, "result": result_dict},
            )
        )

    return CaseResult(
        case_id=case_id,
        title=title,
        passed=bool(ok),
        score=1.0 if ok else 0.0,
        details={"error": err},
        issues=issues,
    )


def _case_tool_usage_writeback(*, repo_root: Path, scratch_root: Path, ci_mode: bool) -> CaseResult:
    import asyncio

    case_id = "tool_usage_writeback_to_memory"
    title = "工具调用写回 tool_knowledge（例子/统计）"
    issues: List[Dict[str, Any]] = []

    from quentin.bootstrap.container import Container
    from quentin.memory.tool_knowledge import stable_tool_knowledge_id

    with _temp_environ(_scratch_env(repo_root=repo_root, scratch_root=scratch_root, ci_mode=ci_mode)):
        c = Container(repo_root=scratch_root)
        tm = c.tool_manager
        mf = c.memory_fabric

        r1 = asyncio.run(
            _call_tool(tm, tool_name="bench.screwdriver", payload={"task": "tighten a screw", "target": "M3"})
        )
        r2 = asyncio.run(
            _call_tool(
                tm,
                tool_name="bench.screwdriver",
                payload={"task": "open package tape", "target": "box-12", "mode": "auto"},
            )
        )

        rec_id = stable_tool_knowledge_id("bench.screwdriver")
        rec = mf.store.get(rec_id)

        ok = True
        if rec is None:
            ok = False
            issues.append(
                _issue(
                    case_id=case_id,
                    key="tool_knowledge_missing",
                    severity="fail",
                    message="未写入 tool_knowledge 记忆（stable id record 缺失）",
                    evidence={"record_id": rec_id},
                )
            )
            md = {}
        else:
            md = dict(rec.metadata or {})

        stats = md.get("stats") if isinstance(md.get("stats"), dict) else {}
        examples = md.get("examples") if isinstance(md.get("examples"), list) else []

        call_count = int(stats.get("call_count") or 0)
        if call_count < 2:
            ok = False
            issues.append(
                _issue(
                    case_id=case_id,
                    key="call_count_too_low",
                    severity="fail",
                    message="tool_knowledge.stats.call_count 未随调用增长到 >=2",
                    evidence={"call_count": call_count, "stats": stats},
                )
            )

        if len(examples) < 2:
            ok = False
            issues.append(
                _issue(
                    case_id=case_id,
                    key="examples_missing",
                    severity="fail",
                    message="tool_knowledge.examples 不足（期望 >=2）",
                    evidence={"examples_len": len(examples), "examples": examples},
                )
            )

        succ1 = bool(_model_to_dict(r1).get("success"))
        succ2 = bool(_model_to_dict(r2).get("success"))
        if not (succ1 and succ2):
            ok = False
            issues.append(
                _issue(
                    case_id=case_id,
                    key="tool_invocation_failed",
                    severity="fail",
                    message="bench.screwdriver 调用失败（基准应是稳定可调用）",
                    evidence={"r1": _model_to_dict(r1), "r2": _model_to_dict(r2)},
                )
            )

    return CaseResult(
        case_id=case_id,
        title=title,
        passed=bool(ok),
        score=1.0 if ok else 0.0,
        details={"record_id": rec_id, "stats": _jsonable(stats), "examples_len": len(examples)},
        issues=issues,
    )


def _case_plugin_cache(*, repo_root: Path, scratch_root: Path, ci_mode: bool) -> CaseResult:
    import asyncio

    case_id = "tool_plugin_cache"
    title = "tool plugin cache 命中（减少重复成本）"
    issues: List[Dict[str, Any]] = []

    from quentin.bootstrap.container import Container

    with _temp_environ(_scratch_env(repo_root=repo_root, scratch_root=scratch_root, ci_mode=ci_mode)):
        c = Container(repo_root=scratch_root)
        tm = c.tool_manager

        payload = {"task": "tighten a screw", "target": "M2", "mode": "screw"}
        t1 = time.perf_counter()
        r1 = asyncio.run(_call_tool(tm, tool_name="bench.screwdriver", payload=payload))
        latency_first_ms = max(0.0, (time.perf_counter() - t1) * 1000.0)

        t2 = time.perf_counter()
        r2 = asyncio.run(_call_tool(tm, tool_name="bench.screwdriver", payload=payload))
        latency_cached_ms = max(0.0, (time.perf_counter() - t2) * 1000.0)

    out2 = _model_to_dict(getattr(r2, "output", None))
    cached = bool(isinstance(out2, dict) and out2.get("cached") is True)
    speedup_ratio = (latency_first_ms / latency_cached_ms) if latency_cached_ms > 0 else 999.0

    ok = bool(cached)
    score = 1.0 if ok else 0.0
    if not cached:
        issues.append(
            _issue(
                case_id=case_id,
                key="cache_miss",
                severity="warn",
                message="未观察到 cache 命中（output.cached != true）",
                evidence={"r1": _model_to_dict(r1), "r2": _model_to_dict(r2)},
            )
        )
    elif speedup_ratio < 1.02:
        score = 0.75
        issues.append(
            _issue(
                case_id=case_id,
                key="cache_low_speedup",
                severity="warn",
                message="观察到 cache 命中，但速度收益很小（speedup_ratio < 1.02）",
                evidence={
                    "latency_first_ms": latency_first_ms,
                    "latency_cached_ms": latency_cached_ms,
                    "speedup_ratio": speedup_ratio,
                },
            )
        )

    return CaseResult(
        case_id=case_id,
        title=title,
        passed=bool(ok),
        score=float(score),
        details={
            "cached_second_call": cached,
            "latency_first_ms": latency_first_ms,
            "latency_cached_ms": latency_cached_ms,
            "speedup_ratio": speedup_ratio,
        },
        issues=issues,
    )


def _case_exec_skill_plugin(*, repo_root: Path, scratch_root: Path, ci_mode: bool) -> CaseResult:
    case_id = "exec_skill_plugin_discovery"
    title = "exec-skill plugin 可发现/可调用"
    issues: List[Dict[str, Any]] = []

    from quentin.bootstrap.container import Container
    from quentin.skills.exec_plugin_loader import discover_exec_skill_plugins, load_exec_skill_callable, resolve_exec_skill

    with _temp_environ(_scratch_env(repo_root=repo_root, scratch_root=scratch_root, ci_mode=ci_mode)):
        c = Container(repo_root=scratch_root)
        plugins = discover_exec_skill_plugins(str(c.repo_root))
        found = [p for p in plugins if p.skill_id == "bench_unpack" or p.name == "bench.unpack"]

        ok = bool(found)
        if not ok:
            issues.append(
                _issue(
                    case_id=case_id,
                    key="exec_skill_missing",
                    severity="fail",
                    message="未发现 bench exec-skill（bench_unpack / bench.unpack）",
                    evidence={"discovered_count": len(plugins)},
                )
            )
            return CaseResult(case_id=case_id, title=title, passed=False, score=0.0, details={}, issues=issues)

        plugin = found[0]
        fn = load_exec_skill_callable(plugin=plugin)
        out = fn({"text": "a b  c"})
        ok = isinstance(out, dict) and str(out.get("status") or "") == "ok"
        if not ok:
            issues.append(
                _issue(
                    case_id=case_id,
                    key="exec_skill_call_failed",
                    severity="fail",
                    message="exec-skill 调用失败（bench.unpack）",
                    evidence={"output": out},
                )
            )

        resolved = resolve_exec_skill(str(c.repo_root), "bench_unpack")
        if resolved is None:
            ok = False
            issues.append(
                _issue(
                    case_id=case_id,
                    key="exec_skill_resolve_failed",
                    severity="fail",
                    message="resolve_exec_skill 未能解析 bench_unpack",
                )
            )

    return CaseResult(
        case_id=case_id,
        title=title,
        passed=bool(ok),
        score=1.0 if ok else 0.0,
        details={"output_keys": list((out.get("output") or {}).keys()) if isinstance(out, dict) else []},
        issues=issues,
    )


def _case_decision_memory_reuse_effect(*, repo_root: Path, scratch_root: Path, ci_mode: bool) -> CaseResult:
    import asyncio
    from types import SimpleNamespace

    case_id = "decision_memory_reuse_effect"
    title = "工具记忆复用 A/B 对决策重试的真实增益"
    issues: List[Dict[str, Any]] = []

    import quentin.execution.skill_executor as executor_mod
    from quentin.bootstrap.container import Container
    from quentin.execution.skill_executor import Executor, StepExecutionRecord
    from quentin.memory.fabric import MemoryFabric
    from quentin.memory.models import MemoryTier
    from quentin.memory.tool_knowledge import ToolKnowledgeEntry

    class _BenchRouter:
        def route(self, mode: str = "", task_type: str = "generic") -> Any:
            _ = (mode, task_type)
            return SimpleNamespace(provider="ollama", name="bench-local")

    def _run_once(*, prompt_enabled: bool) -> Dict[str, Any]:
        with _temp_environ({"QUENTIN_EXECUTOR_TOOL_KNOWLEDGE_PROMPT": "1" if prompt_enabled else "0"}):
            container = Container(repo_root=scratch_root)
            executor = Executor(repo_root=scratch_root, model_router=_BenchRouter(), tool_manager=container.tool_manager)
            record = StepExecutionRecord(
                step_id=f"bench-ab-{'on' if prompt_enabled else 'off'}",
                description="Open package seal safely, then report completion.",
                skill_id=None,
                executor_mode="llm",
                success=False,
            )
            decision_trace: List[Dict[str, Any]] = []
            call_counter = {"count": 0}

            def _fake_call_llm(*args, **kwargs):  # type: ignore[no-untyped-def]
                call_counter["count"] = int(call_counter.get("count") or 0) + 1
                user_prompt = str(kwargs.get("user_prompt") or "")
                system_prompt = str(kwargs.get("system_prompt") or "")
                payload = {}
                try:
                    payload = json.loads(user_prompt) if user_prompt else {}
                except Exception:
                    payload = {}
                iteration = _safe_int((payload or {}).get("iteration"), 0)
                feedback = (payload or {}).get("feedback") if isinstance((payload or {}).get("feedback"), list) else []
                tool_feedback = []
                for item in feedback:
                    if not isinstance(item, dict):
                        continue
                    tc = item.get("tool_call") if isinstance(item.get("tool_call"), dict) else {}
                    tr = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
                    tool_feedback.append({"tool_name": str(tc.get("tool_name") or ""), "success": bool(tr.get("success")), "error": str(tr.get("error") or "")})
                if any(bool(x.get("success")) for x in tool_feedback):
                    decision_trace.append({"iteration": iteration, "tool_name": "", "reason": "finish_after_success"})
                    return json.dumps({"status": "ok", "result": "done", "call_tool": None}, ensure_ascii=False)

                has_knowledge = ("TOOL KNOWLEDGE (learned usage):" in system_prompt) and ("bench.screwdriver" in system_prompt)
                fallback_seen = any("tool_not_found" in str(x.get("error") or "") for x in tool_feedback)
                if fallback_seen:
                    decision_trace.append({"iteration": iteration, "tool_name": "bench.screwdriver", "reason": "fallback_after_not_found"})
                    return json.dumps(
                        {
                            "status": "ok",
                            "result": "fallback to known multipurpose tool",
                            "call_tool": {"tool_name": "bench.screwdriver", "args": {"task": "open package seal tape", "mode": "auto"}},
                        },
                        ensure_ascii=False,
                    )
                if has_knowledge:
                    decision_trace.append({"iteration": iteration, "tool_name": "bench.screwdriver", "reason": "memory_direct_hit"})
                    return json.dumps(
                        {
                            "status": "ok",
                            "result": "memory suggests screwdriver affordance",
                            "call_tool": {"tool_name": "bench.screwdriver", "args": {"task": "open package seal tape", "mode": "auto"}},
                        },
                        ensure_ascii=False,
                    )
                decision_trace.append({"iteration": iteration, "tool_name": "bench.box_opener", "reason": "no_memory_guess"})
                return json.dumps(
                    {
                        "status": "ok",
                        "result": "try guessed tool before fallback",
                        "call_tool": {"tool_name": "bench.box_opener", "args": {"task": "open package seal tape"}},
                    },
                    ensure_ascii=False,
                )

            original_call_llm = getattr(executor_mod, "call_llm")
            setattr(executor_mod, "call_llm", _fake_call_llm)
            try:
                asyncio.run(
                    executor._fallback_llm_execute(
                        step={"step_id": record.step_id, "description": record.description},
                        goal=SimpleNamespace(domain="core", environment="sandbox"),
                        context={"max_step_iterations": 4, "native_tool_calling": False},
                        record=record,
                    )
                )
            finally:
                setattr(executor_mod, "call_llm", original_call_llm)

            successful_tool_index = -1
            tool_calls = [d for d in decision_trace if str(d.get("tool_name") or "").strip()]
            selected_seq = [str(d.get("tool_name") or "") for d in tool_calls]
            for idx, item in enumerate(tool_calls):
                if str(item.get("tool_name") or "") == "bench.screwdriver":
                    successful_tool_index = idx
                    break
            retries_before_success = successful_tool_index if successful_tool_index >= 0 else max(0, len(tool_calls) - 1)
            return {
                "success": bool(record.success),
                "llm_calls": int(call_counter.get("count") or 0),
                "tool_calls": len(tool_calls),
                "retries_before_success": int(retries_before_success),
                "selected_sequence": selected_seq,
                "trace": decision_trace,
            }

    with _temp_environ(_scratch_env(repo_root=repo_root, scratch_root=scratch_root, ci_mode=ci_mode)):
        (scratch_root / "data").mkdir(parents=True, exist_ok=True)
        mf = MemoryFabric(repo_root=scratch_root)
        entry = ToolKnowledgeEntry(
            tool_name="bench.screwdriver",
            signature="bench.screwdriver(task,target,mode)",
            description="Benchmark multipurpose tool.",
            examples=[{"input": {"task": "open package tape"}, "output": {"mode": "cut"}}],
            stats={"call_count": 5, "success_rate": 1.0, "last_used_at": _now_utc_iso()},
        )
        rec = entry.to_memory_record(tier=MemoryTier.LTS)
        exists = mf.store.get(rec.id)
        if exists is None:
            mf.store.add(rec)
        else:
            rec.created_at = exists.created_at
            mf.store.update(rec)

        run_on = _run_once(prompt_enabled=True)
        run_off = _run_once(prompt_enabled=False)

    retry_delta = int(run_off.get("retries_before_success") or 0) - int(run_on.get("retries_before_success") or 0)
    first_on = str((run_on.get("selected_sequence") or [""])[0] if (run_on.get("selected_sequence") or []) else "")
    first_off = str((run_off.get("selected_sequence") or [""])[0] if (run_off.get("selected_sequence") or []) else "")
    tool_choice_delta = bool(first_on == "bench.screwdriver" and first_off != "bench.screwdriver")
    ok = bool(run_on.get("success")) and bool(run_off.get("success")) and bool(retry_delta >= 1 and tool_choice_delta)
    score = 0.0
    if bool(run_on.get("success")) and bool(run_off.get("success")):
        score += 0.4
    if retry_delta >= 1:
        score += 0.4
    if tool_choice_delta:
        score += 0.2
    score = _clamp01(score)
    if not ok:
        issues.append(
            _issue(
                case_id=case_id,
                key="decision_reuse_delta_insufficient",
                severity="fail",
                message="A/B 对比未形成足够的决策复用增益（首选工具或重试次数无差异）",
                evidence={"run_on": run_on, "run_off": run_off, "retry_delta": retry_delta, "tool_choice_delta": tool_choice_delta},
            )
        )

    return CaseResult(
        case_id=case_id,
        title=title,
        passed=ok,
        score=score,
        details={
            "run_on": run_on,
            "run_off": run_off,
            "retry_delta": retry_delta,
            "tool_choice_delta": tool_choice_delta,
            "ab_gain_observed": bool(retry_delta >= 1),
        },
        issues=issues,
    )


def _case_nl_generalization(*, repo_root: Path, scratch_root: Path, ci_mode: bool) -> CaseResult:
    import asyncio
    from types import SimpleNamespace

    case_id = "nl_generalization_affordance"
    title = "规划/执行层自然语言选工具与可解释回退"
    issues: List[Dict[str, Any]] = []

    import quentin.execution.skill_executor as executor_mod
    from quentin.bootstrap.container import Container
    from quentin.execution.skill_executor import Executor, StepExecutionRecord

    class _BenchRouter:
        def route(self, mode: str = "", task_type: str = "generic") -> Any:
            _ = (mode, task_type)
            return SimpleNamespace(provider="ollama", name="bench-local")

    task_desc = "Need to open package seal tape and keep content safe."
    decision_trace: List[Dict[str, Any]] = []
    with _temp_environ(_scratch_env(repo_root=repo_root, scratch_root=scratch_root, ci_mode=ci_mode)):
        container = Container(repo_root=scratch_root)
        executor = Executor(repo_root=scratch_root, model_router=_BenchRouter(), tool_manager=container.tool_manager)
        record = StepExecutionRecord(
            step_id="bench-nl-generalization",
            description=task_desc,
            skill_id=None,
            executor_mode="llm",
            success=False,
        )

        def _fake_call_llm(*args, **kwargs):  # type: ignore[no-untyped-def]
            user_prompt = str(kwargs.get("user_prompt") or "")
            payload = {}
            try:
                payload = json.loads(user_prompt) if user_prompt else {}
            except Exception:
                payload = {}
            iteration = _safe_int((payload or {}).get("iteration"), 0)
            feedback = (payload or {}).get("feedback") if isinstance((payload or {}).get("feedback"), list) else []
            saw_not_found = False
            saw_success = False
            for item in feedback:
                if not isinstance(item, dict):
                    continue
                tr = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
                if "tool_not_found" in str(tr.get("error") or ""):
                    saw_not_found = True
                if bool(tr.get("success")):
                    saw_success = True
            if saw_success:
                decision_trace.append({"iteration": iteration, "selected_tool": "", "reason": "finish_after_success"})
                return json.dumps({"status": "ok", "result": "done", "call_tool": None}, ensure_ascii=False)
            if saw_not_found:
                decision_trace.append(
                    {
                        "iteration": iteration,
                        "selected_tool": "bench.screwdriver",
                        "reason": "fallback_to_affordance_tool_after_tool_not_found",
                    }
                )
                return json.dumps(
                    {
                        "status": "ok",
                        "result": "fallback because guessed tool missing",
                        "call_tool": {"tool_name": "bench.screwdriver", "args": {"task": task_desc, "mode": "auto"}},
                    },
                    ensure_ascii=False,
                )
            decision_trace.append({"iteration": iteration, "selected_tool": "bench.box_opener", "reason": "initial_guess_from_nl"})
            return json.dumps(
                {
                    "status": "ok",
                    "result": "first try guessed single-purpose tool",
                    "call_tool": {"tool_name": "bench.box_opener", "args": {"task": task_desc}},
                },
                ensure_ascii=False,
            )

        original_call_llm = getattr(executor_mod, "call_llm")
        setattr(executor_mod, "call_llm", _fake_call_llm)
        try:
            asyncio.run(
                executor._fallback_llm_execute(
                    step={"step_id": record.step_id, "description": task_desc},
                    goal=SimpleNamespace(domain="core", environment="sandbox"),
                    context={"max_step_iterations": 4, "native_tool_calling": False},
                    record=record,
                )
            )
        finally:
            setattr(executor_mod, "call_llm", original_call_llm)

    selected_tools = [str(x.get("selected_tool") or "") for x in decision_trace if str(x.get("selected_tool") or "").strip()]
    fallback_reasons = [str(x.get("reason") or "") for x in decision_trace if "fallback" in str(x.get("reason") or "")]
    has_fallback = bool(any(t == "bench.screwdriver" for t in selected_tools))
    has_trace_reason = bool(len(fallback_reasons) >= 1)
    ok = bool(record.success) and bool(has_fallback and has_trace_reason)
    matched = int(has_fallback and has_trace_reason)

    if not ok:
        issues.append(
            _issue(
                case_id=case_id,
                key="executor_selection_trace_missing",
                severity="fail",
                message="执行层选工具路径未记录到可解释回退轨迹",
                evidence={
                    "record_success": bool(record.success),
                    "selected_tools": selected_tools,
                    "trace": decision_trace,
                },
            )
        )

    score = 1.0 if ok else float(max(0.0, matched * 0.5))
    return CaseResult(
        case_id=case_id,
        title=title,
        passed=ok,
        score=score,
        details={
            "selected_tools": selected_tools,
            "trace": decision_trace,
            "fallback_reasons": fallback_reasons,
            "record_success": bool(record.success),
        },
        issues=issues,
    )


def _case_memory_conflict_resolution(*, repo_root: Path, scratch_root: Path, ci_mode: bool) -> CaseResult:
    case_id = "memory_conflict_resolution"
    title = "冲突记忆过滤（未知工具不污染执行提示）"
    issues: List[Dict[str, Any]] = []

    from quentin.bootstrap.container import Container
    from quentin.execution.skill_executor import Executor
    from quentin.memory.fabric import MemoryFabric
    from quentin.memory.models import MemoryTier
    from quentin.memory.tool_knowledge import ToolKnowledgeEntry

    with _temp_environ(_scratch_env(repo_root=repo_root, scratch_root=scratch_root, ci_mode=ci_mode)):
        (scratch_root / "data").mkdir(parents=True, exist_ok=True)
        c = Container(repo_root=scratch_root)
        mf = MemoryFabric(repo_root=scratch_root)

        entries = [
            ToolKnowledgeEntry(
                tool_name="bench.screwdriver",
                signature="bench.screwdriver(task,target,mode)",
                description="Known tool for screw/cut affordances.",
                examples=[{"input": {"task": "open package tape"}, "output": {"mode": "cut"}}],
                stats={"call_count": 2, "success_rate": 1.0, "last_used_at": _now_utc_iso()},
            ),
            ToolKnowledgeEntry(
                tool_name="bench.box_opener",
                signature="bench.box_opener(task)",
                description="Unknown tool (should be filtered).",
                examples=[{"input": {"task": "open package tape"}, "output": {"status": "ok"}}],
                stats={"call_count": 50, "success_rate": 0.9, "last_used_at": _now_utc_iso()},
            ),
        ]
        for entry in entries:
            rec = entry.to_memory_record(tier=MemoryTier.LTS)
            prev = mf.store.get(rec.id)
            if prev is None:
                mf.store.add(rec)
            else:
                rec.created_at = prev.created_at
                mf.store.update(rec)

        with _temp_environ({"QUENTIN_EXECUTOR_TOOL_KNOWLEDGE_PROMPT": "1"}):
            ex = Executor(repo_root=scratch_root, tool_manager=c.tool_manager)
            block = ex._build_tool_knowledge_block()

    has_known = "bench.screwdriver" in str(block)
    filtered_unknown = "bench.box_opener" not in str(block)
    ok = bool(has_known and filtered_unknown)
    if not ok:
        issues.append(
            _issue(
                case_id=case_id,
                key="memory_conflict_filter_failed",
                severity="fail",
                message="冲突记忆过滤失效：未知工具进入执行提示词",
                evidence={"block": block, "has_known": has_known, "filtered_unknown": filtered_unknown},
            )
        )

    return CaseResult(
        case_id=case_id,
        title=title,
        passed=ok,
        score=1.0 if ok else 0.0,
        details={"has_known": has_known, "filtered_unknown": filtered_unknown},
        issues=issues,
    )


def _case_full_loop_adversarial_memory(*, repo_root: Path, scratch_root: Path, ci_mode: bool) -> CaseResult:
    import uuid

    case_id = "full_loop_adversarial_memory"
    title = "全链路鲁棒性（planner->executor->done，在对抗记忆下注入）"
    issues: List[Dict[str, Any]] = []

    from quentin.bootstrap.container import Container
    from quentin.cognitive.loop_models import CognitiveTask
    from quentin.memory.models import MemoryTier
    from quentin.memory.tool_knowledge import ToolKnowledgeEntry

    traces_dir = (scratch_root / "traces_full_loop").resolve()
    env = dict(_scratch_env(repo_root=repo_root, scratch_root=scratch_root, ci_mode=ci_mode))
    env.update(
        {
            "LLM_PROVIDER": "stub",
            "LLM_MODEL": "stub-model",
            "QUENTIN_LLM_FORCE_STUB": "1",
            "QUENTIN_COUNCIL_FORCE_FIRST": "1",
            "QUENTIN_TOOL_CALL_PROTOCOLS": "0",
            "QUENTIN_REFLECTION_FAILURE_THRESHOLD": "1",
            "QUENTIN_MAX_LOOPS": "3",
            "QUENTIN_BILLING_BYPASS": "1",
            "QUENTIN_ENABLE_PRE_SENSING": "0",
            "QUENTIN_TRACES_DIR": str(traces_dir),
            "QUENTIN_EXECUTOR_TOOL_KNOWLEDGE_PROMPT": "1",
        }
    )

    with _temp_environ(env):
        c = Container(repo_root=scratch_root)
        mf = c.memory_fabric

        adversarial = ToolKnowledgeEntry(
            tool_name="bench.box_opener",
            signature="bench.box_opener(task)",
            description="Adversarial stale tool memory.",
            examples=[{"input": {"task": "open package tape"}, "output": {"status": "ok"}}],
            stats={"call_count": 99, "success_rate": 0.95, "last_used_at": _now_utc_iso()},
        )
        rec = adversarial.to_memory_record(tier=MemoryTier.LTS)
        prev = mf.store.get(rec.id)
        if prev is None:
            mf.store.add(rec)
        else:
            rec.created_at = prev.created_at
            mf.store.update(rec)

        before = _read_trace_events(traces_dir)
        task = CognitiveTask(
            input_text=(
                "BENCH_SCENARIO:tool_error\n"
                "Goal: even with adversarial memory, recover via reflection and finish with BENCH_DONE."
            ),
            task_id=f"bench_full_loop_{uuid.uuid4().hex[:10]}",
            domain="core",
            environment="sandbox",
            metadata={"session_id": "bench_full_loop"},
        )
        res = c.cognitive_loop.run_task(task)
        events_all = _read_trace_events(traces_dir)
        events = events_all[len(before) :] if len(before) <= len(events_all) else events_all

    trace_id = ""
    for e in reversed(events):
        if str(e.get("event_type") or "").strip().lower() == "summary":
            trace_id = str(e.get("trace_id") or "")
            if trace_id:
                break
    trace_events = [e for e in events if str(e.get("trace_id") or "") == trace_id] if trace_id else events

    fallback_reason_present = False
    for e in trace_events:
        payload = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        if payload.get("action") == "attempt_evaluated":
            ae = payload.get("attempt_evaluation") if isinstance(payload.get("attempt_evaluation"), dict) else {}
            if str(ae.get("category") or "").strip().lower() == "tool_execution_error":
                fallback_reason_present = True
                break
        if str(e.get("event_type") or "").strip().lower() == "planning":
            ctx = payload.get("context_injected") if isinstance(payload.get("context_injected"), dict) else {}
            diag = ctx.get("planning_diagnostics") if isinstance(ctx.get("planning_diagnostics"), dict) else {}
            if str(diag.get("failure_category") or "").strip().lower() == "tool_execution_error":
                fallback_reason_present = True
                break

    done = bool(getattr(res, "done", False))
    final_output = str(getattr(res, "final_output", "") or "")
    actions_summary = str(getattr(res, "actions_summary", "") or "")
    done_evidence = bool(done and ("BENCH_DONE" in final_output or "BENCH_DONE" in actions_summary))
    ok = bool(done_evidence and fallback_reason_present)
    if not done_evidence:
        issues.append(
            _issue(
                case_id=case_id,
                key="full_loop_not_done",
                severity="fail",
                message="全链路在对抗记忆下未达到 done 或缺失 BENCH_DONE 证据",
                evidence={"done": done, "final_output": final_output[:280], "actions_summary": actions_summary[:280]},
            )
        )
    if not fallback_reason_present:
        issues.append(
            _issue(
                case_id=case_id,
                key="full_loop_fallback_trace_missing",
                severity="fail",
                message="未在 trace 中观察到回退原因（tool_execution_error）",
                evidence={"trace_id": trace_id, "trace_event_count": len(trace_events)},
            )
        )

    score = 0.0
    if done_evidence:
        score += 0.6
    if fallback_reason_present:
        score += 0.4
    score = _clamp01(score)
    return CaseResult(
        case_id=case_id,
        title=title,
        passed=ok,
        score=score,
        details={
            "done": done,
            "done_evidence": done_evidence,
            "fallback_reason_present": fallback_reason_present,
            "trace_id": trace_id,
            "trace_event_count": len(trace_events),
            "traces_dir": str(traces_dir),
        },
        issues=issues,
    )


def _case_channel_gateway_contract(*, repo_root: Path, scratch_root: Path, ci_mode: bool) -> CaseResult:
    case_id = "channel_gateway_contract"
    title = "Channel Gateway 合同与降级行为"
    issues: List[Dict[str, Any]] = []

    from fastapi.testclient import TestClient
    from quentin.infra.channels.gateway_server import GatewayServer
    from quentin.infra.channels.provider import ChannelProvider

    _ = repo_root
    _ = scratch_root
    _ = ci_mode

    class _FakeLoop:
        async def run_task_async(self, task: Any) -> None:
            _ = task
            return None

    class _FakeContainer:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            _ = (args, kwargs)
            self.cognitive_loop = _FakeLoop()

    class _FakeProvider(ChannelProvider):
        def __init__(self, pid: str) -> None:
            self._pid = pid
            self.sent: List[Dict[str, Any]] = []

        @property
        def provider_id(self) -> str:
            return self._pid

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        async def send_text(self, target_id: str, text: str, **kwargs: Any) -> None:
            self.sent.append({"target_id": target_id, "text": text, "kwargs": dict(kwargs or {})})

        def set_on_message(self, callback: Any) -> None:
            _ = callback
            return None

    from unittest.mock import patch

    with _temp_environ({"FF_GATEWAY_V1": "0"}):
        gw_disabled = GatewayServer()
        c0 = TestClient(gw_disabled.app)
        resp_disabled = c0.post(
            "/gateway/messages/inbound",
            json={"channel": "discord", "sender_id": "u1", "chat_id": "c1", "text": "hello"},
        )
    disabled_ok = int(resp_disabled.status_code) == 503

    with _temp_environ({"FF_GATEWAY_V1": "1"}):
        gw = GatewayServer()
        provider = _FakeProvider("discord")
        gw.register_provider(provider)
        c1 = TestClient(gw.app)

        with patch("quentin.bootstrap.container.Container", _FakeContainer):
            resp_inbound = c1.post(
                "/gateway/messages/inbound",
                json={"channel": "discord", "sender_id": "u1", "chat_id": "c1", "text": "hello from gateway"},
            )
        inbound_ok = int(resp_inbound.status_code) == 200 and str((resp_inbound.json() or {}).get("status") or "") == "accepted"

        resp_missing = c1.post(
            "/gateway/messages/outbound",
            json={"channel": "slack", "target_id": "c2", "text": "x"},
        )
        missing_ok = int(resp_missing.status_code) == 404

        resp_outbound = c1.post(
            "/gateway/messages/outbound",
            json={"channel": "discord", "target_id": "c1", "text": "reply text"},
        )
        outbound_ok = int(resp_outbound.status_code) == 200 and len(provider.sent) == 1

    ok = bool(disabled_ok and inbound_ok and outbound_ok and missing_ok)
    if not ok:
        issues.append(
            _issue(
                case_id=case_id,
                key="gateway_contract_failed",
                severity="fail",
                message="Gateway 合同（flag gating / inbound accepted / outbound routing）不满足",
                evidence={
                    "disabled_status": int(resp_disabled.status_code),
                    "inbound_ok": inbound_ok,
                    "missing_ok": missing_ok,
                    "outbound_ok": outbound_ok,
                    "provider_sent_count": len(provider.sent),
                },
            )
        )
    score = 0.0
    score += 0.25 if disabled_ok else 0.0
    score += 0.25 if inbound_ok else 0.0
    score += 0.25 if missing_ok else 0.0
    score += 0.25 if outbound_ok else 0.0
    return CaseResult(
        case_id=case_id,
        title=title,
        passed=ok,
        score=_clamp01(score),
        details={
            "disabled_gate": disabled_ok,
            "inbound_accepted": inbound_ok,
            "outbound_missing_provider_404": missing_ok,
            "outbound_routed": outbound_ok,
        },
        issues=issues,
    )


def _case_domain_adapter_channel_gateway(*, repo_root: Path, scratch_root: Path, ci_mode: bool) -> CaseResult:
    import asyncio

    case_id = "domain_adapter_channel_gateway"
    title = "Domain Adapter 跨渠道复用（统一意图到渠道动作）"
    issues: List[Dict[str, Any]] = []

    from quentin.domains.base import DomainRegistry, DomainTask
    from quentin.infra.logging import Tracer
    from quentin.tools.manager import ToolManager

    _ = (repo_root, scratch_root, ci_mode)

    class _SupportAdapter:
        name = "support"
        description = "Support intent adapter for multi-channel gateway actions."

        async def register_tools(self, tool_manager: ToolManager) -> None:
            def _send(params: Dict[str, Any]) -> Dict[str, Any]:
                channel = str(params.get("channel") or "").strip().lower()
                target_id = str(params.get("target_id") or "").strip()
                text = str(params.get("text") or "").strip()
                if channel not in {"discord", "slack", "telegram"}:
                    return {"status": "error", "error": f"unsupported_channel:{channel}"}
                return {"status": "ok", "channel": channel, "target_id": target_id, "text": text}

            tool_manager.register("channel.send_text", _send)

        async def handle_task(self, task: DomainTask, tool_manager: ToolManager) -> Dict[str, Any]:
            from quentin.tools.manager import ToolCallContext
            from quentin.tools.schemas import ToolCallRequest

            payload = dict(task.input or {})
            channel = str(payload.get("channel") or "").strip().lower()
            target_id = str(payload.get("target_id") or "").strip() or "default"
            text = str(payload.get("text") or task.goal).strip()
            out = await tool_manager.call_tool(
                ToolCallRequest(
                    tool_name="channel.send_text",
                    payload={"channel": channel, "target_id": target_id, "text": text},
                ),
                ctx=ToolCallContext(metadata={"actor": "bench_domain_adapter", "session_id": f"bench:{channel}:{target_id}"}),
            )
            out_dict = _model_to_dict(out)
            result = _model_to_dict(out_dict.get("output"))
            return {
                "status": str(result.get("status") or "error"),
                "normalized_intent": {"intent": "send_message", "channel": channel, "target_id": target_id},
                "gateway_action": result,
            }

    tm = ToolManager()
    reg = DomainRegistry(tracer=Tracer(repo_root="."), tool_manager=tm)
    adapter = _SupportAdapter()
    asyncio.run(reg.register_domain(adapter))

    tasks = [
        DomainTask(domain="support", goal="notify user", input={"channel": "discord", "target_id": "c1", "text": "hi"}),
        DomainTask(domain="support", goal="notify user", input={"channel": "slack", "target_id": "c2", "text": "hi"}),
        DomainTask(domain="support", goal="notify user", input={"channel": "telegram", "target_id": "c3", "text": "hi"}),
    ]
    observed: List[Dict[str, Any]] = []
    for task in tasks:
        out = asyncio.run(reg.route_task(task))
        observed.append(dict(out or {}))

    success_count = 0
    for out in observed:
        if str(out.get("status") or "") == "ok":
            normalized = out.get("normalized_intent") if isinstance(out.get("normalized_intent"), dict) else {}
            action = out.get("gateway_action") if isinstance(out.get("gateway_action"), dict) else {}
            if str(normalized.get("intent") or "") == "send_message" and str(action.get("status") or "") == "ok":
                success_count += 1
    ok = bool(success_count == len(tasks))
    if not ok:
        issues.append(
            _issue(
                case_id=case_id,
                key="domain_adapter_channel_reuse_failed",
                severity="fail",
                message="Domain adapter 未稳定复用到多渠道动作",
                evidence={"observed": observed, "success_count": success_count, "total": len(tasks)},
            )
        )
    return CaseResult(
        case_id=case_id,
        title=title,
        passed=ok,
        score=float(success_count / max(1, len(tasks))),
        details={"success_count": success_count, "total": len(tasks), "observed": observed},
        issues=issues,
    )


def _case_channel_provider_config_gate(*, repo_root: Path, scratch_root: Path, ci_mode: bool) -> CaseResult:
    case_id = "channel_provider_config_gate"
    title = "Channel Provider 配置门控（缺 token fail-closed）"
    issues: List[Dict[str, Any]] = []

    from quentin.infra.channels.listener_manager import ChannelListenerManager

    _ = (repo_root, scratch_root, ci_mode)
    mgr = ChannelListenerManager()
    original_build = mgr._build_adapter

    def _fake_build(platform: str, config: Dict[str, Any]) -> Any:
        _ = platform
        token = str((config or {}).get("token") or "").strip()
        if not token:
            raise ValueError("missing_token")
        raise ValueError("unsupported_platform_for_bench")

    mgr._build_adapter = _fake_build  # type: ignore[assignment]
    try:
        out_missing = mgr.start("discord", config={"token": ""}, on_message=None)
        out_bad = mgr.start("discord", config={"token": "x"}, on_message=None)
    finally:
        mgr._build_adapter = original_build  # type: ignore[assignment]

    missing_gate = str(out_missing.get("status") or "") == "error" and "missing_token" in str(out_missing.get("error") or "")
    bad_gate = str(out_bad.get("status") or "") == "error" and "unsupported_platform_for_bench" in str(out_bad.get("error") or "")
    ok = bool(missing_gate and bad_gate)
    if not ok:
        issues.append(
            _issue(
                case_id=case_id,
                key="provider_config_gate_failed",
                severity="fail",
                message="provider 配置门控未 fail-closed（缺 token 或不支持平台）",
                evidence={"out_missing": out_missing, "out_bad": out_bad},
            )
        )
    return CaseResult(
        case_id=case_id,
        title=title,
        passed=ok,
        score=1.0 if ok else 0.0,
        details={"missing_gate": missing_gate, "unsupported_gate": bad_gate},
        issues=issues,
    )


def _case_channel_listener_resilience_policy(*, repo_root: Path, scratch_root: Path, ci_mode: bool) -> CaseResult:
    import asyncio
    import time as _time

    case_id = "channel_listener_resilience_policy"
    title = "Channel Listener 重试/退避/错误分类策略"
    issues: List[Dict[str, Any]] = []

    from quentin.infra.channels.base import ChannelAdapter
    from quentin.infra.channels.listener_manager import (
        ChannelListenerManager,
        _classify_restart_reason,
        _resolve_backoff_policy,
    )

    _ = (repo_root, scratch_root, ci_mode)

    class _FlakyAdapter(ChannelAdapter):
        def __init__(self) -> None:
            super().__init__(name="flaky")
            self.calls = 0
            self._cb = None

        async def start(self) -> None:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("429 too many requests")
            await asyncio.sleep(0.05)

        async def stop(self) -> None:
            return None

        async def send_text(self, target_id: str, text: str, **kwargs):
            _ = (target_id, text, kwargs)
            return None

        def set_on_message(self, callback):
            self._cb = callback

    mgr = ChannelListenerManager()
    original_build = mgr._build_adapter

    def _fake_build(platform: str, config: Dict[str, Any]) -> Any:
        _ = (platform, config)
        return _FlakyAdapter()

    mgr._build_adapter = _fake_build  # type: ignore[assignment]
    try:
        with _temp_environ(
            {
                "QUENTIN_LISTENER_BACKOFF_PROFILE": "linear",
                "QUENTIN_LISTENER_BACKOFF_DISCORD_INIT_SEC": "0.1",
                "QUENTIN_LISTENER_BACKOFF_DISCORD_MAX_SEC": "0.5",
                "QUENTIN_LISTENER_BACKOFF_DISCORD_RATE_LIMIT_FLOOR_SEC": "0.5",
            }
        ):
            start_out = mgr.start("discord", config={"token": "x"}, on_message=lambda _m: None)
            _time.sleep(0.75)
            status = mgr.status("discord")
            stop_out = mgr.stop("discord")
    finally:
        mgr._build_adapter = original_build  # type: ignore[assignment]

    listener = ((status.get("listeners") or [None])[0] if isinstance(status, dict) else None) or {}
    reasons = listener.get("restart_reasons") if isinstance(listener.get("restart_reasons"), dict) else {}
    rate_limit_seen = int(reasons.get("rate_limit") or 0) >= 1
    policy = _resolve_backoff_policy("discord", "linear")
    policy_ok = all(k in policy for k in ("initial_sec", "max_sec", "multiplier", "rate_limit_floor_sec"))
    auth_class_ok = _classify_restart_reason(RuntimeError("unauthorized token")) == "auth_error"
    ok = bool(str(start_out.get("status") or "") == "ok" and rate_limit_seen and policy_ok and auth_class_ok)
    if not ok:
        issues.append(
            _issue(
                case_id=case_id,
                key="listener_resilience_policy_failed",
                severity="fail",
                message="listener 重试/退避/错误分类策略不满足预期",
                evidence={"start": start_out, "status": status, "stop": stop_out, "policy": policy},
            )
        )
    return CaseResult(
        case_id=case_id,
        title=title,
        passed=ok,
        score=1.0 if ok else 0.0,
        details={"rate_limit_seen": rate_limit_seen, "policy_ok": policy_ok, "auth_class_ok": auth_class_ok},
        issues=issues,
    )


def _case_failure_recovery(*, repo_root: Path, scratch_root: Path, ci_mode: bool) -> CaseResult:
    import asyncio

    case_id = "failure_recovery_fallback"
    title = "失败后回退恢复路径"
    issues: List[Dict[str, Any]] = []

    from quentin.bootstrap.container import Container

    env = dict(_scratch_env(repo_root=repo_root, scratch_root=scratch_root, ci_mode=ci_mode))
    env["QUENTIN_PLUGIN_RUNTIME_ISOLATION"] = "1"
    with _temp_environ(env):
        c = Container(repo_root=scratch_root)
        tm = c.tool_manager
        first = asyncio.run(_call_tool(tm, tool_name="test_isolated_tool", payload={"task": "demo"}))
        second = asyncio.run(
            _call_tool(tm, tool_name="bench.screwdriver", payload={"task": "open package tape", "mode": "auto"})
        )

    first_dict = _model_to_dict(first)
    second_dict = _model_to_dict(second)
    first_failed = not bool(first_dict.get("success"))
    second_succeeded = bool(second_dict.get("success"))
    recovered = bool(first_failed and second_succeeded)

    if not recovered:
        issues.append(
            _issue(
                case_id=case_id,
                key="recovery_failed",
                severity="fail",
                message="失败后未能通过回退工具恢复",
                evidence={"first": first_dict, "second": second_dict},
            )
        )

    return CaseResult(
        case_id=case_id,
        title=title,
        passed=recovered,
        score=1.0 if recovered else 0.0,
        details={
            "first_failed": first_failed,
            "second_succeeded": second_succeeded,
            "first_error": str(first_dict.get("error") or ""),
        },
        issues=issues,
    )


def _case_cross_session_persistence(*, repo_root: Path, scratch_root: Path, ci_mode: bool) -> CaseResult:
    import asyncio

    case_id = "cross_session_persistence"
    title = "跨会话工具记忆持久化"
    issues: List[Dict[str, Any]] = []

    from quentin.bootstrap.container import Container
    from quentin.memory.tool_knowledge import stable_tool_knowledge_id

    with _temp_environ(_scratch_env(repo_root=repo_root, scratch_root=scratch_root, ci_mode=ci_mode)):
        c1 = Container(repo_root=scratch_root)
        tm1 = c1.tool_manager
        asyncio.run(_call_tool(tm1, tool_name="bench.screwdriver", payload={"task": "tighten screw", "mode": "auto"}))

        c2 = Container(repo_root=scratch_root)
        rec = c2.memory_fabric.store.get(stable_tool_knowledge_id("bench.screwdriver"))

    ok = rec is not None
    call_count = 0
    if rec is not None:
        md = dict(getattr(rec, "metadata", None) or {})
        stats = md.get("stats") if isinstance(md.get("stats"), dict) else {}
        call_count = _safe_int(stats.get("call_count"), 0)
        if call_count < 1:
            ok = False

    if not ok:
        issues.append(
            _issue(
                case_id=case_id,
                key="persistence_missing",
                severity="fail",
                message="跨会话未读到 tool_knowledge 或计数未持久化",
                evidence={"call_count": call_count},
            )
        )

    return CaseResult(
        case_id=case_id,
        title=title,
        passed=ok,
        score=1.0 if ok else 0.0,
        details={"call_count": call_count},
        issues=issues,
    )


def _case_meta_agent_registry_path(*, repo_root: Path, scratch_root: Path, ci_mode: bool) -> CaseResult:
    case_id = "meta_agent_registry_path"
    title = "meta_agent 工具注册/记忆同步路径"
    issues: List[Dict[str, Any]] = []

    from meta_agent.memory.fabric import MemoryFabric as MetaMemoryFabric
    from meta_agent.memory.store_sqlite import SqliteMemoryStore as MetaSqliteMemoryStore
    from meta_agent.tools.knowledge_sync import record_tool_usage, sync_registry_to_memory
    from meta_agent.tools.registry import RiskLevel, ToolGovernance, ToolLifecycle, ToolRegistration, ToolRegistry

    _ = repo_root
    _ = ci_mode

    db_path = (scratch_root / "meta_agent_memory.db").resolve()
    store = MetaSqliteMemoryStore(db_path=db_path)
    mf = MetaMemoryFabric(store=store)
    reg = ToolRegistry()
    reg.register(
        ToolRegistration(
            tool_id="demo/multiply",
            server="demo_server",
            description="Multiply two numbers",
            signature="multiply(a,b)",
            governance=ToolGovernance(lifecycle=ToolLifecycle.TRUSTED, risk_level=RiskLevel.LOW),
            examples=[{"input": {"a": 2, "b": 3}, "output": 6}],
        )
    )

    written = sync_registry_to_memory(reg, mf)
    reg.record_invocation("demo/multiply", success=True, latency_ms=12)
    record_tool_usage(
        reg,
        mf,
        "demo/multiply",
        arguments={"a": 4, "b": 5},
        output={"result": 20},
        error=None,
        success=True,
    )

    recs = mf.search("", kind="tool_knowledge", limit=10)
    ok = bool(written >= 1 and len(recs) >= 1)
    first = recs[0].to_dict() if recs else {}
    meta = first.get("metadata") if isinstance(first, dict) else {}
    tool_id = str((meta or {}).get("tool_id") or "")

    if not ok or tool_id != "demo/multiply":
        ok = False
        issues.append(
            _issue(
                case_id=case_id,
                key="meta_agent_sync_failed",
                severity="fail",
                message="meta_agent 注册/同步路径异常",
                evidence={"written": written, "records": len(recs), "tool_id": tool_id},
            )
        )

    return CaseResult(
        case_id=case_id,
        title=title,
        passed=ok,
        score=1.0 if ok else 0.0,
        details={"written": written, "records": len(recs), "tool_id": tool_id},
        issues=issues,
    )


def _weights_for_domain(domain_bucket: str) -> Dict[str, float]:
    base = {
        "container_tool_plugins_visible": 0.08,
        "plugin_requires_env_gate": 0.10,
        "tool_usage_writeback_to_memory": 0.14,
        "tool_plugin_cache": 0.07,
        "exec_skill_plugin_discovery": 0.10,
        "decision_memory_reuse_effect": 0.14,
        "memory_conflict_resolution": 0.10,
        "full_loop_adversarial_memory": 0.14,
        "channel_gateway_contract": 0.12,
        "domain_adapter_channel_gateway": 0.12,
        "channel_provider_config_gate": 0.10,
        "channel_listener_resilience_policy": 0.10,
        "nl_generalization_affordance": 0.14,
        "failure_recovery_fallback": 0.11,
        "cross_session_persistence": 0.07,
        "meta_agent_registry_path": 0.05,
    }
    key = str(domain_bucket or "global").strip().lower()
    if key == "maintenance":
        base["failure_recovery_fallback"] += 0.03
        base["plugin_requires_env_gate"] += 0.02
    elif key == "research":
        base["nl_generalization_affordance"] += 0.04
        base["decision_memory_reuse_effect"] += 0.02
        base["memory_conflict_resolution"] += 0.02
    elif key == "ops":
        base["cross_session_persistence"] += 0.03
        base["meta_agent_registry_path"] += 0.03
        base["channel_gateway_contract"] += 0.03
    elif key == "core":
        base["full_loop_adversarial_memory"] += 0.03
    elif key == "communication":
        base["channel_gateway_contract"] += 0.04
        base["domain_adapter_channel_gateway"] += 0.03
        base["channel_provider_config_gate"] += 0.03
        base["channel_listener_resilience_policy"] += 0.03
    total = sum(base.values()) or 1.0
    return {k: float(v / total) for k, v in base.items()}


def _autotune_weights_from_history(
    *,
    base_weights: Dict[str, float],
    history_rows: List[Dict[str, Any]],
    window: int,
) -> Dict[str, Any]:
    w = {str(k): float(v) for k, v in (base_weights or {}).items()}
    rows = history_rows[-max(1, int(window)) :] if history_rows else []
    if not rows:
        total = sum(w.values()) or 1.0
        return {
            "weights": {k: float(v / total) for k, v in w.items()},
            "tuning": {
                "enabled": True,
                "window": int(window),
                "rows_used": 0,
                "mode": "no_history",
                "boosts": {},
            },
        }

    case_pressure: Dict[str, float] = {k: 0.0 for k in w.keys()}
    for row in rows:
        if not isinstance(row, dict):
            continue
        for case in row.get("cases") or []:
            if not isinstance(case, dict):
                continue
            cid = str(case.get("case_id") or "")
            if cid not in case_pressure:
                continue
            passed = bool(case.get("passed"))
            score = _safe_float(case.get("score"), 0.0)
            if not passed:
                case_pressure[cid] += 1.0
            case_pressure[cid] += max(0.0, (1.0 - score)) * 0.3
        for issue in row.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            cid = str(issue.get("case_id") or "")
            severity = str(issue.get("severity") or "").strip().lower()
            if cid not in case_pressure:
                continue
            if severity == "fail":
                case_pressure[cid] += 0.8
            elif severity == "warn":
                case_pressure[cid] += 0.3

    max_pressure = max(case_pressure.values()) if case_pressure else 0.0
    boosts: Dict[str, float] = {}
    if max_pressure > 0:
        for cid, pressure in case_pressure.items():
            if pressure <= 0.0:
                continue
            # capped multiplicative boost (max +35%)
            ratio = float(pressure / max_pressure)
            factor = 1.0 + min(0.35, 0.35 * ratio)
            w[cid] = float(w.get(cid, 0.0) * factor)
            boosts[cid] = float(factor)

    total = sum(w.values()) or 1.0
    tuned = {k: float(v / total) for k, v in w.items()}
    return {
        "weights": tuned,
        "tuning": {
            "enabled": True,
            "window": int(window),
            "rows_used": len(rows),
            "mode": "history_pressure_autotune",
            "boosts": boosts,
        },
    }


def _score(cases: List[CaseResult], case_id: str) -> float:
    for c in cases:
        if c.case_id == case_id:
            return float(c.score)
    return 0.0


def _aggregate_cases(cases: List[CaseResult], *, domain_bucket: str, weights: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    weights = dict(weights or _weights_for_domain(domain_bucket))
    total_w = sum(weights.get(c.case_id, 0.0) for c in cases) or 1.0
    weighted_score = 0.0
    for c in cases:
        weighted_score += float(weights.get(c.case_id, 0.0)) * float(c.score)
    weighted_score = weighted_score / total_w

    dim = {
        "discovery": _score(cases, "container_tool_plugins_visible"),
        "governance": _score(cases, "plugin_requires_env_gate"),
        "memory_reuse": _score(cases, "tool_usage_writeback_to_memory"),
        "efficiency": _score(cases, "tool_plugin_cache"),
        "skills_plugins": _score(cases, "exec_skill_plugin_discovery"),
        "decision_reuse": _score(cases, "decision_memory_reuse_effect"),
        "memory_robustness": _score(cases, "memory_conflict_resolution"),
        "loop_resilience": _score(cases, "full_loop_adversarial_memory"),
        "channel_gateway": _score(cases, "channel_gateway_contract"),
        "domain_gateway_adaptation": _score(cases, "domain_adapter_channel_gateway"),
        "channel_provider_governance": _score(cases, "channel_provider_config_gate"),
        "channel_runtime_resilience": _score(cases, "channel_listener_resilience_policy"),
        "generalization": _score(cases, "nl_generalization_affordance"),
        "recovery": _score(cases, "failure_recovery_fallback"),
        "persistence": _score(cases, "cross_session_persistence"),
        "meta_agent_path": _score(cases, "meta_agent_registry_path"),
    }
    top_weaknesses = [{"name": k, "score": float(v)} for k, v in sorted(dim.items(), key=lambda kv: (kv[1], kv[0]))]
    return {
        "quality_score": _clamp01(weighted_score),
        "capability_radar": dim,
        "top_weaknesses": top_weaknesses,
        "weights": weights,
    }


def _load_history_rows(path: Optional[Path], *, limit: int) -> List[Dict[str, Any]]:
    if path is None or not path.exists():
        return []
    values: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if not isinstance(row, dict):
                    continue
                values.append(row)
    except Exception:
        return []
    if limit > 0:
        return values[-limit:]
    return values


def _load_history_scores(path: Optional[Path], *, limit: int) -> List[float]:
    rows = _load_history_rows(path, limit=limit)
    values: List[float] = []
    for row in rows:
        try:
            values.append(float(row.get("quality_score")))
        except Exception:
            continue
    return values


def _evaluate_trend_guard(
    *,
    current_score: float,
    history_scores: List[float],
    moving_window: int,
    drop_tolerance: float,
) -> Dict[str, Any]:
    window = max(1, int(moving_window))
    prior = history_scores[-window:] if history_scores else []
    moving_avg = (sum(prior) / len(prior)) if prior else None
    if moving_avg is None:
        return {
            "enabled": True,
            "window": window,
            "drop_tolerance": float(drop_tolerance),
            "prior_count": 0,
            "moving_avg": None,
            "pass": True,
            "reason": "no_history",
        }

    threshold = float(moving_avg) - float(drop_tolerance)
    passed = float(current_score) >= threshold
    return {
        "enabled": True,
        "window": window,
        "drop_tolerance": float(drop_tolerance),
        "prior_count": len(prior),
        "moving_avg": float(moving_avg),
        "threshold": float(threshold),
        "pass": bool(passed),
        "reason": "ok" if passed else "score_below_trend_threshold",
    }


def _validate_by_json_schema(*, data: Any, schema: Dict[str, Any], path: str = "$") -> List[str]:
    errors: List[str] = []
    expected = schema.get("type")

    def _check_type(value: Any, kind: str) -> bool:
        if kind == "object":
            return isinstance(value, dict)
        if kind == "array":
            return isinstance(value, list)
        if kind == "string":
            return isinstance(value, str)
        if kind == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if kind == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if kind == "boolean":
            return isinstance(value, bool)
        if kind == "null":
            return value is None
        return True

    if isinstance(expected, str) and not _check_type(data, expected):
        return [f"{path}: expected {expected}"]

    if isinstance(data, dict):
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        for key in required:
            if key not in data:
                errors.append(f"{path}.{key}: missing required key")
        props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        additional = schema.get("additionalProperties", True)
        for key, val in data.items():
            key_path = f"{path}.{key}"
            child_schema = props.get(key)
            if isinstance(child_schema, dict):
                errors.extend(_validate_by_json_schema(data=val, schema=child_schema, path=key_path))
            elif additional is False:
                errors.append(f"{key_path}: additional property not allowed")
    elif isinstance(data, list):
        item_schema = schema.get("items") if isinstance(schema.get("items"), dict) else {}
        for idx, item in enumerate(data):
            errors.extend(_validate_by_json_schema(data=item, schema=item_schema, path=f"{path}[{idx}]"))
    return errors


def _validate_report_schema(report: Dict[str, Any], *, schema_file: Optional[Path]) -> Dict[str, Any]:
    required_top = [
        "schema_version",
        "generated_at",
        "repo_root",
        "quality_score",
        "pass",
        "cases",
        "issues",
        "capability_radar",
        "timeout_summary",
        "trend_export",
        "regression_explain",
        "remediation_queue",
        "replay",
        "weight_tuning",
    ]
    missing = [k for k in required_top if k not in report]
    type_errors: List[str] = []
    schema_file_errors: List[str] = []
    schema_loaded = False

    if not isinstance(report.get("cases"), list):
        type_errors.append("cases must be a list")
    if not isinstance(report.get("issues"), list):
        type_errors.append("issues must be a list")
    if not isinstance(report.get("capability_radar"), dict):
        type_errors.append("capability_radar must be a dict")
    if not isinstance(report.get("quality_score"), (float, int)):
        type_errors.append("quality_score must be numeric")
    if not isinstance(report.get("remediation_queue"), list):
        type_errors.append("remediation_queue must be a list")
    if not isinstance(report.get("replay"), dict):
        type_errors.append("replay must be a dict")
    if not isinstance(report.get("weight_tuning"), dict):
        type_errors.append("weight_tuning must be a dict")

    schema_obj: Dict[str, Any] = {}
    if schema_file is not None:
        try:
            schema_obj = json.loads(Path(schema_file).read_text(encoding="utf-8"))
            schema_loaded = isinstance(schema_obj, dict)
        except Exception as exc:
            schema_file_errors.append(f"schema_load_error:{exc}")
    else:
        schema_file_errors.append("schema_file_missing")

    if schema_loaded and isinstance(schema_obj, dict):
        schema_file_errors.extend(_validate_by_json_schema(data=report, schema=schema_obj, path="$"))
    elif schema_file is not None and not schema_loaded:
        schema_file_errors.append("schema_file_not_dict")

    ok = (not missing) and (not type_errors) and (not schema_file_errors)
    return {
        "ok": bool(ok),
        "missing_keys": missing,
        "type_errors": type_errors,
        "schema_file": str(schema_file) if schema_file is not None else "",
        "schema_loaded": bool(schema_loaded),
        "schema_file_errors": schema_file_errors,
    }


def load_report(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _case_timeout_budgets_ms(ci_mode: bool) -> Dict[str, int]:
    base = 4500 if ci_mode else 6500
    return {
        "container_tool_plugins_visible": base,
        "plugin_requires_env_gate": base,
        "tool_usage_writeback_to_memory": base + 1000,
        "tool_plugin_cache": base + 1500,
        "exec_skill_plugin_discovery": base,
        "decision_memory_reuse_effect": base + 1500,
        "memory_conflict_resolution": base + 1200,
        "full_loop_adversarial_memory": base + 8000,
        "channel_gateway_contract": base + 4500,
        "domain_adapter_channel_gateway": base + 3000,
        "channel_provider_config_gate": base + 2000,
        "channel_listener_resilience_policy": base + 2500,
        "nl_generalization_affordance": base + 1500,
        "failure_recovery_fallback": base,
        "cross_session_persistence": base,
        "meta_agent_registry_path": base + 500,
    }


def _add_timeout_diagnostics(
    *,
    case: CaseResult,
    runtime_ms: int,
    budget_ms: int,
    strict_timeouts: bool,
) -> CaseResult:
    timeout_exceeded = int(runtime_ms) > int(budget_ms)
    details = dict(case.details or {})
    details.update(
        {
            "runtime_ms": int(runtime_ms),
            "timeout_budget_ms": int(budget_ms),
            "timeout_exceeded": bool(timeout_exceeded),
        }
    )
    issues = list(case.issues or [])
    passed = bool(case.passed)
    score = float(case.score)
    if timeout_exceeded:
        issues.append(
            _issue(
                case_id=case.case_id,
                key="case_timeout_exceeded",
                severity="fail" if strict_timeouts else "warn",
                message="case runtime exceeded timeout budget",
                evidence={"runtime_ms": int(runtime_ms), "timeout_budget_ms": int(budget_ms)},
            )
        )
        if strict_timeouts:
            passed = False
            score = 0.0
    return CaseResult(
        case_id=case.case_id,
        title=case.title,
        passed=passed,
        score=score,
        details=_jsonable(details),
        issues=_jsonable(issues),
    )


def _run_case_with_budget(
    *,
    case_id: str,
    title: str,
    budget_ms: int,
    strict_timeouts: bool,
    fn: Callable[[], CaseResult],
) -> CaseResult:
    started = time.perf_counter()
    try:
        raw = fn()
    except Exception as exc:
        raw = CaseResult(
            case_id=case_id,
            title=title,
            passed=False,
            score=0.0,
            details={},
            issues=[
                _issue(
                    case_id=case_id,
                    key="case_runtime_exception",
                    severity="fail",
                    message="benchmark case raised exception",
                    evidence={"error": repr(exc)},
                )
            ],
        )
    runtime_ms = int(max(0.0, (time.perf_counter() - started) * 1000.0))
    return _add_timeout_diagnostics(case=raw, runtime_ms=runtime_ms, budget_ms=int(budget_ms), strict_timeouts=strict_timeouts)


def _build_timeout_summary(cases: List[CaseResult]) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    exceeded = 0
    for c in cases:
        d = dict(c.details or {})
        runtime_ms = _safe_int(d.get("runtime_ms"), 0)
        budget_ms = _safe_int(d.get("timeout_budget_ms"), 0)
        timeout_exceeded = bool(d.get("timeout_exceeded"))
        if timeout_exceeded:
            exceeded += 1
        rows.append(
            {
                "case_id": c.case_id,
                "runtime_ms": runtime_ms,
                "timeout_budget_ms": budget_ms,
                "timeout_exceeded": timeout_exceeded,
            }
        )
    worst = sorted(rows, key=lambda x: int(x.get("runtime_ms") or 0), reverse=True)[:3]
    runtimes = [int(r.get("runtime_ms") or 0) for r in rows]
    tool_runtimes: List[int] = []
    for c in cases:
        d = dict(c.details or {})
        for key in ("latency_first_ms", "latency_cached_ms"):
            if key in d:
                try:
                    tool_runtimes.append(int(float(d.get(key))))
                except Exception:
                    pass

    def _percentile(vals: List[int], q: float) -> float:
        if not vals:
            return 0.0
        data = sorted([int(v) for v in vals])
        if len(data) == 1:
            return float(data[0])
        pos = (len(data) - 1) * float(q)
        lo = int(pos)
        hi = min(len(data) - 1, lo + 1)
        frac = float(pos - lo)
        return float(data[lo] * (1.0 - frac) + data[hi] * frac)

    return {
        "total_cases": len(cases),
        "timeout_exceeded_count": int(exceeded),
        "pass": bool(exceeded == 0),
        "worst_runtime_cases": worst,
        "runtime_percentiles_ms": {"p50": _percentile(runtimes, 0.50), "p90": _percentile(runtimes, 0.90)},
        "tool_runtime_percentiles_ms": {"p50": _percentile(tool_runtimes, 0.50), "p90": _percentile(tool_runtimes, 0.90)},
    }


def _build_regression_explain(*, cases: List[CaseResult], issues: List[Dict[str, Any]], prev_score: Optional[float], quality_score: float) -> Dict[str, Any]:
    failed = [c for c in cases if not bool(c.passed)]
    entries: List[Dict[str, Any]] = []
    for c in failed:
        c_issues = [i for i in issues if str(i.get("case_id") or "") == c.case_id]
        keys = [str(i.get("key") or "") for i in c_issues[:3]]
        entries.append(
            {
                "case_id": c.case_id,
                "title": c.title,
                "score": float(c.score),
                "issue_keys": keys,
                "suggested_actions": [f"investigate:{k}" for k in keys] if keys else ["inspect_case_logs"],
            }
        )
    score_delta = None if prev_score is None else float(quality_score - prev_score)
    return {
        "has_regression": bool(failed) or bool(score_delta is not None and score_delta < 0.0),
        "previous_score": prev_score,
        "current_score": float(quality_score),
        "score_delta": score_delta,
        "failed_cases": entries,
    }


def _build_trend_export(
    *,
    history_rows: List[Dict[str, Any]],
    current_score: float,
    current_dims: Dict[str, Any],
    current_issues: List[Dict[str, Any]],
) -> Dict[str, Any]:
    prior_scores: List[float] = []
    for row in history_rows:
        try:
            prior_scores.append(float(row.get("quality_score")))
        except Exception:
            continue
    avg5 = (sum(prior_scores[-5:]) / len(prior_scores[-5:])) if prior_scores[-5:] else None
    avg10 = (sum(prior_scores[-10:]) / len(prior_scores[-10:])) if prior_scores[-10:] else None

    prior_dims_rows = [r.get("capability_radar") for r in history_rows if isinstance(r.get("capability_radar"), dict)]
    dim_deltas: Dict[str, float] = {}
    for key, val in (current_dims or {}).items():
        cur = _safe_float(val, 0.0)
        hist_vals = [_safe_float(r.get(key), 0.0) for r in prior_dims_rows if isinstance(r, dict) and key in r]
        if hist_vals:
            dim_deltas[key] = float(cur - (sum(hist_vals) / len(hist_vals)))
        else:
            dim_deltas[key] = float(cur)

    issue_counts: Dict[str, int] = {}
    for row in history_rows[-20:]:
        for issue in row.get("issues") or []:
            if isinstance(issue, dict):
                k = str(issue.get("key") or "").strip()
                if k:
                    issue_counts[k] = int(issue_counts.get(k, 0)) + 1
    for issue in current_issues or []:
        if isinstance(issue, dict):
            k = str(issue.get("key") or "").strip()
            if k:
                issue_counts[k] = int(issue_counts.get(k, 0)) + 1
    top_issue_keys = [k for k, _ in sorted(issue_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:8]]

    timeline_tail: List[Dict[str, Any]] = []
    for row in history_rows[-10:]:
        timeline_tail.append(
            {
                "generated_at": str(row.get("generated_at") or ""),
                "quality_score": _safe_float(row.get("quality_score"), 0.0),
                "pass": bool(row.get("pass")),
            }
        )
    timeline_tail.append({"generated_at": _now_utc_iso(), "quality_score": float(current_score), "pass": True})
    return {
        "quality_score_moving_avg_5": avg5,
        "quality_score_moving_avg_10": avg10,
        "quality_score_delta_vs_avg_5": (None if avg5 is None else float(current_score - avg5)),
        "dimension_deltas": dim_deltas,
        "top_issue_keys_rolling": top_issue_keys,
        "timeline_tail": timeline_tail,
    }


def _append_trend_ndjson(*, path: Optional[Path], report: Dict[str, Any]) -> None:
    if path is None:
        return
    try:
        row = {
            "generated_at": str(report.get("generated_at") or ""),
            "quality_score": _safe_float(report.get("quality_score"), 0.0),
            "pass": bool(report.get("pass")),
            "capability_radar": _jsonable(report.get("capability_radar") or {}),
            "top_issue_keys": [str(i.get("key") or "") for i in (report.get("issues") or []) if isinstance(i, dict)][:10],
            "trend_guard": _jsonable(report.get("trend_guard") or {}),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except Exception:
        return


def _build_remediation_queue(regression: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(regression, dict):
        return []
    failed = regression.get("failed_cases") if isinstance(regression.get("failed_cases"), list) else []
    queue: List[Dict[str, Any]] = []
    for item in failed:
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("case_id") or "")
        for idx, action in enumerate(item.get("suggested_actions") or []):
            queue.append(
                {
                    "priority": int(idx + 1),
                    "case_id": case_id,
                    "action": str(action or ""),
                    "issue_keys": [str(k) for k in (item.get("issue_keys") or []) if str(k).strip()],
                }
            )
    queue.sort(key=lambda x: (int(x.get("priority") or 99), str(x.get("case_id") or "")))
    return queue[:30]


def run_benchmark(
    *,
    repo_root: str | Path,
    output: Path,
    previous: Optional[Path] = None,
    history: Optional[Path] = None,
    min_score: float = 0.70,
    domain_bucket: str = "global",
    moving_window: int = 5,
    trend_drop_tolerance: float = 0.05,
    ci_mode: bool = False,
    enforce_schema: bool = True,
    case_timeout_ms: int = 6500,
    strict_timeouts: bool = True,
    schema_file: Optional[Path] = None,
    deterministic_fixtures: bool = True,
    trend_ndjson_output: Optional[Path] = None,
    auto_tune_weights: bool = True,
) -> Dict[str, Any]:
    root = _resolve_repo_root(repo_root)
    prev_report = load_report(previous) if previous is not None else {}
    prev_score = None
    if prev_report:
        try:
            prev_score = float(prev_report.get("quality_score"))
        except Exception:
            prev_score = None

    timeout_budgets = _case_timeout_budgets_ms(ci_mode=ci_mode)
    schema_path = Path(schema_file).resolve() if schema_file is not None else DEFAULT_SCHEMA_FILE
    history_rows = _load_history_rows(history, limit=120)
    base_weights = _weights_for_domain(domain_bucket)
    tuned_weights = dict(base_weights)
    weight_tuning: Dict[str, Any] = {
        "enabled": bool(auto_tune_weights),
        "window": max(1, int(moving_window)),
        "rows_used": 0,
        "mode": "disabled",
        "boosts": {},
    }
    if auto_tune_weights:
        tuned = _autotune_weights_from_history(
            base_weights=base_weights,
            history_rows=history_rows,
            window=max(1, int(moving_window)),
        )
        tuned_weights = dict(tuned.get("weights") or base_weights)
        wt = tuned.get("tuning") if isinstance(tuned.get("tuning"), dict) else {}
        weight_tuning = {
            "enabled": True,
            "window": int(wt.get("window") or max(1, int(moving_window))),
            "rows_used": _safe_int(wt.get("rows_used"), 0),
            "mode": str(wt.get("mode") or "history_pressure_autotune"),
            "boosts": _jsonable(wt.get("boosts") or {}),
        }
    cases: List[CaseResult] = []
    with _benchmark_warning_filters(enabled=bool(deterministic_fixtures)):
        with tempfile.TemporaryDirectory(prefix="tool_adapt_bench_") as td:
            scratch = Path(td).resolve()
            case_specs: List[Dict[str, Any]] = [
                {
                    "case_id": "container_tool_plugins_visible",
                    "title": "Container默认 wiring 能看到 extensions/tools",
                    "fn": lambda: _case_container_sees_tool_plugins(repo_root=root, scratch_root=scratch, ci_mode=ci_mode),
                },
                {
                    "case_id": "plugin_requires_env_gate",
                    "title": "插件 requires_env 在隔离模式下 fail-closed",
                    "fn": lambda: _case_requires_env_gate(repo_root=root, scratch_root=scratch, ci_mode=ci_mode),
                },
                {
                    "case_id": "tool_usage_writeback_to_memory",
                    "title": "工具使用写回到 tool_knowledge 记忆",
                    "fn": lambda: _case_tool_usage_writeback(repo_root=root, scratch_root=scratch, ci_mode=ci_mode),
                },
                {
                    "case_id": "tool_plugin_cache",
                    "title": "插件缓存可复用",
                    "fn": lambda: _case_plugin_cache(repo_root=root, scratch_root=scratch, ci_mode=ci_mode),
                },
                {
                    "case_id": "exec_skill_plugin_discovery",
                    "title": "exec-skill 插件发现与执行",
                    "fn": lambda: _case_exec_skill_plugin(repo_root=root, scratch_root=scratch, ci_mode=ci_mode),
                },
                {
                    "case_id": "decision_memory_reuse_effect",
                    "title": "工具记忆复用 A/B 对决策重试的真实增益",
                    "fn": lambda: _case_decision_memory_reuse_effect(repo_root=root, scratch_root=scratch, ci_mode=ci_mode),
                },
                {
                    "case_id": "memory_conflict_resolution",
                    "title": "冲突记忆过滤（未知工具不污染执行提示）",
                    "fn": lambda: _case_memory_conflict_resolution(repo_root=root, scratch_root=scratch, ci_mode=ci_mode),
                },
                {
                    "case_id": "full_loop_adversarial_memory",
                    "title": "全链路鲁棒性（planner->executor->done，在对抗记忆下注入）",
                    "fn": lambda: _case_full_loop_adversarial_memory(repo_root=root, scratch_root=scratch, ci_mode=ci_mode),
                },
                {
                    "case_id": "channel_gateway_contract",
                    "title": "Channel Gateway 合同与降级行为",
                    "fn": lambda: _case_channel_gateway_contract(repo_root=root, scratch_root=scratch, ci_mode=ci_mode),
                },
                {
                    "case_id": "domain_adapter_channel_gateway",
                    "title": "Domain Adapter 跨渠道复用（统一意图到渠道动作）",
                    "fn": lambda: _case_domain_adapter_channel_gateway(repo_root=root, scratch_root=scratch, ci_mode=ci_mode),
                },
                {
                    "case_id": "channel_provider_config_gate",
                    "title": "Channel Provider 配置门控（缺 token fail-closed）",
                    "fn": lambda: _case_channel_provider_config_gate(repo_root=root, scratch_root=scratch, ci_mode=ci_mode),
                },
                {
                    "case_id": "channel_listener_resilience_policy",
                    "title": "Channel Listener 重试/退避/错误分类策略",
                    "fn": lambda: _case_channel_listener_resilience_policy(repo_root=root, scratch_root=scratch, ci_mode=ci_mode),
                },
                {
                    "case_id": "nl_generalization_affordance",
                    "title": "规划/执行层自然语言选工具与可解释回退",
                    "fn": lambda: _case_nl_generalization(repo_root=root, scratch_root=scratch, ci_mode=ci_mode),
                },
                {
                    "case_id": "failure_recovery_fallback",
                    "title": "失败后回退恢复路径",
                    "fn": lambda: _case_failure_recovery(repo_root=root, scratch_root=scratch, ci_mode=ci_mode),
                },
                {
                    "case_id": "cross_session_persistence",
                    "title": "跨会话工具记忆持久化",
                    "fn": lambda: _case_cross_session_persistence(repo_root=root, scratch_root=scratch, ci_mode=ci_mode),
                },
                {
                    "case_id": "meta_agent_registry_path",
                    "title": "meta_agent 工具注册/记忆同步路径",
                    "fn": lambda: _case_meta_agent_registry_path(repo_root=root, scratch_root=scratch, ci_mode=ci_mode),
                },
            ]
            for spec in case_specs:
                cid = str(spec.get("case_id") or "")
                budget_ms = int(timeout_budgets.get(cid, max(1000, int(case_timeout_ms))))
                budget_ms = int(max(1000, min(int(case_timeout_ms), budget_ms))) if case_timeout_ms > 0 else budget_ms
                cases.append(
                    _run_case_with_budget(
                        case_id=cid,
                        title=str(spec.get("title") or cid),
                        budget_ms=budget_ms,
                        strict_timeouts=bool(strict_timeouts),
                        fn=spec["fn"],
                    )
                )

    agg = _aggregate_cases(cases, domain_bucket=domain_bucket, weights=tuned_weights)
    quality_score = float(agg.get("quality_score") or 0.0)
    improved_vs_previous = True if prev_score is None else (quality_score >= prev_score)
    min_score_pass = quality_score >= float(min_score)

    history_scores = []
    for row in history_rows[-max(1, int(moving_window)):]:
        try:
            history_scores.append(float(row.get("quality_score")))
        except Exception:
            continue
    trend = _evaluate_trend_guard(
        current_score=quality_score,
        history_scores=history_scores,
        moving_window=max(1, int(moving_window)),
        drop_tolerance=float(trend_drop_tolerance),
    )

    issues: List[Dict[str, Any]] = []
    for c in cases:
        issues.extend(list(c.issues or []))

    if not bool(trend.get("pass")):
        issues.append(
            _issue(
                case_id="system",
                key="trend_guard_failed",
                severity="warn",
                message="质量分低于历史移动均值阈值",
                evidence=trend,
            )
        )
    timeout_summary = _build_timeout_summary(cases)
    if not bool(timeout_summary.get("pass")):
        issues.append(
            _issue(
                case_id="system",
                key="timeout_budget_failed",
                severity="fail" if strict_timeouts else "warn",
                message="至少一个 case 超过超时预算",
                evidence=timeout_summary,
            )
        )

    trend_export = _build_trend_export(
        history_rows=history_rows,
        current_score=quality_score,
        current_dims=(agg.get("capability_radar") or {}),
        current_issues=issues,
    )
    regression_explain = _build_regression_explain(
        cases=cases,
        issues=issues,
        prev_score=prev_score,
        quality_score=quality_score,
    )

    report: Dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "repo_root": str(root),
        "calibration_bucket": {"domain": str(domain_bucket or "global").strip().lower() or "global"},
        "quality_score": quality_score,
        "min_score": float(min_score),
        "pass": False,
        "pass_breakdown": {
            "min_score_pass": bool(min_score_pass),
            "trend_pass": bool(trend.get("pass")),
            "schema_pass": True,
            "timeout_pass": bool(timeout_summary.get("pass")),
        },
        "improved_vs_previous": bool(improved_vs_previous),
        "previous_score": prev_score,
        "capability_radar": agg.get("capability_radar", {}),
        "top_weaknesses": agg.get("top_weaknesses", []),
        "weights": agg.get("weights", {}),
        "weights_base": base_weights,
        "weight_tuning": weight_tuning,
        "trend_guard": trend,
        "timeout_summary": timeout_summary,
        "trend_export": trend_export,
        "regression_explain": regression_explain,
        "remediation_queue": [],
        "ci_mode": bool(ci_mode),
        "deterministic_fixtures": bool(deterministic_fixtures),
        "replay": {
            "seed": 0 if ci_mode else _safe_int(os.getenv("PYTHONHASHSEED"), 0),
            "ci_mode": bool(ci_mode),
            "command": (
                "PYTHONPATH=. python scripts/tool_adaptation_benchmark.py "
                "--output generated/benchmarks/tool_adaptation_benchmark_report.json "
                "--previous generated/benchmarks/tool_adaptation_benchmark_prev.json "
                "--history generated/benchmarks/tool_adaptation_benchmark_history.jsonl "
                f"--min-score {float(min_score)} --moving-window {int(moving_window)} "
                f"--trend-drop-tolerance {float(trend_drop_tolerance)} "
                + ("--ci-mode " if ci_mode else "")
                + ("" if strict_timeouts else "--soft-timeouts ")
                + (f"--case-timeout-ms {int(case_timeout_ms)} ")
                + (f"--schema-file {str(schema_path)}")
            ).strip(),
        },
        "environment_snapshot": {
            "pythonhashseed": "0" if ci_mode else os.getenv("PYTHONHASHSEED", ""),
            "plugin_isolation": "1" if ci_mode else os.getenv("QUENTIN_PLUGIN_RUNTIME_ISOLATION", ""),
            "tool_plugins_enabled": "1",
            "memory_store": "sqlite",
            "benchmark_fixture_mode": os.getenv("QUENTIN_BENCHMARK_FIXTURE_MODE", "1"),
        },
        "cases": [
            {
                "case_id": c.case_id,
                "title": c.title,
                "passed": bool(c.passed),
                "score": float(c.score),
                "details": _jsonable(c.details),
            }
            for c in cases
        ],
        "issues": _jsonable(issues),
    }

    schema_check = _validate_report_schema(report, schema_file=schema_path)
    report["schema_validation"] = schema_check
    schema_pass = bool(schema_check.get("ok")) if enforce_schema else True
    report["pass_breakdown"]["schema_pass"] = bool(schema_pass)
    report["pass"] = bool(
        min_score_pass
        and bool(trend.get("pass"))
        and schema_pass
        and (bool(timeout_summary.get("pass")) or (not bool(strict_timeouts)))
    )
    report["remediation_queue"] = _build_remediation_queue(regression_explain)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if history is not None:
        history.parent.mkdir(parents=True, exist_ok=True)
        with history.open("a", encoding="utf-8") as f:
            f.write(json.dumps(report, ensure_ascii=False, default=str) + "\n")
    _append_trend_ndjson(path=trend_ndjson_output, report=report)
    return report
