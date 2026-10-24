from __future__ import annotations
import os
import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("RegressionTest")

async def test_memory_fabric():
    print("\n--- [TEST] Memory Fabric (RRF & KG) ---")
    from quentin.memory.fabric import MemoryFabric
    fabric = MemoryFabric(repo_root=".")
    
    # 1. Test Atomic Remember with Scrubbing
    rec = fabric.remember_atomic(
        content="The secret key is sk-1234567890abcdef1234567890abcdef",
        source="test_source",
        metadata={"path": "/configs/secret.env"}
    )
    print(f"✅ Scrubbing: {rec.content}")
    assert "[[REDACTED_OPENAI_KEY]]" in rec.content

async def test_tool_governance():
    print("\n--- [TEST] Tool Governance & Security ---")
    from quentin.tools.manager import ToolManager
    from quentin.infra.security.network_policy import NetworkPolicyEnforcer
    
    mgr = ToolManager()
    mgr.set_repo_root(".")
    
    # 1. Test Network Policy
    assert NetworkPolicyEnforcer.is_allowed("https://github.com") == True
    assert NetworkPolicyEnforcer.is_allowed("http://169.254.169.254") == False
    print("✅ Network Policy blocking SSRF.")

    # 2. Test Path Sensitivity
    from quentin.infra.security.sensitivity_classifier import SensitivityClassifier
    assert SensitivityClassifier.should_restrict_execution({"path": ".ssh/id_rsa"}) == True
    print("✅ Path Sensitivity detected critical folder.")

async def test_terminal_processing():
    print("\n--- [TEST] Terminal ANSI & Echo Sanitization ---")
    from quentin.infra.terminal.ansi_sanitizer import AnsiSanitizer
    from quentin.utils.echo_sanitizer import EchoSanitizer
    
    # 1. Test ANSI Cleaning
    dirty = "\x1b[31mError\x1b[0m\rFixed"
    clean = AnsiSanitizer.sanitize(dirty)
    print(f"✅ ANSI Sanitized: {repr(clean)}")
    assert "Fixed" in clean
    assert "\x1b" not in clean

    # 2. Test Echo Filtering
    san = EchoSanitizer()
    san.register_command("ls -la")
    assert san.is_echo("ls -la") == True
    assert san.is_echo("user@host:~$ ls -la") == True
    assert san.is_echo("total 40") == False
    print("✅ PTY Echo identified and suppressed.")

async def test_billing_and_cooldown():
    print("\n--- [TEST] Billing & Auth Cooldown ---")
    from quentin.infra.billing.balance_manager import balance_manager
    from quentin.llm.auth_profiles import calculate_cooldown_ms
    
    # 1. Test Streaming Billing
    balance_manager.set_balance("test_user", 0.0001) # Very low balance
    can_deduct = balance_manager.deduct_realtime("test_user", tokens=500)
    print(f"✅ Balance Guard: {can_deduct} (Expected False)")
    assert can_deduct == False

    # 2. Test Cooldown
    cd = calculate_cooldown_ms(error_count=2, provider="openai")
    print(f"✅ Cooldown Logic: {cd}ms for 2 failures.")
    assert cd > 60000

async def main():
    print("🚀 Starting Project Taylor Regression Suite...")
    try:
        await test_memory_fabric()
        await test_tool_governance()
        await test_terminal_processing()
        await test_billing_and_cooldown()
        print("\n✨ ALL CORE SURGERIES VERIFIED. SYSTEM IS STABLE. ✨")
    except Exception as e:
        print(f"\n❌ REGRESSION FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
