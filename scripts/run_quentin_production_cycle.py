from __future__ import annotations

import asyncio
import logging
import os
import uuid
from pathlib import Path
from typing import Dict, Any

from quentin.bootstrap.container import Container
from quentin.cognitive.loop import CognitiveTask
from quentin.sleep.loop_impl import SleepLoopConfig
from quentin.skills.automated_evolution import AutomatedSkillEvolution
from quentin.traces.core import TraceEventType, new_trace_event

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("production_cycle")

async def run_production_cycle():
    """
    Demonstrates the full end-to-end self-evolution closure of Project Quentin.
    """
    repo_root = Path(".").resolve()
    container = Container(repo_root=repo_root)
    
    logger.info("=== STARTING PRODUCTION-READY SELF-EVOLUTION CYCLE ===")
    
    # 1. Initialize Canonical Components
    cog_loop = container.cognitive_loop
    sleep_loop = container.sleep_loop
    immune_loop = container.immune_loop
    research_api = container.observability_service # Using this as a proxy for research data
    
    # 2. RUN COGNITIVE LOOP (Task Execution)
    logger.info("Step 1: Running Cognitive Loop...")
    task = CognitiveTask(
        input_text="Evaluate the current system's engineering maturity and suggest one improvement.",
        domain="core",
        metadata={"session_id": f"prod_cycle_{uuid.uuid4().hex[:4]}"}
    )
    # Call the internal async method directly to avoid nested asyncio.run
    cog_result = await cog_loop._run_goal_internal(task)
    logger.info(f"Cognitive Loop Finished. Done: {cog_result.done}, Confidence: {cog_result.done_confidence}")

    # 3. RUN SLEEP LOOP (Memory Consolidation & v3 Outputs)
    logger.info("Step 2: Running Sleep Loop (Consolidation)...")
    sleep_report = await sleep_loop.run_once()
    logger.info(f"Sleep Loop Finished. Processed STS: {sleep_report.processed_sts}, Procedural Memories: {sleep_report.procedural_memories}")

    # 4. RUN SKILL EVOLUTION (Gap 3: Automated Skill Mining & Promotion)
    logger.info("Step 3: Running Skill & Code Evolution...")
    skill_evo = AutomatedSkillEvolution(repo_root=repo_root)
    # In a real run, this would mine from the successful traces generated above
    evo_results = await skill_evo.run_cycle(domain="core")
    logger.info(f"Skill Evolution Finished. Results: {evo_results['results']}")

    # 5. RUN IMMUNE LOOP (Anomaly Detection & Safety)
    logger.info("Step 4: Running Immune Loop (Anomaly Detection)...")
    immune_cases = immune_loop.run_once()
    logger.info(f"Immune Loop Finished. Cases found: {len(immune_cases) if immune_cases else 0}")

    # 5.5 RUN OBSERVABILITY ANOMALY DETECTION (Gap Sources v2)
    logger.info("Step 4.5: Running Observability Anomaly Detection...")
    try:
        from quentin.observability.anomaly_detector import get_anomaly_generator
        detector = get_anomaly_generator(repo_root=repo_root)
        new_tasks = await detector.check_and_generate()
        logger.info(f"Anomaly Detection Finished. Remediation tasks queued: {len(new_tasks)}")
    except Exception as e:
        logger.warning(f"Anomaly Detection step failed: {e}")

    # 6. RUN RESEARCH PROMOTION (Gap 5: Data-driven Model Routing)
    logger.info("Step 5: Closing the Research-to-Runtime Loop...")
    # Mocking a promotion decision for model router based on usage stats
    try:
        from quentin.l3.research.experiment_orchestrator import ExperimentOrchestrator
        orch = ExperimentOrchestrator(tracer=container.tracer, kv=container.kv_store, safety_kernel=container.safety_kernel)
        
        # In a real scenario, we'd have a specific experiment_id
        # Here we just log the intent to promote based on stats
        logger.info("Research Layer: Analyzing model usage stats for promotion...")
        stats = await container.model_router.get_stats()
        logger.info(f"Current Model Stats: {stats['total_calls']} total calls.")
    except Exception as e:
        logger.warning(f"Research promotion step skipped or failed: {e}")

    logger.info("=== PRODUCTION-READY SELF-EVOLUTION CYCLE COMPLETE ===")

if __name__ == "__main__":
    asyncio.run(run_production_cycle())
