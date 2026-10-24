from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx
from .base import ModelClient, ModelResponse, UsageMetadata
from .retry import RetryStrategy
from .registry import registry

logger = logging.getLogger(__name__)

class GeminiClient(ModelClient):
    """
    Adapter for Google Gemini API (Generative Language API).
    """
    def __init__(
        self,
        name: str,
        provider: str = "google",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
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

    async def _call_api(self, client: httpx.AsyncClient, method: str, url_path: str, payload: Dict[str, Any]) -> httpx.Response:
        url = f"{self.base_url}/{url_path}?key={self.api_key}"
        response = await client.request(method, url, json=payload)
        response.raise_for_status()
        return response

    async def generate(self, messages: List[Dict[str, Any]], **kwargs) -> ModelResponse:
        contents = []
        system_instruction = None
        
        for m in messages:
            role = "user" if m["role"] in ("user", "system") else "model"
            
            parts = []
            raw_content = m["content"]
            
            if isinstance(raw_content, str):
                parts.append({"text": raw_content})
            elif isinstance(raw_content, list):
                for item in raw_content:
                    if item["type"] == "text":
                        parts.append({"text": item["text"]})
                    elif item["type"] == "image":
                        parts.append({
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": item["image"]
                            }
                        })

            if m["role"] == "system" and not system_instruction:
                system_instruction = {"parts": parts}
            else:
                contents.append({
                    "role": role,
                    "parts": parts
                })

        payload: Dict[str, Any] = {"contents": contents}
        if system_instruction: payload["system_instruction"] = system_instruction
        if kwargs: payload.update(kwargs)

        async def _run():
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
                model_path = self.model if self.model.startswith("models/") else f"models/{self.model}"
                resp = await self._call_api(client, "POST", f"{model_path}:generateContent", payload)
                data = resp.json()
                
                candidates = data.get("candidates", [])
                text = "".join([p.get("text", "") for p in candidates[0].get("content", {}).get("parts", [])]) if candidates else ""
                
                # Extract usage
                u = data.get("usageMetadata", {})
                usage = UsageMetadata(
                    prompt_tokens=u.get("promptTokenCount", 0),
                    completion_tokens=u.get("candidatesTokenCount", 0),
                    total_tokens=u.get("totalTokenCount", 0)
                )
                
                return ModelResponse(text=text, usage=usage, raw=data)

        return await self.retry_strategy.execute(_run, label=f"google:generate:{self.model}")

    async def stream(self, messages: List[Dict[str, str]], **kwargs) -> AsyncIterator[str]:
        contents = []
        system_instruction = None
        for m in messages:
            role = "user" if m["role"] in ("user", "system") else "model"
            if m["role"] == "system" and not system_instruction:
                system_instruction = {"parts": [{"text": m["content"]}]}
            else:
                contents.append({"role": role, "parts": [{"text": m["content"]}]})

        payload: Dict[str, Any] = {"contents": contents}
        if system_instruction: payload["system_instruction"] = system_instruction

        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
            model_path = self.model if self.model.startswith("models/") else f"models/{self.model}"
            url = f"{self.base_url}/{model_path}:streamGenerateContent?key={self.api_key}"
            async with client.stream("POST", url, json=payload) as response:
                async for line in response.aiter_lines():
                    if not line: continue
                    try:
                        # Gemini stream returns a JSON array or multiple objects
                        chunk = json.loads(line.strip("[], "))
                        parts = chunk.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                        for p in parts:
                            if "text" in p: yield p["text"]
                    except: continue

    async def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        # Gemini embedding API
        async def _run_one(text: str):
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
                model_path = self.model
                if not model_path.startswith("models/"):
                    model_path = f"models/{model_path}"
                payload = {
                    "model": model_path,
                    "content": {"parts": [{"text": text}]}
                }
                resp = await self._call_api(client, "POST", f"{model_path}:embedContent", payload)
                data = resp.json()
                return data.get("embedding", {}).get("values", [])

        embeddings = []
        for text in texts:
            try:
                emb = await self.retry_strategy.execute(lambda: _run_one(text), label=f"google:embed:{self.model}")
                embeddings.append(emb)
            except Exception as e:
                logger.error("Failed to embed text with Gemini: %s", e)
                embeddings.append([])
        return embeddings

# Register
registry.register("google", GeminiClient)
registry.register("gemini", GeminiClient)
