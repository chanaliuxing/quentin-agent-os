import os
import sys
from pathlib import Path
from collections import defaultdict

def count_loc(directory, extensions=('.py', '.ts', '.js')):
    stats = defaultdict(int)
    total_files = 0
    
    for root, dirs, files in os.walk(directory):
        if any(x in root for x in ('.git', '__pycache__', 'node_modules', 'venv', 'dist')):
            continue
        for f in files:
            if f.endswith(extensions):
                path = Path(root) / f
                try:
                    lines = path.read_text(errors='ignore').splitlines()
                    stats[path.suffix] += len(lines)
                    total_files += 1
                except: pass
    return stats, total_files

def get_dir_structure(directory, depth=2):
    structure = set()
    base = Path(directory)
    for root, dirs, files in os.walk(directory):
        rel = Path(root).relative_to(base)
        if len(rel.parts) <= depth:
            structure.add(str(rel))
        if len(rel.parts) >= depth:
            dirs[:] = [] # stop deep scan
    return structure

def main():
    taylor_root = "quentin"
    openclaw_root = "openclaw/openclaw/src"
    
    print("📊 [Codebase Audit] Analyzing Taylor vs OpenClaw...")
    
    # 1. LOC Comparison
    t_loc, t_files = count_loc(taylor_root, ('.py',))
    o_loc, o_files = count_loc(openclaw_root, ('.ts', '.js'))
    
    print(f"\n--- LOC Summary ---")
    print(f"Taylor (Python):   {sum(t_loc.values()):>6} lines ({t_files} files)")
    print(f"OpenClaw (TS/JS):  {sum(o_loc.values()):>6} lines ({o_files} files)")
    
    gap_loc = sum(o_loc.values()) - sum(t_loc.values())
    parity = (sum(t_loc.values()) / sum(o_loc.values())) * 100 if sum(o_loc.values()) > 0 else 0
    print(f"Parity Score:      {parity:.1f}%")
    
    # 2. Structural Gaps
    t_struct = get_dir_structure(taylor_root)
    o_struct = get_dir_structure(openclaw_root)
    
    print(f"\n--- Structural Gap (Present in OC, Missing/Minimal in Taylor) ---")
    
    # Map OC names to Taylor logical names
    mapping = {
        "acp": "agent_capability_protocol",
        "canvas-host": "ui_canvas",
        "channels": "communication_adapters",
        "auto-reply": "reply_logic",
        "browser/routes": "web_routing"
    }
    
    found_gaps = []
    for o_dir in sorted(o_struct):
        if o_dir == ".": continue
        # Simple check if something similar exists
        matches = [t for t in t_struct if o_dir.split('/')[-1] in t.lower() or mapping.get(o_dir, "") in t]
        if not matches:
            found_gaps.append(o_dir)
            
    for g in found_gaps[:15]:
        print(f"❌ MISSING: {g}")

if __name__ == "__main__":
    main()
