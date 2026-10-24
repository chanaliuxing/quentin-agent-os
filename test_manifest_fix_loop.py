import os
import sys
import yaml
from pathlib import Path

# Add project root to sys.path
repo_root = Path(__file__).parent.resolve()
sys.path.insert(0, str(repo_root))

from quentin.tools.filesystem import fs_write_file

def test_manifest_loop_reproduction():
    test_dir = Path("extensions/tools/temp_test_manifest")
    test_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = test_dir / "manifest.yaml"
    manifest_rel_path = "extensions/tools/temp_test_manifest/manifest.yaml"
    
    # Invalid manifest content (missing 'kind', using 'kinds' instead)
    invalid_content = """
id: "test_plugin"
name: "Test Plugin"
description: "A test plugin"
entrypoint: "logic:run"
kinds: "external"
domain: "extensions"
risk_level: "low"
output_trust: "untrusted"
permissions: []
"""
    
    print(f"Attempting to write invalid manifest to {manifest_rel_path}...")
    params = {"path": manifest_rel_path, "content": invalid_content}
    result = fs_write_file(params)
    
    print(f"Result: {result.get('status')}")
    print(f"Error: {result.get('error')}")
    
    if manifest_path.exists():
        print("FAILURE: manifest.yaml still exists (it should have been renamed).")
    else:
        print("SUCCESS: manifest.yaml was renamed/removed from its original location.")

    # Check if a .invalid file exists
    invalid_manifest_path = manifest_path.with_suffix(".yaml.invalid")
    if invalid_manifest_path.exists():
        print(f"SUCCESS: {invalid_manifest_path.name} exists as expected.")
        # Verify content
        with open(invalid_manifest_path, "r") as f:
            content = f.read()
            if "kinds: \"external\"" in content:
                print("SUCCESS: .invalid file content is correct.")
            else:
                print("FAILURE: .invalid file content is incorrect.")
    else:
        print(f"FAILURE: {invalid_manifest_path.name} does not exist.")

def test_mkdir_reproduction():
    from quentin.tools.middleware.filesystem import SmartFilesystemMiddleware
    from quentin.tools.manager import ToolCallContext
    
    middleware = SmartFilesystemMiddleware(repo_root=str(repo_root))
    
    # Simulate mkdir on a .py file
    params = {"path": "quentin/tools/test_file.py"}
    ctx = ToolCallContext()
    
    print("\nTesting mkdir on a .py file...")
    outcome = middleware.before(tool_name="mkdir", params=params, ctx=ctx)
    
    if outcome.blocked:
        print(f"SUCCESS: mkdir on .py file was blocked. Reason: {outcome.reason}")
    else:
        print("FAILURE: mkdir on .py file was NOT blocked.")

async def test_mkdir_via_tool_manager():
    from quentin.tools.manager import ToolManager, ToolCallRequest, ToolCallContext
    from quentin.tools.packs.filesystem_pack import FileSystemToolPack
    
    tm = ToolManager()
    tm.register_pack(FileSystemToolPack())
    # Note: ToolManager will automatically load the sanitizer as seen in its code
    
    print("\nTesting mkdir on a .py file via ToolManager...")
    req = ToolCallRequest(tool_name="mkdir", payload={"path": "quentin/tools/test_file.py"})
    ctx = ToolCallContext()
    
    result = await tm.call_tool(req, ctx=ctx)
    
    if not result.success:
        print(f"SUCCESS: mkdir via ToolManager was blocked. Error: {result.error}")
        print(f"Hint: {result.output.get('hint')}")
    else:
        print("FAILURE: mkdir via ToolManager was NOT blocked.")

if __name__ == "__main__":
    import asyncio
    try:
        test_manifest_loop_reproduction()
        test_mkdir_reproduction()
        asyncio.run(test_mkdir_via_tool_manager())
    finally:
        # Cleanup
        manifest_path = Path("extensions/tools/temp_test_manifest/manifest.yaml")
        if manifest_path.exists():
            manifest_path.unlink()
        invalid_manifest_path = manifest_path.with_suffix(".yaml.invalid")
        if invalid_manifest_path.exists():
            invalid_manifest_path.unlink()
        test_dir = Path("extensions/tools/temp_test_manifest")
        if test_dir.exists():
            try:
                test_dir.rmdir()
            except Exception:
                pass
