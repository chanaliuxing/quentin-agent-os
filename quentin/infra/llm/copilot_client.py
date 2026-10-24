from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import httpx
from .base import ModelClient
from .retry import RetryStrategy
from .registry import registry

logger = logging.getLogger(__name__)

class GitHubCopilotClient(ModelClient):
    """
    Adapter for GitHub Copilot Chat API.
    Handles the token exchange from GitHub Token to Copilot Token.
    """
    _token_cache: Dict[str, Dict[str, Any]] = {}

    def __init__(
        self,
        name: str = "gpt-4",
        provider: str = "github-copilot",
        github_token: Optional[str] = None,
        timeout_seconds: float = 300.0,
        retry_strategy: Optional[RetryStrategy] = None,
        auth_profile_id: Optional[str] = None,
        **kwargs
    ):
        super().__init__(name, provider, retry_strategy, auth_profile_id)
        self.model = name
        self.github_token = github_token
        self.timeout_seconds = timeout_seconds

    async def _get_copilot_token(self, client: httpx.AsyncClient) -> str:
        if not self.github_token:
            raise ValueError("GitHub Token is required for Copilot Client")
        
        # Check cache
        cache_key = self.github_token
        cached = self._token_cache.get(cache_key)
        if cached and cached["expires_at"] > time.time() + 60:
            return cached["token"]

        # Exchange token
        resp = await client.get(
            "https://api.github.com/copilot_internal/v2/token",
            headers={
                "Authorization": f"token {self.github_token}",
                "User-Agent": "GitHubCopilotChat/1.0",
            }
        )
        resp.raise_for_status()
        data = resp.json()
        token = data["token"]
        
        # Cache it
        self._token_cache[cache_key] = {
            "token": token,
            "expires_at": data["expires_at"]
        }
        return token

    async def generate(self, messages: List[Dict[str, str]], **kwargs) -> ModelResponse:
        async def _run():
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
                token = await self._get_copilot_token(client)
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "temperature": kwargs.get("temperature", 0.1),
                    "top_p": kwargs.get("top_p", 1),
                    "n": 1,
                }
                
                resp = await client.post(
                    "https://api.githubcopilot.com/chat/completions",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-Github-Api-Version": "2023-07-07",
                        "Editor-Version": "vscode/1.85.0",
                    }
                )
                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                
                # Copilot doesn't always expose full usage, providing best effort
                usage = UsageMetadata() 
                if "usage" in data:
                    u = data["usage"]
                    usage = UsageMetadata(
                        prompt_tokens=u.get("prompt_tokens", 0),
                        completion_tokens=u.get("completion_tokens", 0),
                        total_tokens=u.get("total_tokens", 0)
                    )
                
                return ModelResponse(text=text, usage=usage, raw=data)

        return await self.retry_strategy.execute(_run, label=f"copilot:generate:{self.model}")

    async def stream(self, messages: List[Dict[str, str]], **kwargs) -> AsyncIterator[str]:
        # Copilot streaming implementation placeholder
        yield ""

    async def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        logger.warning("GitHub Copilot does not officially support embeddings API via this endpoint.")
        return [[] for _ in texts]

# Register
registry.register("github-copilot", GitHubCopilotClient)
registry.register("copilot", GitHubCopilotClient)
