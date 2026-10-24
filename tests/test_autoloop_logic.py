import unittest
from unittest.mock import patch, MagicMock, ANY
import sys
import os
from pathlib import Path

# Add project root to sys.path so we can import the script
sys.path.append(os.getcwd())

# Correct imports for the robust script version
from scripts.brain_autoloop import main, _run_command, _run_prompt_command, LoopConfig, run_loop

class TestBrainAutoLoop(unittest.TestCase):

    def setUp(self):
        # Create dummy prompt files to avoid FileNotFoundError
        Path("prompts/autoloop").mkdir(parents=True, exist_ok=True)
        # We need actual content for _load_template
        Path("prompts/autoloop/analyzer.md").write_text("Analyzer Prompt Content")
        Path("prompts/autoloop/fixer.md").write_text("Fixer Prompt Content")
        
        # Create dummy web_search dir to test deletion
        Path("extensions/tools/web_search").mkdir(parents=True, exist_ok=True)

    @patch("scripts.brain_autoloop.subprocess.run")
    @patch("scripts.brain_autoloop.subprocess.Popen")
    @patch("scripts.brain_autoloop.shutil.rmtree")
    def test_run_loop_flow(self, mock_rmtree, mock_popen, mock_run):
        # Setup mocks
        
        # Mock _run_command (subprocess.run) - for verify and git status
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Success: True"
        mock_run.return_value.stderr = ""
        
        # Mock _run_prompt_command (subprocess.Popen) - for Gemini
        proc_mock = MagicMock()
        proc_mock.communicate.return_value = ("GEMINI_OUTPUT", "")
        proc_mock.returncode = 0
        mock_popen.return_value = proc_mock

        # Config
        cfg = LoopConfig(
            max_iterations=1,
            session_id="test-session-123456789012345", # > 20 chars
            analyzer_command="gemini -p {prompt}",
            fixer_command="gemini -p {prompt}"
        )

        # Run
        run_loop(cfg)

        # Assertions
        
        # 1. Check Artifact Cleaning
        # Should have called rmtree on extensions/tools/web_search
        self.assertTrue(mock_rmtree.called, "Artifact directory should be cleaned")
        args, _ = mock_rmtree.call_args
        self.assertTrue(str(args[0]).endswith("web_search"), f"Should delete web_search, got {args[0]}")

        # 2. Check Verify Call
        # We check if verify_system.py was called
        verify_called = False
        for call in mock_run.call_args_list:
            if "verify_system.py" in str(call):
                verify_called = True
        self.assertTrue(verify_called, "verify_system.py should be called")

        # 3. Check Gemini Analyzer Call (via Popen)
        analyzer_call_found = False
        fixer_call_found = False
        
        for call in mock_popen.call_args_list:
            cmd_args = call[0][0] # cmd_args is the first arg
            print(f"DEBUG: Captured Popen cmd: {cmd_args}")
            # Check session ID in command
            if "test-session-123456789012345" in str(cmd_args):
                # Now check prompt content which is passed via stdin in communicate()
                # Since mock_popen returns proc_mock, we check proc_mock.communicate calls
                # But wait, we iterate over Popen calls. We need to match this Popen call to a communicate call.
                # Since we use the same mock instance for all calls, we can just check if ANY communicate call had the content.
                pass
        
        # Check if prompts were sent via communicate
        analyzer_prompt_sent = False
        fixer_prompt_sent = False
        print(f"DEBUG: Communicate calls: {proc_mock.communicate.call_args_list}")
        for comm_call in proc_mock.communicate.call_args_list:
            input_data = comm_call.kwargs.get('input') or (comm_call.args[0] if comm_call.args else None)
            if input_data and "Analyzer Prompt Content" in input_data:
                analyzer_prompt_sent = True
            if input_data and "Fixer Prompt Content" in input_data:
                fixer_prompt_sent = True
        
        self.assertTrue(analyzer_prompt_sent, "Analyzer Prompt should be sent via stdin")
        self.assertTrue(fixer_prompt_sent, "Fixer Prompt should be sent via stdin")

    def tearDown(self):
        # Clean up dummy files
        import shutil
        if Path("prompts/autoloop").exists():
            shutil.rmtree("prompts/autoloop")
        if Path("extensions/tools/web_search").exists():
            shutil.rmtree("extensions/tools/web_search")

if __name__ == "__main__":
    unittest.main()
