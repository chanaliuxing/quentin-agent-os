import os
import json
import yaml
import sys
from pathlib import Path
from quentin.tools.filesystem import fs_write_file

def test_atomic_write_failure():
    print("Testing atomic write failure for manifest.yaml...")
    path = "mutable/test_manifest.yaml"
    content = """
id: "test_plugin"
name: "Test Plugin"
entrypoint: "logic:run"
kinds: "external"  # Typo here: should be 'kind'
domain: "extensions"
risk_level: "low"
"""
    # Ensure file doesn't exist
    if os.path.exists(path):
        os.remove(path)
    
    res = fs_write_file({"path": path, "content": content})
    print(f"Result: {res['status']}")
    
    file_exists = os.path.exists(path)
    print(f"File exists after error: {file_exists}")
    
    if res['status'] == 'error' and file_exists:
        print("FAIL: File should NOT exist if validation failed (Atomic Write violation)")
    elif res['status'] == 'error' and not file_exists:
        print("SUCCESS: File deleted after validation failure")
    else:
        print(f"Unexpected status: {res['status']}")

def test_pre_sensing_logic():
    # This is harder to test in isolation without full Loop context, 
    # but we can check if the prompt in loop_orchestration.py contains the penalty instruction.
    print("\nChecking pre-sensing prompt for penalty instruction...")
    with open("quentin/cognitive/loop_orchestration.py", "r") as f:
        content = f.read()
    
    if "confidence must be below 0.5" in content.lower():
        print("SUCCESS: Penalty instruction found in prompt")
    else:
        print("FAIL: Penalty instruction NOT found in pre-sensing prompt")

def test_fuzzy_matching_feedback():
    print("\nTesting fuzzy matching feedback for manifest.yaml...")
    path = "mutable/fuzzy_manifest.yaml"
    content = """
id: "test_plugin"
name: "Test Plugin"
entrypoint: "logic:run"
kinds: "external"  # Typo here: should be 'kind'
domain: "extensions"
risk_level: "low"
"""
    # Ensure file doesn't exist
    if os.path.exists(path):
        os.remove(path)
    
    res = fs_write_file({"path": path, "content": content})
    print(f"Full Result: {res}")
    
    if "Found key 'kinds', did you mean 'kind'?" in res.get('error', ''):
        print("SUCCESS: Fuzzy matching hint found in error message")
    else:
        print("FAIL: Fuzzy matching hint NOT found in error message")

if __name__ == "__main__":
    test_atomic_write_failure()
    test_fuzzy_matching_feedback()
    test_pre_sensing_logic()
