from __future__ import annotations

from app.models import EnergyVector


class BlameRanker:
    def rank(self, energy: EnergyVector) -> list[str]:
        seen: set[str] = set()
        ranked: list[str] = []
        for candidate in [*energy.failing_invariants, *energy.blame_candidates]:
            if candidate not in seen:
                ranked.append(candidate)
                seen.add(candidate)
        return ranked
