# meta_agent/patchflow/queue.py
from __future__ import annotations
from typing import List
from pathlib import Path
import json
import os

from meta_agent.patchflow.models import PatchProposal


class PatchQueue:
    def __init__(self, path: str | Path = "data/patches/patch_queue.jsonl") -> None:
        override = (os.environ.get("META_AGENT_PATCH_QUEUE_PATH") or "").strip()
        self.path = Path(override or path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, proposal: PatchProposal) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(proposal.to_dict(), ensure_ascii=False) + "\n")

    def load_all(self) -> List[PatchProposal]:
        if not self.path.exists():
            return []
        out: List[PatchProposal] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    out.append(PatchProposal.from_dict(d))
                except Exception:
                    continue
        return out

    def save_all(self, proposals: List[PatchProposal]) -> None:
        with self.path.open("w", encoding="utf-8") as f:
            for p in proposals:
                f.write(json.dumps(p.to_dict(), ensure_ascii=False) + "\n")
