from __future__ import annotations
import logging
import os
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ParameterScaler:
    """
    P5: Ported from OpenClaw's dynamic sampling control.
    Adjusts LLM parameters (temp, top_p) based on task failure history.
    """
    @staticmethod
    def scale(
        base_params: Dict[str, Any],
        failure_count: int,
        last_error: Optional[str] = None,
        token_usage: Optional[float] = None,
        context_window: Optional[int] = None,
        model_name: Optional[str] = None,
        provider_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Dynamically boosts creativity when the agent is stuck.
        """
        new_params = dict(base_params)
        model = str(model_name or os.getenv("LLM_MODEL", "")).strip().lower()
        provider = str(provider_name or os.getenv("QUENTIN_LLM_PROVIDER", "")).strip().lower()

        # 1. Base Scaling (OpenClaw Parity)
        # Every failure adds 0.1 to temperature up to 1.0
        current_temp = float(new_params.get("temperature", 0.0))
        temp_boost = failure_count * 0.1
        
        # 2. Pattern-based Boosting
        if last_error:
            err = last_error.lower()
            if "unchanged" in err or "stale" in err:
                # If world isn't moving, we need a big jump in creativity
                temp_boost += 0.3
            elif "repetition" in err:
                # If repeating, force more entropy
                temp_boost += 0.2
                new_params["top_p"] = min(1.0, float(new_params.get("top_p", 0.9)) + 0.05)

        new_params["temperature"] = min(1.0, current_temp + temp_boost)

        # 3. Token-usage hedge (OpenClaw-inspired):
        # when context/token pressure is high, reduce entropy to avoid long noisy generations.
        hedge_enabled = str(os.getenv("QUENTIN_PARAM_SCALER_TOKEN_HEDGE_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}
        if hedge_enabled:
            window = int(context_window or int(os.getenv("QUENTIN_PARAM_SCALER_CONTEXT_WINDOW", "128000") or "128000"))
            usage = float(token_usage or 0.0)
            high_watermark = float(os.getenv("QUENTIN_PARAM_SCALER_HIGH_WATERMARK", "0.75") or "0.75")
            ratio = (usage / max(1.0, float(window))) if usage > 0 else 0.0
            if ratio >= high_watermark:
                # The closer to limit, the stronger the hedge.
                severity = min(1.0, (ratio - high_watermark) / max(0.05, (1.0 - high_watermark)))
                temp_cut = 0.10 + (0.30 * severity)
                new_params["temperature"] = max(0.0, float(new_params.get("temperature", 0.0)) - temp_cut)
                new_params["top_p"] = min(float(new_params.get("top_p", 0.9)), 0.80 - (0.10 * severity))
                logger.info(
                    "ParamScaler: Token hedge activated (usage=%.0f/%d, ratio=%.2f), temp_cut=%.2f.",
                    usage,
                    window,
                    ratio,
                    temp_cut,
                )

        # 4. Provider/model-aware profile clamp.
        profile_enabled = str(os.getenv("QUENTIN_PARAM_SCALER_PROFILE_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}
        if profile_enabled:
            temp_min = float(os.getenv("QUENTIN_PARAM_SCALER_TEMP_MIN", "0.0") or "0.0")
            temp_max = float(os.getenv("QUENTIN_PARAM_SCALER_TEMP_MAX", "1.0") or "1.0")
            top_p_min = float(os.getenv("QUENTIN_PARAM_SCALER_TOP_P_MIN", "0.6") or "0.6")
            top_p_max = float(os.getenv("QUENTIN_PARAM_SCALER_TOP_P_MAX", "1.0") or "1.0")
            if "qwen" in model:
                temp_max = min(temp_max, float(os.getenv("QUENTIN_PARAM_SCALER_TEMP_MAX_QWEN", "0.85") or "0.85"))
            if "gemini" in model:
                temp_max = min(temp_max, float(os.getenv("QUENTIN_PARAM_SCALER_TEMP_MAX_GEMINI", "0.80") or "0.80"))
            if provider in {"anthropic", "claude"}:
                top_p_max = min(top_p_max, float(os.getenv("QUENTIN_PARAM_SCALER_TOP_P_MAX_ANTHROPIC", "0.95") or "0.95"))

            new_params["temperature"] = max(temp_min, min(temp_max, float(new_params.get("temperature", 0.0))))
            if "top_p" in new_params:
                new_params["top_p"] = max(top_p_min, min(top_p_max, float(new_params.get("top_p", 0.9))))

        # 5. Failure-history-aware throttling when repeated runtime failures persist.
        if failure_count >= max(2, int(os.getenv("QUENTIN_PARAM_SCALER_FAILURE_DOWNSHIFT_THRESHOLD", "3") or "3")):
            err = str(last_error or "").lower()
            if any(k in err for k in ("timeout", "rate limit", "resource busy", "context length")):
                new_params["temperature"] = max(0.0, float(new_params.get("temperature", 0.0)) - 0.10)
                new_params["top_p"] = min(float(new_params.get("top_p", 0.9)), 0.82)
                logger.info("ParamScaler: Failure-history downshift activated at failure_count=%s", failure_count)
        
        if temp_boost > 0:
            logger.info(f"ParamScaler: Applied boost of +{temp_boost:.2f} due to {failure_count} failures.")
            
        return new_params
