from dataclasses import dataclass


@dataclass
class _ExplodingCouncil:
    def deliberate(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("PolicyEngine should not consult council when bypass_ai_council is set")


def test_policy_engine_bypass_ai_council_skips_consult():
    from quentin.kernel.policy import PolicyEngine, ActionRequest
    from quentin.kernel.taxonomy import ACTION_LLM_CALL

    engine = PolicyEngine(council=_ExplodingCouncil())
    action = ActionRequest.new(
        actor="unit_test",
        action_type=ACTION_LLM_CALL,
        domain="core",
        environment="sandbox",
        risk_level="medium",
        estimated_cost_tokens=200_001,  # triggers high_cost borderline normally
        description="test bypass",
        metadata={"bypass_ai_council": True},
    )

    dec = engine.evaluate(action)
    assert dec.allow is True

