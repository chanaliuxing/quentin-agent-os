from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, AsyncIterator
from .retry import RetryStrategy

@dataclass
class UsageMetadata:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0

@dataclass
class ModelResponse:
    text: str
    usage: UsageMetadata = field(default_factory=UsageMetadata)
    raw: Any = None
    tool_calls: Optional[List[Dict[str, Any]]] = None

class ModelClient(ABC):
    """
    Unified ModelClient interface (canonical: quentin.infra.llm.base.ModelClient).
    Adapters should inherit from this class.
    """
    name: str
    provider: str
    retry_strategy: Optional[RetryStrategy] = None
    auth_profile_id: Optional[str] = None

    def __init__(
        self,
        name: str,
        provider: str,
        retry_strategy: Optional[RetryStrategy] = None,
        auth_profile_id: Optional[str] = None,
    ):
        self.name = name
        self.provider = provider
        self.retry_strategy = retry_strategy or RetryStrategy()
        self.auth_profile_id = auth_profile_id

    @abstractmethod
    async def generate(self, messages: List[Dict[str, str]], **kwargs) -> ModelResponse:
        """
        Generate text completion for the given messages.
        """
        ...

    @abstractmethod
    async def stream(self, messages: List[Dict[str, str]], **kwargs) -> AsyncIterator[str]:
        """
        Stream text completion.
        """
        ...

    @abstractmethod
    async def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        ...


# Alias for backward compatibility if needed
LLMClient = ModelClient
