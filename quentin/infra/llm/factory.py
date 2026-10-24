from __future__ import annotations

import os
import logging
from typing import Optional, Any, Dict

from .base import ModelClient
from .registry import registry as adapter_registry
from .retry import RetryStrategy, RetryConfig, OLLAMA_RETRY_CONFIG, OPENAI_RETRY_CONFIG
from quentin.llm.auth_profiles import get_auth_manager

logger = logging.getLogger(__name__)

def _infer_provider(model_id: str) -> str:
    mid = model_id.lower()
    if "/" in mid:
        return mid.split("/")[0]
    if ":" in mid:
        return "ollama"
    if "gpt" in mid or "openai" in mid:
        return "openai"
    if "claude" in mid or "anthropic" in mid:
        return "anthropic"
    if "deepseek" in mid:
        return "deepseek"
    if "gemini" in mid:
        return "google"
    return "unknown"

class ModelClientFactory:
    """
    Factory to create ModelClient instances with auto-loaded AuthProfile and RetryStrategy.
    """

    @staticmethod
    def create_client(
        model_id: str,
        provider: Optional[str] = None,
        auth_profile_id: Optional[str] = None,
        retry_config: Optional[RetryConfig] = None,
        **kwargs
    ) -> ModelClient:
        provider = provider or _infer_provider(model_id)
        force_stub = str(os.getenv("QUENTIN_LLM_FORCE_STUB", "0") or "0").strip().lower() in {"1", "true", "yes", "on"}
        if force_stub:
            provider = "stub"
            if not str(model_id or "").strip():
                model_id = "stub-model"
        
        adapter_class = adapter_registry.get_adapter(provider)
        if not adapter_class:
            logger.warning("No adapter found for provider: %s. Falling back to GenericOpenAIClient.", provider)
            from .openai_client import GenericOpenAIClient
            adapter_class = GenericOpenAIClient

        # 1. Resolve Auth Profile with Rotation support
        from .auth_rotation import AuthRotator
        rotator = AuthRotator(provider)
        
        profile = None
        if auth_profile_id:
            auth_mgr = rotator.auth_mgr
            profile = auth_mgr._store.profiles.get(auth_profile_id)
        else:
            profile = rotator.get_next_available_profile()
        
        # 2. Resolve Retry Strategy
        if not retry_config:
            if provider == "ollama":
                retry_config = OLLAMA_RETRY_CONFIG
            elif provider in ("openai", "anthropic", "deepseek"):
                retry_config = OPENAI_RETRY_CONFIG
            else:
                retry_config = RetryConfig()
        
        retry_strategy = RetryStrategy(retry_config)

        # 3. Instantiate Client
        # Handle specialized credentials
        client_kwargs = {**kwargs}
        if provider in ("amazon", "bedrock", "aws"):
            client_kwargs.update({
                "access_key": os.getenv("AWS_ACCESS_KEY_ID"),
                "secret_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
                "session_token": os.getenv("AWS_SESSION_TOKEN"),
                "region": os.getenv("AWS_DEFAULT_REGION", "us-east-1")
            })
        elif provider in ("github-copilot", "copilot"):
            client_kwargs.update({
                "github_token": os.getenv("COPILOT_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
            })
        elif provider in ("azure", "azure-openai"):
            client_kwargs.update({
                "api_key": os.getenv("AZURE_OPENAI_API_KEY"),
                "base_url": os.getenv("AZURE_OPENAI_ENDPOINT"),
                "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
            })

        client = adapter_class(
            name=model_id,
            provider=provider,
            retry_strategy=retry_strategy,
            auth_profile_id=profile.profile_id if profile else "default",
            **client_kwargs
        )

        # Inject base_url and api_key from profile if applicable
        if profile:
            # Atomic Level: Smart Auth Sniffing (OpenClaw Parity)
            # Detect if it's an API Key or an OAuth session token
            raw_key = profile.api_key or (os.getenv(profile.secret_ref) if profile.secret_ref else None)
            
            if raw_key:
                # Normalize Anthropic keys
                if provider == "anthropic" and not raw_key.startswith("sk-ant-"):
                    logger.warning("Sniffed potentially invalid Anthropic key format.")
                
                if hasattr(client, "api_key"):
                    client.api_key = raw_key
            
            if hasattr(client, "base_url") and profile.base_url:
                client.base_url = profile.base_url

        return client
