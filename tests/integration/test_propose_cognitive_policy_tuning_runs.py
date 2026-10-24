from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml


def test_propose_cognitive_policy_tuning_outputs_and_applies(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    events = tmp_path / "events.jsonl"
    policy = tmp_path / "cognitive_policies.yaml"
    events.write_text(
        "\n".join(
            [
                json.dumps({"payload": {"prediction_error_rate": 0.7, "context_misclass_rate": 0.4}}),
                json.dumps({"payload": {"prediction_error_rate": 0.6, "context_misclass_rate": 0.3}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    policy.write_text(
        yaml.safe_dump(
            {
                "cognitive_policies": {
                    "enable_expectation_engine": True,
                    "enable_situation_to_skill": True,
                    "attention_target_ratio": 0.2,
                }
            },
            sort_keys=False,
            allow_unicode=False,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "propose_cognitive_policy_tuning.py"),
            "--events",
            str(events),
            "--policy-path",
            str(policy),
            "--apply",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-2000:] + "\n" + proc.stdout[-2000:]
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert float(out["rates"]["prediction_error_rate_avg"]) >= 0.6
    obj = yaml.safe_load(policy.read_text(encoding="utf-8")) or {}
    cp = obj.get("cognitive_policies") or {}
    assert cp.get("enable_expectation_engine") is False
    assert cp.get("enable_situation_to_skill") is False
    assert float(cp.get("attention_target_ratio")) <= 0.12
