from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from quentin.tools.middleware.base import ToolMiddleware, BeforeOutcome, AfterOutcome, ToolCallContextLike
from quentin.tools.schemas import ToolCallResult
from quentin.llm.auth_profiles import get_auth_manager

logger = logging.getLogger(__name__)

class AuthRotationMiddleware:
    """
    P5: Ported from OpenClaw's auth-profiles.ts.
    Automatically rotates API keys/profiles on 429 (Rate Limit) or 401 (Auth) errors.
    """
    id = "auth_rotator"
    priority = 100 # High priority to catch errors before other middlewares

    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries

    def before(self, *, tool_name: str, params: Dict[str, Any], ctx: ToolCallContextLike) -> BeforeOutcome:
        return BeforeOutcome(params=params)

    def after(self, *, tool_name: str, params: Dict[str, Any], result: ToolCallResult, ctx: ToolCallContextLike) -> AfterOutcome:
        if result.success:
            return AfterOutcome(result=result)

        err_str = str(result.error or "").lower()
        category = "unknown"
        if "429" in err_str or "rate limit" in err_str:
            category = "rate_limit"
        elif "401" in err_str or "unauthorized" in err_str or "invalid api key" in err_str:
            category = "auth"
        
        if category in ("rate_limit", "auth"):
            md = ctx.metadata or {}
            profile_id = md.get("auth_profile_id")
            provider = md.get("provider")
            
            if profile_id and provider:
                auth_mgr = get_auth_manager()
                logger.warning(f"AuthRotator: Tool {tool_name} failed with {category}. Marking profile {profile_id} as failed.")
                auth_mgr.report_result(profile_id, success=False, error_code=category)
                
                # Signal that a retry is needed with a new profile
                # Note: The middleware itself can't easily re-invoke the tool manager's full stack
                # but it can tag the result so the CognitiveLoop knows to rotate and retry.
                result.meta["requires_auth_rotation"] = True
                result.meta["failed_profile_id"] = profile_id
                result.meta["error_category"] = category

        return AfterOutcome(result=result)
