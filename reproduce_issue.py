import os
import sys
import yaml
import shutil
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent.absolute()
sys.path.insert(0, str(project_root))

from quentin.tools.filesystem import fs_write_file
from quentin.tools.shell import shell_mkdir
from quentin.cognitive.loop_context_helpers import generate_sensing_report
from quentin.infra.tools.sanitizer import sanitizer

def setup():
    # Ensure directory exists and clean files
    os.makedirs("extensions/tools/test_plugin", exist_ok=True)
    os.makedirs("extensions/tools/web_search", exist_ok=True)
    
    files_to_clean = [
        "extensions/tools/test_plugin/manifest.yaml",
        "extensions/tools/test_escaped.py"
    ]
    for f in files_to_clean:
        if os.path.exists(f):
            os.remove(f)

def test_manifest_discrepancy():
    print("Testing manifest discrepancy...")
    manifest_6_keys = {
        "id": "test_plugin",
        "name": "Test Plugin",
        "entrypoint": "logic:run",
        "kind": "external",
        "domain": "extensions",
        "risk_level": "low"
    }
    content = yaml.dump(manifest_6_keys)
    path = "extensions/tools/test_plugin/manifest.yaml"
    
    # Check fs_write_file (expected to fail currently)
    res = fs_write_file({"path": path, "content": content})
    print(f"fs_write_file result status: {res['status']}")
    if res['status'] == 'error':
        print(f"Error message: {res.get('error')}")

    # Check sensing report
    report = generate_sensing_report(repo_root=project_root, task=None, focus_paths=[path])
    found = False
    for item in report.get("evidence", []):
        if item.get("path") == path:
            found = True
            print(f"File exists in report: {item.get('exists')}")
            print(f"Sensing report status: {item.get('functional_check', {}).get('status')}")
            print(f"Sensing report error: {item.get('functional_check', {}).get('error')}")
    if not found:
        print("File NOT found in sensing report evidence")

def test_mkdir_rigidity():
    print("\nTesting mkdir rigidity...")
    path = "extensions/tools/web_search/logic.py"
    
    # Test sanitizer
    try:
        sanitizer.sanitize("mkdir", {"path": path})
        print("Sanitizer allowed it (unexpected)")
    except ValueError as e:
        print(f"Sanitizer blocked it: {e}")

    # Test shell_mkdir
    res = shell_mkdir({"path": path})
    print(f"shell_mkdir status: {res['status']}")
    if res['status'] == 'error':
        print(f"Error message: {res.get('error')}")

def test_syntax_healing():
    print("\nTesting syntax healing (escaped newlines)...")
    content = "def test():\\n    print('hello')"
    path = "extensions/tools/test_escaped.py"
    
    res = fs_write_file({"path": path, "content": content})
    print(f"fs_write_file status: {res['status']}")
    if res['status'] == 'error':
        print(f"Error message: {res.get('error')}")

if __name__ == "__main__":
    setup()
    test_manifest_discrepancy()
    test_mkdir_rigidity()
    test_syntax_healing()
