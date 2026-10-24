from quentin.routing.model_router import ModelRouter as CoreModelRouter
from quentin.routing.model_router import ModelRouteRequest
from quentin.llm.types import LLMConfig
from quentin.router.metrics import RouteFeedback  # legacy alias

# Compatibility layer for the legacy `quentin.llm` API surface.
# New code should use `quentin.routing.model_router.ModelRouter` directly.

class ModelRouter(CoreModelRouter):
    def route(
        self,
        *,
        mode: str,
        task_type: str = "generic",
    ) -> LLMConfig:
        # Construct a ModelRouteRequest from old interface
        request = ModelRouteRequest(task_type=task_type, domain=mode)  # simplified mapping
        
        # Call the unified router
        decision = super().route(request)
        
        # Convert ModelRouteDecision back to old LLMConfig
        return LLMConfig(
            provider=decision.provider,
            model=decision.model_id,
            role=decision.reason, # Use reason as role for backward compat
        )

    def record_feedback(self, fb: RouteFeedback) -> None:
        # Deprecated: legacy feedback objects don't include enough context to reconstruct a full
        # (request, decision) pair. Prefer `ModelRouter.record_feedback(request=..., decision=..., outcome=...)`.
        _ = fb
        return
