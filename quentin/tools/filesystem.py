import logging
import os
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

def _ensure_str_path(v: Any) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ValueError("missing_path")
    return v.strip()


def _get_repo_root() -> Path:
    return Path(".").resolve()


def _resolve_for_read(path_str: str) -> Path:
    """
    Read policy: allow any path within repo_root (no allowed_roots restriction),
    but still hard-block absolute paths and repo escape.
    """
    from quentin.kernel.path_guard import PathGuard

    repo_root = _get_repo_root()
    guard = PathGuard(repo_root=repo_root, allowed_roots=[])
    return guard.ensure_allowed_path(path_str)


def _resolve_for_write(path_str: str) -> Path:
    """
    Write policy: restrict to PathGuard's default allowed_roots.
    """
    from quentin.kernel.path_guard import PathGuard

    repo_root = _get_repo_root()
    guard = PathGuard(repo_root=repo_root, allowed_roots=None)
    return guard.ensure_allowed_path(path_str)


def _current_write_policy() -> Dict[str, Any]:
    from quentin.kernel.path_guard import PathGuard

    repo_root = _get_repo_root()
    guard = PathGuard(repo_root=repo_root, allowed_roots=None)
    extra_raw = str(os.getenv("QUENTIN_PATH_GUARD_EXTRA_ALLOWED_ROOTS", "") or "").strip()
    return {
        "allowed_roots": list(guard.allowed_roots),
        "extra_allowed_roots_env": extra_raw,
    }


def _err_with_hint(error: str, *, hint: str = "", next_actions: list[str] | None = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {"status": "error", "error": error}
    if hint:
        out["hint"] = hint
    if next_actions:
        out["next_actions"] = list(next_actions)
    return out

def fs_write_file(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    path_str = params.get("path")
    content = params.get("content")
    if content is None:
        return _err_with_hint(
            "Missing path or content",
            hint="Provide both `path` and `content`.",
            next_actions=["Set `path` to a relative path.", "Set `content` to desired file text."],
        )
    
    try:
        path_str = _ensure_str_path(path_str)
        target = _resolve_for_write(path_str)

        if target.exists() and target.is_dir():
            return _err_with_hint(
                f"Path is a directory: {path_str}",
                hint="fs.write_file can only write to files. A directory exists at this path (common error: mkdir was called on a file path).",
                next_actions=[
                    f"Remove or rename the directory at `{path_str}`.",
                    "Then retry fs.write_file with the intended file content.",
                    "Prevent recurrence: never call mkdir on paths ending with .py/.yaml/etc.",
                ],
            )

        # P0.1: skip-if-unchanged
        if target.exists():
            existing_content = target.read_text(encoding="utf-8")
            if existing_content == content:
                logger.info(f"fs.write_file: {path_str} unchanged, skipping write.")
                return {
                    "status": "ok", 
                    "result": "unchanged_skipped", 
                    "skipped": True,
                    "path": path_str
                }

        # P0.3: Schema validation for manifests (Hard Validation - Fail Fast)
        logger.debug("fs.write_file: checking manifest validation for %s", path_str)
        if path_str.endswith("manifest.yaml") or path_str.endswith("manifest.yml"):
            logger.debug("fs.write_file: validating manifest %s", path_str)
            try:
                import yaml
                import difflib
                data = yaml.safe_load(content)
                # Aligned with loop_context_helpers.py (Align Schema)
                required = ["id", "name", "description", "entrypoint", "kind", "domain", "risk_level", "output_trust", "permissions"]
                found_keys = (data or {}).keys()
                missing = [k for k in required if k not in found_keys]
                
                if missing:
                    # Enhanced feedback: Fuzzy match for common typos (e.g. kinds -> kind)
                    hints = []
                    for m in missing:
                        matches = difflib.get_close_matches(m, found_keys, n=1, cutoff=0.6)
                        if matches:
                            hints.append(f"Found key '{matches[0]}', did you mean '{m}'?")
                    
                    template = (
                        "id: \"plugin_id\"\n"
                        "name: \"Plugin Name\"\n"
                        "description: \"...\"\n"
                        "entrypoint: \"logic:run\"\n"
                        "kind: \"external\"\n"
                        "domain: \"extensions\"\n"
                        "risk_level: \"low\"\n"
                        "output_trust: \"untrusted\"\n"
                        "permissions: []"
                    )
                    error_msg = f"Manifest validation failed: missing required keys: {missing}"
                    if hints:
                        error_msg += f". {' '.join(hints)}"
                        
                    logger.error(f"fs.write_file: {path_str} write REJECTED due to missing keys: {missing}")
                    return {
                        "status": "error",
                        "error": error_msg,
                        "hint": f"The manifest is MISSING required fields. Use this template for full compatibility:\n\n{template}",
                        "path": path_str
                    }
            except Exception as ye:
                # Hard Validation: Block writing if YAML is invalid
                logger.error(f"fs.write_file: {path_str} write REJECTED due to invalid YAML: {ye}")
                from quentin.infra.tools.sanitizer import SemanticHintGenerator
                enriched = SemanticHintGenerator.enrich_error("fs.write_file", ye)
                return {
                    "status": "error",
                    "error": f"Manifest YAML parse error in {path_str}: {ye}",
                    "hint": enriched.get("hint", "Ensure your YAML syntax is correct, especially indentation."),
                    "path": path_str
                }

        # Perform the actual write
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

        # P5: Surgery Twenty-five - Perception Event Bus
        try:
            from quentin.runtime.system_events import system_events
            system_events.enqueue_event(
                event_type="physical_change",
                source="fs.write_file",
                session_id="global",
                payload={"path": str(path_str)}
            )
        except Exception as e:
            print(f"DEBUG: Failed to emit event: {e}")
            pass
        
        # --- [6.3] Lint-on-Write for Python files ---
        if path_str.endswith(".py"):
            try:
                compile(content, path_str, 'exec')
            except SyntaxError as se:
                # P5: Self-healing Lint (Handle escaped newlines \\n)
                if "\\n" in content and ("unexpected character" in str(se) or "line continuation" in str(se)):
                    try:
                        healed_content = content.replace("\\n", "\n")
                        compile(healed_content, path_str, 'exec')
                        # If compile succeeds with healed content, overwrite the file
                        target.write_text(healed_content, encoding="utf-8")
                        logger.info(f"fs.write_file: Self-healed syntax error (escaped newlines) in {path_str}")
                        return {"status": "ok", "result": f"File {path_str} written (self-healed escaped newlines)."}
                    except Exception:
                        pass

                logger.warning(f"fs.write_file: Syntax error detected in {path_str}: {se}")
                # Note: We still write the file (to allow inspection), but return error status
                return {
                    "status": "error", 
                    "error": f"Python Syntax Error in {path_str}: {se.msg} at Line {se.lineno}.",
                    "instruction": f"Please fix the syntax error at line {se.lineno} and retry. Common issues include unclosed quotes or missing brackets.",
                    "partial_content_saved": True
                }

        logger.info(f"fs.write_file: {target} written successfully.")
        return {"status": "ok", "result": f"File {path_str} written."}
    except Exception as e:
        msg = str(e)
        if "Is a directory" in msg:
            return _err_with_hint(
                msg,
                hint="A directory exists where a file write was requested.",
                next_actions=[
                    "List the parent directory to confirm: use `ls`.",
                    "Remove/rename the conflicting directory, then retry fs.write_file.",
                ],
            )
        if "outside repo_root" in msg or "Absolute path not allowed" in msg or "not under allowed roots" in msg:
            return _err_with_hint(
                msg,
                hint=f"The target path '{path_str}' violates path safety policy. Access is restricted to specific allowed roots.",
                next_actions=[
                    "Write to 'mutable/' directory instead (e.g., 'mutable/filename.md').",
                    "Check 'quentin/kernel/path_guard.py' for allowed write roots.",
                    "Set QUENTIN_PATH_GUARD_EXTRA_ALLOWED_ROOTS to add safe write roots (comma-separated).",
                    "Use a repo-relative path without '..' or absolute prefixes.",
                ],
            )
        return _err_with_hint(msg)


def fs_get_write_policy(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    _ = (params, context)
    policy = _current_write_policy()
    return {
        "status": "ok",
        "result": "Current write policy",
        "allowed_roots": policy["allowed_roots"],
        "extra_allowed_roots_env": policy["extra_allowed_roots_env"],
    }

def fs_mkdir(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    path_str = params.get("path")
    if not path_str:
        return _err_with_hint("Missing path", hint="Specify directory path to create.")
        
    try:
        from quentin.kernel.path_guard import PathGuard
        guard = PathGuard(repo_root=Path(".").resolve(), allowed_roots=None)
        target = guard.ensure_allowed_path(path_str)
        
        if target.exists():
            if target.is_dir():
                return {"status": "ok", "result": f"Directory already exists: {path_str}", "already_existed": True}
            return _err_with_hint(
                f"Path exists but is a file: {path_str}", 
                hint="mkdir cannot override a file. (Common error: trying to create a directory for a file path).",
                next_actions=[
                    "Use `ls` to check the parent directory.",
                    "If you intended to write a file, use `fs.write_file` directly (it creates parent directories automatically)."
                ]
            )

        # Pre-emptive check for file-like suffixes (Graceful Softening)
        file_suffixes = {".yaml", ".yml", ".py", ".json", ".md", ".txt", ".sh", ".toml", ".ini"}
        if target.suffix.lower() in file_suffixes:
            parent = target.parent
            if str(parent) != ".":
                logger.info(f"fs.mkdir: Softening for file-like path {path_str} -> {parent}")
                parent.mkdir(parents=True, exist_ok=True)
                return {
                    "status": "ok", 
                    "result": f"Parent directory created: {parent}",
                    "hint": f"Note: '{path_str}' looks like a file. I've created the parent directory '{parent}' instead. Reminder: `fs.write_file` creates parent directories automatically."
                }
            return {
                "status": "error",
                "error": f"PERMISSION_DENIED: Suspicious path for mkdir: {path_str}",
                "error_code": "TOOL_MISUSE_MKDIR_ON_FILE",
                "critical_failure": True,
                "hint": f"CRITICAL ERROR: This path ends with '{target.suffix}', which indicates a FILE. You are attempting to call mkdir on a file path, which is a major tool misuse. Use `fs.write_file` directly to write content to this path. DO NOT retry mkdir on this path.",
                "next_actions": [
                    "SWITCH TOOL: Use `fs.write_file` to create this file and its parent directories.",
                    "ABORT MKDIR: Do not attempt to create directories for individual file paths."
                ]
            }
            
        target.mkdir(parents=True, exist_ok=True)
        return {"status": "ok", "result": f"Directory created: {path_str}"}
    except Exception as e:
        return _err_with_hint(str(e))

def fs_search_replace(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """
    Surgically replace a string in a file. 
    Expects 'path', 'old_string', and 'new_string'.
    """
    path_str = params.get("path")
    old_string = params.get("old_string")
    new_string = params.get("new_string")
    
    if old_string is None or new_string is None:
        return _err_with_hint(
            "Missing path, old_string, or new_string",
            hint="Provide all three fields: `path`, `old_string`, and `new_string`.",
        )
        
    try:
        path_str = _ensure_str_path(path_str)
        target = _resolve_for_write(path_str)
        if not target.exists():
            return _err_with_hint(
                f"File not found: {path_str}",
                hint="Check whether the path exists and is under allowed write roots.",
                next_actions=["Use fs.read_file to inspect nearby files.", "List the directory to confirm path."],
            )
            
        content = target.read_text(encoding="utf-8")
        if old_string not in content:
            # P2.1: check if already applied
            if new_string in content:
                logger.info(f"fs.search_replace: replacement already present in {path_str}, skipping.")
                return {
                    "status": "ok", 
                    "result": "already_applied_skipped", 
                    "skipped": True,
                    "path": path_str
                }

            # P5: Surgery Sixty-three - Fuzzy Match Self-healing (OpenClaw Parity)
            from quentin.utils.fuzzy_matcher import FuzzyMatcher
            
            # 1. Check for simple whitespace differences
            ws_match = FuzzyMatcher.get_whitespace_agnostic_match(content, old_string)
            if ws_match:
                return _err_with_hint(
                    f"Search string not found in {path_str} (exact match failed)",
                    hint=f"The text exists but has different indentation or spacing. Use this EXACT string for 'old_string':\n\n{ws_match}",
                    next_actions=["Copy-paste the hinted text into your next tool call."]
                )
                
            # 2. Check for near-miss semantic match
            near_match = FuzzyMatcher.find_near_match(content, old_string)
            if near_match:
                match_text, line_idx = near_match
                return _err_with_hint(
                    f"Search string not found in {path_str} (near miss)",
                    hint=f"I found a 70%+ match at line {line_idx+1}. Is this what you meant? Use this EXACT string:\n\n{match_text}",
                    next_actions=["Read the file at that line to confirm the context."]
                )

            return _err_with_hint(
                f"Search string not found in {path_str}",
                hint="The match may be too specific or contain a typo.",
                next_actions=[
                    "Read the file first and copy the exact text snippet.",
                    "Use a broader search token before replace.",
                ],
            )
            
        count = content.count(old_string)
        if count > 1:
            return _err_with_hint(
                f"Multiple occurrences ({count}) found. Be more specific.",
                hint="The replacement target is ambiguous.",
                next_actions=[
                    "Use a longer unique context snippet.",
                    "Split into multiple targeted replacements.",
                ],
            )
            
        new_content = content.replace(old_string, new_string)
        
        # Pre-check syntax for .py files
        if path_str.endswith(".py"):
            try:
                compile(new_content, str(target), 'exec')
            except SyntaxError as se:
                return _err_with_hint(
                    f"Syntax error after replacement: {se.msg} (Line {se.lineno})",
                    hint="The replacement broke Python syntax.",
                    next_actions=["Adjust indentation or quotes.", "Apply a smaller replacement scope."],
                )

        target.write_text(new_content, encoding="utf-8")
        return {"status": "ok", "result": f"Successfully replaced in {path_str}."}
    except Exception as e:
        msg = str(e)
        if "outside repo_root" in msg or "Absolute path not allowed" in msg or "not under allowed roots" in msg:
            return _err_with_hint(
                msg,
                hint=f"The target path '{path_str}' violates path safety policy. Access is restricted to specific allowed roots.",
                next_actions=[
                    "Write to 'mutable/' directory instead (e.g., 'mutable/filename.md').",
                    "Check 'quentin/kernel/path_guard.py' for allowed write roots.",
                    "Set QUENTIN_PATH_GUARD_EXTRA_ALLOWED_ROOTS to add safe write roots (comma-separated).",
                    "Use a repo-relative path without '..' or absolute prefixes.",
                ],
            )
        return _err_with_hint(msg)

def fs_read_file(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    path_str = params.get("path")
        
    try:
        path_str = _ensure_str_path(path_str)
        target = _resolve_for_read(path_str)
        if not target.exists():
            return _err_with_hint(
                f"File not found: {path_str}",
                hint="The file does not exist at the given repo-relative path.",
                next_actions=["Check directory structure.", "Try a broader path prefix."],
            )
        
        # P5: OpenClaw Parity - MIME Sniffing / Binary Guard
        # We read first 1024 bytes to check for null bytes (typical binary file marker)
        with open(target, "rb") as f:
            chunk = f.read(1024)
            if b"\x00" in chunk:
                return _err_with_hint(
                    f"Refused to read binary file: {path_str}",
                    hint="fs.read_file only supports text-based formats. This file appears to be binary (PDF, Image, Executable, etc.).",
                    next_actions=["If it's an image, use vision tools.", "If it's a PDF, use specialized PDF parsing tools."],
                )

        content = target.read_text(encoding="utf-8", errors="ignore")
        return {"status": "ok", "result": content}
    except Exception as e:
        msg = str(e)
        if "outside repo_root" in msg or "Absolute path not allowed" in msg:
            return _err_with_hint(
                msg,
                hint="Read paths must remain inside repository root.",
                next_actions=["Use a repo-relative path.", "Avoid absolute or parent traversal paths."],
            )
        return _err_with_hint(msg)
