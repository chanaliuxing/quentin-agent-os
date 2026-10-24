import os
from quentin.tools.filesystem import fs_write_file

def test_manifest_soft_validation():
    print("Testing Manifest Soft Validation...")
    
    path = "mutable/test_manifest.yaml"
    if os.path.exists(path):
        os.remove(path)
    
    # Minimal manifest content (missing many fields)
    content = "id: 'test_plugin'\nname: 'Test Plugin'\n"
    
    params = {
        "path": path,
        "content": content
    }
    
    result = fs_write_file(params)
    
    print(f"Result Status: {result.get('status')}")
    print(f"Result Warning: {result.get('warning')}")
    
    file_exists = os.path.exists(path)
    print(f"File exists on disk: {file_exists}")
    
    if result.get("status") == "ok" and file_exists:
        print("✅ PASS: Manifest written successfully.")
    else:
        print("❌ FAIL: Manifest write failed or file missing.")

if __name__ == "__main__":
    test_manifest_soft_validation()
