# quentin/sleep/loop_impl.py
from __future__ import annotations

import logging
import asyncio
import os
from dataclasses import dataclass, asdict
from datetime import timedelta
from typing import Dict, Any, Optional
import json
import uuid
from pathlib import Path
import time

from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryTier
from quentin.memory.processors.cluster import cluster_records
from quentin.memory.processors.summarizer import Summarizer, Insight
from quentin.memory.processors.dedup import Deduplicator
from quentin.utils.time import now_utc
from meta_agent.council import CouncilManager, CouncilConfig
from quentin.runtime.session_write_lock import acquire_session_write_lock
from quentin.traces.core import TraceRecorder, TraceEventType, new_trace_event

logger = logging.getLogger(__name__)

@dataclass
class SleepLoopConfig:
    cluster_sim_threshold: float = 0.85
    dedup_sim_threshold: float = 0.92
    max_sts_candidates: int = 200
    sts_min_age_hours: float = 0.0
    enable_llm_consolidation: bool = True
    enable_consolidation_council: bool = True
    # Blueprint v3 outputs (training pairs + skill candidates)
    max_records_per_run: int = 200
    training_pairs_path: str = "data/training_pairs/training_pairs.jsonl"
    skill_candidates_path: str = "data/training_pairs/skill_candidates.jsonl"
    # Scheduling / budget caps (v1)
    max_duration_ms: int = 60_000
    max_tokens_est: int = 200_000
    # A/B-able policy knob (v1)
    consolidation_policy: str = "cluster"  # "cluster" | "simple"

@dataclass
class SleepLoopReport:
    processed_sts: int = 0
    generated_clusters: int = 0
    mts_created: int = 0
    mts_merged: int = 0
    sts_archived: int = 0
    errors: int = 0
    # v3 outputs
    consolidated_traces: int = 0
    procedural_memories: int = 0
    training_pairs: int = 0
    skill_candidates: int = 0
    gist_memories: int = 0
    duration_ms: int = 0
    tokens_est: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class SleepLoop:
    """
    Phase 2 Intelligent SleepLoop:
    1. Fetch STS candidates (recent memories)
    2. Cluster by vector similarity
    3. Distill clusters into insights (LLM)
    4. Dedup against MTS (Merge or Insert)
    5. Update relations (crystallized_from)
    6. Archive original STS
    """

    def __init__(
        self,
        memory_fabric: Optional[MemoryFabric] = None,
        config: Optional[SleepLoopConfig] = None,
        council: Any = None,
        trace_recorder: Optional[TraceRecorder] = None,
        skill_library: Any = None,
        repo_root: str | Path | None = None,
        **_ignored: Any,
    ) -> None:
        # `repo_root` is accepted for backwards compatibility with older bootstrap code.
        self.repo_root = Path(repo_root or ".").resolve()
        self.fabric = memory_fabric or MemoryFabric()
        self.config = config or SleepLoopConfig()
        self.council = council
        self.trace_recorder = trace_recorder
        self.skill_library = skill_library
        
        # Initialize processors
        self.summarizer = Summarizer() 
        self.deduplicator = Deduplicator(self.fabric, threshold=self.config.dedup_sim_threshold)
        self.consolidation_council = None
        if self.config.enable_consolidation_council:
            self.consolidation_council = CouncilManager(config=CouncilConfig(max_rounds=1))

    async def run_once(self) -> SleepLoopReport:
        logger.info("SleepLoop: Starting intelligent consolidation cycle...")
        started = time.perf_counter()
        result = SleepLoopReport()
        
        # 1. Fetch Candidates (STS)
        # Assuming Phase 1 has populated vectors.
        limit = min(self.config.max_sts_candidates, self.config.max_records_per_run or self.config.max_sts_candidates)
        candidates = self.fabric.get_sts_for_consolidation(limit=limit)
        
        # Filter by age (don't consolidate thoughts that are too fresh)
        cutoff = now_utc() - timedelta(hours=self.config.sts_min_age_hours)
        candidates = [c for c in candidates if c.created_at <= cutoff]
        
        if not candidates:
            logger.info("SleepLoop: No eligible STS candidates found.")
            return result

        result.processed_sts = len(candidates)

        # v3 minimal outputs: if traces exist, write a single running summary + emit a small training pair + skill candidate
        try:
            await self._emit_v3_outputs(candidates, result)
        except Exception:
            logger.exception("SleepLoop: failed to emit v3 outputs")
            result.errors += 1
        
        # 2. Cluster (policy switch)
        policy = str(self.config.consolidation_policy or "cluster").strip().lower()
        if policy == "simple":
            # One bucket, best-effort center vector.
            vecs = [r.vector for r in candidates if getattr(r, "vector", None)]
            center = []
            if vecs:
                dim = len(vecs[0])
                center = [0.0] * dim
                for v in vecs:
                    if not v:
                        continue
                    for i in range(min(dim, len(v))):
                        center[i] += float(v[i])
                center = [x / max(1, len(vecs)) for x in center]
            clusters = [type("Cluster", (), {"center_vector": center, "records": candidates})()]
        else:
            clusters = cluster_records(candidates, similarity_threshold=self.config.cluster_sim_threshold)
        result.generated_clusters = len(clusters)
        logger.info(f"SleepLoop: Formed {len(clusters)} clusters from {len(candidates)} records.")

        # 3. Process Clusters
        for cluster in clusters:
            # Budget/time cap
            if self.config.max_duration_ms and int((time.perf_counter() - started) * 1000) > int(self.config.max_duration_ms):
                logger.warning("SleepLoop: max_duration_ms reached; stopping early")
                break
            if self.config.max_tokens_est and result.tokens_est > int(self.config.max_tokens_est):
                logger.warning("SleepLoop: max_tokens_est reached; stopping early")
                break
            try:
                await self._process_cluster(cluster, result)
            except Exception as e:
                logger.error(f"Error processing cluster: {e}", exc_info=True)
                result.errors += 1

        result.duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info(f"SleepLoop: Cycle finished. {result.to_dict()}")
        return result

    async def _emit_v3_outputs(self, records, stats: SleepLoopReport) -> None:
        if not records:
            return

        trace_texts = [r.content for r in records if getattr(r, "content", None)]
        if not trace_texts:
            return

        question = "Summarize the following recent execution traces into a concise memory that is reusable later."
        context = {"records": [getattr(r, "to_dict", lambda: {"id": r.id, "content": r.content})() for r in records]}
        summary = None

        if self.council is not None and hasattr(self.council, "ask_text"):
            try:
                summary = await self.council.ask_text("sleep_loop", question, context)
            except Exception:
                summary = None

        if not summary:
            # Rule-based fallback
            summary = "summary of traces\n\n" + "\n".join([t[:200] for t in trace_texts[:10]])

        try:
            from quentin.llm.context_budget import estimate_tokens

            stats.tokens_est += int(estimate_tokens(str(summary)))
        except Exception:
            pass

        # Write consolidated summary as MTS (or LTS if you later decide)
        self.fabric.write_consolidated_summary(
            summary_content=str(summary),
            source="sleep_loop",
            from_records=records,
            target_tier=MemoryTier.MTS,
            importance=0.7,
            tags=["sleep", "summary"],
            metadata={"kind": "running_summary"},
        )
        stats.consolidated_traces += 1

        # v3.1+: Gist memory (v0 heuristic extraction)
        try:
            from quentin.memory.processors.gist_extractor import extract_gist_rules
            from quentin.memory.kinds import KIND_GIST_MEMORY

            rules = extract_gist_rules(trace_texts, max_rules=8)
            if rules:
                content = "GIST:\n" + "\n".join([f"- {r}" for r in rules])
                self.fabric.remember_atomic(
                    content=content,
                    source="sleep_loop",
                    tier=MemoryTier.MTS,
                    domain="cross",
                    importance=0.6,
                    tags=["sleep", "gist"],
                    metadata={
                        "type": "GIST_MEMORY",
                        "domain": "cross",
                        "gist": rules,
                        "evidence_refs": [],
                    },
                    kind=KIND_GIST_MEMORY,
                )
                stats.gist_memories += 1
        except Exception:
            logger.exception("SleepLoop: failed to write gist memory")
            stats.errors += 1

        # v3.1+: Situation profiles + expected state templates (v0, metadata-driven)
        try:
            from quentin.memory.processors.expected_state_template_builder import build_expected_state_templates
            from quentin.memory.processors.situation_profile_builder import build_situation_profiles
            from quentin.memory.expected_state_template import ExpectedStateTemplateEntry
            from quentin.memory.situation_profile import SituationProfileEntry

            try:
                profile_min_obs = int(os.getenv("QUENTIN_SLEEP_PROFILE_MIN_OBSERVATIONS", "2") or 2)
            except Exception:
                profile_min_obs = 2
            try:
                profile_min_success_rate = float(os.getenv("QUENTIN_SLEEP_PROFILE_MIN_SUCCESS_RATE", "0.3") or 0.3)
            except Exception:
                profile_min_success_rate = 0.3
            try:
                template_min_obs = int(os.getenv("QUENTIN_SLEEP_TEMPLATE_MIN_OBSERVATIONS", "2") or 2)
            except Exception:
                template_min_obs = 2
            try:
                template_min_success_rate = float(os.getenv("QUENTIN_SLEEP_TEMPLATE_MIN_SUCCESS_RATE", "0.2") or 0.2)
            except Exception:
                template_min_success_rate = 0.2

            profiles = build_situation_profiles(
                records=records,
                top_k_skills=3,
                min_observations=profile_min_obs,
                min_success_rate=profile_min_success_rate,
            )
            for p in profiles:
                entry = SituationProfileEntry(
                    situation_id=p.situation_id,
                    signals=[],
                    recommended_skills=list(p.recommended_skills or []),
                    stats=dict(p.stats or {}),
                )
                rec = entry.to_memory_record(tier=MemoryTier.MTS)
                try:
                    existing = self.fabric.store.get(rec.id)
                except Exception:
                    existing = None
                if existing is None:
                    self.fabric.store.add(rec)
                else:
                    rec.created_at = getattr(existing, "created_at", rec.created_at)
                    self.fabric.store.update(rec)

            templates = build_expected_state_templates(
                records=records,
                max_markers=6,
                min_observations=template_min_obs,
                min_success_rate=template_min_success_rate,
            )
            for t in templates:
                entry = ExpectedStateTemplateEntry(
                    situation_id=t.situation_id,
                    expected_markers=list(t.expected_markers or []),
                    fallback_paths=list(t.fallback_paths or []),
                    stats=dict(t.stats or {}),
                )
                rec = entry.to_memory_record(tier=MemoryTier.MTS)
                try:
                    existing = self.fabric.store.get(rec.id)
                except Exception:
                    existing = None
                if existing is None:
                    self.fabric.store.add(rec)
                else:
                    rec.created_at = getattr(existing, "created_at", rec.created_at)
                    self.fabric.store.update(rec)
        except Exception:
            logger.exception("SleepLoop: failed to write situation profiles / expected templates")
            stats.errors += 1

        # Emit training pair + skill candidate (JSONL)
        tp_path = Path(self.config.training_pairs_path)
        tp_path.parent.mkdir(parents=True, exist_ok=True)
        sc_path = Path(self.config.skill_candidates_path)
        sc_path.parent.mkdir(parents=True, exist_ok=True)

        training_pair = {
            "schema_version": "v1",
            "pair_id": f"pair_{uuid.uuid4().hex}",
            "created_at": now_utc().isoformat(),
            "source": "sleep_loop",
            "input": {"traces": trace_texts[:5]},
            "output": {"summary": str(summary)},
            "labels": {"kind": "trace_to_summary"},
            "meta": {"record_ids": [r.id for r in records[:50]]},
        }
        skill_candidate = {
            "schema_version": "v1",
            "candidate_id": f"skill_{uuid.uuid4().hex}",
            "created_at": now_utc().isoformat(),
            "source": "sleep_loop",
            "title": "Summarize execution traces",
            "steps": [
                "Collect recent trace-like memories",
                "Summarize into a reusable memory",
                "Store as MTS with provenance",
            ],
            "meta": {"record_ids": [r.id for r in records[:50]]},
        }

        # Procedural memory (v1): store a reusable SOP derived from the candidate steps.
        try:
            sop = "SOP: Summarize execution traces\n\n" + "\n".join(
                [f"{i+1}. {s}" for i, s in enumerate(skill_candidate.get('steps') or [])]
            )
            self.fabric.remember_atomic(
                content=sop,
                source="sleep_loop",
                tier=MemoryTier.MTS,
                domain="cross",
                importance=0.6,
                tags=["sleep", "procedural", "sop"],
                metadata={"candidate_id": skill_candidate["candidate_id"], "record_ids": [r.id for r in records[:50]]},
                kind="procedural",
            )
            stats.procedural_memories += 1
        except Exception:
            logger.exception("SleepLoop: failed to write procedural memory")

        lock = acquire_session_write_lock(session_file=tp_path)
        try:
            with tp_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(training_pair, ensure_ascii=False) + "\n")
        finally:
            lock["release"]()
        stats.training_pairs += 1

        lock = acquire_session_write_lock(session_file=sc_path)
        try:
            with sc_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(skill_candidate, ensure_ascii=False) + "\n")
        finally:
            lock["release"]()
        stats.skill_candidates += 1

        # Optional: ingest skill candidate into SkillLibrary.
        if self.skill_library is not None and hasattr(self.skill_library, "register_skill"):
            try:
                plan_steps = [
                    {"description": s, "tool": "noop", "params": {"source": "sleep_loop_candidate"}}
                    for s in (skill_candidate.get("steps") or [])
                    if isinstance(s, str) and s.strip()
                ]
                await self.skill_library.register_skill(
                    name=str(skill_candidate.get("title") or skill_candidate.get("candidate_id")),
                    kind="procedural",
                    description="Auto-generated skill candidate from SleepLoop v3 outputs.",
                    domain="cross",
                    tags=["sleep_loop", "candidate"],
                    plan_steps=plan_steps,
                    meta={
                        "candidate_id": skill_candidate.get("candidate_id"),
                        "created_at": skill_candidate.get("created_at"),
                        "record_ids": (skill_candidate.get("meta") or {}).get("record_ids"),
                        "schema_version": skill_candidate.get("schema_version"),
                        "evaluation_status": "candidate",
                    },
                )
            except Exception:
                logger.exception("SleepLoop: failed to ingest skill candidate into SkillLibrary")

        if self.trace_recorder is not None:
            try:
                self.trace_recorder.record_event(
                    new_trace_event(
                        trace_id="sleep_loop",
                        event_type=TraceEventType.SLEEP,
                        payload={
                            "action": "v3_outputs_emitted",
                            "report": stats.to_dict(),
                            "consolidated_traces": stats.consolidated_traces,
                            "procedural_memories": stats.procedural_memories,
                            "training_pairs": stats.training_pairs,
                            "skill_candidates": stats.skill_candidates,
                        },
                    )
                )
            except Exception:
                pass

    async def _process_cluster(self, cluster, stats: SleepLoopReport):
        if not cluster.records:
            return

        # 3a. Distill (Summarize)
        insight: Optional[Insight] = None
        if self.config.enable_llm_consolidation:
            insight = await self.summarizer.distill(cluster.records)
        
        if not insight:
            # Fallback: Simple concatenation
            title = f"Consolidated Memory ({len(cluster.records)} items)"
            content = "\n".join([r.content[:100] + "..." for r in cluster.records])
            insight = Insight(title=title, content=content, tags=["auto-consolidated"], relations={})

        # 3a.1 Governance check (optional)
        if self.consolidation_council:
            approved = await self._govern_insight(insight)
            if not approved:
                logger.warning("SleepLoop: consolidation council rejected insight; skipping cluster.")
                return

        # 3b. Vectorize the Insight for Dedup
        # Need to use the embedding client from fabric (Phase 1)
        insight_vector = None
        if hasattr(self.fabric, "embedding_client") and self.fabric.embedding_client:
            # Note: fabric.embedding_client is synchronous in Phase 1 design, but Summarizer is async.
            # Depending on implementation, might need to wrap in executor if blocking.
            # Here assuming direct call is fine or fast enough.
            try:
                insight_vector = self.fabric.embedding_client.embed_text(insight.content)
            except Exception as e:
                logger.warning(f"Failed to embed insight for dedup: {e}")

        # 4. Dedup Check (Against existing MTS)
        existing_mts = None
        if insight_vector:
            existing_mts = self.deduplicator.find_duplicate(insight_vector, tier=MemoryTier.MTS)

        target_record = None
        source_ids = [r.id for r in cluster.records]

        if existing_mts:
            # 5a. Merge (Semantic Update)
            logger.info(f"SleepLoop: Merging into existing MTS {existing_mts.id}")
            merged_insight = await self.summarizer.merge(existing_mts, insight)
            
            existing_mts.content = merged_insight.content
            existing_mts.updated_at = now_utc()
            
            # Relation Inference: Add 'crystallized_from' and update IDs
            for sid in source_ids:
                existing_mts.relations[f"crystallized_from:{sid}"] = 1.0
                if sid not in existing_mts.consolidated_from_ids:
                    existing_mts.consolidated_from_ids.append(sid)
            
            self.fabric.store.update(existing_mts)
            stats.mts_merged += 1
            target_record = existing_mts
        else:
            # 5b. Insert New MTS
            logger.info("SleepLoop: Creating new MTS record.")
            relations = insight.relations or {}
            for sid in source_ids:
                relations[f"crystallized_from:{sid}"] = 1.0
                
            # remember_atomic will handle embedding generation
            target_record = self.fabric.remember_atomic(
                content=insight.content,
                source="sleep_loop",
                tier=MemoryTier.MTS,
                importance=0.8,
                tags=insight.tags,
                metadata={"title": insight.title, "cluster_size": len(cluster.records)},
                vector=insight_vector, 
                relations=relations,
                kind="semantic",
                consolidated_from_ids=source_ids
            )
            stats.mts_created += 1

        # --- Phase 4: Explicit Knowledge Graph Sync ---
        if self.fabric.graph_builder and target_record:
            try:
                # Use standard crystallized_from predicate
                add_relation = getattr(self.fabric.graph_service, "add_relation", None)
                if callable(add_relation):
                    for sid in source_ids:
                        add_relation(
                            source_id=target_record.id,
                            relation="crystallized_from",
                            target_id=sid,
                            props={"weight": 1.0, "source": "sleep_loop_consolidation"}
                        )
            except Exception as e:
                logger.warning(f"SleepLoop: Graph relation sync failed for {target_record.id}: {e}")

        # 6. Archive (Decay) Original STS
        # Using decay_records to mark them as processed/archived
        self.fabric.decay_records(source_ids)
        stats.sts_archived += len(source_ids)

    async def _govern_insight(self, insight: Insight) -> bool:
        """
        Run a consolidation council to validate the generated insight.
        Returns True if approved; False otherwise (skips this cluster).
        """
        try:
            question = "Assess whether this consolidated memory is concise, faithful, and executable. Approve only if safe."
            ctx = {
                "title": insight.title,
                "content": insight.content[:4000],
                "tags": insight.tags,
            }
            outcome = self.consolidation_council.run(question, context=ctx)
            verdict = outcome.final_output.verdict
            return verdict in ("approve",)
        except Exception as e:
            logger.warning(f"Consolidation council failed, auto-approving insight: {e}")
            return True
