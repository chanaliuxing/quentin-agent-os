from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx
from .base import ModelClient, ModelResponse, UsageMetadata
from .retry import RetryStrategy
from .registry import registry

logger = logging.getLogger(__name__)

class GenericOpenAIClient(ModelClient):
    """
    Generic adapter for OpenAI-compatible APIs (OpenAI, DeepSeek, OpenRouter, etc.)
    """
    def __init__(
        self,
        name: str,
        provider: str = "openai",
        base_url: str = "https://api.openai.com/v1",
        api_key: Optional[str] = None,
        timeout_seconds: float = 300.0,
        retry_strategy: Optional[RetryStrategy] = None,
        auth_profile_id: Optional[str] = None,
        **kwargs
    ):
        super().__init__(name, provider, retry_strategy, auth_profile_id)
        self.model = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def _call_api(self, client: httpx.AsyncClient, method: str, url: str, payload: Dict[str, Any]) -> httpx.Response:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        response = await client.request(method, url, json=payload, headers=headers)
        response.raise_for_status()
        return response

    async def generate(self, messages: List[Dict[str, str]], **kwargs) -> ModelResponse:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False
        }
        if kwargs:
            payload.update(kwargs)

        async def _run():
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
                resp = await self._call_api(client, "POST", f"{self.base_url}/chat/completions", payload)
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

        return await self.retry_strategy.execute(
            _run, 
            label=f"{self.provider}:generate:{self.model}",
            auth_profile_id=self.auth_profile_id
        )

    async def stream(self, messages: List[Dict[str, str]], **kwargs) -> AsyncIterator[str]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True
        }
        
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        
        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
            async with client.stream("POST", f"{self.base_url}/chat/completions", json=payload, headers=headers) as response:
                async for line in response.aiter_lines():
                    if not line.startswith("data: "): continue
                    data_str = line[6:]
                    if data_str == "[DONE]": break
                    
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        if "content" in delta:
                            yield delta["content"]
                    except:
                        continue

    async def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        async def _run():
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
                payload = {"model": self.model, "input": texts}
                resp = await self._call_api(client, "POST", f"{self.base_url}/embeddings", payload)
                data = resp.json()
                return [item.get("embedding", []) for item in data.get("data", [])]

        return await self.retry_strategy.execute(
            _run, 
            label=f"{self.provider}:embed:{self.model}",
            auth_profile_id=self.auth_profile_id
        )

# Register for common providers
registry.register("openai", GenericOpenAIClient)
registry.register("deepseek", GenericOpenAIClient)
registry.register("openrouter", GenericOpenAIClient)
registry.register("kimi", GenericOpenAIClient)
registry.register("moonshot", GenericOpenAIClient)
registry.register("qwen", GenericOpenAIClient)
registry.register("dashscope", GenericOpenAIClient)
registry.register("groq", GenericOpenAIClient)
registry.register("perplexity", GenericOpenAIClient)
registry.register("xai", GenericOpenAIClient)
registry.register("mistral", GenericOpenAIClient)
registry.register("cerebras", GenericOpenAIClient)
registry.register("together", GenericOpenAIClient)
registry.register("fireworks", GenericOpenAIClient)
registry.register("venice", GenericOpenAIClient)
registry.register("minimax", GenericOpenAIClient)
registry.register("zai", GenericOpenAIClient)
registry.register("zhipu", GenericOpenAIClient)
registry.register("lingyi", GenericOpenAIClient)
registry.register("baichuan", GenericOpenAIClient)
registry.register("volcengine", GenericOpenAIClient)
registry.register("doubao", GenericOpenAIClient)
registry.register("opencode", GenericOpenAIClient)
registry.register("vercel", GenericOpenAIClient)
registry.register("xiaomi", GenericOpenAIClient)
registry.register("synthetic", GenericOpenAIClient)
registry.register("novita", GenericOpenAIClient)
registry.register("deepinfra", GenericOpenAIClient)
registry.register("perp", GenericOpenAIClient)
registry.register("pplx", GenericOpenAIClient)
registry.register("siliconflow", GenericOpenAIClient)
