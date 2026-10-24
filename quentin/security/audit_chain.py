from __future__ import annotations
import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Any, Optional

@dataclass
class ChainLink:
    event_id: str
    prev_hash: str
    current_hash: str
    timestamp: float

class AuditChain:
    """
    P5-B: Audit Chain (Tamper-evident log)
    Each event hash depends on the previous event's hash.
    Persistent version.
    """
    def __init__(self, repo_root: str = ".", initial_seed: str = "quentin_genesis") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.chain_path = self.repo_root / "data" / "audit_chain.jsonl"
        self.chain_path.parent.mkdir(parents=True, exist_ok=True)
        self.initial_seed = initial_seed
        self._load_last_hash()

    def _load_last_hash(self) -> None:
        if not self.chain_path.exists():
            self.last_hash = hashlib.sha256(self.initial_seed.encode()).hexdigest()
            return

        try:
            with self.chain_path.open("r", encoding="utf-8") as f:
                last_line = None
                for line in f:
                    if line.strip():
                        last_line = line
                if last_line:
                    data = json.loads(last_line)
                    self.last_hash = data["current_hash"]
                else:
                    self.last_hash = hashlib.sha256(self.initial_seed.encode()).hexdigest()
        except Exception:
            self.last_hash = hashlib.sha256(self.initial_seed.encode()).hexdigest()

    def sign_event(self, event_id: str, event_data: Dict[str, Any]) -> str:
        """
        Sign an event, return its hash, and persist it.
        """
        payload = json.dumps(event_data, sort_keys=True)
        prev_hash = self.last_hash
        combined = f"{prev_hash}|{event_id}|{payload}"
        new_hash = hashlib.sha256(combined.encode()).hexdigest()
        
        link = ChainLink(
            event_id=event_id,
            prev_hash=prev_hash,
            current_hash=new_hash,
            timestamp=time.time()
        )
        
        self._persist_link(link, event_data)
        self.last_hash = new_hash
        return new_hash

    def _persist_link(self, link: ChainLink, event_data: Dict[str, Any]) -> None:
        record = {
            **asdict(link),
            "data": event_data
        }
        with self.chain_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def verify_integrity(self) -> bool:
        """
        Scan the entire file and verify the hash chain.
        """
        if not self.chain_path.exists():
            return True
        
        current_prev_hash = hashlib.sha256(self.initial_seed.encode()).hexdigest()
        with self.chain_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                record = json.loads(line)
                
                # Check prev_hash alignment
                if record["prev_hash"] != current_prev_hash:
                    print(f"DEBUG: Prev hash alignment failed for event {record['event_id']}")
                    print(f"DEBUG: Record prev_hash: {record['prev_hash']}")
                    print(f"DEBUG: Current tracker: {current_prev_hash}")
                    return False
                
                # Recalculate hash
                payload = json.dumps(record["data"], sort_keys=True)
                combined = f"{record['prev_hash']}|{record['event_id']}|{payload}"
                expected_hash = hashlib.sha256(combined.encode()).hexdigest()
                
                if record["current_hash"] != expected_hash:
                    print(f"DEBUG: Hash mismatch for event {record['event_id']}")
                    print(f"DEBUG: Expected: {expected_hash}")
                    print(f"DEBUG: Actual: {record['current_hash']}")
                    return False
                
                current_prev_hash = record["current_hash"]
        return True
