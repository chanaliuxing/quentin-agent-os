import os
import sys
from pathlib import Path

# Add quentin to sys.path
sys.path.append(os.getcwd())

from quentin.tools.filesystem import fs_write_file

def test_yaml_deadlock_fixed():
    print("--- Testing YAML Deadlock Fix Verification ---")
    
    # Path to a manifest file
    manifest_path = "mutable/manifest.yaml"
    
    # Ensure it doesn't exist
    p = Path(manifest_path)
    if p.exists():
        p.unlink()
    
    # Content with invalid YAML (indentation error)
    invalid_yaml_content = """
id: "test_plugin"
name: "Test Plugin"
description: "A test plugin"
entrypoint: "logic:run"
kind: "external"
domain: "extensions"
risk_level: "low"
output_trust: "untrusted"
permissions:
- "read_file"
  - "invalid_indent"
"""
    
    params = {
        "path": manifest_path,
        "content": invalid_yaml_content
    }
    
    print(f"Attempting to write invalid YAML to {manifest_path}...")
    result = fs_write_file(params)
    
    print(f"Result Status: {result.get('status')}")
    print(f"Result Error: {result.get('error')}")
    print(f"Result Hint: {result.get('hint')}")
    
    # Check if file was physically written
    if p.exists():
        print(f"FAILED: FILE WAS PHYSICALLY WRITTEN to {manifest_path}")
        p.unlink()
        return False
    else:
        print(f"SUCCESS: FILE WAS NOT WRITTEN to {manifest_path}")

    # Expected behavior:
    # status: "error"
    # error: contains YAML parse error
    # hint: contains specific YAML advice
    
    if result.get('status') == "error" and "YAML" in result.get('error', ''):
        print("\nCONFIRMED: Hard Validation (status: error) is working.")
        if "HINT: Indentation mismatch" in result.get('hint', ''):
             print("CONFIRMED: Enhanced Semantic Hinting is working.")
             return True
        else:
             print(f"HINT NOT AS EXPECTED: {result.get('hint')}")
             return False
    else:
        print(f"\nFAILED: Status is {result.get('status')}, expected 'error'.")
        return False

if __name__ == "__main__":
    # Ensure mutable exists
    os.makedirs("mutable", exist_ok=True)
    success = test_yaml_deadlock_fixed()
    if success:
        print("\nALL CHECKS PASSED.")
        sys.exit(0)
    else:
        print("\nSOME CHECKS FAILED.")
        sys.exit(1)
