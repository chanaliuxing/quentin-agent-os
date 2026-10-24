from __future__ import annotations

from quentin.cognitive.vision_budget import (
    allocate_vision_token_budget,
    record_vision_budget_feedback,
    summarize_vision_budget_feedback,
)


def test_allocate_vision_token_budget_default() -> None:
    b = allocate_vision_token_budget(domain="web", metadata={})
    assert int(b.get("total_tokens") or 0) > 0
    assert int(b.get("screenshot_tokens") or 0) > int(b.get("ui_tree_tokens") or 0)


def test_allocate_vision_token_budget_disabled(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_VISION_BUDGET_ENABLED", "0")
    b = allocate_vision_token_budget(domain="mobile", metadata={})
    assert b == {}


def test_allocate_vision_token_budget_adaptive_debug_ui() -> None:
    b = allocate_vision_token_budget(
        domain="web",
        metadata={"vision_task_class": "debug_ui", "screenshot_entropy": 0.8},
    )
    assert b.get("task_class") == "debug_ui"
    assert int(b.get("screenshot_tokens") or 0) > int(b.get("ui_tree_tokens") or 0)


def test_allocate_vision_token_budget_low_entropy_shifts_ratio(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_VISION_BUDGET_TOTAL_TOKENS_WEB", "5000")
    monkeypatch.setenv("QUENTIN_VISION_BUDGET_LOW_ENTROPY_THRESHOLD", "0.30")
    b = allocate_vision_token_budget(
        domain="web",
        metadata={"vision_task_class": "layout_compare", "screenshot_entropy": 0.1},
    )
    assert int(b.get("screenshot_tokens") or 0) < int(int(b.get("total_tokens") or 0) * 0.76)


def test_vision_budget_feedback_adapts_doc_ocr(tmp_path, monkeypatch) -> None:
    fb = tmp_path / "vision_feedback.jsonl"
    monkeypatch.setenv("QUENTIN_VISION_BUDGET_FEEDBACK_ENABLED", "1")
    monkeypatch.setenv("QUENTIN_VISION_BUDGET_FEEDBACK_PATH", str(fb))
    monkeypatch.setenv("QUENTIN_VISION_BUDGET_FEEDBACK_MIN_SAMPLES", "4")
    for _ in range(4):
        record_vision_budget_feedback(
            domain="web",
            task_class="doc_ocr",
            budget={"total_tokens": 5000, "screenshot_tokens": 3000, "ui_tree_tokens": 900, "ocr_tokens": 1100},
            outcome_score=0.3,
            success=False,
            metadata={},
        )
    b = allocate_vision_token_budget(domain="web", metadata={"vision_task_class": "doc_ocr"})
    assert bool(b.get("feedback_applied")) is True
    # OCR should be boosted on low doc_ocr outcomes.
    assert int(b.get("ocr_tokens") or 0) >= 1200


def test_vision_budget_feedback_summary(tmp_path, monkeypatch) -> None:
    fb = tmp_path / "vision_feedback.jsonl"
    monkeypatch.setenv("QUENTIN_VISION_BUDGET_FEEDBACK_ENABLED", "1")
    monkeypatch.setenv("QUENTIN_VISION_BUDGET_FEEDBACK_PATH", str(fb))
    record_vision_budget_feedback(
        domain="web",
        task_class="debug_ui",
        budget={"total_tokens": 5000, "screenshot_tokens": 3200, "ui_tree_tokens": 1000, "ocr_tokens": 800},
        outcome_score=0.9,
        success=True,
        metadata={},
    )
    out = summarize_vision_budget_feedback(limit=100)
    assert int(out.get("total_rows") or 0) == 1
    assert len(list(out.get("by_task_class") or [])) == 1
    assert float(out.get("avg_effective_outcome_score") or 0.0) == 0.9


def test_vision_budget_feedback_uses_judge_signal_for_effective_score(tmp_path, monkeypatch) -> None:
    fb = tmp_path / "vision_feedback.jsonl"
    monkeypatch.setenv("QUENTIN_VISION_BUDGET_FEEDBACK_ENABLED", "1")
    monkeypatch.setenv("QUENTIN_VISION_BUDGET_FEEDBACK_PATH", str(fb))
    monkeypatch.setenv("QUENTIN_VISION_BUDGET_FEEDBACK_MIN_SAMPLES", "4")
    monkeypatch.setenv("QUENTIN_VISION_BUDGET_JUDGE_WEIGHT", "0.70")
    for _ in range(4):
        record_vision_budget_feedback(
            domain="web",
            task_class="doc_ocr",
            budget={"total_tokens": 5000, "screenshot_tokens": 3000, "ui_tree_tokens": 900, "ocr_tokens": 1100},
            outcome_score=0.30,
            success=False,
            metadata={"judge_score": 0.95},
        )
    out = summarize_vision_budget_feedback(limit=100)
    assert float(out.get("judge_signal_coverage") or 0.0) == 1.0
    assert float(out.get("avg_effective_outcome_score") or 0.0) > 0.70
    b = allocate_vision_token_budget(domain="web", metadata={"vision_task_class": "doc_ocr"})
    # With high effective score from judge signals, no low-score OCR boost should be applied.
    assert bool(b.get("feedback_applied")) is False
