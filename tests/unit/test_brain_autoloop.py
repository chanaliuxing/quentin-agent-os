from scripts.brain_autoloop import (
    _apply_changes,
    _build_strategy_recovery_prompt,
    _extract_strategy_focus_from_audit,
    _extract_first_json_obj,
    _extract_process_issues_from_verify_output,
    _extract_strategy_switch_issues,
    _is_enabled,
    _looks_like_token_exhausted,
    _path_allowed,
    _parse_verify_result,
    _read_benchmark_score,
)


def test_token_exhaust_detection() -> None:
    text = "Error 429: quota exceeded for this project."
    assert _looks_like_token_exhausted(text) is True


def test_extract_first_json_obj_from_markdown_wrapper() -> None:
    raw = "Here is result:\n```json\n{\"summary\":\"ok\",\"issues\":[]}\n```"
    obj = _extract_first_json_obj(raw)
    assert obj is not None
    assert obj["summary"] == "ok"


def test_parse_verify_result_fields() -> None:
    stdout = "--- TEST RESULT ---\nGoal ID: abc-123\nSuccess: True\nFinal Output: ok"
    parsed = _parse_verify_result(stdout)
    assert parsed["goal_id"] == "abc-123"
    assert parsed["success"] is True


def test_path_allowed() -> None:
    assert _path_allowed("extensions/tools/a.py", ["extensions/tools"]) is True
    assert _path_allowed("meta_agent/x.py", ["extensions/tools"]) is False


def test_apply_changes_write_and_blocked(tmp_path) -> None:
    ok = _apply_changes(
        repo_root=tmp_path,
        changes=[{"path": "generated/a.txt", "action": "write", "content": "hello"}],
        allowed_write_roots=["generated"],
        max_changes_per_iteration=5,
    )
    assert ok["ok"] is True
    assert any(str(x).startswith("generated/a.txt") for x in ok["changed_files"])
    assert (tmp_path / "generated" / "a.txt").read_text(encoding="utf-8") == "hello"

    blocked = _apply_changes(
        repo_root=tmp_path,
        changes=[{"path": "outside/a.txt", "action": "write", "content": "x"}],
        allowed_write_roots=["generated"],
        max_changes_per_iteration=5,
    )
    assert blocked["ok"] is False
    assert blocked["errors"]


def test_extract_strategy_switch_issues_from_verify_output() -> None:
    stdout = (
        "❌ PROCESS EVIDENCE FAILURE:\n"
        " - mutation_without_discovery_evidence\n"
        " - strategy_switch_effectiveness_below_threshold:0.20<0.55\n"
        " - risky_plans_without_planning_diagnostics:2\n"
        " - interrupt_effectiveness_below_threshold:0.00<0.50\n"
    )
    issues = _extract_process_issues_from_verify_output(stdout)
    assert "mutation_without_discovery_evidence" in issues
    switch_issues = _extract_strategy_switch_issues(issues)
    assert any("strategy_switch_effectiveness_below_threshold" in x for x in switch_issues)
    assert any("risky_plans_without_planning_diagnostics" in x for x in switch_issues)
    assert any("interrupt_effectiveness_below_threshold" in x for x in switch_issues)


def test_build_strategy_recovery_prompt_contains_required_actions() -> None:
    prompt = _build_strategy_recovery_prompt(
        ["strategy_switch_effectiveness_below_threshold:0.20<0.55"]
    )
    assert "PLANNING STRATEGY RECOVERY MODE" in prompt
    assert "planning_diagnostics" in prompt
    assert "strategy_switch_effectiveness" in prompt


def test_extract_strategy_focus_from_audit_prefers_example_subcategory() -> None:
    focus = _extract_strategy_focus_from_audit(
        {
            "strategy_regression": {
                "strategy_switching": {
                    "examples": [
                        {
                            "payload_variant_id": "pv_retry_shell_tool_execution_error_shell_permission_denied_v1",
                            "error_subcategory": "shell_permission_denied",
                        }
                    ]
                },
                "execution_resilience": {
                    "interrupt_effectiveness": 0.5,
                    "reset_recovery_rate": 0.2,
                    "progress_sync_compliance": 0.9,
                },
            }
        }
    )
    assert focus["error_subcategory"] == "shell_permission_denied"
    assert focus["tool_family"] == "shell"
    assert focus["interrupt_effectiveness"] == "0.5"


def test_build_strategy_recovery_prompt_includes_subtype_action() -> None:
    prompt = _build_strategy_recovery_prompt(
        ["strategy_switch_effectiveness_below_threshold:0.20<0.55"],
        {"error_subcategory": "browser_selector_not_found", "tool_family": "browser"},
    )
    assert "browser_selector_not_found" in prompt
    assert "refresh DOM/UI-tree" in prompt


def test_read_benchmark_score(tmp_path) -> None:
    p = tmp_path / "bench.json"
    p.write_text('{"quality_score": 0.77}', encoding="utf-8")
    assert _read_benchmark_score(p) == 0.77


def test_is_enabled_parses_boolean_env(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_THRESHOLD_RECOMMENDATION_ENABLED", "0")
    assert _is_enabled("QUENTIN_THRESHOLD_RECOMMENDATION_ENABLED", "1") is False
    monkeypatch.setenv("QUENTIN_THRESHOLD_RECOMMENDATION_ENABLED", "true")
    assert _is_enabled("QUENTIN_THRESHOLD_RECOMMENDATION_ENABLED", "0") is True
