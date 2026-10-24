from __future__ import annotations
import os
import json
import hashlib
import logging
from pathlib import Path
from typing import Any, Union

logger = logging.getLogger(__name__)

class BlobStore:
    """
    P5: Ported from OpenClaw's blob externalization system.
    Saves large payloads separately to keep main traces lean.
    """
    def __init__(self, storage_root: str | Path = "data/blobs"):
        self.root = Path(storage_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.threshold_bytes = 32 * 1024 # 32KB

    def offload_if_large(self, data: Any) -> Any:
        """
        If data is a large string or dict, move it to a blob and return a ref.
        """
        raw_str = ""
        if isinstance(data, str):
            raw_str = data
        elif isinstance(data, (dict, list)):
            raw_str = json.dumps(data, ensure_ascii=False)
        else:
            return data

        if len(raw_str.encode("utf-8")) < self.threshold_bytes:
            return data

        # 1. Compute Hash
        h = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()
        blob_path = self.root / f"{h[:2]}" / f"{h}.json"
        blob_path.parent.mkdir(parents=True, exist_ok=True)

        # 2. Physical Save (Atomic)
        if not blob_path.exists():
            blob_path.write_text(raw_str, encoding="utf-8")
            logger.debug(f"BlobStore: Offloaded {len(raw_str)} bytes to {h[:8]}...")

        # 3. Return Reference
        return {
            "[[BLOB_REF]]": h,
            "original_size": len(raw_str),
            "hint": "Full content moved to external blob to save trace space."
        }

    def load_blob(self, blob_hash: str) -> Optional[str]:
        blob_path = self.root / f"{blob_hash[:2]}" / f"{blob_hash}.json"
        if blob_path.exists():
            return blob_path.read_text(encoding="utf-8")
        return None

# Global Singleton
blob_store = BlobStore()
