from __future__ import annotations

import os
import re
from typing import Any, Dict, Tuple


def _is_small_local_model(provider: str, model_name: str) -> bool:
    prov = (provider or "").strip().lower()
    name = (model_name or "").strip().lower()
    if prov not in {"ollama", "local", "unknown"}:
        return False
    if not name:
        return False
    if any(tag in name for tag in ("qwen", "llama", "mistral", "deepseek", "phi", "gemma")):
        m = re.search(r"(\d+(?:\.\d+)?)\s*b", name)
        if m:
            try:
                return float(m.group(1)) <= 14.0
            except Exception:
                return True
        return True
    return False


def apply_model_dialect(
    *,
    provider: str,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
) -> Tuple[str, str, Dict[str, Any]]:
    """
    Apply lightweight prompt dialect adaptation by provider/model.
    Returns (system_prompt, user_prompt, meta).
    """
    sp = str(system_prompt or "")
    up = str(user_prompt or "")
    before_len = len(sp) + len(up)
    profile = "default_noop"

    if str(os.getenv("QUENTIN_DISABLE_MODEL_DIALECT", "0")).strip().lower() in {"1", "true", "yes", "on"}:
        meta = {"dialect_profile": "disabled_noop", "prompt_compaction_ratio": 1.0}
        return sp, up, meta

    prov = (provider or "").strip().lower()
    model = (model_name or "").strip().lower()

    if prov == "gemini":
        dynamic_lines = []
        static_lines = []
        for line in sp.splitlines():
            low = line.lower()
            if any(k in low for k in ("trace_id", "session", "runtime", "tool state", "metadata", "context snapshot", "cancel_token")):
                dynamic_lines.append(line)
            else:
                static_lines.append(line)
        if dynamic_lines:
            prefill = "Runtime context (prefill):\n" + "\n".join(dynamic_lines).strip()
            up = f"{prefill}\n\n{up}".strip()
            sp = "\n".join(static_lines).strip()
            profile = "gemini_prefill"
        else:
            profile = "gemini_noop"

    elif prov in {"anthropic", "claude"}:
        profile = "anthropic_noop"

    elif _is_small_local_model(prov, model):
        # Keep local-model instructions short and explicit.
        if len(sp) > 1000:
            sp = sp[:1000].rstrip() + "\n[Prompt compacted for local model.]"
        if len(up) > 12000:
            up = up[:12000]
        profile = "local_small_compact"

    after_len = max(1, len(sp) + len(up))
    ratio = round(float(after_len) / float(max(1, before_len)), 4)
    meta = {"dialect_profile": profile, "prompt_compaction_ratio": ratio}
    return sp, up, meta

