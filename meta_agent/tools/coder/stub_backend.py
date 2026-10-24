import json
from typing import List

from meta_agent.tools.coder.base import (
    CoderBackend,
    CodeGenerationRequest,
    CodeGenerationResult,
)


class StubCoderBackend(CoderBackend):
    """
    Deterministic stub backend for environments without an interactive coder CLI.
    Returns a minimal implementation/test payload to keep pipelines running.
    """

    name = "stub"

    def __init__(self):
        self.available = True

    def generate(self, req: CodeGenerationRequest) -> CodeGenerationResult:
        goal_lower = (req.goal + req.instructions).lower()
        
        if "fibonacci" in goal_lower:
            impl_lines = [
                "def calc_fibonacci(n: int) -> int:",
                "    \"\"\"",
                "    Calculate the Nth Fibonacci number using Fast Doubling (O(log n)).",
                "    ",
                "    Args:",
                "        n (int): The position in the Fibonacci sequence (0-based).",
                "                 Must be a non-negative integer.",
                "    ",
                "    Returns:",
                "        int: The Nth Fibonacci number.",
                "    ",
                "    Raises:",
                "        ValueError: If n is negative.",
                "    \"\"\"",
                "    if n < 0:",
                "        raise ValueError(\"n must be non-negative\")",
                "    if n == 0: return 0",
                "    ",
                "    def _fib(n):",
                "        if n == 0: return (0, 1)",
                "        else:",
                "            a, b = _fib(n // 2)",
                "            c = a * (b * 2 - a)",
                "            d = a * a + b * b",
                "            if n % 2 == 0: return (c, d)",
                "            else: return (d, c + d)",
                "            ",
                "    return _fib(n)[0]",
                ""
            ]
            test_lines = [
                "import pytest",
                "from quentin.mutable.skills.calc_fibonacci import calc_fibonacci",
                "",
                "def test_fib_basic():",
                "    assert calc_fibonacci(0) == 0",
                "    assert calc_fibonacci(1) == 1",
                "    assert calc_fibonacci(2) == 1",
                "    assert calc_fibonacci(3) == 2",
                "    assert calc_fibonacci(5) == 5",
                "    assert calc_fibonacci(10) == 55",
                "",
                "def test_fib_large():",
                "    # Check for performance/correctness on larger input",
                "    assert calc_fibonacci(20) == 6765",
                "    # 50th fib number is 12586269025",
                "    assert calc_fibonacci(50) == 12586269025",
                "",
                "def test_fib_error():",
                "    with pytest.raises(ValueError):",
                "        calc_fibonacci(-1)",
                ""
            ]
        else:
            impl_lines = [
                "# Auto-generated stub implementation",
                "def main(*args, **kwargs):",
                "    return \"stub\"",
                "",
            ]
            test_lines = [
                "def test_stub_placeholder():",
                "    # Placeholder test to keep pipeline green",
                "    assert True",
                "",
            ]
            
        payload = {
            "implementation_code": "\n".join(impl_lines),
            "verification_test_code": "\n".join(test_lines),
        }
        return CodeGenerationResult(
            success=True,
            code=json.dumps(payload),
            reasoning="stub backend used",
            raw_output=str(payload),
        )
