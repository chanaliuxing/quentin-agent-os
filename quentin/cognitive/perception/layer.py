from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from quentin.cognitive.perception.schemas import AttentionPack, ExpectedState, PerceptionSnapshot, SituationAssessment
from quentin.cognitive.perception.situation_classifier import RuleBasedSituationClassifier, SituationClassifier
from quentin.cognitive.perception.attention_filter import HeuristicAttentionFilter, AttentionFilter
from quentin.cognitive.perception.expectation_engine import TemplateExpectationEngine, ExpectationEngine
from quentin.cognitive.perception.situation_skill_router import SituationSkillRouter
from quentin.cognitive.perception.policy_provider import PolicyPerceptionProvider
from quentin.cognitive.perception.file_provider import FilePerceptionProvider
from quentin.cognitive.perception.media_provider import MediaPerceptionProvider
from quentin.cognitive.perception.link_provider import LinkPerceptionProvider
from quentin.cognitive.perception.ui_provider import UIPerceptionProvider
from pathlib import Path


@dataclass
class PerceptionContextConfig:
    enable_situation_classifier: bool = True
    enable_attention_filter: bool = True
    enable_expectation_engine: bool = False
    enable_situation_to_skill: bool = False
    enable_file_perception: bool = True
    enable_media_perception: bool = True
    enable_link_perception: bool = True
    enable_ui_perception: bool = True
    attention_target_ratio: float = 0.15
    debug_use_full_context: bool = False


class PerceptionContextLayer:
    """
    Perception & Context Layer (v1):
    - situation classification
    - attention gating
    - advanced providers: Policy, File, Media, Link
    """

    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        config: Optional[PerceptionContextConfig] = None,
        classifier: Optional[SituationClassifier] = None,
        attention_filter: Optional[AttentionFilter] = None,
        expectation_engine: Optional[ExpectationEngine] = None,
        situation_skill_router: Optional[SituationSkillRouter] = None,
        model_router: Optional[Any] = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.config = config or PerceptionContextConfig()
        self.classifier = classifier or RuleBasedSituationClassifier()
        self.attention_filter = attention_filter or HeuristicAttentionFilter(target_ratio=float(self.config.attention_target_ratio))
        self.expectation_engine = expectation_engine or TemplateExpectationEngine()
        self.situation_skill_router = situation_skill_router
        self.model_router = model_router

        # Initialize providers
        self.policy_provider = PolicyPerceptionProvider(self.repo_root)
        self.file_provider = FilePerceptionProvider(self.repo_root)
        self.media_provider = MediaPerceptionProvider(self.repo_root, self.model_router) if self.model_router else None
        self.link_provider = LinkPerceptionProvider(self.model_router) if self.model_router else None
        self.ui_provider = UIPerceptionProvider()
        
        # P5: Surgery Fifty - Invalidation Listener (OpenClaw Parity)
        from quentin.infra.events.environment_bus import environment_bus
        environment_bus.subscribe("file_modified", self._on_environment_change)
        self._last_hashes: Dict[str, str] = {}

    def _on_environment_change(self, payload: Dict[str, Any]):
        """
        Physically invalidates all caches when any part of the environment changes.
        Supports merged payloads from debounced events.
        """
        paths = payload.get("paths", [payload.get("path")])
        logger.info(f"PerceptionLayer: Invalidating all caches due to {len(paths)} file changes (Debounced).")
        self._last_hashes.clear() # Nuclear invalidation for consistency

    def build_snapshot(self, *, ctx: Dict[str, Any]) -> PerceptionSnapshot:
        situation = SituationAssessment(situation_id="unknown_text_only", confidence=0.0, features={})
        if self.config.enable_situation_classifier:
            situation = self.classifier.classify(ctx=ctx)

        attention: Optional[AttentionPack] = None
        if self.config.enable_attention_filter:
            attention = self.attention_filter.build_attention(ctx=ctx, situation=situation)

        expected: Optional[ExpectedState] = None
        if self.config.enable_expectation_engine:
            # v0: expectation is primarily executor-time; leave a tiny placeholder here.
            expected = ExpectedState(situation_id=situation.situation_id, markers=[], template_id=None, fallback_skills=[])

        # P5: Aggregated Perception (OpenClaw parity)
        perception_data: Dict[str, Any] = {
            "system_policies": self.policy_provider.get_policy_summary()
        }
        
        if self.config.enable_file_perception:
            perception_data.update(self.file_provider.get_perception_data(ctx))
            
        if self.config.enable_media_perception and self.media_provider:
            perception_data.update(self.media_provider.get_perception_data(ctx))
            
        if self.config.enable_link_perception and self.link_provider:
            perception_data.update(self.link_provider.get_perception_data(ctx))
            
        if self.config.enable_ui_perception:
            perception_data.update(self.ui_provider.get_perception_data(ctx))

        # P5: Surgery Forty-two - Hash-based Filtering (OpenClaw Parity)
        from quentin.cognitive.perception.hasher import PerceptionHasher
        current_hash = PerceptionHasher.compute_ui_hash(perception_data)
        
        # Track hash in session context if available
        session_id = ctx.get("session_id", "default")
        if not hasattr(self, "_last_hashes"):
            self._last_hashes: Dict[str, str] = {}
            
        last_hash = self._last_hashes.get(session_id)
        
        is_unchanged = False
        if last_hash == current_hash and not ctx.get("force_refresh"):
            logger.info(f"PerceptionLayer: Context for session {session_id} is UNCHANGED. Filtering output.")
            is_unchanged = True
            # Return minimal semantic data to avoid token waste
            perception_data = {
                "status": "unchanged",
                "summary": "UI and file state remain identical to previous snapshot.",
                "last_observed_hash": current_hash
            }
        else:
            self._last_hashes[session_id] = current_hash

        return PerceptionSnapshot(
            situation=situation, 
            attention=attention, 
            expected_state=expected,
            metadata=perception_data
        )

