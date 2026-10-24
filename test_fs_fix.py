import os
import sys
from pathlib import Path
from quentin.tools.filesystem import fs_write_file

def test():
    # 1. Test Manifest Alignment
    print("Testing Manifest Alignment...")
    params = {
        "path": "mutable/test_manifest.yaml",
        "content": """
id: test_id
name: Test Name
entrypoint: test:run
kind: external
domain: maintenance
risk_level: low
"""
    }
    # These 6 keys should now pass
    res = fs_write_file(params)
    print(f"Manifest Result: {res.get('status')} - {res.get('error', 'No Error')}")

    # 2. Test Self-healing Lint
    print("\nTesting Self-healing Lint...")
    params = {
        "path": "mutable/test_healing.py",
        "content": "import json\\ndef run():\\n    print('hello')\\n"
    }
    res = fs_write_file(params)
    print(f"Healing Result: {res.get('status')} - {res.get('result', 'No Result')}")
    if res.get('status') == 'ok':
        content = Path("mutable/test_healing.py").read_text()
        print(f"Healed Content: {repr(content)}")

if __name__ == "__main__":
    test()
