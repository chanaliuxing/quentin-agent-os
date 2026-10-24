from __future__ import annotations
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

def get_goal_fingerprint(goal: str, context: Dict[str, Any]) -> str:
    """
    Generate a stable hash for a goal and its context.
    """
    # Normalize context to remove highly dynamic fields like trace_id or timestamps if present
    stable_context = {k: v for k, v in context.items() if k not in ["trace_id", "timestamp", "start_time", "cancel_token"]}
    
    data = {
        "goal": goal,
        "context": stable_context
    }
    
    # Sort keys for stable JSON string
    data_str = json.dumps(data, sort_keys=True)
    return hashlib.sha256(data_str.encode("utf-8")).hexdigest()

def get_file_hash(path: str | Path) -> str:
    """
    Get SHA256 hash of a file's content.
    """
    p = Path(path)
    if not p.exists() or not p.is_file():
        return ""
    
    hasher = hashlib.sha256()
    try:
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
    except Exception:
        return ""
    return hasher.hexdigest()

class EnvironmentHasher:
    """
    P5: Ported from OpenClaw's delta tracking logic.
    Computes a joint fingerprint of the physical workspace state efficiently.
    """
    @staticmethod
    def get_fast_directory_fingerprint(root_path: Path, ignore_dirs: Optional[List[str]] = None) -> str:
        """
        Computes a fingerprint based on file metadata (name, size, mtime).
        Fast but sensitive to 'touch'.
        """
        if ignore_dirs is None:
            ignore_dirs = [".git", "__pycache__", "venv", "node_modules", "data", "logs"]
            
        file_stats = []
        for root, dirs, files in os.walk(str(root_path)):
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
            for f in sorted(files):
                if f.startswith("."): continue
                p = Path(root) / f
                try:
                    stat = p.stat()
                    # We combine path, size and mtime into a record
                    rel_p = p.relative_to(root_path)
                    file_stats.append(f"{rel_p}|{stat.st_size}|{stat.st_mtime}")
                except Exception:
                    continue
        
        digest_str = "\n".join(file_stats)
        return hashlib.sha256(digest_str.encode("utf-8")).hexdigest()

    @staticmethod
    def get_system_state_fingerprint() -> Dict[str, Any]:
        """
        P5: OpenClaw Parity - Captures non-file state (ports, essential env).
        """
        import socket
        # Sample common ports used in dev (just as a fingerprint signal)
        ports = [8000, 8080, 3000, 5432, 11434]
        open_ports = []
        for p in ports:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.01)
                if s.connect_ex(('127.0.0.1', p)) == 0:
                    open_ports.append(p)
        
        return {
            "open_ports": open_ports,
            "platform": os.name,
            "cwd": os.getcwd()
        }
