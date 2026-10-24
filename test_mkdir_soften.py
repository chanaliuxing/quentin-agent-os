import os
import sys
from pathlib import Path
from quentin.tools.filesystem import fs_mkdir
from quentin.tools.shell import shell_mkdir

def test():
    # 1. Test fs_mkdir softening
    print("Testing fs_mkdir softening...")
    params = {"path": "mutable/soften_fs/logic.py"}
    res = fs_mkdir(params)
    print(f"fs_mkdir Result: {res.get('status')} - {res.get('result', 'No Result')}")
    print(f"fs_mkdir Hint: {res.get('hint', 'No Hint')}")
    print(f"Parent exists: {Path('mutable/soften_fs').exists()}")

    # 2. Test shell_mkdir softening
    print("\nTesting shell_mkdir softening...")
    params = {"path": "mutable/soften_shell/manifest.yaml"}
    res = shell_mkdir(params)
    print(f"shell_mkdir Result: {res.get('status')} - {res.get('result', 'No Result')}")
    print(f"shell_mkdir Hint: {res.get('hint', 'No Hint')}")
    print(f"Parent exists: {Path('mutable/soften_shell').exists()}")

if __name__ == "__main__":
    test()
