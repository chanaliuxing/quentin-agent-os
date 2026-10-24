import sys
import os
import time
from unittest.mock import MagicMock, patch
from scripts.brain_autoloop import _run_prompt_command

def test_recovery_retry_mechanism():
    print("Testing Recovery Retry Mechanism...")
    
    # We want to simulate a failure that triggers retries
    with patch("subprocess.Popen") as mock_popen:
        # Configure the mock to simulate a Quota Exhausted error
        mock_proc = MagicMock()
        mock_proc.returncode = 429
        mock_proc.communicate.return_value = ("", "rate limit exceeded")
        mock_popen.return_value = mock_proc
        
        # We also need to patch time.sleep to avoid actually waiting
        with patch("time.sleep") as mock_sleep:
            res = _run_prompt_command(
                "gemini -p {prompt}", 
                "original prompt", 
                timeout_s=10, 
                session_id="a0332e2e-8e0e-4e04-b992-858659123b34"
            )
            
            # Check if it tried 5 times
            print(f"  Total Attempts: {mock_popen.call_count}")
            assert mock_popen.call_count == 5
            
            # Check if wait times were exponential (60, 120, 240, 480)
            sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
            print(f"  Sleep Intervals: {sleep_calls}")
            assert sleep_calls == [60, 120, 240, 480, 960]
            
            # Check if input_data changed to "CONTINUE" after attempt 3
            # In our implementation, attempt 3 is index 2. So for attempts 4 and 5, it should be the recovery prompt.
            # communicate is called inside the loop. Let's check its arguments.
            communicate_calls = [call[1].get("input") for call in mock_proc.communicate.call_args_list]
            print(f"  Input Data per turn: {communicate_calls[:5]}")
            assert "original prompt" in communicate_calls[0]
            assert "CONTINUE" in communicate_calls[3]
            assert "CONTINUE" in communicate_calls[4]

if __name__ == "__main__":
    try:
        test_recovery_retry_mechanism()
        print("\n✅ RECOVERY LOGIC TEST PASSED")
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        # Print more info for debugging
        import traceback
        traceback.print_exc()
        sys.exit(1)
