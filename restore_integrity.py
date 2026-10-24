import subprocess
from pathlib import Path
import sys

def get_broken_files():
    cmd = ["python3", "-m", "compileall", "quentin/"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    broken = []
    # Parse SyntaxError lines
    for line in res.stdout.splitlines():
        if "File \"" in line and "line" in line:
            parts = line.split("\"")
            if len(parts) > 1:
                broken.append(parts[1])
    return sorted(list(set(broken)))

def find_good_rev(file_path):
    # Try last 50 commits
    cmd = ["git", "rev-list", "-n", "50", "HEAD"]
    revs = subprocess.check_output(cmd, text=True).splitlines()
    for rev in revs:
        try:
            # Check if file existed in this rev
            subprocess.check_call(["git", "cat-file", "-e", f"{rev}:{file_path}"], stderr=subprocess.DEVNULL)
            # Pull content
            content = subprocess.check_output(["git", "show", f"{rev}:{file_path}"])
            # Try to compile
            temp_p = Path("/tmp/integrity_check.py")
            temp_p.write_bytes(content)
            if subprocess.run(["python3", "-m", "py_compile", str(temp_p)], capture_output=True).returncode == 0:
                return rev
        except:
            continue
    return None

broken_files = get_broken_files()
print(f"Broken files found: {broken_files}")

for f in broken_files:
    print(f"Analyzing {f}...")
    good_rev = find_good_rev(f)
    if good_rev:
        print(f"✅ Found good version for {f} at {good_rev}. Restoring...")
        subprocess.check_call(["git", "checkout", good_rev, "--", f])
    else:
        print(f"❌ No good version found in Git for {f}. It might be a new corrupted file.")

print("\n--- Final Integrity Check ---")
subprocess.run(["python3", "-m", "compileall", "quentin/"])
