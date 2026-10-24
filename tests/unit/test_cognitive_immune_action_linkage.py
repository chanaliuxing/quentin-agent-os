from __future__ import annotations

from types import SimpleNamespace

from quentin.cognitive.loop_maintenance import apply_immune_action
from quentin.cognitive.perception.layer import PerceptionContextConfig


class _Action:
    def __init__(self, *, anomaly_type: str, degrade: bool = True, disable_self_prog: bool = False) -> None:
        self.degrade_mode = degrade
        self.disable_self_programming = disable_self_prog
        self.revert_version = False
        self.anomaly = {"anomaly_type": anomaly_type}

    def to_dict(self):
        return {
            "degrade_mode": self.degrade_mode,
            "disable_self_programming": self.disable_self_programming,
            "revert_version": self.revert_version,
            "anomaly": self.anomaly,
        }


def test_apply_immune_action_prediction_error_disables_reflex_features() -> None:
    loop = SimpleNamespace(
        degrade_mode=False,
        self_programming_enabled=True,
        perception_layer=SimpleNamespace(
            config=PerceptionContextConfig(
                enable_situation_to_skill=True,
                enable_expectation_engine=True,
            )
        ),
    )
    action = _Action(anomaly_type="prediction_error_spike", degrade=True, disable_self_prog=False)
    apply_immune_action(loop, action=action, goal=SimpleNamespace(goal_id="g1"))

    assert loop.degrade_mode is True
    assert loop.perception_layer.config.enable_situation_to_skill is False
    assert loop.perception_layer.config.enable_expectation_engine is False


def test_apply_immune_action_can_disable_self_programming() -> None:
    loop = SimpleNamespace(
        degrade_mode=False,
        self_programming_enabled=True,
        perception_layer=SimpleNamespace(config=PerceptionContextConfig()),
    )
    action = _Action(anomaly_type="high_failure_rate", degrade=True, disable_self_prog=True)
    apply_immune_action(loop, action=action, goal=SimpleNamespace(goal_id="g2"))
    assert loop.degrade_mode is True
    assert loop.self_programming_enabled is False
