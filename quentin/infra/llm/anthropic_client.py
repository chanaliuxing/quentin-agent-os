from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx
from .base import ModelClient, ModelResponse, UsageMetadata
from .retry import RetryStrategy
from .registry import registry

logger = logging.getLogger(__name__)

class AnthropicClient(ModelClient):
    """
    Adapter for Anthropic Messages API.
    """
    def __init__(
        self,
        name: str,
        provider: str = "anthropic",
        base_url: str = "https://api.anthropic.com/v1",
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
        self.anthropic_version = kwargs.get("anthropic_version", "2023-06-01")

    async def _call_api(self, client: httpx.AsyncClient, method: str, url: str, payload: Dict[str, Any]) -> httpx.Response:
        headers = {
            "x-api-key": self.api_key or "",
            "anthropic-version": self.anthropic_version,
            "content-type": "application/json",
        }
        response = await client.request(method, url, json=payload, headers=headers)
        response.raise_for_status()
        return response

    async def generate(self, messages: List[Dict[str, Any]], **kwargs) -> ModelResponse:
        system_msg = ""
        anthropic_messages = []
        for m in messages:
            raw_content = m["content"]
            content_list = []
            
            if isinstance(raw_content, str):
                content_list.append({"type": "text", "text": raw_content})
            elif isinstance(raw_content, list):
                for item in raw_content:
                    if item["type"] == "text":
                        content_list.append({"type": "text", "text": item["text"]})
                    elif item["type"] == "image":
                        content_list.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": item["image"]
                            }
                        })

            if m["role"] == "system":
                # Anthropic prefers system as a single string if possible, or list of text blocks
                system_msg += "".join([c["text"] for c in content_list if c["type"] == "text"])
            else:
                anthropic_messages.append({"role": m["role"], "content": content_list})

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "stream": False
        }
        if system_msg:
            payload["system"] = system_msg

        async def _run():
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
                resp = await self._call_api(client, "POST", f"{self.base_url}/messages", payload)
                data = resp.json()
                content = data.get("content", [])
                text = "".join([c.get("text", "") for c in content if c.get("type") == "text"])
                
                # Extract usage
                u = data.get("usage", {})
                usage = UsageMetadata(
                    prompt_tokens=u.get("input_tokens", 0),
                    completion_tokens=u.get("output_tokens", 0),
                    total_tokens=u.get("input_tokens", 0) + u.get("output_tokens", 0)
                )
                
                return ModelResponse(text=text, usage=usage, raw=data)

        return await self.retry_strategy.execute(
            _run, 
            label=f"anthropic:generate:{self.model}",
            auth_profile_id=self.auth_profile_id
        )

    async def stream(self, messages: List[Dict[str, str]], **kwargs) -> AsyncIterator[str]:
        system_msg = ""
        anthropic_messages = []
        for m in messages:
            if m["role"] == "system":
                system_msg += m["content"]
            else:
                anthropic_messages.append({"role": m["role"], "content": m["content"]})

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "stream": True
        }
        if system_msg: payload["system"] = system_msg
        
        headers = {
            "x-api-key": self.api_key or "",
            "anthropic-version": self.anthropic_version,
            "content-type": "application/json",
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
            async with client.stream("POST", f"{self.base_url}/messages", json=payload, headers=headers) as response:
                async for line in response.aiter_lines():
                    if not line.startswith("data: "): continue
                    try:
                        chunk = json.loads(line[6:])
                        if chunk.get("type") == "content_block_delta":
                            yield chunk["delta"].get("text", "")
                    except:
                        continue

    async def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        # Anthropic doesn't have a public embedding API yet (usually users use OpenAI or Voyage)
        logger.warning("Anthropic does not support native embeddings.")
        return [[] for _ in texts]

# Register
registry.register("anthropic", AnthropicClient)
registry.register("claude", AnthropicClient)
