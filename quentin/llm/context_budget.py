from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ContextWindowInfo:
    tokens: int
    source: str


@dataclass
class ContextWindowGuardResult:
    tokens: int
    source: str
    prompt_tokens: int
    reserve_tokens: int
    total_tokens: int
    should_warn: bool
    should_block: bool
    reason: Optional[str] = None


def _env_int(name: str) -> Optional[int]:
    import os
    raw = os.getenv(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except Exception:
        return None


def _env_bool(name: str) -> Optional[bool]:
    import os
    raw = os.getenv(name)
    if raw is None:
        return None
    return raw.strip().lower() in ("1", "true", "yes", "on")


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def resolve_context_window_info(
    *,
    model_context_window: Optional[int],
    default_tokens: int,
    cap_tokens: Optional[int] = None,
) -> ContextWindowInfo:
    base = model_context_window or default_tokens
    base = max(1, int(base))
    if cap_tokens and cap_tokens > 0 and cap_tokens < base:
        return ContextWindowInfo(tokens=cap_tokens, source="cap")
    if model_context_window:
        return ContextWindowInfo(tokens=base, source="model")
    return ContextWindowInfo(tokens=base, source="default")


def evaluate_context_window_guard(
    *,
    info: ContextWindowInfo,
    prompt_text: str,
    reserve_tokens: int = 0,
    warn_below: int = 32_000,
    hard_min: int = 16_000,
) -> ContextWindowGuardResult:
    prompt_tokens = estimate_tokens(prompt_text)
    reserve = max(0, int(reserve_tokens))
    total = prompt_tokens + reserve
    warn_below = max(1, int(warn_below))
    hard_min = max(1, int(hard_min))

    should_block = False
    reason = None
    
    # [OpenClaw] Pre-emptive buffer: trigger compaction/guard BEFORE absolute overflow
    buffer_tokens = _env_int("LLM_PREEMPTIVE_BUFFER_TOKENS") or 2000
    
    if info.tokens < hard_min:
        should_block = True
        reason = "context_window_too_small"
    elif total > (info.tokens - buffer_tokens):
        # We haven't hit the hard limit, but we're in the 'danger zone'
        should_block = True
        reason = "context_near_overflow"
    elif total > info.tokens:
        should_block = True
        reason = "context_overflow"

    should_warn = info.tokens < warn_below or total > warn_below

    return ContextWindowGuardResult(
        tokens=info.tokens,
        source=info.source,
        prompt_tokens=prompt_tokens,
        reserve_tokens=reserve,
        total_tokens=total,
        should_warn=should_warn,
        should_block=should_block,
        reason=reason,
    )


def get_context_window_limit() -> int:
    return _env_int("LLM_CONTEXT_WINDOW_TOKENS") or 32_000


def apply_context_budget(
    *,
    prompt_text: str,
    context_window_tokens: Optional[int] = None,
    reserve_tokens: int = 0,
    warn_below_tokens: int = 32_000,
    hard_min_tokens: int = 16_000,
    auto_compact: bool = False,
    compaction_max_chars: Optional[int] = None,
    history_texts: Optional[list[str]] = None,
    keep_recent_turns: int = 0,
) -> tuple[str, ContextWindowGuardResult]:
    if context_window_tokens is None:
        context_window_tokens = _env_int("LLM_CONTEXT_WINDOW_TOKENS")
    if reserve_tokens == 0:
        reserve_tokens = _env_int("LLM_RESERVE_TOKENS") or 0
    if warn_below_tokens == 32_000:
        warn_below_tokens = _env_int("LLM_WARN_BELOW_TOKENS") or warn_below_tokens
    if hard_min_tokens == 16_000:
        hard_min_tokens = _env_int("LLM_HARD_MIN_TOKENS") or hard_min_tokens
    if not auto_compact:
        auto_compact = bool(_env_bool("LLM_AUTO_COMPACT"))

    if not context_window_tokens:
        info = resolve_context_window_info(
            model_context_window=None,
            default_tokens=hard_min_tokens,
            cap_tokens=None,
        )
        guard = evaluate_context_window_guard(
            info=info,
            prompt_text=prompt_text,
            reserve_tokens=reserve_tokens,
            warn_below=warn_below_tokens,
            hard_min=hard_min_tokens,
        )
        return prompt_text, guard

    info = resolve_context_window_info(
        model_context_window=context_window_tokens,
        default_tokens=context_window_tokens,
        cap_tokens=None,
    )
    guard = evaluate_context_window_guard(
        info=info,
        prompt_text=prompt_text,
        reserve_tokens=reserve_tokens,
        warn_below=warn_below_tokens,
        hard_min=hard_min_tokens,
    )
    if guard.should_block and guard.reason in ("context_overflow", "context_near_overflow") and history_texts:
        from quentin.llm.compaction import prune_history_texts

        pruned, changed = prune_history_texts(
            history_texts,
            max_chars=max(1, int(guard.tokens * 4)),
            keep_recent=keep_recent_turns,
        )
        if changed and pruned:
            prompt_text = "\n\n".join(pruned)
            guard = evaluate_context_window_guard(
                info=info,
                prompt_text=prompt_text,
                reserve_tokens=reserve_tokens,
                warn_below=warn_below_tokens,
                hard_min=hard_min_tokens,
            )
    if guard.should_block and guard.reason in ("context_overflow", "context_near_overflow") and auto_compact:
        # P5: Plug-in Compaction
        from quentin.llm.compactors.router import compactor_router
        
        # Determine strategy from env (default to 'truncate' for safety)
        import os
        strategy = os.getenv("QUENTIN_COMPACTION_STRATEGY", "truncate").strip().lower()
        compactor = compactor_router.get_compactor(strategy)
        
        max_chars = compaction_max_chars or max(1, guard.tokens * 4)
        result = compactor.compact(prompt_text, max_chars)
        prompt_text = result.text
        
        guard = evaluate_context_window_guard(
            info=info,
            prompt_text=prompt_text,
            reserve_tokens=reserve_tokens,
            warn_below=warn_below_tokens,
            hard_min=hard_min_tokens,
        )
    return prompt_text, guard
