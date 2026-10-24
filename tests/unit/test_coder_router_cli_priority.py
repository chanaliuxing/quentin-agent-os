from meta_agent.tools.coder.base import (
    CoderBackend,
    CodeGenerationRequest,
    CodeGenerationResult,
)
from meta_agent.tools.coder.router import CoderRouter


class _FakeBackend(CoderBackend):
    def __init__(self, name: str, *, available: bool = True, success: bool = True):
        self.name = name
        self.available = available
        self._success = success
        self.calls = 0

    def generate(self, req: CodeGenerationRequest) -> CodeGenerationResult:
        self.calls += 1
        return CodeGenerationResult(
            success=self._success,
            code=f"{self.name}-code" if self._success else "",
            reasoning=f"{self.name}-reason",
        )


def _req() -> CodeGenerationRequest:
    return CodeGenerationRequest(
        goal="Implement feature",
        context_files=[],
        instructions="Do it",
    )


def test_auto_cli_prefers_gemini_then_fallback() -> None:
    gemini = _FakeBackend("gemini_cli", success=False)
    codex = _FakeBackend("codex_cli", success=True)
    claude = _FakeBackend("claude_code_cli", success=True)
    stub = _FakeBackend("stub", success=True)
    router = CoderRouter(
        backends={
            "gemini_cli": gemini,
            "codex_cli": codex,
            "claude_code_cli": claude,
            "stub": stub,
        }
    )
    router.default_backend = "auto_cli"

    result = router.generate(_req())
    assert result.success is True
    assert result.code == "codex_cli-code"
    assert gemini.calls == 1
    assert codex.calls == 1
    assert claude.calls == 0
    assert stub.calls == 0


def test_auto_cli_skips_unavailable_backend() -> None:
    gemini = _FakeBackend("gemini_cli", available=False, success=True)
    codex = _FakeBackend("codex_cli", success=True)
    claude = _FakeBackend("claude_code_cli", success=True)
    stub = _FakeBackend("stub", success=True)
    router = CoderRouter(
        backends={
            "gemini_cli": gemini,
            "codex_cli": codex,
            "claude_code_cli": claude,
            "stub": stub,
        }
    )
    router.default_backend = "auto_cli"

    result = router.generate(_req())
    assert result.success is True
    assert result.code == "codex_cli-code"
    assert gemini.calls == 0
    assert codex.calls == 1
    assert claude.calls == 0
    assert stub.calls == 0


def test_auto_cli_falls_back_to_stub_after_all_failures() -> None:
    gemini = _FakeBackend("gemini_cli", success=False)
    codex = _FakeBackend("codex_cli", success=False)
    claude = _FakeBackend("claude_code_cli", success=False)
    stub = _FakeBackend("stub", success=True)
    router = CoderRouter(
        backends={
            "gemini_cli": gemini,
            "codex_cli": codex,
            "claude_code_cli": claude,
            "stub": stub,
        }
    )
    router.default_backend = "auto_cli"

    result = router.generate(_req())
    assert result.success is True
    assert result.code == "stub-code"
    assert gemini.calls == 1
    assert codex.calls == 1
    assert claude.calls == 1
    assert stub.calls == 1
