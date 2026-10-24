import sys
import os
from unittest.mock import MagicMock, patch
from scripts.brain_autoloop import _run_prompt_command, _is_valid_gemini_session

def test_session_validation():
    print("Testing Session Validation Logic...")
    cases = [
        ("latest", True),
        ("1", True),
        ("123", True),
        ("a0332e2e-8e0e-4e04-b992-858659123b34", True),
        ("session_evolve_v7_1771572385", False),
        ("invalid_chars_!", False),
        ("", False),
        (None, False),
    ]
    for sid, expected in cases:
        res = _is_valid_gemini_session(sid)
        print(f"  ID: {sid} -> Valid: {res} (Expected: {expected})")
        assert res == expected

def test_command_reconstruction():
    print("\nTesting Command Reconstruction...")
    # We mock subprocess.Popen to see what command is actually being built
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value.communicate.return_value = ("ok", "")
        mock_popen.return_value.returncode = 0
        
        # Case 1: Valid UUID
        _run_prompt_command("gemini -p {prompt}", "hello", timeout_s=10, session_id="a0332e2e-8e0e-4e04-b992-858659123b34")
        args = mock_popen.call_args[0][0]
        print(f"  Valid UUID Command: {args}")
        assert "--resume a0332e2e-8e0e-4e04-b992-858659123b34" in args

        # Case 2: Invalid Custom String
        _run_prompt_command("gemini -p {prompt}", "hello", timeout_s=10, session_id="session_v7_bad")
        args = mock_popen.call_args[0][0]
        print(f"  Invalid String Command: {args}")
        assert "--resume" not in args

        # Case 3: Numeric index
        _run_prompt_command("gemini -p {prompt}", "hello", timeout_s=10, session_id="5")
        args = mock_popen.call_args[0][0]
        print(f"  Numeric Index Command: {args}")
        assert "--resume 5" in args

if __name__ == "__main__":
    try:
        test_session_validation()
        test_command_reconstruction()
        print("\n✅ ALL SESSION TESTS PASSED")
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
