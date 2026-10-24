# quentin/skills/registrar.py
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Dict, Any

from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryTier
from quentin.knowledge_graph.service import GraphService
from quentin.knowledge_graph.schema import NodeType, EdgeType
from quentin.utils.time import now_iso

logger = logging.getLogger(__name__)

class SkillRegistrar:
    def __init__(self, registry_path: str = "quentin/mutable/skills/registry.json", memory_fabric: MemoryFabric | None = None, repo_root: str | Path = "."):
        self.repo_root = Path(repo_root).resolve()
        rp = Path(registry_path)
        if not rp.is_absolute():
            rp = (self.repo_root / rp).resolve()
        self.registry_path = rp
        
        # Ensure parent exists early
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.fabric = memory_fabric or MemoryFabric(repo_root=self.repo_root)
        self.graph_service = GraphService()

    def register(self, skill_name: str, file_path: str, candidate: Dict[str, Any]) -> bool:
        """
        1. Verify file exists
        2. Update registry.json
        3. Write Memory
        """
        path_obj = Path(file_path)
        if not path_obj.exists():
            logger.error(f"Skill file not found at {file_path}, cannot register.")
            return False

        # 2. Update Registry
        entry = {
            "module": str(file_path).replace("/", ".").replace(".py", ""),
            "callable": skill_name, # Convention: main function name == skill name
            "created_at": now_iso(),
            "source_candidate": candidate.get("candidate_id"),
            "tags": candidate.get("tags", []),
            "version": "1.0.0"
        }
        
        try:
            self._update_json_registry(skill_name, entry)
        except Exception as e:
            logger.error(f"Failed to update registry: {e}")
            return False

        # 3. Write MTS Memory (Closing the loop)
        try:
            content = f"Learned new skill '{skill_name}'.\nDescription: {candidate.get('description')}"
            self.fabric.remember_atomic(
                content=content,
                source="skill_registrar",
                tier=MemoryTier.MTS,
                importance=1.0,
                tags=["skill", "learned", "auto-generated"],
                relations={
                    f"crystallized_from:{candidate.get('candidate_id')}": 1.0
                },
                kind="procedural"
            )
        except Exception as e:
            logger.warning(f"Failed to record skill memory: {e}")

        logger.info(f"✅ Skill '{skill_name}' registered successfully.")
        
        # --- PHASE 4 HOOK START ---
        try:
            # 1. Ensure Skill Node
            self.graph_service.sync_node(
                NodeType.SKILL, skill_name, title=candidate.get("description", "")
            )
            # 2. Link Candidate -> Skill
            cid = candidate.get("candidate_id")
            if cid:
                self.graph_service.create_link(
                    (NodeType.CANDIDATE, cid),
                    (NodeType.SKILL, skill_name),
                    EdgeType.PRODUCES_SKILL
                )
        except Exception as e:
            logger.warning(f"Graph sync failed for skill {skill_name}: {e}")
        # --- PHASE 4 HOOK END ---
        
        return True

    def _update_json_registry(self, name: str, entry: Dict[str, Any]):
        if not self.registry_path.exists():
            self.registry_path.parent.mkdir(parents=True, exist_ok=True)
            self.registry_path.write_text("{}", encoding="utf-8")
            
        try:
            data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except:
            data = {}
            
        data[name] = entry
        
        with self.registry_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
