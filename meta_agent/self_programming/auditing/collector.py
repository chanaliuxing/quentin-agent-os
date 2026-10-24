import os
from typing import List, Dict, Tuple
from .templates import Evidence
from .ast_index import ASTIndex, ParsedFileInfo


class StaticEvidenceCollector:
    """
    Collect static evidence for a requirement using a global AST index.
    - file existence
    - expected symbols presence (class/method/function)
    - placeholder detection (pass / NotImplemented / Ellipsis / marker tokens)
    """

    def __init__(self, project_root: str, ast_index: ASTIndex):
        self.root = project_root
        self.index = ast_index

    def collect(self, req: Dict) -> Tuple[List[Evidence], List[str]]:
        evidences: List[Evidence] = []
        missing_items: List[str] = []
        module_hint = req.get("module_hint")
        expected_symbols = req.get("symbols_expected", [])

        if not module_hint:
            return evidences, missing_items

        info: ParsedFileInfo | None = self.index.get(module_hint)

        if info is None:
            evidences.append(Evidence("file_system", "file_missing", 0.0, f"File not found: {module_hint}"))
            missing_items.append(f"missing_file:{module_hint}")
            return evidences, missing_items

        evidences.append(Evidence("file_system", "file_exists", 0.1, f"File found: {module_hint}"))

        # Placeholder penalties
        if info.placeholders > 0 or info.todo_tokens:
            evidences.append(
                Evidence(
                    "ast",
                    "placeholder_detected",
                    -0.3,
                    f"Placeholders/marker tokens detected (count={info.placeholders})",
                )
            )

        strong_hit = False

        if expected_symbols:
            for sym in expected_symbols:
                if not sym:
                    continue
                kind, name = self._parse_symbol(sym)
                if kind == "method":
                    cls, _, m = name.partition(".")
                    method_key = f"{cls}.{m}"
                    if method_key in info.methods:
                        evidences.append(Evidence("ast", "method_found", 0.5, f"Method '{method_key}' found"))
                        strong_hit = True
                    elif cls in info.classes:
                        evidences.append(Evidence("ast", "class_found", 0.1, f"Class '{cls}' found, method missing"))
                        missing_items.append(f"missing_method:{method_key}")
                    else:
                        evidences.append(Evidence("ast", "symbol_missing", 0.0, f"Class '{cls}' missing"))
                        missing_items.append(f"missing_class:{cls}")
                elif kind == "class":
                    if name in info.classes:
                        evidences.append(Evidence("ast", "class_found", 0.2, f"Class '{name}' found"))
                    else:
                        evidences.append(Evidence("ast", "symbol_missing", 0.0, f"Class '{name}' missing"))
                        missing_items.append(f"missing_class:{name}")
                else:  # func
                    if name in info.functions:
                        evidences.append(Evidence("ast", "function_found", 0.5, f"Function '{name}' found"))
                        strong_hit = True
                    else:
                        evidences.append(Evidence("ast", "symbol_missing", 0.0, f"Function '{name}' missing"))
                        missing_items.append(f"missing_function:{name}")
        else:
            # Generic content reward if no specific symbols expected
            if info.classes:
                evidences.append(Evidence("ast", "class_found", 0.1, f"Found {len(info.classes)} classes"))
            if info.functions or info.methods:
                evidences.append(Evidence("ast", "generic_defs", 0.05, f"Found {len(info.functions)+len(info.methods)} defs"))

        # Annotate strong_hit to help scorer cap status if absent
        evidences.append(Evidence("meta", "strong_hit", 1.0 if strong_hit else 0.0, "internal strong evidence flag"))

        return evidences, missing_items

    def _parse_symbol(self, sym: str) -> tuple[str, str]:
        """
        Supports prefixes: class:, func:, method:
        Heuristic fallback:
          - contains '.' => method
          - starts with uppercase => class
          - else function
        """
        if ":" in sym:
            prefix, _, name = sym.partition(":")
            if prefix in ("class", "cls"):
                return "class", name
            if prefix in ("func", "function"):
                return "func", name
            if prefix in ("method",):
                return "method", name
        if "." in sym:
            return "method", sym
        if sym and sym[0].isupper():
            return "class", sym
        return "func", sym
