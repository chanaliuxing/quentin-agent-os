from __future__ import annotations
from typing import List, Tuple, Any, Dict
from quentin.tools.packs.base import ToolPack
from quentin.tools.schemas import ToolSpec, ToolKind

class CoderToolPack(ToolPack):
    """
    Exposes high-level coding capabilities (Gemini CLI, Claude Code, Codex)
    to the brain as structured tools.
    """
    @property
    def domain(self) -> str:
        return "coder"

    def get_tools(self) -> List[Tuple[ToolSpec, Any]]:
        from meta_agent.tools.coder.router import coder_router
        from meta_agent.tools.coder.base import CodeGenerationRequest

        def coder_generate_impl(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
            goal = params.get("goal", "")
            instructions = params.get("instructions", "")
            context_files = params.get("context_files", [])
            backend = params.get("backend", "gemini_cli")
            lang = params.get("language", "python")

            req = CodeGenerationRequest(
                goal=goal,
                instructions=instructions,
                context_files=context_files,
                preferred_language=lang
            )
            
            result = coder_router.generate(req, backend_name=backend)
            
            return {
                "success": result.success,
                "code": result.code,
                "reasoning": result.reasoning,
                "backend_used": backend
            }

        coder_spec = ToolSpec(
            name="coder.generate",
            description="Use a specialized coding CLI (Gemini, Claude, Codex) to generate code for a specific goal.",
            domain="coder",
            input_schema={
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "High-level objective (e.g. 'Fix bug in auth logic')"},
                    "instructions": {"type": "string", "description": "Detailed prompt for the coding tool. Include requirements and edge cases."},
                    "context_files": {
                        "type": "array", 
                        "items": {"type": "string"},
                        "description": "List of relevant file paths to provide as context."
                    },
                    "backend": {
                        "type": "string", 
                        "enum": ["gemini_cli", "claude_code_cli", "codex_cli"],
                        "default": "gemini_cli",
                        "description": "Which specialized tool to use. gemini_cli is preferred."
                    },
                    "language": {"type": "string", "default": "python"}
                },
                "required": ["goal", "instructions"]
            }
        )

        gemini_spec = ToolSpec(
            name="gemini.code",
            description="Fast-track coding task specifically using Gemini CLI.",
            domain="coder",
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Instructions for Gemini CLI."},
                    "context_files": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["prompt"]
            }
        )

        claude_spec = ToolSpec(
            name="claude.code",
            description="Fast-track coding task specifically using Claude Code CLI.",
            domain="coder",
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Instructions for Claude Code CLI."},
                    "context_files": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["prompt"]
            }
        )

        return [
            (coder_spec, coder_generate_impl),
            (gemini_spec, lambda p, c: coder_generate_impl({**p, "backend": "gemini_cli", "instructions": p.get("prompt")}, c)),
            (claude_spec, lambda p, c: coder_generate_impl({**p, "backend": "claude_code_cli", "instructions": p.get("prompt")}, c))
        ]
