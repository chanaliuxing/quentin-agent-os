import sys
from pathlib import Path
import json
import os

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from quentin.self_programming.auto_fixer import AutoFixerLoop

def test_auto_fixer():
    print("Testing AutoFixer...")
    repo_root = "."
    fixer = AutoFixerLoop(repo_root=repo_root)
    ticket_path = Path("data/tasks/repair_tickets.jsonl")
    if ticket_path.exists(): ticket_path.unlink()
    
    # Simulate 3 identical errors
    payload = {"error": "syntax error in x.py", "trace_id": "t1"}
    for i in range(3):
        fixer.on_system_event("error", payload)
        
    if ticket_path.exists():
        print("✅ Ticket created after 3 errors.")
        content = ticket_path.read_text()
        if "syntax error" in content:
            print("AutoFixer: OK")
        else:
            raise ValueError("Ticket content wrong")
    else:
        raise ValueError("Ticket NOT created")

if __name__ == "__main__":
    test_auto_fixer()
