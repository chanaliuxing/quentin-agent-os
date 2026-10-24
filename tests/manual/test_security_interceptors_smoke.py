import os
from pathlib import Path
from quentin.kernel.safety import SafetyKernel
from quentin.kernel.policy import ActionRequest

def test_interceptors():
    print("Testing Security Interceptors...")
    os.environ["QUENTIN_POLICY_INTERCEPTORS"] = "1"
    
    repo_root = Path(".").resolve()
    kernel = SafetyKernel(repo_root=repo_root)
    
    # 1. Test Path Traversal
    print("\nTesting Path Traversal...")
    bad_path_action = ActionRequest.new(
        actor="test",
        action_type="fs_read",
        domain="core",
        environment="sandbox",
        risk_level="low",
        estimated_cost_tokens=0,
        description="Try to read /etc/passwd",
        metadata={"path": "/etc/passwd"}
    )
    res = kernel.guard_action(bad_path_action)
    print(f"Path Traversal result: allow={res.allow}, reason={res.reason}")
    assert res.allow == False
    assert "outside repository root" in res.reason

    # 2. Test Destructive Command
    print("\nTesting Destructive Command...")
    bad_cmd_action = ActionRequest.new(
        actor="test",
        action_type="shell",
        domain="core",
        environment="sandbox",
        risk_level="critical",
        estimated_cost_tokens=0,
        description="Run rm -rf /",
        metadata={"command": "rm -rf /"}
    )
    res = kernel.guard_action(bad_cmd_action)
    print(f"Destructive Command result: allow={res.allow}, reason={res.reason}")
    assert res.allow == False
    assert "Potentially destructive command" in res.reason

    # 3. Test Safe Action
    print("\nTesting Safe Action...")
    safe_action = ActionRequest.new(
        actor="test",
        action_type="fs_read",
        domain="core",
        environment="sandbox",
        risk_level="low",
        estimated_cost_tokens=0,
        description="Read README.md",
        metadata={"path": "README.md"}
    )
    res = kernel.guard_action(safe_action)
    print(f"Safe Action result: allow={res.allow}")
    assert res.allow == True
    
    print("\nSecurity Interceptors check PASSED.")

if __name__ == "__main__":
    try:
        test_interceptors()
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
