import asyncio
import logging
import os
from typing import Any, Dict, List, Optional, AsyncIterator

import httpx
from .base import ModelClient, ModelResponse, UsageMetadata
from .retry import RetryStrategy
from .registry import registry

logger = logging.getLogger(__name__)

class OllamaClient(ModelClient):
    def __init__(
        self,
        name: Optional[str] = None,
        provider: str = "ollama",
        base_url: str = "http://localhost:11434",
        timeout_seconds: float = 300.0,
        retry_strategy: Optional[RetryStrategy] = None,
        auth_profile_id: Optional[str] = None,
        **kwargs
    ):
        name = name or os.getenv("LLM_MODEL")
        if not name:
             raise ValueError("LLM_MODEL environment variable not set.")
        super().__init__(name, provider, retry_strategy, auth_profile_id)
        # P5: Robust URL Sanitization
        # If the provided URL already contains /api, strip it to get the base
        if "/api" in base_url:
            self.base_url = base_url.split("/api")[0].rstrip("/")
        else:
            self.base_url = base_url.rstrip("/")
            
        self.model = name
        self.timeout_seconds = timeout_seconds

    async def _call_api(self, client: httpx.AsyncClient, method: str, url: str, payload: Dict[str, Any]) -> httpx.Response:
        # P5: Force console visibility
        print(f"\n[Ollama] Calling {method} {url} for model {self.model}...", flush=True)
        response = await client.request(method, url, json=payload)
        if response.status_code >= 400:
            try:
                error_msg = response.json().get("error", response.text)
            except Exception:
                error_msg = response.text
            raise RuntimeError(f"Ollama Error [{response.status_code}]: {error_msg}")
        return response

    async def generate(self, messages: List[Dict[str, Any]], **kwargs) -> ModelResponse:
        # P5: Context Window Optimization
        options = kwargs.get("options", {})
        if "num_ctx" not in options:
            options["num_ctx"] = int(os.getenv("LLM_OLLAMA_NUM_CTX", "4096"))
        
        # P5: Handle multi-part content (text + image list)
        def _get_text(content):
            if isinstance(content, str): return content
            if isinstance(content, list):
                return "\n".join([str(c.get("text", "")) for c in content if isinstance(c, dict) and c.get("type") == "text"])
            return str(content)

        prompt = "\n".join([_get_text(m.get("content", "")) for m in messages])
        payload: Dict[str, Any] = {
            "model": self.model, 
            "prompt": prompt, 
            "stream": False,
            "options": options
        }

        async def _run():
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
                resp = await self._call_api(client, "POST", f"{self.base_url}/api/generate", payload)
                data = resp.json()
                
                usage = UsageMetadata(
                    prompt_tokens=data.get("prompt_eval_count", 0),
                    completion_tokens=data.get("eval_count", 0),
                    total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
                )
                
                return ModelResponse(
                    text=data.get("response", ""),
                    usage=usage,
                    raw=data
                )

        return await self.retry_strategy.execute(_run, label=f"ollama:generate:{self.model}")

    async def chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, **kwargs) -> ModelResponse:
        """
        P5: Support native tool calling using Ollama /api/chat endpoint.
        """
        options = kwargs.get("options", {})
        if "num_ctx" not in options:
            options["num_ctx"] = int(os.getenv("LLM_OLLAMA_NUM_CTX", "4096"))

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": options
        }
        if tools:
            payload["tools"] = tools
        if kwargs:
            payload.update(kwargs)

        async def _run():
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
                resp = await self._call_api(client, "POST", f"{self.base_url}/api/chat", payload)
                data = resp.json()
                msg = data.get("message", {})
                
                usage = UsageMetadata(
                    prompt_tokens=data.get("prompt_eval_count", 0),
                    completion_tokens=data.get("eval_count", 0),
                    total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
                )
                
                return ModelResponse(
                    text=msg.get("content", ""),
                    usage=usage,
                    raw=data,
                    tool_calls=msg.get("tool_calls") # Extract tool calls
                )

        return await self.retry_strategy.execute(_run, label=f"ollama:chat:{self.model}")

    async def stream(self, messages: List[Dict[str, Any]], **kwargs) -> AsyncIterator[str]:
        # P5: Handle multi-part content
        def _get_text(content):
            if isinstance(content, str): return content
            if isinstance(content, list):
                return "\n".join([str(c.get("text", "")) for c in content if isinstance(c, dict) and c.get("type") == "text"])
            return str(content)

        prompt = "\n".join([_get_text(m.get("content", "")) for m in messages])
        payload: Dict[str, Any] = {"model": self.model, "prompt": prompt, "stream": True}
        
        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
            async with client.stream("POST", f"{self.base_url}/api/generate", json=payload) as response:
                async for line in response.aiter_lines():
                    if not line: continue
                    chunk = json.loads(line)
                    if "response" in chunk:
                        yield chunk["response"]
                    if chunk.get("done"):
                        break

    async def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        model = kwargs.get("model", self.model)
        
        async def _run_one(text: str):
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
                payload = {"model": model, "prompt": text}
                resp = await self._call_api(client, "POST", f"{self.base_url}/api/embeddings", payload)
                data = resp.json()
                return data.get("embedding", [])

        embeddings = []
        for text in texts:
            try:
                emb = await self.retry_strategy.execute(lambda: _run_one(text), label=f"ollama:embed:{model}")
                embeddings.append(emb)
            except Exception as e:
                logger.error("Failed to embed text: %s", e)
                embeddings.append([])
        return embeddings

# Register the adapter
registry.register("ollama", OllamaClient)
