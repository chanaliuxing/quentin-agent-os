from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Any, Dict, Optional

from quentin.llm.datastore import ModelPerformanceDataStore
from quentin.llm.ollama_client import OllamaLLMClient


@dataclass
class RoutingWeights:
    success: float = 1.0
    latency: float = -0.3
    cost: float = -0.5


class DataDrivenModelRouter:
    """
    Data-driven router (epsilon-greedy).

    Kept as an optional router implementation; the canonical router surface lives in
    `quentin.routing.model_router.ModelRouter`.
    """

    def __init__(
        self,
        datastore: ModelPerformanceDataStore,
        llm_clients: Dict[str, OllamaLLMClient],
        epsilon: float = 0.1,
        weights: Optional[RoutingWeights] = None,
        model_priors: Optional[Dict[str, Dict[str, float]]] = None,
    ):
        self.datastore = datastore
        self.llm_clients = llm_clients
        self.epsilon = epsilon
        self.weights = weights or RoutingWeights()
        self.model_priors = model_priors or {}

    def choose_model(self, task_domain: Optional[str] = None) -> str:
        if random.random() < self.epsilon:
            return random.choice(list(self.llm_clients.keys()))

        best_model: Optional[str] = None
        best_score = float("-inf")
        for model_name in self.llm_clients.keys():
            score = self._score_model(model_name=model_name, task_domain=task_domain)
            if score > best_score:
                best_score = score
                best_model = model_name
        return best_model if best_model else random.choice(list(self.llm_clients.keys()))

    def _score_model(self, *, model_name: str, task_domain: Optional[str]) -> float:
        stats = self.datastore.get_stats(model_name, task_domain)
        priors = self.model_priors.get(model_name, {})

        success_rate = stats.get("success_rate") or priors.get("success_rate") or priors.get("quality")
        if success_rate is None:
            success_rate = 0.5
        latency = stats.get("avg_latency_sec") or priors.get("latency_sec")
        cost = stats.get("avg_cost")
        if cost is None:
            cost = priors.get("cost") or priors.get("cost_per_call")

        score = (
            self.weights.success * float(success_rate)
            + (self.weights.latency * float(latency) if latency is not None else 0.0)
            + (self.weights.cost * float(cost) if cost is not None else 0.0)
        )
        return score

    async def run_task(self, goal: str, context: Dict[str, Any]) -> Dict[str, Any]:
        task_domain = context.get("domain")
        model_name = self.choose_model(task_domain)
        client = self.llm_clients[model_name]

        prompt = f"Goal: {goal}\nContext: {json.dumps(context)}"
        import time

        start_time = time.time()
        try:
            output = await client.complete(prompt)
            latency_sec = time.time() - start_time
            cost_prior = (
                context.get("estimated_cost")
                or (self.model_priors.get(model_name, {}) or {}).get("cost")
                or 0.0
            )
            cost = float(cost_prior)

            self.datastore.record_performance(
                model_name=model_name,
                task_domain=task_domain,
                success=True,
                latency_sec=latency_sec,
                cost=cost,
            )
            return {"raw_output": output, "model_name": model_name}
        except Exception as e:  # noqa: BLE001
            latency_sec = time.time() - start_time
            self.datastore.record_performance(
                model_name=model_name,
                task_domain=task_domain,
                success=False,
                latency_sec=latency_sec,
                cost=0.0,
            )
            raise e

