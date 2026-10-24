# P8 Long Horizon Evolution Guide

## Roadmap-driven Evolution
Autonomous evolution is now guided by a `RoadmapManager`. Tasks that align with active milestones (e.g., "M2: Scale to 100 nodes") receive higher priority scores.

## Prioritization Logic
`Score = (Impact * Roadmap_Alignment) / Risk`

This ensures the system doesn't just chase small gains but works towards long-term organizational goals.
