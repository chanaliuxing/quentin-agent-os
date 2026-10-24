from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class ExpectedStateTemplate:
    situation_id: str
    expected_markers: List[str]
    fallback_paths: List[str]
    stats: Dict[str, Any]

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "type": "EXPECTED_STATE_TEMPLATE",
            "situation_id": self.situation_id,
            "expected_markers": list(self.expected_markers or []),
            "fallback_paths": list(self.fallback_paths or []),
            "stats": dict(self.stats or {}),
        }


def build_expected_state_templates(
    *,
    records: Iterable[Any],
    max_markers: int = 6,
    min_observations: int = 1,
    min_success_rate: float = 0.0,
) -> List[ExpectedStateTemplate]:
    """
    v0 builder: produce conservative expected-state templates per situation.

    This is intentionally minimal until we have reliable observed markers (UI/DOM/etc).
    Uses the session delta metadata as a proxy signal.
    """
    max_m = max(0, min(20, int(max_markers or 0)))
    if max_m <= 0:
        return []

    seen: Dict[str, Dict[str, Any]] = {}
    for r in records:
        md = getattr(r, "metadata", None) or {}
        if not isinstance(md, dict):
            continue
        situation_id = str(md.get("situation_id") or "").strip()
        if not situation_id:
            continue
        item = seen.setdefault(
            situation_id,
            {
                "observations": 0,
                "successes": 0,
                "fallback_skills": set(),
            },
        )
        item["observations"] += 1
        if bool(md.get("exec_success")):
            item["successes"] += 1
        skills = md.get("executed_skill_ids")
        if isinstance(skills, list):
            for sid in skills:
                s = str(sid or "").strip()
                if s:
                    item["fallback_skills"].add(s)

    min_obs = max(1, int(min_observations or 1))
    min_sr = max(0.0, min(1.0, float(min_success_rate or 0.0)))
    out: List[ExpectedStateTemplate] = []
    for situation_id, stats in sorted(seen.items(), key=lambda kv: kv[0]):
        obs = int(stats.get("observations") or 0)
        succ = int(stats.get("successes") or 0)
        success_rate = (succ / float(obs)) if obs > 0 else 0.0
        if obs < min_obs:
            continue
        if float(success_rate) < min_sr:
            continue

        markers = [
            "exec_success:true",
            f"situation:{situation_id}",
        ][:max_m]
        fallback = sorted(list(stats.get("fallback_skills") or set()))[:5]
        out.append(
            ExpectedStateTemplate(
                situation_id=situation_id,
                expected_markers=markers,
                fallback_paths=fallback,
                stats={
                    "observations": obs,
                    "successes": succ,
                    "success_rate": float(success_rate),
                },
            )
        )
    return out
