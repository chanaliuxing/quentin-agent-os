from pathlib import Path
from quentin.skills.manager import SkillManager
from quentin.skills.backends.base import get_skill_backend_registry

def test_backends_smoke():
    repo_root = Path(".").resolve()
    mgr = SkillManager(repo_root=repo_root)
    
    print("Backend Registry initialized.")
    backends = mgr.backend_registry.list_backends()
    print(f"Registered backends: {[b.id for b in backends]}")
    
    # Check if we have at least legacy, sop, exec backends
    expected = {"legacy_registry", "filesystem_sop", "exec_plugin"}
    found = {b.id for b in backends}
    assert expected.issubset(found), f"Missing backends: {expected - found}"

    # Try loading a known SOP (e.g., from existing ones)
    # quentin/mutable/skills/write_patch.md usually exists
    known_sop = "write_patch"
    print(f"Testing load_sop_prompt for: {known_sop}")
    text = mgr.load_sop_prompt(known_sop)
    if text:
        print(f"Loaded SOP text for {known_sop}, length: {len(text)}")
    else:
        print(f"Failed to load SOP text for {known_sop}")
        # Try listing to see what we found
        print("Listing discovered markdown skills:")
        for s in mgr.list_markdown_skills():
            print(f"- {s.get('skill_id')}")

    # Try loading an exec skill (if any exist)
    exec_plugins = mgr.list_exec_skill_plugins()
    if exec_plugins:
        first_exec = exec_plugins[0]
        sid = first_exec["skill_id"]
        print(f"Testing load_exec_skill_callable for: {sid}")
        fn, _ = mgr.load_exec_skill_callable(sid)
        assert fn is not None, f"Failed to load exec callable for {sid}"
        print("Loaded exec callable successfully.")
    else:
        print("No exec skills found to test load_exec_skill_callable.")

if __name__ == "__main__":
    try:
        test_backends_smoke()
        print("Skill Backends Smoke Test PASSED")
    except Exception as e:
        print(f"Skill Backends Smoke Test FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
