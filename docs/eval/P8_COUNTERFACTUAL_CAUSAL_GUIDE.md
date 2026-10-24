# P8 Counterfactual & Causal Guide

## Causal Attribution
Every significant metric change is linked back to a `change_id`. This prevents the system from misattributing random noise to policy improvements.

## Counterfactual Simulation
Before promoting a high-risk change, the `CounterfactualRunner` simulates alternative paths to estimate the "delta" gain. If the confidence is low, the change is blocked by the `AntiRegressionGuard`.
