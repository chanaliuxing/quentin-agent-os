# quentin/skills/candidate_store.py
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Set

logger = logging.getLogger(__name__)
from quentin.runtime.session_write_lock import acquire_session_write_lock

class CandidateStore:
    """
    Manages the lifecycle of skill candidates from discovery to ingestion.
    Ensures idempotency using a simple processed log.
    """
    def __init__(self, candidates_path: str = "data/skill_candidates.jsonl"):
        self.candidates_path = Path(candidates_path)
        self.processed_path = self.candidates_path.with_suffix(".processed")
        self._processed_ids: Set[str] = self._load_processed()

    def _load_processed(self) -> Set[str]:
        if not self.processed_path.exists():
            return set()
        try:
            return set(self.processed_path.read_text(encoding="utf-8").splitlines())
        except Exception:
            return set()

    def mark_processed(self, candidate_id: str):
        if candidate_id in self._processed_ids:
            return
        self._processed_ids.add(candidate_id)
        lock = acquire_session_write_lock(session_file=self.processed_path)
        try:
            with self.processed_path.open("a", encoding="utf-8") as f:
                f.write(candidate_id + "\n")
        finally:
            lock["release"]()

    def get_pending(self, limit: int = 10) -> List[Dict[str, Any]]:
        if not self.candidates_path.exists():
            return []

        pending = []
        try:
            with self.candidates_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    try:
                        data = json.loads(line)
                        cid = data.get("candidate_id")
                        if cid and cid not in self._processed_ids:
                            pending.append(data)
                            if len(pending) >= limit:
                                break
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"Failed to read candidates: {e}")
            
        return pending
