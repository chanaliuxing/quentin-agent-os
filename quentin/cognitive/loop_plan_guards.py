from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List


def _infer_expected_tool_from_step(step: Dict[str, Any]) -> str:
    desc = str(step.get("description") or "").strip().lower()
    notes = str(step.get("notes") or "").strip().lower()
    text = f"{desc}\n{notes}"
    explicit = (
        "fs.read_file",
        "fs.write_file",
        "fs.search_replace",
        "shell.run_command",
        "ls",
        "mkdir",
        "cat",
        "grep",
    )
    for tool in explicit:
        if tool in text:
            return tool
    if is_discovery_step(desc):
        return "fs.read_file"
    if is_risky_step(desc):
        return "fs.search_replace"
    return ""


def _fallback_families_for_tool(expected: str) -> List[str]:
    e = str(expected or "").strip().lower()
    if not e:
        return []
    if e.startswith("fs.") or e in {"ls", "cat", "mkdir", "grep"}:
        return ["filesystem", "shell"]
    if e.startswith("shell."):
        return ["shell", "filesystem"]
    if e.startswith("browser.") or e.startswith("web_search."):
        return ["browser"]
    return ["generic"]


def _normalize_step_tool_intent(step: Dict[str, Any]) -> Dict[str, Any]:
    src = step.get("tool_intent") if isinstance(step.get("tool_intent"), dict) else {}
    expected = str(src.get("expected_tool") or "").strip().lower()
    if not expected:
        expected = _infer_expected_tool_from_step(step)
    fallback = src.get("allowed_fallback_families")
    fallback_list = [str(x).strip().lower() for x in fallback] if isinstance(fallback, list) else []
    fallback_list = [x for x in fallback_list if x]
    if not fallback_list:
        fallback_list = _fallback_families_for_tool(expected)
    why = str(src.get("why") or "plan_lint_normalized").strip()
    return {"expected_tool": expected, "allowed_fallback_families": fallback_list, "why": why}


def _coding_tool_preference_text() -> str:
    primary = str(os.getenv("QUENTIN_CODING_TOOL_PRIMARY", "gemini.code") or "").strip()
    fallback_raw = str(os.getenv("QUENTIN_CODING_TOOL_FALLBACKS", "coder.generate") or "")
    fallbacks = [x.strip() for x in fallback_raw.split(",") if x.strip()]
    names: List[str] = []
    for x in [primary, *fallbacks]:
        if x and x not in names:
            names.append(x)
    return "/".join(names[:3]) if names else "configured coding tools"


def build_planner_fallback_steps(*, task_text: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidate_files = context.get("candidate_files") if isinstance(context, dict) else []
    target_hint = str(candidate_files[0]) if isinstance(candidate_files, list) and candidate_files else "relevant target files"
    steps = [
        {
            "step_id": "s1",
            "description": (
                f"Discovery precheck: inspect workspace and locate exact files for this task ({target_hint}) "
                "using ls/find/grep/fs.read_file."
            ),
            "skill_id": None,
            "notes": "planner_fallback_discovery_precheck",
            "tool_intent": {
                "expected_tool": "fs.read_file",
                "allowed_fallback_families": ["filesystem", "shell"],
                "why": "discovery_before_risky",
            },
        },
        {
            "step_id": "s2",
            "description": (
                "Apply minimal targeted change on confirmed file(s) only; prefer fs.search_replace and "
                "use fs.write_file only when necessary."
            ),
            "skill_id": None,
            "notes": "planner_fallback_apply_change",
            "tool_intent": {
                "expected_tool": "fs.search_replace",
                "allowed_fallback_families": ["filesystem", "shell"],
                "why": "targeted_mutation",
            },
        },
        {
            "step_id": "s3",
            "description": "Run non-interactive verification and produce a user-visible progress summary.",
            "skill_id": None,
            "notes": "planner_fallback_verify",
            "tool_intent": {
                "expected_tool": "shell.run_command",
                "allowed_fallback_families": ["shell", "filesystem"],
                "why": "verification_evidence",
            },
        },
    ]
    lifecycle = context.get("planner_lifecycle_payload") if isinstance(context.get("planner_lifecycle_payload"), dict) else {}
    stage = str(lifecycle.get("stage") or "").strip().lower()
    strategy_patch = context.get("planning_strategy_patch") if isinstance(context.get("planning_strategy_patch"), dict) else {}
    payload_variant = context.get("planner_payload_variant") if isinstance(context.get("planner_payload_variant"), dict) else {}
    payload_variant = context.get("planner_payload_variant") if isinstance(context.get("planner_payload_variant"), dict) else {}
    payload_variant = context.get("planner_payload_variant") if isinstance(context.get("planner_payload_variant"), dict) else {}
    strategy_category = str(strategy_patch.get("category") or "").strip().lower()
    variant_tool_family = str(payload_variant.get("tool_family") or "").strip().lower()
    if strategy_category == "environment_timeout_error":
        steps.insert(
            1,
            {
                "step_id": "s1a",
                "description": (
                    "Timeout diagnostics precheck: run low-cost probes (pwd/ls/id and one targeted read) "
                    "to confirm environment responsiveness before edits."
                ),
                "skill_id": None,
                "notes": "planner_fallback_timeout_diagnostics",
            },
        )
    elif strategy_category == "tool_execution_error":
        steps.insert(
            1,
            {
                "step_id": "s1a",
                "description": (
                    "Tool guardrail precheck: verify path existence and write policy "
                    "(fs.exists/fs.get_write_policy) before mutation."
                ),
                "skill_id": None,
                "notes": "planner_fallback_tool_guardrail_precheck",
            },
        )
    elif strategy_category == "logic_path_error":
        steps.insert(
            1,
            {
                "step_id": "s1a",
                "description": (
                    "Branch strategy probe: define one alternative path and run a cheap validation "
                    "to avoid replaying the failed strategy."
                ),
                "skill_id": None,
                "notes": "planner_fallback_branch_probe",
            },
        )
    elif strategy_category == "model_syntax_error":
        steps.insert(
            1,
            {
                "step_id": "s1a",
                "description": (
                    "Schema guard precheck: keep each step single-purpose and validate "
                    "tool args/expected output format before execution."
                ),
                "skill_id": None,
                "notes": "planner_fallback_schema_guard",
            },
        )
    if variant_tool_family == "browser":
        steps.insert(
            1,
            {
                "step_id": "s1c",
                "description": (
                    "Browser state probe: refresh UI/tree snapshot and verify selector/page readiness "
                    "before repeating click/type/navigation."
                ),
                "skill_id": None,
                "notes": "planner_fallback_browser_state_probe",
            },
        )
    elif variant_tool_family == "shell":
        steps.insert(
            1,
            {
                "step_id": "s1c",
                "description": (
                    "Shell diagnostics probe: run pwd/id/ls first and change command shape "
                    "before any repeated shell mutation."
                ),
                "skill_id": None,
                "notes": "planner_fallback_shell_diag_probe",
            },
        )
    if stage == "stuck":
        steps.insert(
            1,
            {
                "step_id": "s1b",
                "description": (
                    "Speculative probe set (stuck mode): define 2 hypotheses and run cheap checks "
                    "(pwd/ls/fs.exists/grep) to disambiguate root cause before edits."
                ),
                "skill_id": None,
                "notes": "planner_fallback_speculative_probe",
            },
        )
    return steps


def update_circuit_breaker_state(
    *,
    raw_error: Any,
    consecutive_errors: int,
    last_error_msg: str,
    threshold: int = 2,
) -> tuple[int, str, str, bool]:
    current_err = str(raw_error or "").strip()
    if not current_err:
        return 0, "", "", False

    if current_err == str(last_error_msg or ""):
        consecutive_errors += 1
    else:
        consecutive_errors = 1
        last_error_msg = current_err
    triggered = consecutive_errors >= max(1, int(threshold or 1))
    return consecutive_errors, last_error_msg, current_err, triggered


def assess_discovery_guard(steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    risky_indices: List[int] = []
    for idx, step in enumerate(steps or []):
        if is_risky_step(str(step.get("description") or "")):
            risky_indices.append(idx)
    if not risky_indices:
        return {
            "risky_steps": 0,
            "discovery_before_risky": True,
            "first_risky_step_id": "",
            "first_discovery_step_id": "",
        }
    first_risky = risky_indices[0]
    discovery_idx = -1
    for i, step in enumerate((steps or [])[:first_risky]):
        if is_discovery_step(str(step.get("description") or "")):
            discovery_idx = i
            break
    first_risky_step = (steps or [])[first_risky] if first_risky < len(steps or []) else {}
    first_discovery_step = (steps or [])[discovery_idx] if discovery_idx >= 0 else {}
    return {
        "risky_steps": len(risky_indices),
        "discovery_before_risky": discovery_idx >= 0,
        "first_risky_step_id": str(first_risky_step.get("step_id") or ""),
        "first_discovery_step_id": str(first_discovery_step.get("step_id") or ""),
    }


def is_discovery_step(desc: str) -> bool:
    d = str(desc or "").lower()
    markers = ("discover", "probe", "inspect", "ls", "which", "find", "grep", "cat", "read_file", "fs.read_file")
    return any(m in d for m in markers)


def is_risky_step(desc: str) -> bool:
    d = str(desc or "").lower()
    markers = (
        "write", "delete", "remove", "download", "install", "wget", "curl",
        "fs.write_file", "fs.search_replace", "patch", "edit",
    )
    return any(m in d for m in markers)


def repair_plan_quality(
    *,
    task_text: str,
    context: Dict[str, Any],
    steps: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], List[str]]:
    repaired = [dict(s) for s in (steps or []) if isinstance(s, dict)]
    notes: List[str] = []

    previous_plan_steps = context.get("previous_plan_steps")
    if len(repaired) <= 1 and isinstance(previous_plan_steps, list) and len(previous_plan_steps) >= 3:
        repaired = [dict(s) for s in previous_plan_steps[:6] if isinstance(s, dict)]
        notes.append("prevent_strategy_regression_reused_previous_decomposition")

    if len(repaired) <= 1:
        repaired = build_planner_fallback_steps(task_text=task_text, context=context)
        notes.append("decompose_single_step_fallback")

    lifecycle = context.get("planner_lifecycle_payload") if isinstance(context.get("planner_lifecycle_payload"), dict) else {}
    stage = str(lifecycle.get("stage") or "").strip().lower()
    strategy_patch = context.get("planning_strategy_patch") if isinstance(context.get("planning_strategy_patch"), dict) else {}
    payload_variant = context.get("planner_payload_variant") if isinstance(context.get("planner_payload_variant"), dict) else {}
    if stage == "stuck":
        has_speculative_probe = any(
            any(k in str(s.get("description") or "").lower() for k in ("speculative", "hypothesis"))
            for s in repaired
        )
        if not has_speculative_probe:
            insert_idx = 1 if repaired else 0
            repaired.insert(
                insert_idx,
                {
                    "step_id": "s_spec",
                    "description": (
                        "Stuck-mode speculative execution: create 2 hypotheses for failure root cause and "
                        "run one low-cost validation step for each hypothesis."
                    ),
                    "skill_id": None,
                    "notes": "inject_speculative_probe_stuck_mode",
                },
            )
            notes.append("inject_speculative_probe_stuck_mode")
    lifecycle = context.get("planner_lifecycle_payload") if isinstance(context.get("planner_lifecycle_payload"), dict) else {}
    force_progress_sync = bool(lifecycle.get("force_progress_sync", False))
    if force_progress_sync:
        has_sync_step = any(
            any(k in str(s.get("description") or "").lower() for k in ("progress update", "report progress", "user-visible progress", "status update"))
            for s in repaired
        )
        if not has_sync_step:
            repaired.insert(
                0,
                {
                    "step_id": "s_sync",
                    "description": (
                        "User-visible progress sync: provide a brief status update (what was tried, what failed, "
                        "what will change next) before additional tool calls."
                    ),
                    "skill_id": None,
                    "notes": "inject_progress_sync_step",
                },
            )
            notes.append("inject_progress_sync_step")
    if bool(context.get("interrupt_cooldown_active", False)):
        has_cooldown_diag = any(
            any(k in str(s.get("description") or "").lower() for k in ("bounded diagnostics", "pwd", "fs.get_write_policy", "runtime health"))
            for s in repaired
        )
        if not has_cooldown_diag:
            repaired.insert(
                0,
                {
                    "step_id": "s_cooldown",
                    "description": (
                        "Interrupt cooldown diagnostics: run bounded probes (pwd/id/ls/fs.get_write_policy) "
                        "and confirm environment health before any mutating step."
                    ),
                    "skill_id": None,
                    "notes": "inject_interrupt_cooldown_diagnostics",
                },
            )
            notes.append("inject_interrupt_cooldown_diagnostics")

    merged_prechecks: List[str] = []
    if isinstance(strategy_patch, dict) and strategy_patch:
        merged_prechecks.extend([str(x).strip().lower() for x in (strategy_patch.get("required_prechecks") or []) if str(x).strip()])
    if isinstance(payload_variant, dict) and payload_variant:
        merged_prechecks.extend([str(x).strip().lower() for x in (payload_variant.get("required_prechecks") or []) if str(x).strip()])
    required_prechecks = sorted({x for x in merged_prechecks if x})
    if required_prechecks:
        all_desc = " ".join([str(s.get("description") or "").lower() for s in repaired])
        missing: List[str] = []
        marker_map = {
            "env_diagnostics": ("pwd", "ls", "id", "diagnostic"),
            "timeout_probe": ("timeout", "responsive", "latency"),
            "shell_diag": ("pwd", "id", "ls", "shell"),
            "browser_state_probe": ("page", "browser", "observe", "state"),
            "selector_probe": ("selector", "element", "ui tree", "dom"),
            "command_exists_probe": ("which ", "type ", "command -v", "command exists"),
            "path_exists_probe": ("exists", "path", "find"),
            "write_policy_check": ("write policy", "fs.get_write_policy"),
            "schema_guard": ("schema", "format", "single-purpose"),
            "delta_explanation": ("delta", "differ", "previous"),
            "branch_probe": ("alternative", "branch", "hypothesis"),
            "runtime_health_probe": ("health", "runtime", "diagnostic"),
            "progress_sync": ("progress sync", "status update", "report progress", "user-visible progress"),
        }
        for req in required_prechecks:
            markers = marker_map.get(req, (req,))
            if not any(m in all_desc for m in markers):
                missing.append(req)
        if missing:
            repaired.insert(
                0,
                {
                    "step_id": "s_patch",
                    "description": (
                        "Strategy patch prechecks: "
                        + ", ".join(missing[:4])
                        + ". Run low-cost probes first, then proceed with edits only on positive signals."
                    ),
                    "skill_id": None,
                    "notes": "inject_strategy_patch_prechecks",
                },
            )
            notes.append("inject_strategy_patch_prechecks")

    first_risky_idx = -1
    for idx, step in enumerate(repaired):
        if is_risky_step(str(step.get("description") or "")):
            first_risky_idx = idx
            break
    if first_risky_idx >= 0:
        has_discovery_before = any(
            is_discovery_step(str(s.get("description") or ""))
            for s in repaired[:first_risky_idx]
        )
        if not has_discovery_before:
            repaired.insert(
                0,
                {
                    "step_id": "s0",
                    "description": (
                        "Discovery precheck before risky operations: verify environment state "
                        "with ls/which/find/fs.read_file."
                    ),
                    "skill_id": None,
                    "notes": "injected_discovery_precheck",
                },
            )
            notes.append("inject_discovery_precheck")

    for i, step in enumerate(repaired, start=1):
        if not str(step.get("step_id") or "").strip():
            step["step_id"] = f"s{i}"
        step["tool_intent"] = _normalize_step_tool_intent(step)
        notes_text = str(step.get("notes") or "").strip()
        if notes_text and ("verify" in notes_text.lower() or "validation" in notes_text.lower()):
            continue
        if "verify" in str(step.get("description") or "").lower() or "check" in str(step.get("description") or "").lower():
            if notes_text:
                step["notes"] = notes_text + " | verify_condition:tool_result_success_or_test_green"
            else:
                step["notes"] = "verify_condition:tool_result_success_or_test_green"
                notes.append("inject_verify_condition_note")
    return repaired, notes


def apply_self_awareness_runtime_controls(snapshot: Any) -> Dict[str, Any]:
    control = {
        "request_flush": False,
        "force_reflection": False,
        "abort_now": False,
        "abort_reason": "",
    }
    if snapshot.failover_reason == "context_overflow":
        control["request_flush"] = True
    if snapshot.anti_pattern_reason:
        control["force_reflection"] = True
    if snapshot.status in {"warning", "critical"}:
        control["force_reflection"] = True
    if snapshot.consecutive_no_progress >= 2:
        control["force_reflection"] = True
    if snapshot.consecutive_system_errors >= 2 and snapshot.status == "critical":
        control["abort_now"] = True
        control["abort_reason"] = (
            f"consecutive_system_errors={snapshot.consecutive_system_errors}, "
            f"last_error={snapshot.last_error[:200]}"
        )
    return control


def detect_execution_antipattern(*, raw_exec_data: Dict[str, Any]) -> Dict[str, Any]:
    interactive = {"nano", "vim", "vi", "emacs"}
    steps = raw_exec_data.get("steps", []) if isinstance(raw_exec_data, dict) else []
    if not isinstance(steps, list):
        return {"detected": False}

    for step in steps:
        if not isinstance(step, dict):
            continue
        result = step.get("result")
        if not isinstance(result, dict):
            continue
        if str(result.get("error") or "") == "repeated_tool_call_loop":
            return {
                "detected": True,
                "reason": "repeated_tool_call_loop",
                "target_path": "",
            }
        call_tool = result.get("call_tool")
        if not isinstance(call_tool, dict):
            call_tool = {}
        tool_name = str(call_tool.get("tool_name") or "").strip()
        args = call_tool.get("args") if isinstance(call_tool.get("args"), dict) else {}
        command = str(args.get("command") or "").strip()

        def _detect_command_pattern(cmd_text: str) -> Dict[str, Any]:
            cmd = str(cmd_text or "").strip()
            if not cmd:
                return {"detected": False}
            parts = cmd.split()
            base_cmd = parts[0].split("/")[-1].lower() if parts else ""
            if base_cmd in interactive or " nano " in f" {cmd.lower()} ":
                return {
                    "detected": True,
                    "reason": "interactive_editor_command",
                    "target_path": extract_interactive_target_path(cmd),
                }
            cmd_lower = cmd.lower()
            if ("wget " in cmd_lower or "curl " in cmd_lower) and ("github.com" in cmd_lower or "releases/" in cmd_lower):
                return {
                    "detected": True,
                    "reason": "guessed_download_command",
                    "target_path": "",
                }
            return {"detected": False}

        if tool_name in {"shell.run_command", "shell_run_command"}:
            signal = _detect_command_pattern(command)
            if signal.get("detected"):
                return signal
        tool_result = result.get("tool_result")
        if isinstance(tool_result, dict):
            err = str(tool_result.get("error") or "").lower()
            hint = str(tool_result.get("hint") or "").lower()
            if "outside repo_root" in err or "not under allowed roots" in err or "violates path safety policy" in hint:
                return {
                    "detected": True,
                    "reason": "path_permission_denied",
                    "target_path": args.get("path") or args.get("file_path") or args.get("dir_path") or "",
                }
            if "interactive command" in err:
                return {
                    "detected": True,
                    "reason": "interactive_editor_command",
                    "target_path": extract_interactive_target_path(command),
                }
        feedback_tail = result.get("feedback_tail")
        if isinstance(feedback_tail, list):
            for fb in feedback_tail:
                if not isinstance(fb, dict):
                    continue
                fb_call = fb.get("tool_call") if isinstance(fb.get("tool_call"), dict) else {}
                fb_name = str(fb_call.get("tool_name") or "").strip()
                fb_args = fb_call.get("args") if isinstance(fb_call.get("args"), dict) else {}
                fb_cmd = str(fb_args.get("command") or "").strip()
                if fb_name in {"shell.run_command", "shell_run_command"}:
                    signal = _detect_command_pattern(fb_cmd)
                    if signal.get("detected"):
                        return signal
                fb_result = fb.get("tool_result")
                if isinstance(fb_result, dict):
                    err = str(fb_result.get("error") or "").lower()
                    if "interactive command" in err:
                        return {
                            "detected": True,
                            "reason": "interactive_editor_command",
                            "target_path": extract_interactive_target_path(fb_cmd),
                        }
    return {"detected": False}


def extract_interactive_target_path(command: str) -> str:
    text = str(command or "").strip()
    lower = text.lower()
    for token in ("nano ", "vim ", "vi ", "emacs "):
        idx = lower.rfind(token)
        if idx == -1:
            continue
        tail = text[idx + len(token):].strip().strip("\"'")
        file_part = tail.split()[0] if tail else ""
        if not file_part:
            return ""
        if "&&" not in text:
            return file_part
        prefix = text[:idx]
        if "cd " not in prefix:
            return file_part
        cd_tail = prefix.split("cd ", 1)[1].split("&&", 1)[0].strip().strip("\"'")
        if cd_tail:
            return f"{cd_tail.rstrip('/')}/{file_part.lstrip('./')}"
        return file_part
    return ""


def build_antipattern_recovery_plan(*, task: Any, anti_pattern: Dict[str, Any]) -> Dict[str, Any]:
    reason = str(anti_pattern.get("reason") or "unknown")
    target_path = str(anti_pattern.get("target_path") or "").strip()
    target_hint = target_path or "the target source file"

    if reason == "path_permission_denied":
        steps = [
            {
                "step_id": "s1",
                "description": (
                    f"The previous path '{target_hint}' was denied by security policy. "
                    "Switch to an allowed directory like 'mutable/' or 'quentin/mutable/'."
                ),
                "skill_id": None,
                "notes": "path_remapping_recovery",
            },
            {
                "step_id": "s2",
                "description": (
                    f"Write the content to 'mutable/{Path(target_path).name if target_path else 'output.md'}' instead."
                ),
                "skill_id": None,
                "notes": "use_allowed_root",
            },
            {
                "step_id": "s3",
                "description": "Verify the file was written to the new location and summarize progress.",
                "skill_id": None,
                "notes": "verify_remapped_path",
            },
        ]
    elif reason == "repeated_tool_call_loop":
        coding_tools = _coding_tool_preference_text()
        steps = [
            {
                "step_id": "s1",
                "description": (
                    "Run environment diagnostics first: call pwd, run shell.run_command('id'), then ls on current directory."
                ),
                "skill_id": None,
                "notes": "dead_loop_diagnostic_probe",
            },
            {
                "step_id": "s2",
                "description": (
                    "Call fs.get_write_policy and remap target path to an allowed writable root if needed."
                ),
                "skill_id": None,
                "notes": "dead_loop_check_write_policy",
            },
            {
                "step_id": "s3",
                "description": (
                    f"Retry with a changed strategy on {target_hint}: if coding is complex use {coding_tools} first, "
                    "then apply minimal file edits."
                ),
                "skill_id": None,
                "notes": "dead_loop_strategy_pivot",
            },
        ]
    else:
        steps = [
            {
                "step_id": "s1",
                "description": (
                    f"Read {target_hint} using fs.read_file and identify exact code changes. "
                    "Do not use shell editors."
                ),
                "skill_id": None,
                "notes": f"antipattern_recovery:{reason}",
            },
            {
                "step_id": "s2",
                "description": (
                    f"Apply the required edit to {target_hint} using fs.search_replace if possible; "
                    "fallback to fs.write_file only if needed."
                ),
                "skill_id": None,
                "notes": "prefer_non_interactive_file_tools",
            },
            {
                "step_id": "s3",
                "description": (
                    "Run only non-interactive verification command (for example python -m py_compile on changed file), "
                    "then produce a user-visible progress summary."
                ),
                "skill_id": None,
                "notes": "no_wget_no_nano_no_vim",
            },
        ]
    return {
        "steps": steps,
        "metadata": {
            "source": "antipattern_recovery",
            "reason": reason,
            "task_id": task.task_id,
            "target_path": target_path,
        },
    }


def has_meaningful_progress(final_output: str) -> bool:
    text = str(final_output or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if lowered in {"{}", "none", "null", "ok"}:
        return False
    return len(text) >= 16


def is_tool_only_no_update(*, raw_exec_data: Dict[str, Any], final_output: str) -> bool:
    if has_meaningful_progress(final_output):
        return False
    steps = raw_exec_data.get("steps", []) if isinstance(raw_exec_data, dict) else []
    if not isinstance(steps, list) or not steps:
        return False
    has_tool_activity = False
    for step in steps:
        if not isinstance(step, dict):
            continue
        result = step.get("result")
        if not isinstance(result, dict):
            continue
        if "tool_result" in result or result.get("call_tool"):
            has_tool_activity = True
    return has_tool_activity
