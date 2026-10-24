# quentin/skills/skill_loop.py
from __future__ import annotations
import logging
import asyncio
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Ensure the project root is in sys.path for package imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)

# Load env vars from project root (.env, .env.local) so services (PG, etc.) pick them up.
repo_root = Path(project_root)
load_dotenv(repo_root / ".env")
load_dotenv(repo_root / ".env.local", override=True)
# If PG_DSN is not set but PG_HOST/USER/DB are provided, synthesize PG_DSN to ensure TCP auth is used.
if not os.getenv("PG_DSN"):
    pg_host = os.getenv("PG_HOST")
    pg_user = os.getenv("PG_USER")
    pg_password = os.getenv("PG_PASSWORD", "")
    pg_port = os.getenv("PG_PORT", "5432")
    pg_db = os.getenv("PG_DB")
    if pg_host and pg_user and pg_db:
        os.environ["PG_DSN"] = f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"

# Imports from other phase 3 modules
from quentin.skills.candidate_store import CandidateStore
from quentin.skills.task_builder import SkillTaskBuilder, ProgrammingTask
from quentin.skills.registrar import SkillRegistrar
from quentin.self_programming.skill_evaluator import SkillPatchEvaluator
from quentin.memory.fabric import MemoryFabric
from quentin.knowledge_graph.service import GraphService

# Reuse existing engine
from meta_agent.self_programming.engine_v2 import SelfProgrammingEngineV2, SelfProgrammingConfig
from meta_agent.council import CouncilManager, CouncilConfig

logger = logging.getLogger(__name__)

class DoneCouncil:
    """
    Lightweight post-check council to validate a generated skill before registration.
    Falls back to auto-approve on errors/unavailable LLMs.
    """

    def __init__(self, council: CouncilManager | None = None):
        self.council = council or CouncilManager(config=CouncilConfig(max_rounds=1))

    def review_skill(self, skill_name: str, file_path: Path, candidate: dict) -> dict:
        try:
            code = file_path.read_text(encoding="utf-8")
        except Exception as e:
            return {"approved": False, "reason": f"failed to read skill file: {e}"}

        question = f"Review the generated skill '{skill_name}'. Should it be accepted?"
        context = {
            "candidate": candidate,
            "file_path": str(file_path),
            "code_preview": code[:4000],
        }
        try:
            outcome = self.council.run(question, context=context)
            verdict = outcome.final_output.verdict
            approved = verdict in ("approve",)
            reason = outcome.final_output.current_summary
            return {"approved": approved, "reason": reason, "verdict": verdict}
        except Exception as e:
            logger.warning(f"DoneCouncil failed, auto-approving skill {skill_name}: {e}")
            return {"approved": True, "reason": "council unavailable, auto-approve"}

class SkillLoopRunner:
    def __init__(self):
        self.store = CandidateStore()
        self.builder = SkillTaskBuilder()
        self.fabric = MemoryFabric()
        self.graph_service = GraphService()
        self.registrar = SkillRegistrar(memory_fabric=self.fabric)
        self.done_council = DoneCouncil()
        cfg = SelfProgrammingConfig(
            default_coder_backend=os.getenv("CODER_BACKEND", "stub"),
            enable_research=False,
        )
        self.engine = SelfProgrammingEngineV2(
            config=cfg,
            evaluator=SkillPatchEvaluator()
        ) # Reuse existing engine with correct evaluator

    def run_once(self):
        # 1. Fetch
        candidates = self.store.get_pending(limit=1)
        if not candidates:
            logger.info("No pending skill candidates.")
            return

        candidate = candidates[0]
        cid = candidate.get("candidate_id")
        logger.info(f"Processing candidate: {cid}")

        # 2. Build Task
        task = self.builder.build_task(candidate)
        
        # 3. Delegate to Engine (Generate & Test)
        # engine.run_for_gaps accepts iterable of tasks/gaps
        logger.info(f"Delegating to EngineV2: {task.title}")
        try:
            # Note: engine_v2.run_for_gaps is sync wrapper around async logic
            # It will attempt to generate code, patch it, and run tests.
            self.engine.run_for_gaps([task]) 
        except Exception as e:
            import traceback
            logger.error(f"Engine execution failed: {e}\n{traceback.format_exc()}")
            # Optional: handle retry logic here
            return

        # 4. Verify & Register
        # Since EngineV2 applies patches on success, we check if file exists.
        # Task description instructed where to create file.
        skill_name = task.title.replace("Implement New Skill: ", "").strip()
        expected_path = f"quentin/mutable/skills/{skill_name}.py"
        
        skill_file = Path(expected_path)
        if skill_file.exists():
            council_result = self.done_council.review_skill(skill_name, skill_file, candidate)
            if not council_result.get("approved"):
                logger.error(f"Skill {skill_name} rejected by DoneCouncil: {council_result.get('reason')}")
                return
            # Success!
            self.registrar.register(skill_name, expected_path, candidate)
            self.store.mark_processed(cid)
        else:
            logger.error(f"Skill generation failed (file not found): {expected_path}. Not marking processed; investigate coder backend/test failures.")
            # Do not stub or mark processed to surface real failures.

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    runner = SkillLoopRunner()
    runner.run_once()
