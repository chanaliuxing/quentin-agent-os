from __future__ import annotations

from quentin.cognitive.perception.layer import PerceptionContextConfig, PerceptionContextLayer


def test_perception_layer_builds_snapshot_and_attention() -> None:
    layer = PerceptionContextLayer(
        config=PerceptionContextConfig(
            enable_situation_classifier=True,
            enable_attention_filter=True,
            enable_expectation_engine=False,
            enable_situation_to_skill=False,
            attention_target_ratio=0.15,
            debug_use_full_context=False,
        )
    )
    snap = layer.build_snapshot(
        ctx={
            "domain": "core",
            "environment": "sandbox",
            "window_title": "Login Required",
            "historical_attempts": "prev attempt failed",
            "current_environment_tree": "a/\n b/\n",
            "system_event_prompt": "login expired",
        }
    )
    assert snap.situation.situation_id
    assert 0.0 <= snap.situation.confidence <= 1.0
    assert snap.attention is not None
    assert isinstance(snap.attention.selected_context, dict)
    assert 0.0 <= snap.attention.reduction_ratio <= 1.0


def test_perception_layer_handles_empty_metadata_ctx() -> None:
    layer = PerceptionContextLayer(
        config=PerceptionContextConfig(
            enable_situation_classifier=True,
            enable_attention_filter=True,
            enable_expectation_engine=False,
            enable_situation_to_skill=False,
        )
    )
    snap = layer.build_snapshot(ctx={})
    assert snap.situation.situation_id == "unknown_text_only"
    assert snap.attention is not None
    assert 0.0 <= snap.attention.reduction_ratio <= 1.0


def test_perception_layer_handles_large_context_with_truncation() -> None:
    layer = PerceptionContextLayer(
        config=PerceptionContextConfig(
            enable_situation_classifier=True,
            enable_attention_filter=True,
            enable_expectation_engine=False,
            enable_situation_to_skill=False,
            attention_target_ratio=0.1,
        )
    )
    huge = "x" * 12000
    snap = layer.build_snapshot(
        ctx={
            "domain": "core",
            "environment": "sandbox",
            "historical_attempts": huge,
            "current_environment_tree": huge,
            "ui_tree": huge,
            "metadata_blob": {"raw": huge},
        }
    )
    assert snap.attention is not None
    selected = snap.attention.selected_context
    assert isinstance(selected.get("historical_attempts"), str)
    assert len(selected["historical_attempts"]) <= 4000
    assert isinstance(selected.get("current_environment_tree_preview"), str)
    assert len(selected["current_environment_tree_preview"]) <= 2000
    assert 0.0 <= snap.attention.reduction_ratio <= 1.0
