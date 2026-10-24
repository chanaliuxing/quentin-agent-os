from __future__ import annotations

import json
import os
import random
import string
from pathlib import Path
from typing import Dict, List, Optional, Set

class PairingManager:
    """
    Manages trusted mobile devices.
    Ensures only approved sender_ids can control the brain.
    """
    def __init__(self, storage_path: str = "data/trusted_nodes.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._trusted_ids: Set[str] = self._load()
        self._pending_requests: Dict[str, str] = {} # code -> sender_id

    def _load(self) -> Set[str]:
        if not self.storage_path.exists():
            return set()
        try:
            data = json.loads(self.storage_path.read_text())
            return set(data.get("trusted_ids", []))
        except:
            return set()

    def _save(self):
        data = {"trusted_ids": list(self._trusted_ids)}
        self.storage_path.write_text(json.dumps(data, indent=2))

    def is_trusted(self, sender_id: str) -> bool:
        return sender_id in self._trusted_ids

    def generate_pairing_code(self, sender_id: str) -> str:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        self._pending_requests[code] = sender_id
        return code

    def approve_code(self, code: str) -> Optional[str]:
        sender_id = self._pending_requests.pop(code, None)
        if sender_id:
            self._trusted_ids.add(sender_id)
            self._save()
            return sender_id
        return None
