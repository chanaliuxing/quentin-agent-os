"""
Compatibility wrapper.

Blueprint v3 YAML references `meta_agent.evolution.code_tool_backend_stub.CodeToolBackend`.
Canonical implementation lives at `meta_agent.tools.code_tools.CodeToolBackend`.
"""

from meta_agent.tools.code_tools import CodeToolBackend

__all__ = ["CodeToolBackend"]
