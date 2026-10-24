from typing import Any, Dict
import unittest

class MockResult:
    def __init__(self, success: bool):
        self.success = success

class TestStepTermination(unittest.TestCase):
    def test_should_end_after_write(self):
        from quentin.execution.skill_executor import Executor
        
        executor = Executor(repo_root=".")
        
        tool_call = {"tool_name": "fs.write_file", "args": {"path": "test.txt", "content": "hi"}}
        tool_res = MockResult(success=True)
        
        should_end = executor._should_end_step_after_tool_call(
            desc="Write to test.txt",
            tool_call=tool_call,
            tool_res=tool_res
        )
        
        print(f"Should end after write_file: {should_end}")
        self.assertTrue(should_end)

    def test_should_end_after_search_replace(self):
        from quentin.execution.skill_executor import Executor
        executor = Executor(repo_root=".")
        
        tool_call = {"tool_name": "fs.search_replace", "args": {"path": "test.txt", "search": "a", "replace": "b"}}
        tool_res = MockResult(success=True)
        
        should_end = executor._should_end_step_after_tool_call(
            desc="Fix typo",
            tool_call=tool_call,
            tool_res=tool_res
        )
        
        print(f"Should end after search_replace: {should_end}")
        self.assertTrue(should_end)

    def test_should_not_end_after_failed_write(self):
        from quentin.execution.skill_executor import Executor
        executor = Executor(repo_root=".")
        
        tool_call = {"tool_name": "fs.write_file", "args": {"path": "test.txt", "content": "hi"}}
        tool_res = MockResult(success=False)
        
        should_end = executor._should_end_step_after_tool_call(
            desc="Write to test.txt",
            tool_call=tool_call,
            tool_res=tool_res
        )
        
        print(f"Should end after failed write_file: {should_end}")
        self.assertFalse(should_end)

if __name__ == "__main__":
    unittest.main()
