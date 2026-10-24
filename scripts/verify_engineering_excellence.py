import asyncio
import os
import json
import time
from pathlib import Path
from quentin.bootstrap.container import Container
from quentin.tools.filesystem import fs_write_file, fs_search_replace
from quentin.tools.shell import shell_run_command
from quentin.infra.concurrency.cancellation import CancellationToken

async def test_all_modules():
    print("=== STARTING ARCHITECTURE VERIFICATION ===")
    repo_root = Path(".").resolve()
    container = Container(repo_root=repo_root)

    # 1. 测试空间感知 (SA)
    print("\n[1/7] Testing Spatial Awareness...")
    snapshot = container.cognitive_loop._get_environment_snapshot()
    # Check if key folders are present in the snapshot string
    if "quentin/" in snapshot.lower() or "quentin" in snapshot:
        print("✅ SA: Environment snapshot generated correctly.")
    else:
        print(f"❌ SA: Snapshot failed or incomplete. Preview: {snapshot[:100]}")

    # 2. 测试路径自愈 (PH)
    print("\n[2/7] Testing Path Correction Hook...")
    # 模拟一个错误的路径 'qentin/kernel/safety.py'
    hook = container.tool_manager._before_hooks[0]
    result = hook("fs.read_file", {"path": "qentin/kernel/safety.py"}, None)
    if result["params"]["path"] == "quentin/kernel/safety.py":
        print("✅ PH: Hallucinated path 'qentin/' auto-corrected to 'quentin/'.")
    else:
        print(f"❌ PH: Correction failed. Got: {result['params']['path']}")

    # 3. 测试语法预检 (LoW)
    print("\n[3/7] Testing Lint-on-Write...")
    bad_code = "def error():\n    print('unclosed quote"
    res = fs_write_file({"path": "tests/temp_syntax_error.py", "content": bad_code})
    if res["status"] == "error" and "Syntax Error" in res["error"]:
        print("✅ LoW: Successfully caught invalid Python syntax.")
    else:
        print(f"❌ LoW: Failed to catch syntax error. Result: {res}")

    # 4. 测试手术级编辑 (SR)
    print("\n[4/7] Testing Surgical Search-Replace...")
    test_file = repo_root / "tests" / "temp_sr_test.py"
    test_file.write_text("class Test:\n    def run(self):\n        pass", encoding="utf-8")
    res = fs_search_replace({"path": "tests/temp_sr_test.py", "old_string": "pass", "new_string": "print('ok')"})
    if res["status"] == "ok" and "print('ok')" in test_file.read_text():
        print("✅ SR: Successfully performed surgical replacement.")
    else:
        print(f"❌ SR: Replacement failed. Result: {res}")
    if test_file.exists(): test_file.unlink()

    # 5. 测试非交互守卫 (Guard)
    print("\n[5/7] Testing Non-Interactive Guard...")
    res = shell_run_command({"command": "nano test.txt"})
    if res["status"] == "error" and "blocked" in res["error"]:
        print("✅ Guard: Blocked interactive 'nano' command.")
    else:
        print(f"❌ Guard: Failed to block interactive command.")

    # 6. 测试取消信号 (Abort)
    print("\n[6/7] Testing Abort Signal...")
    token = CancellationToken()
    # 启动一个耗时任务并取消
    async def run_and_cancel():
        loop = asyncio.get_running_loop()
        task = loop.run_in_executor(None, lambda: shell_run_command({"command": "sleep 10"}, type('Context', (), {'cancel_token': token})))
        await asyncio.sleep(0.5)
        token.cancel(reason="test abort")
        return await task

    res = await run_and_cancel()
    if res.get("aborted"):
        print("✅ Abort: Successfully terminated long-running process via token.")
    else:
        print(f"❌ Abort: Failed to terminate process. Result: {res}")

    # 7. 测试凭据轮转 (Auth)
    print("\n[7/7] Testing Auth Profile Rotation...")
    from quentin.llm.auth_profiles import AuthProfile, get_auth_manager
    mgr = get_auth_manager()
    mgr.add_profile(AuthProfile(profile_id="key1", api_key="sk-1", provider="openai"))
    mgr.report_result("key1", success=False, error_code=429)
    best = mgr.get_best_profile("openai")
    if best is None:
        print("✅ Auth: Profile 'key1' correctly cooled down after 429.")
    else:
        print(f"❌ Auth: Cooldown failed. Best: {best.profile_id}")

    print("\n=== VERIFICATION COMPLETE ===")

if __name__ == "__main__":
    asyncio.run(test_all_modules())