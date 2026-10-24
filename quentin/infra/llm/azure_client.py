from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx
from .base import ModelClient, ModelResponse, UsageMetadata
from .retry import RetryStrategy
from .registry import registry

logger = logging.getLogger(__name__)

class AzureOpenAIClient(ModelClient):
    """
    Adapter for Azure OpenAI Service.
    """
    def __init__(
        self,
        name: str,
        provider: str = "azure",
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_version: str = "2024-02-01",
        timeout_seconds: float = 300.0,
        retry_strategy: Optional[RetryStrategy] = None,
        auth_profile_id: Optional[str] = None,
        **kwargs
    ):
        super().__init__(name, provider, retry_strategy, auth_profile_id)
        self.deployment_id = name
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.api_key = api_key
        self.api_version = api_version
        self.timeout_seconds = timeout_seconds

    async def _call_api(self, client: httpx.AsyncClient, method: str, url_path: str, payload: Dict[str, Any]) -> httpx.Response:
        headers = {
            "api-key": self.api_key or "",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/openai/deployments/{self.deployment_id}/{url_path}?api-version={self.api_version}"
        response = await client.request(method, url, json=payload, headers=headers)
        response.raise_for_status()
        return response

    async def generate(self, messages: List[Dict[str, str]], **kwargs) -> ModelResponse:
        payload: Dict[str, Any] = {"messages": messages, "stream": False}
        if kwargs: payload.update(kwargs)

        async def _run():
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
                resp = await self._call_api(client, "POST", "chat/completions", payload)
                data = resp.json()
                choices = data.get("choices", [])
                text = choices[0].get("message", {}).get("content", "") if choices else ""
                
                # Extract usage
                u = data.get("usage", {})
                usage = UsageMetadata(
                    prompt_tokens=u.get("prompt_tokens", 0),
                    completion_tokens=u.get("completion_tokens", 0),
                    total_tokens=u.get("total_tokens", 0)
                )
                
                return ModelResponse(text=text, usage=usage, raw=data)

        return await self.retry_strategy.execute(_run, label=f"azure:generate:{self.deployment_id}")

    async def stream(self, messages: List[Dict[str, str]], **kwargs) -> AsyncIterator[str]:
        payload: Dict[str, Any] = {"messages": messages, "stream": True}
        headers = {"api-key": self.api_key or "", "Content-Type": "application/json"}
        url = f"{self.base_url}/openai/deployments/{self.deployment_id}/chat/completions?api-version={self.api_version}"

        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                async for line in response.aiter_lines():
                    if not line.startswith("data: "): continue
                    data_str = line[6:]
                    if data_str == "[DONE]": break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        if "content" in delta: yield delta["content"]
                    except: continue

    async def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        async def _run():
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
                payload = {"input": texts}
                resp = await self._call_api(client, "POST", "embeddings", payload)
                data = resp.json()
                return [item.get("embedding", []) for item in data.get("data", [])]

        return await self.retry_strategy.execute(_run, label=f"azure:embed:{self.deployment_id}")

# Register
registry.register("azure", AzureOpenAIClient)
registry.register("azure-openai", AzureOpenAIClient)
