from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Tuple
import json
import logging
import statistics as stats

logger = logging.getLogger(__name__)


@dataclass
class RouterStatRecord:
    mode: str
    task_type: str
    model: str
    provider: str
    latency_ms: float
    success: bool
    score: float

    @classmethod
    def from_dict(cls, d: Dict) -> "RouterStatRecord":
        return cls(
            mode=str(d.get("mode", "")).lower(),
            task_type=str(d.get("task_type", "generic")).lower(),
            model=str(d.get("model", "")),
            provider=str(d.get("provider", "")),
            latency_ms=float(d.get("latency_ms", 0.0)),
            success=bool(d.get("success", True)),
            score=float(d.get("score", 0.0)),
        )


@dataclass
class RouterPolicy:
    """
    对于某个 (mode, task_type) 的推荐策略：
    - model / provider : 推荐用哪个模型
    - metric           : 优化使用的指标
    - score            : 聚合后的有效得分（score - λ * latency）
    - raw              : 原始 success_rate / avg_latency / avg_score
    """

    mode: str
    task_type: str
    model: str
    provider: str
    metric: str
    score: float
    success_rate: float
    avg_latency_ms: float
    avg_model_score: float

    def to_dict(self) -> Dict:
        return asdict(self)


class ModelRouterOptimizer:
    """
    从 data/model_router_stats.jsonl 中采样数据，给每个 (mode, task_type) 选出最优模型。

    v1 策略：
    - 按三项统计：
        - success_rate
        - avg_latency_ms
        - avg_model_score  (如果有的话，否则用 success)
    - 综合评价函数：
        effective_score = avg_model_score * success_rate - weight_latency * (avg_latency_ms / 1000)
    - 对每个 (mode, task_type) 选出 effective_score 最大的 model。
    """

    def __init__(
        self,
        *,
        stats_path: str | Path = "data/model_router_stats.jsonl",
        rules_path: str | Path = "config/model_router_rules.json",
        weight_latency: float = 0.1,
    ) -> None:
        self.stats_path = Path(stats_path)
        self.rules_path = Path(rules_path)
        self.weight_latency = weight_latency

    def optimize(self) -> Dict[str, RouterPolicy]:
        records = self._load_records()
        if not records:
            logger.warning("ModelRouterOptimizer: no router stats found; nothing to optimize.")
            return {}

        # 分组：((mode, task_type, model, provider) -> [records])
        by_key: Dict[Tuple[str, str, str, str], List[RouterStatRecord]] = {}
        for r in records:
            key = (r.mode, r.task_type, r.model, r.provider)
            by_key.setdefault(key, []).append(r)

        # 对每个 (mode, task_type) 选模型
        best_policies: Dict[str, RouterPolicy] = {}
        # key2: (mode, task_type) -> [(policy, effective_score)]
        group_by_route: Dict[Tuple[str, str], List[RouterPolicy]] = {}

        for (mode, task_type, model, provider), rs in by_key.items():
            if not rs:
                continue
            success_rate = stats.mean(1.0 if r.success else 0.0 for r in rs)
            latencies = [max(1.0, r.latency_ms) for r in rs]
            avg_latency = stats.mean(latencies)
            if all(r.score == 0.0 for r in rs):
                avg_score = success_rate  # 没有显式 score 就用 success_rate
                metric = "success_rate"
            else:
                avg_score = stats.mean(r.score for r in rs)
                metric = "score"

            effective_score = avg_score * success_rate - self.weight_latency * (avg_latency / 1000.0)

            policy = RouterPolicy(
                mode=mode,
                task_type=task_type,
                model=model,
                provider=provider,
                metric=metric,
                score=effective_score,
                success_rate=success_rate,
                avg_latency_ms=avg_latency,
                avg_model_score=avg_score,
            )

            key_route = (mode, task_type)
            group_by_route.setdefault(key_route, []).append(policy)

        for key_route, policies in group_by_route.items():
            if not policies:
                continue
            # 选择 effective_score 最大的 policy
            policies.sort(key=lambda p: p.score, reverse=True)
            best = policies[0]
            route_key = self._route_key(best.mode, best.task_type)
            best_policies[route_key] = best

        # 写入规则文件
        data = {k: p.to_dict() for k, p in best_policies.items()}
        self.rules_path.parent.mkdir(parents=True, exist_ok=True)
        self.rules_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        return best_policies

    # ---------- 内部 ----------

    def _load_records(self) -> List[RouterStatRecord]:
        if not self.stats_path.exists():
            return []
        records: List[RouterStatRecord] = []
        try:
            with self.stats_path.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    d = json.loads(line)
                    records.append(RouterStatRecord.from_dict(d))
        except Exception:
            logger.exception("ModelRouterOptimizer._load_records: failed to read %s", self.stats_path)
        return records

    @staticmethod
    def _route_key(mode: str, task_type: str) -> str:
        return f"{mode}::{task_type}"
