
import json
from typing import Any, Dict, List, Optional

def simulate_physical_guard(focus_paths: List[str], sensing_report: Dict[str, Any], verdict: str):
    """
    Simulated logic from quentin/cognitive/loop_orchestration.py
    """
    sensing_hallucination_blocked = False
    path_triggered = None
    
    # CURRENT BUGGY LOGIC:
    for path in (focus_paths or []):
        stat = sensing_report.get(path) # This is the bug
        if isinstance(stat, dict) and stat.get("exists") is False:
            if verdict == "already_done":
                sensing_hallucination_blocked = True
            verdict = "not_done"
            path_triggered = path
            break
            
    return verdict, sensing_hallucination_blocked, path_triggered

# Mock sensing report structure as defined in loop_context_helpers.py
mock_sensing_report = {
    "system_policies": {},
    "focus_paths": ["non_existent_file.txt"],
    "keywords": [],
    "evidence": [
        {
            "path": "non_existent_file.txt",
            "exists": False,
            "is_dir": False
        }
    ]
}

focus_paths = ["non_existent_file.txt"]
hallucinated_verdict = "already_done"

print("--- Testing Current (Buggy) Logic ---")
verdict, blocked, path = simulate_physical_guard(focus_paths, mock_sensing_report, hallucinated_verdict)
print(f"Verdict: {verdict}")
print(f"Blocked: {blocked}")
print(f"Path Triggered: {path}")

if not blocked and verdict == "already_done":
    print("❌ BUG REPRODUCED: Physical guard failed to block hallucination because of wrong indexing.")
else:
    print("✅ Physical guard worked (Unexpected if buggy logic is present).")

def simulate_fixed_physical_guard(focus_paths: List[str], sensing_report: Dict[str, Any], verdict: str):
    """
    Proposed fixed logic
    """
    # 1. Convert evidence list to a map for easy lookup
    evidence_map = {item["path"]: item for item in sensing_report.get("evidence", [])}
    
    sensing_hallucination_blocked = False
    path_triggered = None
    
    for path in (focus_paths or []):
        stat = evidence_map.get(path)
        if isinstance(stat, dict) and stat.get("exists") is False:
            if verdict == "already_done":
                sensing_hallucination_blocked = True
            verdict = "not_done"
            path_triggered = path
            break
            
    return verdict, sensing_hallucination_blocked, path_triggered

print("\n--- Testing Fixed Logic ---")
verdict, blocked, path = simulate_fixed_physical_guard(focus_paths, mock_sensing_report, hallucinated_verdict)
print(f"Verdict: {verdict}")
print(f"Blocked: {blocked}")
print(f"Path Triggered: {path}")

if blocked and verdict == "not_done":
    print("✅ FIX VERIFIED: Physical guard correctly blocked hallucination.")
else:
    print("❌ FIX FAILED.")
