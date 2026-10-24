from __future__ import annotations

import logging
import json
import datetime
import hashlib
import hmac
from typing import Any, Dict, List, Optional, AsyncIterator

import httpx
from .base import ModelClient, ModelResponse, UsageMetadata
from .retry import RetryStrategy
from .registry import registry

logger = logging.getLogger(__name__)

class BedrockClient(ModelClient):
    """
    Adapter for Amazon Bedrock (AWS SigV4 signing).
    Supports Claude and other models hosted on Bedrock.
    """
    def __init__(
        self,
        name: str,
        provider: str = "amazon",
        region: str = "us-east-1",
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        session_token: Optional[str] = None,
        timeout_seconds: float = 300.0,
        retry_strategy: Optional[RetryStrategy] = None,
        auth_profile_id: Optional[str] = None,
        **kwargs
    ):
        super().__init__(name, provider, retry_strategy, auth_profile_id)
        self.model_id = name
        self.region = region
        self.access_key = access_key
        self.secret_key = secret_key
        self.session_token = session_token
        self.timeout_seconds = timeout_seconds
        self.service = "bedrock"
        self.host = f"bedrock-runtime.{self.region}.amazonaws.com"

    def _sign(self, key, msg):
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def _get_signature_key(self, key, date_stamp, region_name, service_name):
        k_date = self._sign(("AWS4" + key).encode("utf-8"), date_stamp)
        k_region = self._sign(k_date, region_name)
        k_service = self._sign(k_region, service_name)
        k_signing = self._sign(k_service, "aws4_request")
        return k_signing

    async def _call_api(self, client: httpx.AsyncClient, payload: Dict[str, Any], stream: bool = False) -> httpx.Response:
        # Simplified SigV4 signing for Bedrock InvokeModel
        method = "POST"
        action = "invoke-with-response-stream" if stream else "invoke"
        url = f"https://{self.host}/model/{self.model_id}/{action}"
        request_parameters = json.dumps(payload)
        
        t = datetime.datetime.now(datetime.timezone.utc)
        amz_date = t.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = t.strftime("%Y%m%d")

        canonical_uri = f"/model/{self.model_id}/{action}"
        canonical_querystring = ""
        canonical_headers = (
            "content-type:application/json\n"
            f"host:{self.host}\n"
            f"x-amz-date:{amz_date}\n"
        )
        signed_headers = "content-type;host;x-amz-date"
        payload_hash = hashlib.sha256(request_parameters.encode("utf-8")).hexdigest()
        
        canonical_request = (
            f"{method}\n"
            f"{canonical_uri}\n"
            f"{canonical_querystring}\n"
            f"{canonical_headers}\n"
            f"{signed_headers}\n"
            f"{payload_hash}"
        )
        
        algorithm = "AWS4-HMAC-SHA256"
        credential_scope = f"{date_stamp}/{self.region}/{self.service}/aws4_request"
        string_to_sign = (
            f"{algorithm}\n"
            f"{amz_date}\n"
            f"{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )
        
        signing_key = self._get_signature_key(self.secret_key, date_stamp, self.region, self.service)
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        
        authorization_header = f"{algorithm} Credential={self.access_key}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"
        
        headers = {
            "Content-Type": "application/json",
            "X-Amz-Date": amz_date,
            "Authorization": authorization_header,
        }
        if self.session_token:
            headers["X-Amz-Security-Token"] = self.session_token

        if stream:
            # We return the response object for streaming
            return await client.post(url, content=request_parameters, headers=headers, timeout=self.timeout_seconds)
        
        response = await client.post(url, content=request_parameters, headers=headers)
        response.raise_for_status()
        return response

    async def generate(self, messages: List[Dict[str, str]], **kwargs) -> ModelResponse:
        # Bedrock Claude payload format
        prompt = ""
        for m in messages:
            role = "Assistant" if m["role"] == "assistant" else "Human"
            prompt += f"\n\n{role}: {m.get('content','')}"
        prompt += "\n\nAssistant:"

        payload = {
            "prompt": prompt,
            "max_tokens_to_sample": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", 0.7),
            "top_p": kwargs.get("top_p", 1.0),
        }

        async def _run():
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
                resp = await self._call_api(client, payload)
                data = resp.json()
                return ModelResponse(
                    text=data.get("completion", ""),
                    usage=UsageMetadata(),
                    raw=data
                )

        return await self.retry_strategy.execute(_run, label=f"bedrock:generate:{self.model_id}")

    async def stream(self, messages: List[Dict[str, str]], **kwargs) -> AsyncIterator[str]:
        # Placeholder for Bedrock streaming logic (requires EventStream decoding)
        yield ""

    async def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        embeddings = []
        for text in texts:
            payload = {"inputText": text}
            async def _run():
                async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
                    resp = await self._call_api(client, payload)
                    return resp.json().get("embedding", [])
            
            emb = await self.retry_strategy.execute(_run, label=f"bedrock:embed")
            embeddings.append(emb)
        return embeddings

# Register
registry.register("amazon", BedrockClient)
registry.register("bedrock", BedrockClient)
registry.register("aws", BedrockClient)