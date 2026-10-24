from __future__ import annotations

import logging
from typing import List, Dict, Optional
from quentin.llm.auth_profiles import AuthProfile, get_auth_manager

logger = logging.getLogger(__name__)

class AuthRotator:
    """
    Manages multi-key rotation and cooldown tracking.
    Aligned with OpenClaw's auth-profile ordering.
    """
    def __init__(self, provider: str):
        self.provider = provider
        self.auth_mgr = get_auth_manager()

    def get_next_available_profile(self) -> Optional[AuthProfile]:
        """
        Retrieves the best available profile, automatically 
        handling rotation and ignoring those in cooldown.
        """
        profile = self.auth_mgr.get_best_profile(self.provider)
        if not profile:
            logger.error(f"No available auth profiles for provider: {self.provider}")
        return profile

    def report_failure(self, profile_id: str, error_code: str):
        """Marks a profile as failing to trigger rotation."""
        logger.warning(f"Rotating away from profile {profile_id} due to {error_code}")
        self.auth_mgr.report_result(profile_id, success=False, error_code=error_code)

    def report_success(self, profile_id: str):
        """Confirms profile is working."""
        self.auth_mgr.report_result(profile_id, success=True)
