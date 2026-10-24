import asyncio
import os
import logging
import re
import json
from pathlib import Path
from quentin.bootstrap.container import Container
from quentin.cognitive.loop import CognitiveTask

# Respect caller environment: only set defaults when unset.
if not os.getenv("LLM_BASE_URL"):
    os.environ["LLM_BASE_URL"] = "http://localhost:11434"

# Enable basic logging to stdout
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    xs = sorted([float(v) for v in values])
    qq = min(1.0, max(0.0, float(q)))
    idx = int(round((len(xs) - 1) * qq))
    return float(xs[idx])


def _read_jsonl(path: Path, *, limit: int = 400) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                try:
                    row = json.loads(s)
                except Exception:
                    continue
                if isinstance(row, dict):
                    out.append(row)
    except Exception:
        return []
    if limit > 0 and len(out) > limit:
        return out[-limit:]
    return out


def _load_calibrated_thresholds() -> dict[str, float]:
    enabled = (os.getenv("QUENTIN_VERIFY_AUTOCALIBRATE_FROM_HISTORY", "0") or "").strip().lower() in ("1", "true", "yes", "on")
    if not enabled:
        return {}
    history_path = Path(
        os.getenv(
            "QUENTIN_VERIFY_AUTOCALIBRATE_HISTORY_PATH",
            "generated/benchmarks/planning_process_benchmark_history.jsonl",
        )
    )
    rows = _read_jsonl(history_path, limit=int(os.getenv("QUENTIN_VERIFY_AUTOCALIBRATE_HISTORY_LIMIT", "400") or "400"))
    min_samples = max(5, int(os.getenv("QUENTIN_VERIFY_AUTOCALIBRATE_MIN_SAMPLES", "8") or "8"))
    if len(rows) < min_samples:
        return {}
    target_bucket = str(os.getenv("QUENTIN_VERIFY_AUTOCALIBRATE_DOMAIN_BUCKET", "global") or "global").strip().lower()
    if target_bucket and target_bucket != "global":
        bucket_rows = []
        for r in rows:
            b = r.get("calibration_bucket")
            if isinstance(b, dict):
                val = str(b.get("domain") or "global").strip().lower()
            else:
                val = str(r.get("domain_bucket") or "global").strip().lower()
            if val == target_bucket:
                bucket_rows.append(r)
        if len(bucket_rows) >= min_samples:
            rows = bucket_rows

    q = float(os.getenv("QUENTIN_VERIFY_AUTOCALIBRATE_QUANTILE", "0.30") or "0.30")
    margins = {
        "strategy_switch_effectiveness": float(os.getenv("QUENTIN_VERIFY_AUTOCALIBRATE_MARGIN_STRATEGY", "0.02") or "0.02"),
        "interrupt_effectiveness": float(os.getenv("QUENTIN_VERIFY_AUTOCALIBRATE_MARGIN_INTERRUPT", "0.03") or "0.03"),
        "reset_recovery_rate": float(os.getenv("QUENTIN_VERIFY_AUTOCALIBRATE_MARGIN_RESET", "0.03") or "0.03"),
        "progress_sync_compliance": float(os.getenv("QUENTIN_VERIFY_AUTOCALIBRATE_MARGIN_PROGRESS", "0.03") or "0.03"),
        "attempt_band_coverage": float(os.getenv("QUENTIN_VERIFY_AUTOCALIBRATE_MARGIN_ATTEMPT_BAND", "0.02") or "0.02"),
    }
    clamps = {
        "strategy_switch_effectiveness": (0.40, 0.85),
        "interrupt_effectiveness": (0.35, 0.90),
        "reset_recovery_rate": (0.25, 0.85),
        "progress_sync_compliance": (0.60, 0.95),
        "attempt_band_coverage": (0.60, 0.95),
    }
    buckets: dict[str, list[float]] = {
        "strategy_switch_effectiveness": [],
        "interrupt_effectiveness": [],
        "reset_recovery_rate": [],
        "progress_sync_compliance": [],
        "attempt_band_coverage": [],
    }
    for row in rows:
        comps = row.get("score_components") if isinstance(row.get("score_components"), dict) else {}
        if isinstance(comps, dict):
            for key in (
                "strategy_switch_effectiveness",
                "interrupt_effectiveness",
                "reset_recovery_rate",
                "progress_sync_compliance",
            ):
                try:
                    buckets[key].append(float(comps.get(key)))
                except Exception:
                    pass
        ia = row.get("intelligence_audit") if isinstance(row.get("intelligence_audit"), dict) else {}
        strat = ia.get("strategy_regression") if isinstance(ia.get("strategy_regression"), dict) else {}
        switching = strat.get("strategy_switching") if isinstance(strat.get("strategy_switching"), dict) else {}
        try:
            buckets["attempt_band_coverage"].append(float(switching.get("attempt_band_coverage")))
        except Exception:
            pass

    out: dict[str, float] = {}
    for key, vals in buckets.items():
        if len(vals) < min_samples:
            continue
        base = _quantile(vals, q) - margins[key]
        lo, hi = clamps[key]
        out[key] = max(lo, min(hi, float(base)))
    return out


def _audit_execution_process(result) -> list[str]:  # type: ignore[no-untyped-def]
    issues: list[str] = []
    actions = str(getattr(result, "actions_summary", "") or "").lower()
    final_output = str(getattr(result, "final_output", "") or "")
    awareness = getattr(result, "self_awareness", {}) or {}
    if not isinstance(awareness, dict):
        awareness = {}

    def _has_token(text: str, token: str) -> bool:
        return re.search(rf"(?<![a-z0-9_]){re.escape(token.lower())}(?![a-z0-9_])", text) is not None

    has_discovery = any(_has_token(actions, k) for k in ("ls", "fs.read_file", "discover", "inspect", "probe"))
    has_verification = any(_has_token(actions, k) for k in ("verify", "pytest", "compile", "check", "验证"))
    has_mutation = any(_has_token(actions, k) for k in ("fs.write_file", "fs.search_replace", "mkdir"))

    if has_mutation and not has_discovery:
        issues.append("mutation_without_discovery_evidence")
    if has_mutation and not has_verification:
        issues.append("mutation_without_verification_evidence")

    anti_pattern = str(awareness.get("anti_pattern_reason") or "").strip()
    if anti_pattern:
        issues.append(f"anti_pattern:{anti_pattern}")
    if "repeated_tool_call_loop" in final_output:
        issues.append("repeated_tool_call_loop_detected")
    if int(awareness.get("consecutive_no_progress", 0) or 0) >= 2:
        issues.append("no_progress_streak>=2")
    return issues


def _audit_intelligence_process(*, repo_root: str | Path = ".") -> list[str]:
    issues: list[str] = []
    try:
        from quentin.diagnostics.intelligence_auditor import build_intelligence_audit
    except Exception as e:  # pragma: no cover
        return [f"intelligence_audit_unavailable:{e}"]

    report = build_intelligence_audit(repo_root=repo_root)
    strategy = report.get("strategy_regression") if isinstance(report.get("strategy_regression"), dict) else {}
    switching = strategy.get("strategy_switching") if isinstance(strategy.get("strategy_switching"), dict) else {}
    resilience = strategy.get("execution_resilience") if isinstance(strategy.get("execution_resilience"), dict) else {}

    planning_diag_total = int(switching.get("planning_diag_total") or 0)
    risky_without_diag = int(switching.get("risky_without_diag") or 0)
    strategy_switch_effectiveness = float(switching.get("strategy_switch_effectiveness") or 0.0)
    attempt_band_required = int(switching.get("attempt_band_required") or 0)
    attempt_band_coverage = float(switching.get("attempt_band_coverage") or 0.0)

    calibrated = _load_calibrated_thresholds()
    min_effectiveness = float(calibrated.get("strategy_switch_effectiveness", os.getenv("QUENTIN_VERIFY_STRATEGY_SWITCH_MIN", "0.55")) or "0.55")
    min_attempt_band_coverage = float(calibrated.get("attempt_band_coverage", os.getenv("QUENTIN_VERIFY_ATTEMPT_BAND_COVERAGE_MIN", "0.80")) or "0.80")
    min_interrupt_effectiveness = float(calibrated.get("interrupt_effectiveness", os.getenv("QUENTIN_VERIFY_INTERRUPT_EFFECTIVENESS_MIN", "0.50")) or "0.50")
    min_reset_recovery = float(calibrated.get("reset_recovery_rate", os.getenv("QUENTIN_VERIFY_RESET_RECOVERY_MIN", "0.40")) or "0.40")
    min_progress_sync = float(calibrated.get("progress_sync_compliance", os.getenv("QUENTIN_VERIFY_PROGRESS_SYNC_COMPLIANCE_MIN", "0.80")) or "0.80")
    if planning_diag_total > 0 and strategy_switch_effectiveness < min_effectiveness:
        issues.append(
            "strategy_switch_effectiveness_below_threshold:"
            f"{strategy_switch_effectiveness:.3f}<{min_effectiveness:.3f}"
        )
    if attempt_band_required > 0 and attempt_band_coverage < min_attempt_band_coverage:
        issues.append(
            "attempt_band_coverage_below_threshold:"
            f"{attempt_band_coverage:.3f}<{min_attempt_band_coverage:.3f}"
        )
    interrupt_total = int(resilience.get("interrupt_total") or 0)
    hard_reset_total = int(resilience.get("hard_reset_total") or 0)
    interrupt_effectiveness = float(resilience.get("interrupt_effectiveness") or 0.0)
    reset_recovery_rate = float(resilience.get("reset_recovery_rate") or 0.0)
    progress_sync_required = int(resilience.get("progress_sync_required") or 0)
    progress_sync_compliance = float(resilience.get("progress_sync_compliance") or 0.0)
    if interrupt_total > 0 and interrupt_effectiveness < min_interrupt_effectiveness:
        issues.append(
            "interrupt_effectiveness_below_threshold:"
            f"{interrupt_effectiveness:.3f}<{min_interrupt_effectiveness:.3f}"
        )
    if hard_reset_total > 0 and reset_recovery_rate < min_reset_recovery:
        issues.append(
            "reset_recovery_rate_below_threshold:"
            f"{reset_recovery_rate:.3f}<{min_reset_recovery:.3f}"
        )
    if progress_sync_required > 0 and progress_sync_compliance < min_progress_sync:
        issues.append(
            "progress_sync_compliance_below_threshold:"
            f"{progress_sync_compliance:.3f}<{min_progress_sync:.3f}"
        )
    if risky_without_diag > 0:
        issues.append(f"risky_plans_without_planning_diagnostics:{risky_without_diag}")
    return issues


def _audit_session_model_benchmark(*, repo_root: str | Path = ".") -> list[str]:
    issues: list[str] = []
    enabled = (os.getenv("QUENTIN_VERIFY_SESSION_BENCHMARK", "1") or "").strip().lower() in ("1", "true", "yes", "on")
    if not enabled:
        return issues
    try:
        from quentin.benchmarks.session_model import run_benchmark
    except Exception as e:  # pragma: no cover
        return [f"session_model_benchmark_unavailable:{e}"]

    try:
        report = run_benchmark(repo_root=repo_root)
    except Exception as e:
        return [f"session_model_benchmark_run_failed:{e}"]

    quality_score = float(report.get("quality_score") or 0.0)
    min_score = float(os.getenv("QUENTIN_VERIFY_SESSION_BENCHMARK_MIN_SCORE", "0.95") or "0.95")
    require_pass = (os.getenv("QUENTIN_VERIFY_SESSION_BENCHMARK_REQUIRE_PASS", "1") or "").strip().lower() in ("1", "true", "yes", "on")
    report_pass = bool(report.get("pass"))
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    failed_keys = summary.get("failed_keys") if isinstance(summary.get("failed_keys"), list) else []

    if quality_score < min_score:
        issues.append(f"session_model_benchmark_score_below_threshold:{quality_score:.3f}<{min_score:.3f}")
    if require_pass and not report_pass:
        issues.append(
            "session_model_benchmark_report_failed:"
            + ",".join([str(x) for x in failed_keys[:16]])
        )
    return issues


async def run_test_task():
    print("🚀 Initializing Project Taylor Quentin Brain...")
    
    # ------------------------------------------------------------
    # Verify mode: by default this should behave like a *smoke test*,
    # not a self-modifying stress test.
    #
    # Set `QUENTIN_VERIFY_STRESS=1` if you explicitly want background
    # self-programming / patchflow behaviors enabled during verification.
    # ------------------------------------------------------------
    stress = (os.getenv("QUENTIN_VERIFY_STRESS", "0") or "").strip().lower() in ("1", "true", "yes", "on")

    # Force some environment variables for the test
    os.environ["QUENTIN_TOOL_PACKS_ENABLED"] = "1"
    os.environ["QUENTIN_TOOL_PLUGINS_ENABLED"] = "1"
    os.environ["QUENTIN_EXECUTOR_NATIVE_TOOL_CALLING"] = "1"
    os.environ["QUENTIN_CONTEXT_SNAPSHOT_PROVIDERS"] = "1"
    # Enable protocol registry so the executor can use native tool calling
    # instead of fragile "JSON-in-text" parsing.
    os.environ["QUENTIN_TOOL_CALL_PROTOCOLS"] = "1"

    if not stress:
        # Disable autonomous self-programming / patchflow side effects for smoke runs.
        os.environ["META_AGENT_ENABLE_SELF_PROGRAMMING"] = "0"
        os.environ["META_AGENT_PATCHFLOW_RUN"] = "0"
        os.environ["QUENTIN_BRAIN_RUN_BLUEPRINT_AUTOPATCH"] = "0"
        os.environ["QUENTIN_TASK_SOURCES_ENABLE"] = "0"
        os.environ["QUENTIN_AUTO_FIXER_ENABLED"] = "0"
    
    # Use user provided preferences
    if not os.getenv("LLM_MODEL"):
        raise ValueError("Environment variable LLM_MODEL must be set before running verify_system.py")
    
    # Council Timeouts (Plan: Member >= 420, Arbiter >= 900)
    if not os.getenv("QUENTIN_COUNCIL_LOCAL_MEMBER_TIMEOUT_S"):
        os.environ["QUENTIN_COUNCIL_LOCAL_MEMBER_TIMEOUT_S"] = "420"
    if not os.getenv("QUENTIN_COUNCIL_LOCAL_ARBITER_TIMEOUT_S"):
        os.environ["QUENTIN_COUNCIL_LOCAL_ARBITER_TIMEOUT_S"] = "900"

    # Initialize BalanceManager with "infinite" balance for local testing (P5: Surgery Sixty-eight)
    try:
        from quentin.infra.billing.balance_manager import balance_manager
        user_id = os.getenv("QUENTIN_USER_ID", "default_user")
        balance_manager.set_balance(user_id, 9000000.0)
        print(f"💰 Billing initialized: {user_id} balance set to 9,000,000.0 (Infinite mode)")
    except Exception as e:
        print(f"⚠️ Warning: Failed to initialize balance manager: {e}")

    container = Container()
    brain = container.cognitive_loop

    # Strong guarantee: don't let this verification run mutate the codebase via self-programming.
    # (Use QUENTIN_VERIFY_STRESS=1 to override.)
    if not stress:
        try:
            brain.self_programming_enabled = False
        except Exception:
            pass
    
    # Verify Memory Store Type
    store_type = type(brain.memory_fabric.store).__name__
    print(f"\n🔍 Memory Store Active: {store_type}")
    if store_type == "SqliteVecMemoryStore":
        print("✅ Hybrid Search Upgrade Active (sqlite-vec)")
    else:
        print("⚠️ Standard Search Active (sqlite-vec not found/loaded)")

    # NEW TASK: Xiaohongshu Leads Generation
    task_text = (
        "TASK: 实现一个自动化小红书（Xiaohongshu）销售线索获取工具，存放在 'extensions/tools/xh_leads/'。\n"
        "目标需求：\n"
        "1. 寻找对 '微信AI自动聊天'、'AI营销工具'、'自动成单' 有需求的用户。\n"
        "2. 提取关键信息：需求帖子链接、用户 ID、用户昵称。\n"
        "3. 将结果持久化保存到 'mutable/xh_leads.csv' 文件中。\n"
        "工程要求：\n"
        "- 使用 'gemini.code' 工具来生成核心的网页爬取或搜索解析逻辑。\n"
        "- manifest.yaml 必须包含 9 个必需字段。\n"
        "- 逻辑代码 logic.py 必须处理空结果和异常情况。\n"
        "验证：\n"
        "- 成功运行该工具，并在 'mutable/xh_leads.csv' 中生成至少包含一条数据的记录。"
    )
    
    task = CognitiveTask(
        input_text=task_text,
        domain="maintenance",
        environment="sandbox",
        metadata={"session_id": "system_bootstrap_test"}
    )
    
    print("🧠 Brain is thinking...")
    result = await brain.run_task_async(task)
    
    print("\n--- TEST RESULT ---")
    print(f"Goal ID: {result.goal_id}")
    print(f"Success: {result.done}")
    print(f"Confidence: {result.done_confidence}")
    print(f"Final Output: {result.final_output}")
    
    print("\n--- [COGNITIVE AUDIT] ---")
    print(f"Plan Summary: {result.plan_summary}")
    print(f"Actions Taken: {result.actions_summary}")
    print("\nSelf-Awareness Snapshot:")
    import json
    print(json.dumps(result.self_awareness, indent=2, ensure_ascii=False))

    process_issues = _audit_execution_process(result)
    intelligence_audit_enabled = (os.getenv("QUENTIN_VERIFY_INTELLIGENCE_AUDIT", "1") or "").strip().lower() in ("1", "true", "yes", "on")
    if intelligence_audit_enabled:
        process_issues.extend(_audit_intelligence_process(repo_root=Path(".")))
    process_issues.extend(_audit_session_model_benchmark(repo_root=Path(".")))
    process_audit_enabled = (os.getenv("QUENTIN_VERIFY_PROCESS_AUDIT", "1") or "").strip().lower() in ("1", "true", "yes", "on")
    if process_audit_enabled and process_issues:
        print("\n❌ PROCESS EVIDENCE FAILURE:")
        for issue in process_issues:
            print(f" - {issue}")
        import sys
        sys.exit(1)
    if process_audit_enabled:
        print("\n✅ PROCESS EVIDENCE VERIFIED: execution trace looks consistent.")

    # P5: Evolution - Physical Evidence Check (Anti-Hallucination)
    if result.done:
        csv_path = Path("mutable/xh_leads.csv")
        if not csv_path.exists():
            print(f"\n❌ PHYSICAL EVIDENCE FAILURE: Brain claimed success but {csv_path} is missing!")
            import sys
            sys.exit(1)
        else:
            print(f"\n✅ PHYSICAL EVIDENCE VERIFIED: {csv_path} exists.")

    import sys
    if not result.done:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_test_task())
