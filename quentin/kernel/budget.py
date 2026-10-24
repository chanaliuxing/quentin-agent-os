from __future__ import annotations

from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, Optional
import json
import logging
from datetime import datetime, date

logger = logging.getLogger(__name__)


@dataclass
class BudgetProfile:
    """
    某个预算 profile（比如 'default', 'research', 'prod_trading'）的配额：

    - daily_token_limit / monthly_token_limit
    - daily_usd_limit   / monthly_usd_limit
    - hard_stop: 超出是否直接拒绝（True）还是只告警（False）
    """

    profile_id: str
    daily_token_limit: int
    monthly_token_limit: int

    daily_usd_limit: float
    monthly_usd_limit: float

    hard_stop: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BudgetUsage:
    """
    某 profile 当前的使用状态：
    - day / month 维度的 tokens / usd
    """

    profile_id: str
    day: str           # YYYY-MM-DD
    month: str         # YYYY-MM
    tokens_today: int
    tokens_month: int
    usd_today: float
    usd_month: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BudgetDecision:
    allow: bool
    reason: str
    remaining_tokens_today: int
    remaining_tokens_month: int
    remaining_usd_today: float
    remaining_usd_month: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BudgetController:
    """
    BudgetController v1：

    - 使用 config/budgets.json 定义多个 BudgetProfile
    - 使用 data/budget_state.json 维护当前使用量
    - 提供 check_and_reserve(profile_id, tokens, usd) 进行限额检查 + 预定

    budgets.json 示例：

    {
      "profiles": {
        "default": {
          "daily_token_limit": 200000,
          "monthly_token_limit": 5000000,
          "daily_usd_limit": 5.0,
          "monthly_usd_limit": 100.0,
          "hard_stop": true
        },
        "research": {
          "daily_token_limit": 1000000,
          "monthly_token_limit": 2e7,
          "daily_usd_limit": 20.0,
          "monthly_usd_limit": 400.0,
          "hard_stop": false
        }
      },
      "routing": {
        "environment:prod": "default",
        "environment:sandbox": "research",
        "domain:trading": "default"
      }
    }
    """

    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        budgets_config_path: str | Path = "config/budgets.json",
        state_path: str | Path = "data/budget_state.json",
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.budgets_config_path = self.repo_root / budgets_config_path
        self.state_path = self.repo_root / state_path
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

        self._profiles: Dict[str, BudgetProfile] = {}
        self._routing: Dict[str, str] = {}
        self._usage: Dict[str, BudgetUsage] = {}

        self._load_config()
        self._load_state()

    # ---------- 配额检查入口 ----------

    def resolve_profile(self, *, environment: str, domain: str) -> str:
        """
        根据 environment / domain 选择 profile_id。
        优先级：
          1) domain:xxx
          2) environment:xxx
          3) default
        """
        key_dom = f"domain:{domain}"
        key_env = f"environment:{environment}"
        if key_dom in self._routing:
            return self._routing[key_dom]
        if key_env in self._routing:
            return self._routing[key_env]
        return "default"

    def check_and_reserve(
        self,
        *,
        profile_id: str,
        tokens: int,
        usd: float,
    ) -> BudgetDecision:
        import os
        is_canary = os.getenv("QUENTIN_CANARY", "0").strip().lower() in ("1", "true", "yes", "on")
        
        today = date.today().strftime("%Y-%m-%d")
        month = date.today().strftime("%Y-%m")

        profile = self._profiles.get(profile_id)
        if not profile:
            # 如果没配置 profile，则视作无限额，但会 Warn
            logger.warning("BudgetController: profile '%s' not found, treating as unlimited.", profile_id)
            profile = BudgetProfile(
                profile_id=profile_id,
                daily_token_limit=10**12,
                monthly_token_limit=10**13,
                daily_usd_limit=10**6,
                monthly_usd_limit=10**7,
                hard_stop=False,
            )

        # Canary override: strict limits
        if is_canary:
            # Max 50k tokens per day, max 1.0 USD per day in canary mode
            canary_token_limit = 50_000
            canary_usd_limit = 1.0
            profile = BudgetProfile(
                profile_id=f"canary:{profile_id}",
                daily_token_limit=min(profile.daily_token_limit, canary_token_limit),
                monthly_token_limit=profile.monthly_token_limit,
                daily_usd_limit=min(profile.daily_usd_limit, canary_usd_limit),
                monthly_usd_limit=profile.monthly_usd_limit,
                hard_stop=True, # Always hard stop in canary
            )

        usage = self._usage.get(profile_id)
        if not usage or usage.day != today or usage.month != month:
            usage = BudgetUsage(
                profile_id=profile_id,
                day=today,
                month=month,
                tokens_today=0,
                tokens_month=0,
                usd_today=0.0,
                usd_month=0.0,
            )

        new_tokens_today = usage.tokens_today + tokens
        new_tokens_month = usage.tokens_month + tokens
        new_usd_today = usage.usd_today + usd
        new_usd_month = usage.usd_month + usd

        over_daily_tokens = new_tokens_today > profile.daily_token_limit
        over_month_tokens = new_tokens_month > profile.monthly_token_limit
        over_daily_usd = new_usd_today > profile.daily_usd_limit
        over_month_usd = new_usd_month > profile.monthly_usd_limit

        any_over = over_daily_tokens or over_month_tokens or over_daily_usd or over_month_usd

        if any_over and profile.hard_stop:
            # 不更新 usage，直接拒绝
            reason = "Budget exceeded: "
            parts = []
            if over_daily_tokens:
                parts.append("daily tokens")
            if over_month_tokens:
                parts.append("monthly tokens")
            if over_daily_usd:
                parts.append("daily USD")
            if over_month_usd:
                parts.append("monthly USD")
            reason += ", ".join(parts)
            return BudgetDecision(
                allow=False,
                reason=reason,
                remaining_tokens_today=max(0, profile.daily_token_limit - usage.tokens_today),
                remaining_tokens_month=max(0, profile.monthly_token_limit - usage.tokens_month),
                remaining_usd_today=max(0.0, profile.daily_usd_limit - usage.usd_today),
                remaining_usd_month=max(0.0, profile.monthly_usd_limit - usage.usd_month),
            )

        # 允许，更新 usage
        usage.tokens_today = new_tokens_today
        usage.tokens_month = new_tokens_month
        usage.usd_today = new_usd_today
        usage.usd_month = new_usd_month
        self._usage[profile_id] = usage
        self._flush_state()

        reason = "Within budget."
        if any_over and not profile.hard_stop:
            reason = "Budget exceeded soft limit, but hard_stop=false."

        return BudgetDecision(
            allow=True,
            reason=reason,
            remaining_tokens_today=max(0, profile.daily_token_limit - usage.tokens_today),
            remaining_tokens_month=max(0, profile.monthly_token_limit - usage.tokens_month),
            remaining_usd_today=max(0.0, profile.daily_usd_limit - usage.usd_today),
            remaining_usd_month=max(0.0, profile.monthly_usd_limit - usage.usd_month),
        )

    # ---------- 配置 & 状态 ----------

    def _load_config(self) -> None:
        if not self.budgets_config_path.exists():
            # 默认一个“无限但 soft 限制”的 default profile
            self._profiles = {
                "default": BudgetProfile(
                    profile_id="default",
                    daily_token_limit=1_000_000,
                    monthly_token_limit=20_000_000,
                    daily_usd_limit=10.0,
                    monthly_usd_limit=200.0,
                    hard_stop=False,
                )
            }
            self._routing = {}
            return
        try:
            raw = json.loads(self.budgets_config_path.read_text(encoding="utf-8") or "{}")
        except Exception:
            logger.exception("BudgetController._load_config: failed to read %s", self.budgets_config_path)
            raw = {}

        profiles_raw = raw.get("profiles") or {}
        routing_raw = raw.get("routing") or {}

        self._profiles = {}
        for pid, pdata in profiles_raw.items():
            self._profiles[pid] = BudgetProfile(
                profile_id=pid,
                daily_token_limit=int(pdata.get("daily_token_limit", 0)),
                monthly_token_limit=int(pdata.get("monthly_token_limit", 0)),
                daily_usd_limit=float(pdata.get("daily_usd_limit", 0.0)),
                monthly_usd_limit=float(pdata.get("monthly_usd_limit", 0.0)),
                hard_stop=bool(pdata.get("hard_stop", True)),
                metadata=pdata.get("metadata") or {},
            )
        self._routing = {str(k): str(v) for k, v in routing_raw.items()}

    def _load_state(self) -> None:
        if not self.state_path.exists():
            self._usage = {}
            return
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8") or "{}")
            self._usage = {
                pid: BudgetUsage(
                    profile_id=pid,
                    day=v["day"],
                    month=v["month"],
                    tokens_today=int(v["tokens_today"]),
                    tokens_month=int(v["tokens_month"]),
                    usd_today=float(v["usd_today"]),
                    usd_month=float(v["usd_month"]),
                )
                for pid, v in raw.items()
            }
        except Exception:
            logger.exception("BudgetController._load_state: failed to read %s", self.state_path)
            self._usage = {}

    def _flush_state(self) -> None:
        try:
            raw = {pid: u.to_dict() for pid, u in self._usage.items()}
            self.state_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("BudgetController._flush_state: failed to write %s", self.state_path)
