from quentin.runtime.system import build_default_runtime


class StubLLM:
    def __call__(self, prompt: str, **kwargs):
        return "stub-response"

    def complete(self, prompt: str, **kwargs):
        return "stub-complete"


def test_build_default_runtime_sets_loops(tmp_path):
    runtime = build_default_runtime(
        repo_root=tmp_path,
        llm=StubLLM(),
        council=None,
        enable_self_programming=False,
    )

    # Cognitive loop should be present and runnable
    result = runtime.run_task("hello world", {"domain": "general"})
    assert result.status == "success"
    # The runtime uses the canonical core loop; the critic still uses the provided LLM stub.
    assert result.lessons is not None
    assert "stub" in (result.lessons.content or "")

    # Sleep loop should return a dict even when no memories exist
    sleep_result = runtime.run_sleep_cycle()
    assert isinstance(sleep_result, dict)
    assert "sts_processed" in sleep_result

    # Immune loop should default to a benign action
    immune_action = runtime.run_immune_check()
    assert immune_action.action_type in {"none", "degrade", "reduce_exploration"}

    # Skill evolution loop should exist (even with stub engine)
    assert runtime.skill_evolution_loop is not None
