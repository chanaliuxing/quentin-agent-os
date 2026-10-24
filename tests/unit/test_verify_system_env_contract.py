from pathlib import Path

def test_verify_system_env_contract():
    # We want to verify that verify_system.py respect existing env vars.
    # We'll run it with a special flag if possible, or just check its source.
    # Since we can't easily run the whole verify_system.py without it doing things,
    # we can check if it has a dry-run or just test the logic by importing it if possible.
    
    # Actually, verify_system.py is usually a script. Let's see if it's importable.
    # If not, we can test by running it in a subprocess and checking env (though that's hard).
    
    verify_system = Path(__file__).resolve().parents[2] / "verify_system.py"
    lines = verify_system.read_text(encoding="utf-8").splitlines()
    
    # L18: if not os.getenv("LLM_BASE_URL"):
    # L19: os.environ["LLM_BASE_URL"] = "http://localhost:11434"
    
    found_gate = False
    for line in lines:
        if 'if not os.getenv("LLM_BASE_URL")' in line:
            found_gate = True
            break
    
    assert found_gate, "verify_system.py should check if LLM_BASE_URL is already set before overriding"

def test_verify_system_runs_preflight():
    # Check if verify_system.py has some basic structure we expect
    verify_system = Path(__file__).resolve().parents[2] / "verify_system.py"
    content = verify_system.read_text(encoding="utf-8")
    
    assert "LLM_BASE_URL" in content
    assert "Memory Store" in content or "MemoryFabric" in content
