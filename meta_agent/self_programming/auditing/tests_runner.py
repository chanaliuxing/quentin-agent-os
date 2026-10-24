import subprocess
from typing import List
from .templates import Evidence


class TestEvidenceCollector:
    """
    Optional test runner for requirements that declare tests_expected.
    Disabled by default (to be used in nightly or explicit flag).
    """

    def __init__(self, timeout: int = 300):
        self.timeout = timeout
        self.was_run = False

    def run(self, tests_expected: List[str]) -> List[Evidence]:
        evidences: List[Evidence] = []
        if not tests_expected:
            return evidences
        self.was_run = True
        for cmd in tests_expected:
            try:
                proc = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
                if proc.returncode == 0:
                    evidences.append(Evidence("test", "test_pass", 0.5, f"Test passed: {cmd}"))
                else:
                    evidences.append(
                        Evidence(
                            "test",
                            "test_fail",
                            -0.3,
                            f"Test failed ({proc.returncode}): {cmd} stderr={proc.stderr[:200]}",
                        )
                    )
            except Exception as e:
                evidences.append(Evidence("test", "test_error", -0.3, f"Test error: {cmd} err={e}"))
        return evidences
