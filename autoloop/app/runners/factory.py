from app.config import settings
from .base import BaseAgentRunner
from .codex_runner import CodexRunner
from .gemini_runner import GeminiRunner
from .claude_runner import ClaudeRunner
from .mock_runner import MockRunner


def create_runner(runner_type: str | None = None) -> BaseAgentRunner:
    runner_type = runner_type or settings.agent_runner_type

    if runner_type == "codex":
        return CodexRunner({"session_id": settings.codex_session_id})
    elif runner_type == "gemini":
        return GeminiRunner({"session_id": settings.gemini_session_id})
    elif runner_type == "claude":
        return ClaudeRunner({"session_id": settings.claude_session_id})
    elif runner_type == "mock":
        return MockRunner()
    else:
        raise ValueError(f"Unknown runner type: {runner_type}")


async def health_check_all_runners() -> dict[str, bool]:
    results = {}

    for runner_type in ["codex", "gemini", "claude", "mock"]:
        try:
            if runner_type == "mock":
                runner = MockRunner()
            else:
                runner = create_runner(runner_type)
            results[runner_type] = await runner.health_check()
        except Exception as e:
            results[runner_type] = False

    return results
