from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple


@dataclass(frozen=True)
class SituationProfile:
    situation_id: str
    recommended_skills: List[str]
    stats: Dict[str, Any]

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "type": "SITUATION_PROFILE",
            "situation_id": self.situation_id,
            "recommended_skills": list(self.recommended_skills or []),
            "stats": dict(self.stats or {}),
        }


def build_situation_profiles(
    *,
    records: Iterable[Any],
    top_k_skills: int = 3,
    min_observations: int = 1,
    min_success_rate: float = 0.0,
) -> List[SituationProfile]:
    """
    v0 builder: derive situation->skill recommendations from STS session deltas.

    Expected record metadata (best-effort):
    - situation_id: str
    - executed_skill_ids: list[str]
    - exec_success: bool
    """
    top_k = max(0, min(10, int(top_k_skills or 0)))
    if top_k <= 0:
        return []

    totals: Dict[str, int] = defaultdict(int)
    successes: Dict[str, int] = defaultdict(int)
    skill_totals: Dict[Tuple[str, str], int] = defaultdict(int)
    skill_successes: Dict[Tuple[str, str], int] = defaultdict(int)

    for r in records:
        md = getattr(r, "metadata", None) or {}
        if not isinstance(md, dict):
            continue
        situation_id = str(md.get("situation_id") or "").strip()
        if not situation_id:
            continue

        totals[situation_id] += 1
        ok = bool(md.get("exec_success"))
        if ok:
            successes[situation_id] += 1

        skill_ids = md.get("executed_skill_ids")
        if not isinstance(skill_ids, list):
            continue
        for sid in skill_ids:
            skill_id = str(sid or "").strip()
            if not skill_id:
                continue
            skill_totals[(situation_id, skill_id)] += 1
            if ok:
                skill_successes[(situation_id, skill_id)] += 1

    min_obs = max(1, int(min_observations or 1))
    min_sr = max(0.0, min(1.0, float(min_success_rate or 0.0)))
    profiles: List[SituationProfile] = []
    for situation_id, count in sorted(totals.items(), key=lambda kv: kv[0]):
        ok_count = int(successes.get(situation_id, 0))
        success_rate = (ok_count / float(count)) if count > 0 else 0.0
        if int(count) < min_obs:
            continue
        if float(success_rate) < min_sr:
            continue

        # Score skills by success_count then total_count.
        scored: List[Tuple[int, int, str]] = []
        for (sid, skill_id), t in skill_totals.items():
            if sid != situation_id:
                continue
            s = int(skill_successes.get((sid, skill_id), 0))
            scored.append((s, t, skill_id))
        scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
        recommended = [skill_id for _, __, skill_id in scored[:top_k]]

        profiles.append(
            SituationProfile(
                situation_id=situation_id,
                recommended_skills=recommended,
                stats={
                    "observations": int(count),
                    "successes": int(ok_count),
                    "success_rate": float(success_rate),
                },
            )
        )
    return profiles
