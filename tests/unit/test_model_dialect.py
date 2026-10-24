from __future__ import annotations

from quentin.llm.model_dialect import apply_model_dialect


def test_gemini_dialect_moves_runtime_lines_to_user_prefix() -> None:
    system_prompt = (
        "You are planner.\n"
        "runtime: trace_id=abc\n"
        "metadata: session=xyz\n"
        "Keep output JSON."
    )
    user_prompt = '{"task":"x"}'
    sp, up, meta = apply_model_dialect(
        provider="gemini",
        model_name="gemini-2.0-flash",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    assert meta["dialect_profile"] == "gemini_prefill"
    assert "trace_id=abc" not in sp
    assert up.startswith("Runtime context (prefill):")
    assert '{"task":"x"}' in up


def test_gemini_dialect_moves_runtime_prefix_to_user() -> None:
    test_gemini_dialect_moves_runtime_lines_to_user_prefix()


def test_local_small_model_dialect_reduces_prompt_density() -> None:
    system_prompt = "S" * 2400
    user_prompt = "U" * 100
    sp, up, meta = apply_model_dialect(
        provider="ollama",
        model_name="qwen3-vl:latest",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    assert meta["dialect_profile"] == "local_small_compact"
    assert len(sp) < len(system_prompt)
    assert len(up) == len(user_prompt)
    assert meta["prompt_compaction_ratio"] < 1.0


def test_dialect_transform_is_noop_when_disabled(monkeypatch) -> None:
    test_model_dialect_noop_when_disabled(monkeypatch)


def test_model_dialect_noop_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_DISABLE_MODEL_DIALECT", "1")
    sp0 = "sys prompt"
    up0 = "user prompt"
    sp, up, meta = apply_model_dialect(
        provider="gemini",
        model_name="gemini-2.0-flash",
        system_prompt=sp0,
        user_prompt=up0,
    )
    assert sp == sp0
    assert up == up0
    assert meta["dialect_profile"] == "disabled_noop"
    assert meta["prompt_compaction_ratio"] == 1.0
