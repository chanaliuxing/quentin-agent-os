from __future__ import annotations

import json
from pathlib import Path

from scripts.planning_threshold_ci_gate import run_gate


def _write_env(path: Path, rows: dict[str, str]) -> None:
    body = "\n".join(f"{k}={v}" for k, v in rows.items()) + "\n"
    path.write_text(body, encoding="utf-8")


def test_ci_gate_passes_when_within_delta(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    patch_path = tmp_path / "patch.env"
    approval_path = tmp_path / "approval.json"
    _write_env(
        env_path,
        {
            "QUENTIN_VERIFY_STRATEGY_SWITCH_MIN": "0.55",
            "QUENTIN_VERIFY_INTERRUPT_EFFECTIVENESS_MIN": "0.50",
        },
    )
    _write_env(
        patch_path,
        {
            "QUENTIN_VERIFY_STRATEGY_SWITCH_MIN": "0.57",
            "QUENTIN_VERIFY_INTERRUPT_EFFECTIVENESS_MIN": "0.54",
        },
    )
    out = run_gate(
        env_path=env_path,
        patch_path=patch_path,
        approval_path=approval_path,
        max_delta=0.08,
    )
    assert out.ok is True
    assert out.status == "within_delta_limit"


def test_ci_gate_fails_over_limit_without_approval(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    patch_path = tmp_path / "patch.env"
    approval_path = tmp_path / "approval.json"
    _write_env(env_path, {"QUENTIN_VERIFY_STRATEGY_SWITCH_MIN": "0.55"})
    _write_env(patch_path, {"QUENTIN_VERIFY_STRATEGY_SWITCH_MIN": "0.80"})
    out = run_gate(
        env_path=env_path,
        patch_path=patch_path,
        approval_path=approval_path,
        max_delta=0.08,
    )
    assert out.ok is False
    assert out.status == "over_limit_without_approval"
    assert len(out.over_limit) == 1


def test_ci_gate_passes_over_limit_with_valid_approval(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    patch_path = tmp_path / "patch.env"
    approval_path = tmp_path / "approval.json"
    _write_env(env_path, {"QUENTIN_VERIFY_STRATEGY_SWITCH_MIN": "0.55"})
    _write_env(patch_path, {"QUENTIN_VERIFY_STRATEGY_SWITCH_MIN": "0.80"})
    approval_path.write_text(
        json.dumps(
            {
                "approved": True,
                "expires_at": "2099-12-31",
                "ticket": "PLN-123",
                "owner": "planner-team",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out = run_gate(
        env_path=env_path,
        patch_path=patch_path,
        approval_path=approval_path,
        max_delta=0.08,
    )
    assert out.ok is True
    assert out.status == "over_limit_but_approved"
