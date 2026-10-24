from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

from quentin.tools.learning.schema_examples import synthesize_examples_from_schema


class ExampleSynthesizer(Protocol):
    def synthesize(
        self, *, tool_name: str, signature: str, input_schema: Dict[str, Any], max_examples: int
    ) -> List[Dict[str, Any]]: ...


@dataclass(frozen=True)
class SchemaExampleSynthesizer:
    """
    v0 synthesizer based purely on JSON schema (no LLM).
    """

    max_depth: int = 4

    def synthesize(
        self, *, tool_name: str, signature: str, input_schema: Dict[str, Any], max_examples: int
    ) -> List[Dict[str, Any]]:
        return synthesize_examples_from_schema(
            input_schema=input_schema,
            tool_name=tool_name,
            signature=signature,
            max_examples=max_examples,
            max_depth=int(self.max_depth),
        )


@dataclass(frozen=True)
class ToolLearningConfig:
    enabled: bool = False
    max_examples: int = 2


class ToolLearningModule:
    """
    Tool learning module (v0):
    - Optionally synthesize examples from schema
    - Attach to ToolSpec.meta (pluggable)

    This intentionally does not call any remote models.
    """

    def __init__(
        self,
        *,
        config: Optional[ToolLearningConfig] = None,
        synthesizer: Optional[ExampleSynthesizer] = None,
    ) -> None:
        self.config = config or ToolLearningConfig()
        self.synthesizer = synthesizer or SchemaExampleSynthesizer()

    def maybe_augment_tool_meta(self, *, tool_name: str, meta: Dict[str, Any], input_schema: Dict[str, Any]) -> Dict[str, Any]:
        if not self.config.enabled:
            return meta
        md = dict(meta or {})
        if isinstance(md.get("examples"), list) and md.get("examples"):
            return md
        signature = str(md.get("signature") or md.get("tool_signature") or tool_name)
        examples = self.synthesizer.synthesize(
            tool_name=tool_name,
            signature=signature,
            input_schema=input_schema or {},
            max_examples=int(self.config.max_examples),
        )
        if examples:
            md["examples"] = examples
        return md

