from __future__ import annotations
import socket
import logging
import re
from urllib.parse import urlparse
from typing import List, Set

logger = logging.getLogger(__name__)

class NetworkPolicyEnforcer:
    """
    P5: Ported from OpenClaw's network egress filter.
    Blocks unauthorized outbound connections at the application level.
    """
    
    # Default Safe Engineering Domains
    ALLOWLIST = {
        "github.com", "raw.githubusercontent.com",
        "pypi.org", "files.pythonhosted.org",
        "registry.npmjs.org", "yarnpkg.com",
        "huggingface.co", "cdn-lfs.huggingface.co",
        "openai.com", "anthropic.com", "googleapis.com"
    }
    
    # Blocked local metadata IPs (Anti-SSRF)
    BLOCKED_IPS = [
        "169.254.169.254", "127.0.0.1", "0.0.0.0", "::1"
    ]

    @classmethod
    def is_allowed(cls, url: str) -> bool:
        """
        Validates URL against allowlist and IP policy.
        """
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            if not hostname: return False
            
            # 1. Domain Whitelist Check
            # Allow exact match or subdomain
            allowed = False
            for domain in cls.ALLOWLIST:
                if hostname == domain or hostname.endswith(f".{domain}"):
                    allowed = True
                    break
            
            if not allowed:
                logger.warning(f"NetworkPolicy: Blocked domain {hostname}")
                return False
                
            # 2. DNS/IP Check (Anti-SSRF)
            # In a real system, we'd resolve and check IP ranges.
            # Simplified for surgery: check if hostname is a blocked IP literal
            if hostname in cls.BLOCKED_IPS:
                logger.critical(f"NetworkPolicy: Blocked SSRF attempt to {hostname}")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"NetworkPolicy: Check failed for {url}: {e}")
            return False
