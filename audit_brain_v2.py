import os
from pathlib import Path
from collections import defaultdict

def count_loc(base_dir, sub_dirs, extensions=('.py', '.ts')):
    total_lines = 0
    file_count = 0
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
                        if len(lines) > 5:
                            total_lines += len(lines)
                            file_count += 1
                    except: pass
    return total_lines, file_count

def main():
    oc_base = "openclaw/openclaw/src"
    t_base = "quentin"
    
    # 物理映射关系 V2 (包含所有 Surgery 新增目录)
    mapping = {
        "1. Orchestration (调度/同步)": {
            "oc": ["agents/pi-embedded-runner", "agents/pi-extensions", "infra/concurrency"],
            "t": ["cognitive", "infra/concurrency", "infra/events"]
        },
        "2. Planning (规划/策略)": {
            "oc": ["agents/pi-embedded-runner/run"],
            "t": ["planning"]
        },
        "3. Execution (执行/环境)": {
            "oc": ["agents/tools", "agents/cli-runner", "infra/terminal", "browser"],
            "t": ["execution", "tools", "infra/terminal", "infra/browser", "infra/storage", "infra/canvas", "infra/tools"]
        },
        "4. Memory (记忆体系)": {
            "oc": ["memory"],
            "t": ["memory"]
        },
        "5. LLM Layer (模型/安全)": {
            "oc": ["infra/llm", "acp"],
            "t": ["llm", "infra/llm", "infra/security"]
        },
        "6. Skill Evolution (进化)": {
            "oc": ["agents/skills"],
            "t": ["skills"]
        }
    }
    
    print(f"{'Brain Component':<30} | {'OC (TS)':>10} | {'Taylor (Py)':>12} | {'Parity'}")
    print("-" * 75)
    
    total_oc = 0
    total_t = 0
    
    for label, dirs in mapping.items():
        oc_loc, oc_fc = count_loc(oc_base, dirs["oc"], ('.ts',))
        t_loc, t_fc = count_loc(t_base, dirs["t"], ('.py',))
        
        total_oc += oc_loc
        total_t += t_loc
        
        parity = (t_loc / oc_loc) * 100 if oc_loc > 0 else 0
        print(f"{label:<30} | {oc_loc:>10} | {t_loc:>12} | {parity:>6.1f}% ({t_fc} files)")

    print("-" * 75)
    full_parity = (total_t / total_oc) * 100 if total_oc > 0 else 0
    print(f"{'TOTAL BRAIN ARCHITECTURE':<30} | {total_oc:>10} | {total_t:>12} | {full_parity:>6.1f}%")

if __name__ == "__main__":
    main()
