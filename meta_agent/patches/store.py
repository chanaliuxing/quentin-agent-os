import json
from pathlib import Path
from typing import List, Optional
from dataclasses import asdict
from datetime import datetime
from meta_agent.patches.models import PatchProposal
from quentin.utils.time import normalize_to_utc_iso

class PatchStore:
    """
    Persistence layer for patches.
    Migrated from quentin/self_programming/engine.old.py but using File storage for simplicity and debuggability.
    """
    def __init__(self, path: str = "data/patches.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, data: dict):
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_patch(self, patch: PatchProposal) -> None:
        data = self._load()
        patch_dict = asdict(patch)
        # Serialize datetime
        if isinstance(patch_dict.get('created_at'), datetime):
            patch_dict['created_at'] = patch_dict['created_at'].isoformat()
        
        data[patch.id] = patch_dict
        self._save(data)

    def get_patch(self, patch_id: str) -> Optional[PatchProposal]:
        data = self._load()
        p_data = data.get(patch_id)
        if not p_data:
            return None
        
        # Deserialize datetime
        if 'created_at' in p_data:
            try:
                p_data['created_at'] = datetime.fromisoformat(normalize_to_utc_iso(p_data['created_at']))
            except (ValueError, TypeError):
                pass # Keep as string or default? PatchProposal expects datetime.
                # If fail, maybe set to now or handle gracefully.
                # For now let's hope it's valid ISO.

        return PatchProposal(**p_data)

    def list_patches(self, limit: int = 100) -> List[PatchProposal]:
        data = self._load()
        # Sort by created_at desc if possible, or just list
        # Simple list for now
        patches = []
        for p_data in list(data.values())[-limit:]:
             if 'created_at' in p_data:
                try:
                    p_data['created_at'] = datetime.fromisoformat(normalize_to_utc_iso(p_data['created_at']))
                except: pass
             patches.append(PatchProposal(**p_data))
        return patches
