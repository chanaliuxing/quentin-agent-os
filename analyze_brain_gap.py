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
            if any(x in root for x in ('.git', '__pycache__', 'node_modules', 'test-helpers')):
                continue
            for f in files:
                if f.endswith(extensions):
                    p = Path(root) / f
                    try:
                        lines = p.read_text(errors='ignore').splitlines()
                        # Simple logic filter: skip very short files or pure exports
                        if len(lines) > 5:
                            total_lines += len(lines)
                            file_count += 1
                    except: pass
    return total_lines, file_count

def main():
    # 1. Define OC Brain Components
    oc_base = "openclaw/openclaw/src"
    oc_brain_dirs = [
        "agents/pi-embedded-runner",
        "agents/pi-embedded-helpers",
        "agents/pi-extensions",
        "agents/skills",
        "agents/schema",
        "memory",
        "infra/llm",
        "acp"
    ]
    
    # 2. Define Taylor Brain Components
    t_base = "quentin"
    t_brain_dirs = [
        "cognitive",
        "planning",
        "execution",
        "memory",
        "llm",
        "skills"
    ]
    
    print("🧠 [Brain Audit] Analyzing Pi-Logic Gap...")
    
    oc_loc, oc_files = count_loc(oc_base, oc_brain_dirs, ('.ts',))
    t_loc, t_files = count_loc(t_base, t_brain_dirs, ('.py',))
    
    print(f"\n--- Brain LOC Summary ---")
    print(f"Taylor Brain (Python):  {t_loc:>6} lines ({t_files} files)")
    print(f"OpenClaw Pi Brain (TS): {oc_loc:>6} lines ({oc_files} files)")
    
    gap = oc_loc - t_loc
    ratio = (t_loc / oc_loc) * 100 if oc_loc > 0 else 0
    print(f"Brain Parity Score:     {ratio:.1f}%")
    
    print(f"\n--- Specific Brain Gaps (Logical Modules) ---")
    # Check for missing logical sub-components in Taylor's brain folders
    oc_sub = set()
    for d in oc_brain_dirs:
        p = Path(oc_base) / d
        if p.exists():
            for item in p.iterdir():
                if item.is_dir(): oc_sub.add(item.name)
                
    t_sub = set()
    for d in t_brain_dirs:
        p = Path(t_base) / d
        if p.exists():
            for item in p.iterdir():
                if item.is_dir(): t_sub.add(item.name)
                
    missing = oc_sub - t_sub
    # Filter common names
    real_missing = [m for m in missing if m not in ('run', 'tests', 'utils', 'helpers', 'types', 'proto', 'protocol')]
    for m in real_missing[:10]:
        print(f"❌ Missing Logic Module: {m}")

if __name__ == "__main__":
    main()
