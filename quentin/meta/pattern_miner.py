from collections import defaultdict
from typing import List, Dict, Any, Tuple
from quentin.kernel.schemas import ExecutionSummary, SkillCandidate
from quentin.utils.time import now_utc


class PatternMiner:
    """
    极简版本的模式挖掘：
    - 输入：一组成功的 ExecutionSummary
    - 输出：一组 SkillCandidate（只是「模式描述」，不包含具体代码）
    """

    def __init__(self, min_support: int = 3, max_pattern_len: int = 10):
        self.min_support = min_support
        self.max_pattern_len = max_pattern_len

    def mine(self, summaries: List[ExecutionSummary]) -> List[SkillCandidate]:
        # 按 (domain, decisions_sequence) 分组
        buckets: Dict[Tuple[str, str], List[ExecutionSummary]] = defaultdict(list)

        for s in summaries:
            if not s.key_decisions:
                continue
            seq = s.key_decisions[: self.max_pattern_len]
            seq_text = "\n".join(seq)
            key = (s.domain, seq_text)
            buckets[key].append(s)

        candidates: List[SkillCandidate] = []
        now = now_utc()

        for (domain, seq_text), group in buckets.items():
            if len(group) < self.min_support:
                continue

            example_ids = [g.task_id for g in group[:5]]

            candidate = SkillCandidate(
                candidate_id=f"skillcand_{int(now.timestamp()*1000)}_{len(candidates)}",
                source="skill_evolution_loop",
                pattern_key=f"{domain}:{hash(seq_text)}",
                name=f"Pattern-{domain}-{len(candidates)}",
                description=(
                    f"A repeated decision pattern observed in domain '{domain}' "
                    f"from {len(group)} successful tasks."
                ),
                steps=seq_text.split("\n"),
                input_spec={"type": "generic_task", "fields": ["goal", "context"]},
                output_spec={"type": "generic_plan", "fields": ["steps"]},
                example_task_ids=example_ids,
                created_at=now,
            )
            candidates.append(candidate)

        return candidates
