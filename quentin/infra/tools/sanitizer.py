from __future__ import annotations
import logging
import re
from typing import Any, Dict, Optional, List

logger = logging.getLogger(__name__)

class ToolParameterSanitizer:
    """
    P5: OpenClaw Parity - Parameter Sanitization.
    Prevents common mistakes like calling mkdir on a file path.
    """
    
    def sanitize(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        # 1. mkdir safety
        if tool_name in ("mkdir", "fs_mkdir", "fs.mkdir"):
            path = params.get("path")
            if isinstance(path, str):
                # P5: Evolution Phase 2 - Explicit Rejection (Break loop)
                # Instead of "softening" (creating parent), we now raise error to force reflection.
                file_suffixes = (".py", ".yaml", ".yml", ".json", ".md", ".txt", ".sh", ".toml", ".ini")
                if any(path.endswith(ext) for ext in file_suffixes):
                    logger.warning(f"Sanitizer: REJECTED mkdir for file-like path {path}")
                    raise ValueError(
                        f"Path '{path}' looks like a file (ends in '.py'/'.yaml'/etc). "
                        "'mkdir' is ONLY for directories. Use 'fs.write_file' to create files; "
                        "it will automatically create parent directories if needed."
                    )
        
        # 2. Add more sanitization rules here as needed
        
        return params

sanitizer = ToolParameterSanitizer()

class SemanticHintGenerator:
    """
    P5: Ported from OpenClaw's error-to-hint mapping.
    Converts raw technical errors into actionable LLM instructions.
    """
    
    HINTS = {
        "missing_parameter": "You missed the mandatory parameter '{param}'. Please check the tool definition and try again.",
        "invalid_path": "The path '{path}' is invalid or inaccessible. Try using 'ls' to verify the file's existence first.",
        "permission_denied": "Access denied to '{path}'. This path might be outside the allowed workspace or protected.",
        "type_mismatch": "Parameter '{param}' expected type {expected}, but received {actual}. Ensure your JSON follows the schema.",
        "syntax_error": "I detected a syntax error in your provided code. Check for missing quotes or brackets.",
    }

    @classmethod
    def get_hint(cls, error_type: str, context: Dict[str, Any]) -> str:
        template = cls.HINTS.get(error_type, "Please review the tool documentation and correct your arguments.")
        try:
            return f"Hint: {template.format(**context)}"
        except Exception:
            return f"Hint: {template}"

    @classmethod
    def enrich_error(cls, tool_name: str, raw_error: Exception) -> Dict[str, Any]:
        """
        Takes a raw exception and returns a structured error with a hint.
        """
        err_msg = str(raw_error)
        out = {"status": "error", "error": err_msg}
        
        # P5: OpenClaw Parity - YAML Hinting
        err_name = raw_error.__class__.__name__
        if "yaml" in err_name.lower() or "ScannerError" in err_name or "ParserError" in err_name:
            if "expected <block end>" in err_msg and "found '-'" in err_msg:
                out["hint"] = "HINT: Your YAML list item is misaligned. Ensure list markers ('-') are at the SAME indentation level as their parent or indented consistently. YAML is extremely sensitive to 2-space vs 4-space differences."
            elif "expected <block end>" in err_msg and "block sequence start" in err_msg:
                 out["hint"] = "HINT: Indentation mismatch. You started a list ('-') where a mapping (key: value) was expected, or vice-versa. Please check the line mentioned in the error."
            elif "could not find expected ':'" in err_msg:
                out["hint"] = "HINT: Missing colon or invalid key. Ensure every key is followed by ': ' (with a space) and that strings with special characters are quoted."
            else:
                out["hint"] = "HINT: YAML Syntax Error. This is usually caused by incorrect indentation. Use exactly 2 spaces for nested blocks and ensure list items ('-') are properly aligned."
            return out

        # 1. Detect Missing Params
        if "missing" in err_msg.lower() and "parameter" in err_msg.lower():
            # Try to extract param name
            m = re.search(r"parameter ['\"]?([a-zA-Z0-9_]+)['\"]?", err_msg)
            param = m.group(1) if m else "unknown"
            out["hint"] = cls.get_hint("missing_parameter", {"param": param})
            
        # 2. Detect Path Issues
        elif "no such file" in err_msg.lower() or "not found" in err_msg.lower():
            out["hint"] = cls.get_hint("invalid_path", {"path": "the one you provided"})
            
        # 3. Fallback
        else:
            out["hint"] = f"Hint: Something went wrong while running {tool_name}. Re-check your parameters."
            
        return out
