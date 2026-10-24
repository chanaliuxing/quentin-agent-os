from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any


TOKEN_EXHAUST_PATTERNS = (
    "rate limit",
    "quota",
    "exceeded",
    "resource exhausted",
    "insufficient_quota",
    "billing",
    "429",
    "credit",
    "token limit",
)

STRATEGY_SWITCH_ISSUE_KEYS = (
    "strategy_switch_effectiveness_below_threshold",
    "risky_plans_without_planning_diagnostics",
    "interrupt_effectiveness_below_threshold",
    "reset_recovery_rate_below_threshold",
    "progress_sync_compliance_below_threshold",
)


def _is_enabled(name: str, default: str = "1") -> bool:
    raw = (os.getenv(name, default) or default).strip().lower()
    return raw in ("1", "true", "yes", "on")


@dataclass
class LoopConfig:
    max_iterations: int = 20
    sleep_seconds: float = 0.0
    session_id: str = "latest"
    verify_command: str = "python3 verify_system.py"
    test_command: str = "pytest -q tests/unit/test_verify_system_env_contract.py"
    analyzer_command: str = "gemini -p {prompt}"
    fixer_command: str = "gemini -p {prompt}"
    analyzer_timeout_s: int = 420
    fixer_timeout_s: int = 900
    verify_timeout_s: int = 1800
    test_timeout_s: int = 1200
    stop_on_token_exhausted: bool = True
    max_log_lines_per_file: int = 400
    log_files: list[str] = field(
        default_factory=lambda: [
            "data/traces/events.jsonl",
            "data/audit_events.jsonl",
            "data/llm_raw_history.jsonl",
        ]
    )
    run_root: str = "generated/brain_autoloop"
    analyzer_prompt_template: str = "prompts/autoloop/analyzer.md"
    fixer_prompt_template: str = "prompts/autoloop/fixer.md"
    env_overrides: dict[str, str] = field(default_factory=dict)
    fixer_expect_json: bool = True
    require_file_changes: bool = True
    stop_on_no_file_change: bool = True
    allowed_write_roots: list[str] = field(
        default_factory=lambda: [
            "extensions/tools",
            "mutable",
            "generated",
            "tests",
            "scripts",
            "meta_agent",
            "quentin",
            "docs",
            "config",
            "verify_system.py",
        ]
    )
    max_changes_per_iteration: int = 20
    benchmark_command: str = field(
        default_factory=lambda: os.getenv(
            "QUENTIN_BENCHMARK_COMMAND",
            (
                "python3 scripts/planning_process_benchmark.py "
                "--repo-root . "
                "--output generated/benchmarks/planning_process_benchmark_report.json "
                "--previous generated/benchmarks/planning_process_benchmark_prev.json "
                "--history generated/benchmarks/planning_process_benchmark_history.jsonl "
                "--domain-bucket ${QUENTIN_BENCHMARK_DOMAIN_BUCKET:-global}"
            ),
        )
    )
    benchmark_timeout_s: int = 600
    benchmark_report_path: str = "generated/benchmarks/planning_process_benchmark_report.json"
    benchmark_previous_report_path: str = "generated/benchmarks/planning_process_benchmark_prev.json"
    require_benchmark_improve: bool = False
    session_benchmark_command: str = field(
        default_factory=lambda: os.getenv(
            "QUENTIN_SESSION_BENCHMARK_COMMAND",
            "python3 scripts/session_model_benchmark.py --output generated/benchmarks/session_model_benchmark_report.json",
        )
    )
    session_benchmark_timeout_s: int = 300
    session_benchmark_report_path: str = "generated/benchmarks/session_model_benchmark_report.json"
    session_benchmark_min_score: float = 0.95
    session_benchmark_require_pass: bool = True
    threshold_recommendation_command: str = field(
        default_factory=lambda: os.getenv(
            "QUENTIN_THRESHOLD_RECOMMENDATION_COMMAND",
            (
                "python3 scripts/planning_threshold_recommendation.py "
                "--history generated/benchmarks/planning_process_benchmark_history.jsonl "
                "--output generated/benchmarks/planning_threshold_recommendation.json "
                "--min-samples ${QUENTIN_VERIFY_AUTOCALIBRATE_MIN_SAMPLES:-8} "
                "--quantile ${QUENTIN_VERIFY_AUTOCALIBRATE_QUANTILE:-0.30}"
            ),
        )
    )
    threshold_recommendation_timeout_s: int = 300
    threshold_recommendation_report_path: str = "generated/benchmarks/planning_threshold_recommendation.json"
    threshold_env_patch_command: str = field(
        default_factory=lambda: os.getenv(
            "QUENTIN_THRESHOLD_ENV_PATCH_COMMAND",
            (
                "python3 scripts/planning_threshold_env_patch.py "
                "--recommendation generated/benchmarks/planning_threshold_recommendation.json "
                "--output generated/benchmarks/planning_threshold_env_patch.env "
                "--bucket ${QUENTIN_BENCHMARK_DOMAIN_BUCKET:-global}"
            ),
        )
    )
    threshold_env_patch_timeout_s: int = 300
    threshold_env_patch_path: str = "generated/benchmarks/planning_threshold_env_patch.env"
    iteration_cleanup_paths: list[str] = field(default_factory=list)


def _now_utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def _extract_first_json_obj(text: str) -> dict[str, Any] | None:
    if not text.strip():
        return None
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _looks_like_token_exhausted(text: str) -> bool:
    lower = (text or "").lower()
    return any(p in lower for p in TOKEN_EXHAUST_PATTERNS)


def _run_command(
    command: str,
    *,
    timeout_s: int,
    env_overrides: dict[str, str] | None = None,
    cwd: str | None = None,
) -> dict[str, Any]:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    
    started = time.time()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
            cwd=cwd,
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration_s": round(time.time() - started, 3),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout.decode("utf-8", "ignore") if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = e.stderr.decode("utf-8", "ignore") if isinstance(e.stderr, bytes) else (e.stderr or "")
        return {
            "ok": False,
            "returncode": None,
            "stdout": stdout,
            "stderr": stderr,
            "duration_s": round(time.time() - started, 3),
            "timed_out": True,
        }


def _is_valid_gemini_session(sid: str) -> bool:
    if not sid:
        return False
    if sid == "latest" or sid.isdigit():
        return True
    # UUID check (8-4-4-4-12 hex)
    uuid_pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
    return bool(uuid_pattern.match(sid))


def _run_prompt_command(
    command_template: str,
    prompt: str,
    *,
    timeout_s: int,
    session_id: str | None = None,
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    # Reconstruction for shell execution
    cmd_str = command_template
    input_data = prompt # Default to sending prompt via stdin
    if "{prompt}" in cmd_str:
        if cmd_str.startswith("gemini"):
            cmd_str = cmd_str.replace("{prompt}", "").replace("-p", "").replace("--prompt", "").strip()
            if session_id and _is_valid_gemini_session(session_id):
                cmd_str += f" --resume {session_id}"
            if "--no-sandbox" not in cmd_str:
                cmd_str += " --no-sandbox"
            if "--approval-mode" not in cmd_str:
                cmd_str += " --approval-mode yolo"
            
            # PIN MODEL
            if "-m" not in cmd_str and "--model" not in cmd_str:
                cmd_str += " -m gemini-3-pro-preview"
        else:
            cmd_str = cmd_str.replace("{prompt}", prompt)
            input_data = None
    else:
        if cmd_str.startswith("gemini"):
            if session_id and _is_valid_gemini_session(session_id):
                cmd_str += f" --resume {session_id}"
            if "--no-sandbox" not in cmd_str:
                cmd_str += " --no-sandbox"
            if "--approval-mode" not in cmd_str:
                cmd_str += " --approval-mode yolo"
            if "-m" not in cmd_str and "--model" not in cmd_str:
                cmd_str += " -m gemini-3-pro-preview"
        input_data = prompt

    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    
    max_retries = 5
    for attempt in range(max_retries):
        started = time.time()
        proc = None
        try:
            # Revert to shell=True to handle complex prompts/pipes reliably
            # start_new_session=True ensures we can still kill the whole group
            proc = subprocess.Popen(
                cmd_str,
                shell=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                start_new_session=True 
            )
            
            try:
                stdout, stderr = proc.communicate(input=input_data, timeout=timeout_s)
            except subprocess.TimeoutExpired:
                # ONLY kill the process group we just created
                import signal
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except:
                    pass
                stdout, stderr = proc.communicate()
                return {
                    "ok": False,
                    "returncode": None,
                    "stdout": stdout,
                    "stderr": stderr,
                    "duration_s": round(time.time() - started, 3),
                    "timed_out": True,
                    "argv": cmd_str,
                }
            
            full_out = (stdout or "") + "\n" + (stderr or "")
            if proc.returncode != 0 and _looks_like_token_exhausted(full_out):
                # Exponential backoff: 60s, 120s, 240s...
                wait_time = 60 * (2 ** attempt)
                print(f"             Quota hit (Attempt {attempt+1}/{max_retries}). Waiting {wait_time}s...", flush=True)
                time.sleep(wait_time)
                
                # If we've failed 3 times, try a "Recovery Prompt" if session is valid
                if attempt >= 2 and session_id and _is_valid_gemini_session(session_id):
                    print("             Attempting recovery turn with 'continue' prompt...", flush=True)
                    input_data = "The connection was interrupted. Please CONTINUE your previous task exactly where you left off."
                
                continue

            return {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "duration_s": round(time.time() - started, 3),
                "timed_out": False,
                "argv": cmd_str,
            }
        except Exception as e:
            if proc and proc.poll() is None:
                try:
                    import signal
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except:
                    pass
            return {
                "ok": False,
                "returncode": None,
                "stdout": "",
                "stderr": str(e),
                "duration_s": round(time.time() - started, 3),
                "timed_out": False,
                "argv": cmd_str,
            }
    
    return {
        "ok": False,
        "returncode": 429,
        "stdout": "",
        "stderr": "Exhausted all retries for 429/quota errors.",
        "error": "Exhausted all retries for 429/quota errors.",
        "duration_s": 0,
        "timed_out": False,
        "argv": cmd_str,
    }


def _read_tail(path: Path, max_lines: int) -> str:
    if not path.exists():
        return f"[missing] {path}"
    try:
        if path.suffix == ".gz":
            import gzip
            with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            return "\n".join([l.strip() for l in lines[-max_lines:]])
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception as e:
        return f"[read_error] {path}: {e}"


def _normalize_relative_path(path_text: str) -> str:
    path_text = (path_text or "").strip()
    if not path_text:
        raise ValueError("empty path")
    p = Path(path_text)
    if p.is_absolute():
        raise ValueError(f"absolute path not allowed: {path_text}")
    norm = p.as_posix()
    parts = [x for x in norm.split("/") if x]
    if any(part == ".." for part in parts):
        raise ValueError(f"parent traversal not allowed: {path_text}")
    return "/".join(parts)


def _path_allowed(path_text: str, allowed_roots: list[str]) -> bool:
    norm = _normalize_relative_path(path_text)
    if not allowed_roots:
        return True
    for root in allowed_roots:
        root_norm = _normalize_relative_path(root)
        if norm == root_norm or norm.startswith(root_norm + "/"):
            return True
    return False


def _apply_changes(
    *,
    repo_root: Path,
    changes: list[dict[str, Any]],
    allowed_write_roots: list[str],
    max_changes_per_iteration: int,
) -> dict[str, Any]:
    if len(changes) > max_changes_per_iteration:
        return {
            "ok": False,
            "error": f"too_many_changes: {len(changes)} > {max_changes_per_iteration}",
            "applied_count": 0,
            "changed_files": [],
            "errors": [],
        }
    changed_files: list[str] = []
    errors: list[str] = []
    applied = 0
    for idx, change in enumerate(changes):
        try:
            action = str(change.get("action") or "write").strip().lower()
            rel = _normalize_relative_path(str(change.get("path") or ""))
            if not _path_allowed(rel, allowed_write_roots):
                raise ValueError(f"path blocked by allowlist: {rel}")
            target = (repo_root / rel).resolve()
            if not str(target).startswith(str(repo_root)):
                raise ValueError(f"path escapes repo root: {rel}")
            
            before_content = target.read_text(encoding="utf-8", errors="ignore") if target.exists() else None
            before_lines = len(before_content.splitlines()) if before_content else 0
            
            if action in {"write", "replace", "create"}:
                content = str(change.get("content") or "")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            elif action == "append":
                content = str(change.get("content") or "")
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("a", encoding="utf-8") as f:
                    f.write(content)
            elif action == "delete":
                if target.exists():
                    target.unlink()
            else:
                raise ValueError(f"unsupported action: {action}")
            
            after_content = target.read_text(encoding="utf-8", errors="ignore") if target.exists() else None
            after_lines = len(after_content.splitlines()) if after_content else 0
            
            if before_content != after_content:
                diff = after_lines - before_lines
                changed_files.append(f"{rel} ({'++' if diff >= 0 else '--'}{abs(diff)} lines)")
            applied += 1
        except Exception as e:
            errors.append(f"change[{idx}] failed: {e}")
    return {
        "ok": len(errors) == 0,
        "applied_count": applied,
        "changed_files": sorted(set(changed_files)),
        "errors": errors,
    }


def _parse_verify_result(stdout: str) -> dict[str, Any]:
    goal = None
    success = None
    goal_m = re.search(r"Goal ID:\s*([^\s]+)", stdout or "")
    if goal_m:
        goal = goal_m.group(1).strip()
    
    # P5: Strict Success Check (Avoid false positives from intermediate tool call logs)
    # We look for the final "--- TEST RESULT ---" block
    if "--- TEST RESULT ---" in (stdout or ""):
        result_block = stdout.split("--- TEST RESULT ---")[-1]
        success_m = re.search(r"Success:\s*(True|False)", result_block, re.IGNORECASE)
        if success_m:
            success = success_m.group(1).lower() == "true"
    
    return {"goal_id": goal, "success": success}


def _extract_process_issues_from_verify_output(stdout: str) -> list[str]:
    out: list[str] = []
    for line in (stdout or "").splitlines():
        s = line.strip()
        if s.startswith("- "):
            out.append(s[2:].strip())
    return out


def _extract_strategy_switch_issues(issues: list[str]) -> list[str]:
    out: list[str] = []
    for it in issues or []:
        txt = str(it or "").strip()
        if not txt:
            continue
        if any(k in txt for k in STRATEGY_SWITCH_ISSUE_KEYS):
            out.append(txt)
    return out


def _extract_strategy_focus_from_audit(audit_report: dict[str, Any] | None) -> dict[str, str]:
    report = audit_report if isinstance(audit_report, dict) else {}
    strat = report.get("strategy_regression") if isinstance(report.get("strategy_regression"), dict) else {}
    switching = strat.get("strategy_switching") if isinstance(strat.get("strategy_switching"), dict) else {}
    resilience = strat.get("execution_resilience") if isinstance(strat.get("execution_resilience"), dict) else {}
    examples = switching.get("examples") if isinstance(switching.get("examples"), list) else []
    if not examples:
        return {
            "error_subcategory": "",
            "payload_variant_id": "",
            "tool_family": "",
            "interrupt_effectiveness": str(resilience.get("interrupt_effectiveness") or ""),
            "reset_recovery_rate": str(resilience.get("reset_recovery_rate") or ""),
            "progress_sync_compliance": str(resilience.get("progress_sync_compliance") or ""),
        }
    first = examples[0] if isinstance(examples[0], dict) else {}
    sub = str(first.get("error_subcategory") or "").strip().lower()
    variant = str(first.get("payload_variant_id") or "").strip().lower()
    fam = ""
    if "_shell_" in variant:
        fam = "shell"
    elif "_browser_" in variant:
        fam = "browser"
    elif "_filesystem_" in variant:
        fam = "filesystem"
    return {
        "error_subcategory": sub,
        "payload_variant_id": variant,
        "tool_family": fam,
        "interrupt_effectiveness": str(resilience.get("interrupt_effectiveness") or ""),
        "reset_recovery_rate": str(resilience.get("reset_recovery_rate") or ""),
        "progress_sync_compliance": str(resilience.get("progress_sync_compliance") or ""),
    }


def _load_intelligence_audit(repo_root: Path) -> dict[str, Any]:
    try:
        from quentin.diagnostics.intelligence_auditor import build_intelligence_audit

        out = build_intelligence_audit(repo_root=repo_root)
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


def _build_strategy_recovery_prompt(issues: list[str], focus: dict[str, str] | None = None) -> str:
    issue_lines = "\n".join([f"- {x}" for x in (issues or [])[:6]])
    fx = focus if isinstance(focus, dict) else {}
    sub = str(fx.get("error_subcategory") or "").strip().lower()
    fam = str(fx.get("tool_family") or "").strip().lower()
    interrupt_eff = str(fx.get("interrupt_effectiveness") or "").strip()
    reset_rate = str(fx.get("reset_recovery_rate") or "").strip()
    sync_rate = str(fx.get("progress_sync_compliance") or "").strip()
    subtype_action = (
        "- Subtype focus: shell_permission_denied -> verify write policy and permissions before rerunning shell mutations.\n"
        if sub == "shell_permission_denied"
        else "- Subtype focus: shell_command_not_found -> run which/type/command -v before retrying command.\n"
        if sub == "shell_command_not_found"
        else "- Subtype focus: browser_selector_not_found -> refresh DOM/UI-tree and re-resolve selector before click/type.\n"
        if sub == "browser_selector_not_found"
        else "- Subtype focus: browser_navigation_timeout -> split navigation chain and gate each step with readiness probe.\n"
        if sub == "browser_navigation_timeout"
        else "- Subtype focus: filesystem_path_not_found -> verify exact path/parent existence before write/search_replace.\n"
        if sub == "filesystem_path_not_found"
        else "- Subtype focus: prioritize subtype-specific prechecks tied to current failure evidence.\n"
    )
    return (
        "PLANNING STRATEGY RECOVERY MODE:\n"
        "Recent verify gate detected weak planning-strategy switching.\n"
        "You must prioritize planning-layer fixes (payload variants / strategy patches / retry delta / diagnostics), "
        "not surface-only edits.\n"
        f"Recovery focus:\n- tool_family: {fam or '(unknown)'}\n- error_subcategory: {sub or '(unknown)'}\n"
        f"- interrupt_effectiveness: {interrupt_eff or '(n/a)'}\n"
        f"- reset_recovery_rate: {reset_rate or '(n/a)'}\n"
        f"- progress_sync_compliance: {sync_rate or '(n/a)'}\n"
        "Detected issues:\n"
        f"{issue_lines}\n"
        "Required actions:\n"
        "- Ensure planning trace includes context_injected.planning_diagnostics.\n"
        "- Ensure strategy_switch_effectiveness reaches threshold by improving variant/patch/retry-delta coverage.\n"
        "- Improve interrupt/reset/progress-sync resilience metrics when those gates fail.\n"
        + subtype_action +
        "- Add or update tests proving process-based gate behavior.\n"
    )


def _load_template(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_benchmark_score(path: Path) -> float | None:
    if not path.exists():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            return None
        for key in ("quality_score", "overall_score", "score", "pass_rate"):
            if key in obj:
                return float(obj.get(key) or 0.0)
    except Exception:
        return None
    return None


def _read_benchmark_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _render(template: str, values: dict[str, Any]) -> str:
    out = template
    for k, v in values.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _build_run_dir(root: Path) -> Path:
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    run_dir = root / ts
    _ensure_dir(run_dir)
    return run_dir


def _default_issues_from_text(text: str) -> dict[str, Any]:
    return {
        "summary": "Analyzer did not return valid JSON; using raw output.",
        "issues": [{"id": "raw_output_only", "severity": "medium", "description": text[:2000]}],
    }


def _default_fixer_plan(raw_text: str) -> dict[str, Any]:
    return {
        "summary": "Fixer did not return valid JSON plan.",
        "changes": [],
        "tests": [],
        "notes": (raw_text or "")[:2000],
    }


def run_loop(config: LoopConfig) -> dict[str, Any]:
    root = Path(config.run_root)
    _ensure_dir(root)
    run_dir = _build_run_dir(root)
    analyzer_tpl = _load_template(Path(config.analyzer_prompt_template))
    fixer_tpl = _load_template(Path(config.fixer_prompt_template))

    # Phase 0: Warm-up (SKIPPED)
    persistent_session_uuid = config.session_id
    print(f"🔥 [Init] Using persistent session: {persistent_session_uuid} (Warm-up skipped)", flush=True)

    report: dict[str, Any] = {
        "started_at": _now_utc_iso(),
        "run_dir": str(run_dir),
        "config": asdict(config),
        "iterations": [],
        "stop_reason": "",
    }

    for idx in range(1, config.max_iterations + 1):
        print(f"\n[Iteration {idx:03d}/{config.max_iterations}] Starting...", flush=True)
        
        current_session_id = persistent_session_uuid
        
        # New Cleanup Phase
        if config.iteration_cleanup_paths:
            print(f"  [Step 0/6] Cleaning up test environment...", flush=True)
            for cp in config.iteration_cleanup_paths:
                p = Path(cp)
                if p.exists():
                    import shutil
                    if p.is_dir():
                        shutil.rmtree(p)
                        print(f"             Deleted directory: {cp}", flush=True)
                    else:
                        p.unlink()
                        print(f"             Deleted file: {cp}", flush=True)

        iter_dir = run_dir / f"iter_{idx:03d}"
        _ensure_dir(iter_dir)
        iter_rec: dict[str, Any] = {"iteration": idx, "started_at": _now_utc_iso()}

        print(f"  [Step 1/6] Verifying system status (command: {config.verify_command})...", flush=True)
        verify = _run_command(
            config.verify_command,
            timeout_s=config.verify_timeout_s,
            env_overrides=config.env_overrides,
        )
        (iter_dir / "verify_stdout.log").write_text(verify["stdout"] or "", encoding="utf-8")
        (iter_dir / "verify_stderr.log").write_text(verify["stderr"] or "", encoding="utf-8")
        iter_rec["verify"] = {k: v for k, v in verify.items() if k not in {"stdout", "stderr"}}
        iter_rec["verify_parsed"] = _parse_verify_result(verify["stdout"] or "")
        verify_issues = _extract_process_issues_from_verify_output(verify["stdout"] or "")
        strategy_switch_issues = _extract_strategy_switch_issues(verify_issues)
        iter_rec["verify_process_issues"] = verify_issues
        iter_rec["strategy_switch_issues"] = strategy_switch_issues
        strategy_focus = {"error_subcategory": "", "payload_variant_id": "", "tool_family": ""}
        if strategy_switch_issues:
            audit_report = _load_intelligence_audit(Path("."))
            strategy_focus = _extract_strategy_focus_from_audit(audit_report)
        iter_rec["strategy_switch_focus"] = strategy_focus
        print(f"             Success: {iter_rec['verify_parsed'].get('success')} (ReturnCode: {verify['returncode']})", flush=True)

        log_bundle_parts: list[str] = []
        for rel in config.log_files:
            p = Path(rel)
            log_text = _read_tail(p, config.max_log_lines_per_file)
            (iter_dir / f"log_{p.name}.txt").write_text(log_text, encoding="utf-8")
            log_bundle_parts.append(f"### {rel}\n{log_text}")
        logs_bundle = "\n\n".join(log_bundle_parts)
        
        if len(logs_bundle) > 20000:
            print(f"             Truncating logs_bundle from {len(logs_bundle)} to 20000 chars.", flush=True)
            logs_bundle = logs_bundle[:10000] + "\n... [TRUNCATED] ...\n" + logs_bundle[-10000:]

        # Step 2: Analyze (Writes report to mutable/last_brain_diagnosis.md)
        print(f"  [Step 2/6] Analyzing issues (Gemini will write to mutable/last_brain_diagnosis.md)...", flush=True)
        
        # Inject current context into the analyzer prompt
        context_payload = {
            "verify_command": config.verify_command,
            "verify_stdout": verify["stdout"][-5000:] if verify["stdout"] else "",
            "verify_stderr": verify["stderr"][-5000:] if verify["stderr"] else "",
            "logs_bundle": logs_bundle,
        }
        strategy_recovery_block = (
            _build_strategy_recovery_prompt(strategy_switch_issues, strategy_focus)
            if strategy_switch_issues
            else ""
        )
        analyzer_prompt = f"""
ERROR CONTEXT:
Verification Command: {context_payload['verify_command']}
Return Code: {verify['returncode']}

VERIFY STDERR:
{context_payload['verify_stderr']}

LOG TAIL:
{context_payload['logs_bundle']}

---
{strategy_recovery_block}
---
{analyzer_tpl}
"""
        
        analyzer = _run_prompt_command(
            config.analyzer_command,
            analyzer_prompt,
            timeout_s=600, 
            session_id=current_session_id, 
            env_overrides=config.env_overrides,
        )
        (iter_dir / "analyzer_raw.txt").write_text(
            (analyzer.get("stdout") or "") + "\n\n--- STDERR ---\n" + (analyzer.get("stderr") or ""),
            encoding="utf-8",
        )
        
        # Step 3: Fix (Reads report from file and uses tools)
        print(f"  [Step 3/6] Executing autonomous fix (Gemini will read report and apply fixes)...", flush=True)
        
        fixer_prompt = f"""
The diagnosis report has been written to 'mutable/last_brain_diagnosis.md'.
Please read it and perform the required surgical fixes in the 'quentin/' directory.

---
{strategy_recovery_block}
---
{fixer_tpl}
"""
        
        fixer = _run_prompt_command(
            config.fixer_command,
            fixer_prompt,
            timeout_s=1200, 
            session_id=current_session_id, 
            env_overrides=config.env_overrides,
        )
        (iter_dir / "fixer_raw.txt").write_text(
            (fixer.get("stdout") or "") + "\n\n--- STDERR ---\n" + (fixer.get("stderr") or ""),
            encoding="utf-8",
        )

        # Step 4: Verification of physical changes
        print(f"  [Step 4/6] Code changes should already be applied by Gemini tools. Checking git status...", flush=True)
        git_status = _run_command("git status --short", timeout_s=30)
        (iter_dir / "post_fix_git_status.log").write_text(git_status["stdout"] or "")
        if git_status["stdout"]:
            print(f"             Detected changes:\n{git_status['stdout']}", flush=True)
        else:
            print("             No physical changes detected in workspace.", flush=True)

        print(f"  [Step 5/6] Running validation tests (command: {config.test_command})...", flush=True)
        test_res = _run_command(
            config.test_command,
            timeout_s=config.test_timeout_s,
            env_overrides=config.env_overrides,
        )
        (iter_dir / "tests_stdout.log").write_text(test_res["stdout"] or "", encoding="utf-8")
        (iter_dir / "tests_stderr.log").write_text(test_res["stderr"] or "", encoding="utf-8")
        iter_rec["tests"] = {k: v for k, v in test_res.items() if k not in {"stdout", "stderr"}}
        print(f"             Tests OK: {test_res['ok']}", flush=True)

        benchmark_ok = True
        session_benchmark_ok = True
        benchmark_improved = True
        recommendation_ok = True
        env_patch_ok = True
        if str(config.benchmark_command or "").strip():
            print(f"  [Step 6/6] Running planning benchmark (command: {config.benchmark_command})...", flush=True)
            bench = _run_command(
                config.benchmark_command,
                timeout_s=config.benchmark_timeout_s,
                env_overrides=config.env_overrides,
            )
            (iter_dir / "benchmark_stdout.log").write_text(bench["stdout"] or "", encoding="utf-8")
            (iter_dir / "benchmark_stderr.log").write_text(bench["stderr"] or "", encoding="utf-8")
            iter_rec["benchmark"] = {k: v for k, v in bench.items() if k not in {"stdout", "stderr"}}
            benchmark_ok = bool(bench.get("ok"))

            report_path = Path(config.benchmark_report_path)
            prev_path = Path(config.benchmark_previous_report_path)
            curr_score = _read_benchmark_score(report_path)
            prev_score = _read_benchmark_score(prev_path)
            if config.require_benchmark_improve and curr_score is not None and prev_score is not None:
                benchmark_improved = curr_score >= prev_score
            iter_rec["benchmark_score_current"] = curr_score
            iter_rec["benchmark_score_previous"] = prev_score
            iter_rec["benchmark_improved"] = benchmark_improved
            if report_path.exists():
                _ensure_dir(prev_path.parent)
                shutil.copyfile(report_path, prev_path)
            print(f"             Benchmark OK: {benchmark_ok}, improved: {benchmark_improved}", flush=True)

            if (
                benchmark_ok
                and _is_enabled("QUENTIN_THRESHOLD_RECOMMENDATION_ENABLED", "1")
                and str(config.threshold_recommendation_command or "").strip()
            ):
                print(
                    "             Running threshold recommendation "
                    f"(command: {config.threshold_recommendation_command})...",
                    flush=True,
                )
                rec = _run_command(
                    config.threshold_recommendation_command,
                    timeout_s=config.threshold_recommendation_timeout_s,
                    env_overrides=config.env_overrides,
                )
                (iter_dir / "threshold_recommendation_stdout.log").write_text(rec["stdout"] or "", encoding="utf-8")
                (iter_dir / "threshold_recommendation_stderr.log").write_text(rec["stderr"] or "", encoding="utf-8")
                iter_rec["threshold_recommendation"] = {k: v for k, v in rec.items() if k not in {"stdout", "stderr"}}
                recommendation_ok = bool(rec.get("ok"))
                iter_rec["threshold_recommendation_report_path"] = str(config.threshold_recommendation_report_path)
                print(f"             Threshold recommendation OK: {recommendation_ok}", flush=True)

            if (
                benchmark_ok
                and recommendation_ok
                and _is_enabled("QUENTIN_THRESHOLD_ENV_PATCH_ENABLED", "1")
                and str(config.threshold_env_patch_command or "").strip()
            ):
                print(
                    "             Running threshold env patch "
                    f"(command: {config.threshold_env_patch_command})...",
                    flush=True,
                )
                patch = _run_command(
                    config.threshold_env_patch_command,
                    timeout_s=config.threshold_env_patch_timeout_s,
                    env_overrides=config.env_overrides,
                )
                (iter_dir / "threshold_env_patch_stdout.log").write_text(patch["stdout"] or "", encoding="utf-8")
                (iter_dir / "threshold_env_patch_stderr.log").write_text(patch["stderr"] or "", encoding="utf-8")
                iter_rec["threshold_env_patch"] = {k: v for k, v in patch.items() if k not in {"stdout", "stderr"}}
                env_patch_ok = bool(patch.get("ok"))
                iter_rec["threshold_env_patch_path"] = str(config.threshold_env_patch_path)
                print(f"             Threshold env patch OK: {env_patch_ok}", flush=True)

        if str(config.session_benchmark_command or "").strip():
            print(f"             Running session benchmark (command: {config.session_benchmark_command})...", flush=True)
            sbench = _run_command(
                config.session_benchmark_command,
                timeout_s=config.session_benchmark_timeout_s,
                env_overrides=config.env_overrides,
            )
            (iter_dir / "session_benchmark_stdout.log").write_text(sbench["stdout"] or "", encoding="utf-8")
            (iter_dir / "session_benchmark_stderr.log").write_text(sbench["stderr"] or "", encoding="utf-8")
            iter_rec["session_benchmark"] = {k: v for k, v in sbench.items() if k not in {"stdout", "stderr"}}
            session_benchmark_ok = bool(sbench.get("ok"))

            session_report_path = Path(config.session_benchmark_report_path)
            session_report = _read_benchmark_report(session_report_path)
            session_score = float(session_report.get("quality_score") or 0.0) if session_report else None
            session_pass = bool(session_report.get("pass")) if session_report else None
            iter_rec["session_benchmark_score"] = session_score
            iter_rec["session_benchmark_pass"] = session_pass
            if session_score is not None and float(session_score) < float(config.session_benchmark_min_score):
                session_benchmark_ok = False
            if bool(config.session_benchmark_require_pass) and session_pass is False:
                session_benchmark_ok = False
            print(f"             Session benchmark OK: {session_benchmark_ok}", flush=True)

        iter_rec["session_benchmark_ok"] = session_benchmark_ok
        iter_rec["threshold_recommendation_ok"] = recommendation_ok
        iter_rec["threshold_env_patch_ok"] = env_patch_ok

        iter_rec["finished_at"] = _now_utc_iso()
        report["iterations"].append(iter_rec)
        (run_dir / "run_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        if (
            verify["ok"]
            and bool(iter_rec["verify_parsed"].get("success")) is True
            and test_res["ok"]
            and benchmark_ok
            and session_benchmark_ok
            and benchmark_improved
            and recommendation_ok
            and env_patch_ok
        ):
            report["stop_reason"] = "verify_and_tests_green"
            print("\n✅ MISSION ACCOMPLISHED: System is verified and tests are green.", flush=True)
            break
        if config.sleep_seconds > 0:
            time.sleep(config.sleep_seconds)

    if not report["stop_reason"]:
        report["stop_reason"] = "max_iterations_reached"
    report["finished_at"] = _now_utc_iso()
    (Path(report["run_dir"]) / "run_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    
    (Path(report["run_dir"]) / "COMPLETED").write_text(f"Stop Reason: {report['stop_reason']}", encoding="utf-8")
    print(f"\n🏁 Run finished. Report at: {report['run_dir']}/run_report.json", flush=True)
    return report


def _load_config(path: Path | None) -> LoopConfig:
    if not path:
        return LoopConfig()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return LoopConfig(**raw)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run verify->analyze->fix->test autoloop with Gemini CLI.")
    parser.add_argument("--config", type=str, default="", help="JSON config path")
    parser.add_argument("--max-iterations", type=int, default=None, help="Override max iterations (deprecated)")
    parser.add_argument("--iterations", type=int, default=None, help="Override max iterations")
    parser.add_argument("--session", type=str, default=None, help="Override session ID")
    args = parser.parse_args()

    cfg = _load_config(Path(args.config)) if args.config else LoopConfig()
    if args.max_iterations is not None:
        cfg.max_iterations = args.max_iterations
    if args.iterations is not None:
        cfg.max_iterations = args.iterations
    if args.session is not None:
        cfg.session_id = args.session
    
    report = run_loop(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
