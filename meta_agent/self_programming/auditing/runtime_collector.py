import json
import os
from glob import glob
from typing import List, Dict
from .templates import Evidence


class RuntimeEvidenceCollector:
    """
    Optional runtime evidence collector.
    Scans jsonl event files under a directory for declared runtime_signals.
    """

    def __init__(self, events_root: str):
        self.events_root = events_root

    def collect(self, req: Dict) -> List[Evidence]:
        evidences: List[Evidence] = []
        signals = req.get("runtime_signals") or []
        if not signals:
            return evidences
        found = False
        files = glob(os.path.join(self.events_root, "**", "*.jsonl"), recursive=True)
        for fp in files:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        for sig in signals:
                            if sig and sig in line:
                                found = True
                                break
                        if found:
                            break
            except Exception:
                continue
            if found:
                break
        if found:
            evidences.append(Evidence("runtime", "runtime_signal_seen", 0.5, f"Signals {signals} seen in events"))
        else:
            evidences.append(Evidence("runtime", "runtime_signal_missing", 0.0, f"Signals {signals} not seen"))
        return evidences
