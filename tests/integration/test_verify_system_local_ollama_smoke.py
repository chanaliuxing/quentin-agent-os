# tests/integration/test_verify_system_local_ollama_smoke.py
import os
import subprocess
import pytest
import time

def is_ollama_available():
    base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434")
    import httpx
    try:
        resp = httpx.get(f"{base_url}/api/tags", timeout=2.0)
        return resp.status_code == 200
    except Exception:
        return False

@pytest.mark.skipif(not is_ollama_available(), reason="Ollama not available")
def test_verify_system_local_ollama_smoke():
    # Run verify_system.py and capture output
    # We use a timeout to prevent it from running forever in case of issues
    try:
        env = os.environ.copy()
        # We might want to use a mock goal if it supports it, 
        # but the plan says run verify_system.py as is.
        
        start_time = time.time()
        process = subprocess.Popen(
            ["python3", "verify_system.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env
        )
        
        # We don't necessarily need it to finish if it's long, 
        # but we want to see it starts and doesn't crash immediately.
        # Let's give it some time to show "Memory Store Active" and maybe some logs.
        output = ""
        for line in process.stdout:
            print(line, end="") # Stream to console for visibility
            output += line
            if "Memory Store Active" in line:
                # Good sign, it's starting
                pass
            if time.time() - start_time > 300: # 5 minutes smoke test
                process.terminate()
                break
        
        process.wait(timeout=20)
        
        assert "Memory Store Active" in output
        assert "/api/generate/api/generate" not in output
        assert "/api/chat/api/chat" not in output
        
    except Exception as e:
        pytest.fail(f"verify_system.py smoke test failed: {e}")
