"""
Tests for Strategy Council implementation.
"""
import tempfile
from pathlib import Path
import pytest

from quentin.l3.research.strategy_council import (
    generate_proposals,
    cross_review,
    synthesize_plan,
    run_council,
    log_plan_vs_outcome,
    load_recent_plan_outcomes,
    StrategyProposal,
    HedgePlan,
)


class TestStrategyCouncil:
    """Test strategy council functionality."""

    def test_generate_proposals_fallback(self):
        """✓ Verify generate_proposals works in fallback mode."""
        ctx = {"disable_llm": True, "universe": ["AAPL", "MSFT", "SPY"]}
        proposals = generate_proposals(ctx)

        assert len(proposals) > 0, "Should generate at least one fallback proposal"

        # Check first proposal structure
        p = proposals[0]
        assert hasattr(p, 'proposal_id')
        assert hasattr(p, 'symbols')
        assert hasattr(p, 'expected_ev')
        assert hasattr(p, 'confidence')
        assert p.expected_ev > 0, "Fallback proposal should have positive EV"

        print(f"✓ Generated {len(proposals)} fallback proposals")
        print(f"  First proposal: {p.symbols}, EV={p.expected_ev:.2f}, confidence={p.confidence:.2f}")

    def test_cross_review_fallback(self):
        """✓ Verify cross_review works in fallback mode."""
        ctx = {"disable_llm": True}

        # Create a sample proposal
        proposal = StrategyProposal(
            proposal_id="test123",
            symbols=["AAPL"],
            side="long",
            weights={"AAPL": 1.0},
            entry_rule="breakout",
            exit_rule="stop_loss",
            hold_horizon_min=60,
            expected_ev=0.15,
            confidence=0.6,
        )

        reviews = cross_review([proposal], ctx)

        assert len(reviews) > 0, "Should generate at least one review"

        r = reviews[0]
        assert r.target_proposal_id == proposal.proposal_id
        assert hasattr(r, 'concerns')
        assert hasattr(r, 'feasibility_score')

        print(f"✓ Generated {len(reviews)} reviews")
        print(f"  Concerns: {r.concerns}")

    def test_synthesize_plan(self):
        """✓ Verify synthesize_plan creates a valid plan."""
        ctx = {"disable_llm": True}

        # Create proposals
        proposals = generate_proposals(ctx)
        reviews = cross_review(proposals, ctx)

        plan = synthesize_plan(proposals, reviews, ctx)

        assert plan is not None, "Should synthesize a plan"
        assert hasattr(plan, 'base_proposal_id')
        assert hasattr(plan, 'risk_limits')
        assert hasattr(plan, 'approvals')

        print(f"✓ Synthesized plan based on {plan.base_proposal_id[:8]}...")
        print(f"  Risk limits: {list(plan.risk_limits.keys())}")
        print(f"  Approvals: {plan.approvals}")

    def test_run_council_end_to_end(self):
        """✓ Verify full council workflow works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "council_output"

            ctx = {
                "disable_llm": True,
                "universe": ["AAPL", "TSLA", "SPY"],
                "output_dir": str(output_dir),
            }

            result = run_council(ctx)

            # Verify result structure
            assert "proposals" in result
            assert "final_plan" in result

            proposals = result["proposals"]
            assert len(proposals) > 0, "Should have proposals"

            final_plan = result["final_plan"]
            assert final_plan is not None, "Should have final plan"

            print(f"✓ Council completed successfully")
            print(f"  Proposals: {len(proposals)}")
            print(f"  Final plan: {final_plan.base_proposal_id[:8]}...")

            # Check paper result
            paper_result = result.get("paper_result")
            if paper_result:
                print(f"  Paper result: PnL={paper_result.pnl:.2f}, MDD={paper_result.mdd:.1f}%")

    def test_plan_outcome_logger(self):
        """✓ Verify plan outcome logging works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Change to temp directory for test
            import os
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)

                record = log_plan_vs_outcome(
                    plan_id="test_plan_123",
                    summary="Test strategy execution",
                    ev_plan=0.15,
                    ev_realized=0.12,
                    mdd=3.5,
                    hedge_effect={"var_reduction": 0.2},
                    issues=["minor_slippage"],
                    lessons=["reduce_size_in_low_liquidity"],
                )

                assert record["plan_id"] == "test_plan_123"
                assert record["ev_plan"] == 0.15
                assert record["ev_realized"] == 0.12
                assert record["type"] == "plan_vs_outcome"

                # Check file was created
                log_file = Path("runs/memory/plan_vs_outcome.jsonl")
                assert log_file.exists(), "Log file should be created"

                print(f"✓ Plan outcome logged: {record['plan_id']}")
                print(f"  EV: {record['ev_plan']:.2f} → {record['ev_realized']:.2f}")
                print(f"  MDD: {record['mdd']:.1f}%")

            finally:
                os.chdir(original_cwd)

    def test_load_recent_plan_outcomes(self):
        """✓ Verify loading recent plan outcomes works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import os
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)

                # Log some outcomes
                for i in range(3):
                    log_plan_vs_outcome(
                        plan_id=f"plan_{i}",
                        summary=f"Test plan {i}",
                        ev_plan=0.1 + i * 0.05,
                        ev_realized=0.08 + i * 0.04,
                        mdd=2.0 + i,
                    )

                # Load them back
                outcomes = load_recent_plan_outcomes(limit=5, mark_accessed=False)

                assert len(outcomes) == 3, "Should load all 3 outcomes"

                # Should be sorted by timestamp (most recent first)
                assert outcomes[0]["plan_id"] == "plan_2"
                assert outcomes[1]["plan_id"] == "plan_1"
                assert outcomes[2]["plan_id"] == "plan_0"

                print(f"✓ Loaded {len(outcomes)} recent plan outcomes")
                for o in outcomes:
                    print(f"  {o['plan_id']}: EV {o['ev_plan']:.2f} → {o['ev_realized']:.2f}")

            finally:
                os.chdir(original_cwd)

    def test_hedge_plan_structure(self):
        """✓ Verify HedgePlan dataclass works correctly."""
        hedge = HedgePlan(
            hedge_type="beta",
            instrument="ETF",
            ratio_or_target_beta=0.5,
            trigger_rules={"if_confidence_below": 0.6},
            fallback="reduce_size",
        )

        assert hedge.hedge_type == "beta"
        assert hedge.instrument == "ETF"
        assert hedge.ratio_or_target_beta == 0.5

        # Test to_dict
        d = hedge.to_dict()
        assert d["hedge_type"] == "beta"
        assert d["trigger_rules"]["if_confidence_below"] == 0.6

        print(f"✓ HedgePlan structure validated")
        print(f"  Type: {hedge.hedge_type}, Instrument: {hedge.instrument}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
