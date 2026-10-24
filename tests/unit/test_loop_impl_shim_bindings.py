from __future__ import annotations

from quentin.cognitive.loop_impl import CognitiveLoop, SkillMiner, TraceEvent


def test_compat_exports_present() -> None:
    assert TraceEvent is not None
    assert SkillMiner is not None


def test_shim_methods_installed_on_class() -> None:
    required = [
        "_get_environment_snapshot",
        "_compute_plan_for_attempt",
        "_run_goal_internal",
        "_extract_attempt_metrics",
        "_repair_plan_quality",
        "_build_planner_hints",
        "_prompt_factory_enabled",
    ]
    for name in required:
        assert hasattr(CognitiveLoop, name), name
        assert callable(getattr(CognitiveLoop, name)), name


def test_static_shim_methods_callable() -> None:
    metrics = CognitiveLoop._extract_attempt_metrics(
        raw_exec_data={},
        attempt_start="2026-01-01T00:00:00+00:00",
        attempt_end="2026-01-01T00:00:01+00:00",
    )
    assert isinstance(metrics, dict)

    hints = CognitiveLoop._build_planner_hints({"forbidden_actions": ["nano"]})
    assert isinstance(hints, list)
