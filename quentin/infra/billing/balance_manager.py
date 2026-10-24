from __future__ import annotations
import logging
import threading
import os
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class BalanceManager:
    """
    P5: Ported from OpenClaw's real-time billing system.
    Handles streaming credit tracking and mid-call balance guards.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(BalanceManager, cls).__new__(cls)
                cls._instance.balances: Dict[str, float] = {} # user_id -> usd_balance
                # P0: Cache bypass state during initialization for reliability across layers
                bypass_env = os.getenv("QUENTIN_BILLING_BYPASS", "0").strip().lower()
                cls._instance.global_bypass = bypass_env in {"1", "true", "yes", "on"}
                if cls._instance.global_bypass:
                    logger.info("BalanceManager: Global Billing Bypass is ACTIVE (Infinite Mode).")
        return cls._instance

    def set_balance(self, user_id: str, amount: float):
        self.balances[user_id] = amount

    def get_balance(self, user_id: str) -> float:
        return self.balances.get(user_id, 0.0)

    def deduct_realtime(self, user_id: str, tokens: int, price_per_1k: float = 0.01) -> bool:
        """
        Deducts tokens from balance. Returns False if balance exhausted.
        """
        # P0: Use cached global bypass for speed and consistency
        if getattr(self, "global_bypass", False):
            return True

        cost = (tokens / 1000.0) * price_per_1k
        
        with self._lock:
            current = self.balances.get(user_id, 0.0)
            if current < cost:
                return False
            self.balances[user_id] = current - cost
            return True

# Global Singleton
balance_manager = BalanceManager()
