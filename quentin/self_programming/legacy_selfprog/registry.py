from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Union
import json
import logging

from quentin.self_programming.legacy_selfprog.models import Patch

logger = logging.getLogger(__name__)


class FileBackedPatchRegistry:
    """
    Legacy file-backed patch registry (JSON).
    """

    def __init__(self, path: Union[str, Path] = "data/patches.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._loaded = False
        self._patches: Dict[str, Patch] = {}

    def _load(self) -> None:
        if self._loaded:
            return
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8") or "{}")
                patches_raw = raw.get("patches", {}) or {}
                self._patches = {pid: Patch.from_dict(pd) for pid, pd in patches_raw.items()}
            except Exception:
                logger.exception("FileBackedPatchRegistry: failed to load patches; using empty.")
                self._patches = {}
        else:
            self._patches = {}
        self._loaded = True

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = {"patches": {pid: p.to_dict() for pid, p in self._patches.items()}}
        self.path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    def upsert_patch(self, patch: Patch) -> None:
        self._load()
        self._patches[patch.patch_id] = patch
        self._save()

    def get_patch(self, patch_id: str) -> Optional[Patch]:
        self._load()
        return self._patches.get(patch_id)

    def list_patches(self, *, status: Optional[str] = None, target_path: Optional[str] = None) -> List[Patch]:
        self._load()
        patches = list(self._patches.values())
        if status:
            patches = [p for p in patches if p.status == status]
        if target_path:
            patches = [p for p in patches if p.target_path == target_path]
        patches.sort(key=lambda p: p.updated_at, reverse=True)
        return patches

