# P4 Autonomy Governance Runbook

## Overview
This runbook defines the procedures for managing autonomous evolution proposals in Project Taylor.

## Proposal Lifecycle
1. **Generation**: `ProposalEngine` analyzes metrics and gaps to generate structured proposals.
2. **Evaluation**: `ProposalGate` checks proposals against safety, correctness, and performance criteria.
3. **Sandbox Application**: Approved proposals are applied to a sandbox environment for observation.
4. **Promotion**: Successful sandbox experiments are promoted to production via the `LifecycleManager`.

## Handling Rejected Proposals
- Check `EvaluationResult` reason.
- If rejected by `SafetyGate`, ensure the proposal is not targeting protected paths.
- If rejected for `Correctness`, verify the proposed changes and rollback plan.

## Manual Override
- High-risk proposals are automatically rejected by the gate and require manual review.
- Use the `/capabilities/{id}/promote` API to manually approve after review.
