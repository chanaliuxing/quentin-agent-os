from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from quentin.cognitive.learning_writeback import (
    build_task_gist_lines,
    build_task_lesson_content,
)
from quentin.cognitive.loop_goal_flow import lesson_memory_context


def test_build_task_lesson_content_includes_status_and_error() -> None:
    text = build_task_lesson_content(
        done=False,
        done_confidence=0.12,
        domain="core",
        environment="sandbox",
        actions_summary="Tried tool X; failed",
        final_output="",
        primary_error="tool not found",
    )
    assert "status: failed" in text
    assert "primary_error:" in text
    assert "tool not found" in text


def test_build_task_gist_lines_is_small_and_ordered() -> None:
    gist = build_task_gist_lines(
        done=True,
        domain="core",
        actions_summary="did A then B",
        final_output="ok",
    )
    assert isinstance(gist, list)
    assert len(gist) >= 2
    assert gist[0].startswith("Outcome:")


@dataclass
class _Rec:
    id: str
    tier: Any
    domain: str
    content: str
    tags: List[str]
    metadata: Dict[str, Any]


class _Tier:
    def __init__(self, value: str) -> None:
        self.value = value


class _Mem:
    def __init__(self, recs: List[_Rec]) -> None:
        self._recs = recs

    def recall(self, _query: Any) -> List[_Rec]:
        return list(self._recs)


class _Policies:
    lesson_top_k = 2


class _Loop:
    def __init__(self) -> None:
        self.cognitive_policies = _Policies()
        self.memory_fabric = _Mem(
            [
                _Rec(
                    id="l1",
                    tier=_Tier("sts"),
                    domain="core",
                    content="lesson 1",
                    tags=["lesson"],
                    metadata={"x": 1},
                ),
                _Rec(
                    id="l2",
                    tier=_Tier("sts"),
                    domain="core",
                    content="lesson 2",
                    tags=["lesson"],
                    metadata={"x": 2},
                ),
            ]
        )


class _Task:
    input_text = "do something"


class _Goal:
    title = "do something"
    description = ""


def test_lesson_memory_context_limits_top_k() -> None:
    out = lesson_memory_context(_Loop(), task=_Task(), goal=_Goal())
    assert "lesson_memories" in out
    assert len(out["lesson_memories"]) == 2

