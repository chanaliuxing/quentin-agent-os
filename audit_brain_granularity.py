import os
from pathlib import Path
from collections import defaultdict

def count_loc(base_dir, sub_dirs, extensions=('.py', '.ts')):
    total_lines = 0
    for sd in sub_dirs:
        path = Path(base_dir) / sd
        if not path.exists(): continue
        for root, dirs, files in os.walk(path):
            if any(x in root for x in ('.git', '__pycache__', 'node_modules', 'test-helpers')):
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
    
    # 物理映射关系 (OC vs Taylor)
    mapping = {
        "1. Orchestration (认知调度)": {
            "oc": ["agents/pi-embedded-runner", "agents/pi-extensions"],
            "t": ["cognitive"]
        },
        "2. Planning (规划/策略)": {
            "oc": ["agents/pi-embedded-runner/run"],
            "t": ["planning"]
        },
        "3. Execution (执行/原子工具)": {
            "oc": ["agents/tools", "agents/cli-runner"],
            "t": ["execution", "tools"]
        },
        "4. Memory (记忆存储/检索)": {
            "oc": ["memory"],
            "t": ["memory"]
        },
        "5. LLM Layer (模型适配/协议)": {
            "oc": ["infra/llm", "acp"],
            "t": ["llm"]
        },
        "6. Skill Evolution (技能进化)": {
            "oc": ["agents/skills"],
            "t": ["skills"]
        }
    }
    
    print(f"{'Module Name':<30} | {'OC (TS)':>10} | {'Taylor (Py)':>12} | {'Parity'}")
    print("-" * 75)
    
    total_oc = 0
    total_t = 0
    
    for label, dirs in mapping.items():
        oc_loc = count_loc(oc_base, dirs["oc"], ('.ts',))
        t_loc = count_loc(t_base, dirs["t"], ('.py',))
        
        total_oc += oc_loc
        total_t += t_loc
        
        parity = (t_loc / oc_loc) * 100 if oc_loc > 0 else 0
        print(f"{label:<30} | {oc_loc:>10} | {t_loc:>12} | {parity:>6.1f}%")

    print("-" * 75)
    full_parity = (total_t / total_oc) * 100 if total_oc > 0 else 0
    print(f"{'TOTAL BRAIN LOGIC':<30} | {total_oc:>10} | {total_t:>12} | {full_parity:>6.1f}%")

if __name__ == "__main__":
    main()
