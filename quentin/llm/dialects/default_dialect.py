from __future__ import annotations

from typing import Any, Dict, Tuple
from quentin.llm.dialects.base import PromptDialect
from quentin.llm.model_dialect import apply_model_dialect

class DefaultPromptDialect(PromptDialect):
    """
    Standard dialect transformation logic.
    """
    @property
    def id(self) -> str:
        return "default"

    @property
    def priority(self) -> int:
        return 0

    def supports(self, provider: str, model_name: str) -> bool:
        return True

    def transform(
        self,
        provider: str,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        metadata: Dict[str, Any]
    ) -> Tuple[str, str, Dict[str, Any]]:
        sp, up, meta = apply_model_dialect(
            provider=provider,
            model_name=model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt
        )
        return sp, up, {**metadata, **meta}
