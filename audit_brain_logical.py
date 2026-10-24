import os
from pathlib import Path

def count_loc(base_dir, sub_dirs, extensions=('.py', '.ts')):
    total_lines = 0
    for sd in sub_dirs:
        path = Path(base_dir) / sd
        if not path.exists(): continue
        for root, dirs, files in os.walk(path):
            if any(x in root for x in ('.git', '__pycache__', 'node_modules', 'test-helpers', 'data')):
                continue
            for f in files:
                if f.endswith(extensions):
                    p = Path(root) / f
                    try:
                        lines = p.read_text(errors='ignore').splitlines()
                        if len(lines) > 5: total_lines += len(lines)
                    except: pass
    return total_lines

def main():
    oc_base = "openclaw/openclaw/src"
    t_base = "quentin"
    
    # 逻辑功能对冲 (将大脑思考过程合一)
    oc_thinking_loc = count_loc(oc_base, ["agents/pi-embedded-runner", "agents/pi-extensions"], ('.ts',))
    t_thinking_loc = count_loc(t_base, ["cognitive", "planning"], ('.py',))
    
    print("🧠 [Logical Brain Audit] Conceptual Parity Check")
    print("-" * 60)
    print(f"Taylor Thinking Logic (Py):  {t_thinking_loc:>6} lines")
    print(f"OpenClaw Thinking Logic (TS): {oc_thinking_loc:>6} lines")
    
    parity = (t_thinking_loc / oc_thinking_loc) * 100 if oc_thinking_loc > 0 else 0
    print(f"Thinking Logic Parity:        {parity:.1f}%")
    
    # Execution & Perception
    oc_action_loc = count_loc(oc_base, ["agents/tools", "infra/terminal", "browser"], ('.ts',))
    t_action_loc = count_loc(t_base, ["execution", "tools", "infra/terminal", "infra/browser"], ('.py',))
    
    print(f"\nTaylor Action Logic (Py):    {t_action_loc:>6} lines")
    print(f"OpenClaw Action Logic (TS):   {oc_action_loc:>6} lines")
    
    action_parity = (t_action_loc / oc_action_loc) * 100 if oc_action_loc > 0 else 0
    print(f"Action Logic Parity:          {action_parity:.1f}%")

if __name__ == "__main__":
    main()
