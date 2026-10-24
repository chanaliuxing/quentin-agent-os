# meta_agent/config/feature_flags.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, Optional
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)

PROMPT_MIGRATION_TRACE_PREFIX = "prompt_migration_"
PROMPT_MIGRATION_M1_SYSTEM_FACTORY = "PROMPT_MIGRATION_M1_SYSTEM_FACTORY"
PROMPT_MIGRATION_M2_EXEC_STYLE = "PROMPT_MIGRATION_M2_EXEC_STYLE"
PROMPT_MIGRATION_M3_SYSTEM_EVENTS = "PROMPT_MIGRATION_M3_SYSTEM_EVENTS"
PROMPT_MIGRATION_M4_TOOL_SUMMARY = "PROMPT_MIGRATION_M4_TOOL_SUMMARY"
PROMPT_MIGRATION_M5_SUBAGENT_MINIMAL = "PROMPT_MIGRATION_M5_SUBAGENT_MINIMAL"
PROMPT_MIGRATION_M6_SOP_SKILLS = "PROMPT_MIGRATION_M6_SOP_SKILLS"
PROMPT_MIGRATION_M7_SILENT_PROTOCOL = "PROMPT_MIGRATION_M7_SILENT_PROTOCOL"
PROMPT_MIGRATION_M8_CONTEXT_PRUNING = "PROMPT_MIGRATION_M8_CONTEXT_PRUNING"
PROMPT_MIGRATION_FLAGS: tuple[str, ...] = (
    PROMPT_MIGRATION_M1_SYSTEM_FACTORY,
    PROMPT_MIGRATION_M2_EXEC_STYLE,
    PROMPT_MIGRATION_M3_SYSTEM_EVENTS,
    PROMPT_MIGRATION_M4_TOOL_SUMMARY,
    PROMPT_MIGRATION_M5_SUBAGENT_MINIMAL,
    PROMPT_MIGRATION_M6_SOP_SKILLS,
    PROMPT_MIGRATION_M7_SILENT_PROTOCOL,
    PROMPT_MIGRATION_M8_CONTEXT_PRUNING,
)

PROMPT_MIGRATION_SYSTEM_EVENT_ENQUEUED = f"{PROMPT_MIGRATION_TRACE_PREFIX}system_event_enqueued"
PROMPT_MIGRATION_SYSTEM_EVENT_INJECTED = f"{PROMPT_MIGRATION_TRACE_PREFIX}system_event_injected"


@dataclass
class AutoPatchFlag:
    enabled: bool = True
    reason: str = ""
    case_id: Optional[str] = None


@dataclass
class OrchestratorBudgetOverride:
    target: str         # e.g. "desktop::*" or "global" or concrete task name
    reduce_factor: float
    case_id: Optional[str] = None
    reason: str = ""


class FeatureFlagManager:
    def __init__(
        self,
        flags_root: str | Path = "data",
    ):
        self.flags_root = Path(flags_root)

    # ---------- Auto patch 开关 ----------

    def get_auto_patch_flag(self) -> AutoPatchFlag:
        """
        ImmuneLoop 会写 data/feature_flags/auto_patch_disabled.json:
        {
          "disabled": true,
          "reason": "...",
          "case_id": "..."
        }
        """
        flag_path = self.flags_root / "feature_flags" / "auto_patch_disabled.json"
        if not flag_path.exists():
            return AutoPatchFlag(enabled=True)

        try:
            data = json.loads(flag_path.read_text(encoding="utf-8") or "{}")
        except Exception:
            logger.warning("Failed to read auto_patch flag file.", exc_info=True)
            return AutoPatchFlag(enabled=True)

        disabled = bool(data.get("disabled", False))
        return AutoPatchFlag(
            enabled=not disabled,
            reason=data.get("reason", ""),
            case_id=data.get("case_id"),
        )

    def is_auto_patch_enabled(self) -> bool:
        return self.get_auto_patch_flag().enabled

    # ---------- Orchestrator 预算覆盖（限流） ----------

    def get_orchestrator_budget_overrides(self) -> Dict[str, OrchestratorBudgetOverride]:
        """
        ImmuneLoop 写 data/immune/orchestrator_budget_overrides.json:
        {
          "desktop::*": {
            "reduce_factor": 0.5,
            "case_id": "...",
            "reason": "..."
          },
          "global": {...}
        }
        """
        path = self.flags_root / "immune" / "orchestrator_budget_overrides.json"
        overrides: Dict[str, OrchestratorBudgetOverride] = {}

        if not path.exists():
            return overrides

        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
        except Exception:
            logger.warning("Failed to read orchestrator budget overrides.", exc_info=True)
            return overrides

        for key, val in data.items():
            try:
                overrides[key] = OrchestratorBudgetOverride(
                    target=key,
                    reduce_factor=float(val.get("reduce_factor", 1.0)),
                    case_id=val.get("case_id"),
                    reason=val.get("reason", ""),
                )
            except Exception:
                continue

        return overrides

    def find_budget_override_for_task(self, task_name: str) -> Optional[OrchestratorBudgetOverride]:
        """
        简单匹配策略：
        - 精确匹配 task_name
        - 匹配 domain::*（例如 desktop::*）
        - fallback "global"
        """
        overrides = self.get_orchestrator_budget_overrides()

        # 精确匹配
        if task_name in overrides:
            return overrides[task_name]

        # domain::* 匹配
        # 比如你的 task_name 是 "skill_evolution_desktop"
        # 你可以约定 domain 前缀用 '_' 分割，或者自己写映射
        for key, ov in overrides.items():
            if key.endswith("::*"):
                prefix = key[:-3]
                if task_name.startswith(prefix):
                    return ov

        # 全局
        if "global" in overrides:
            return overrides["global"]

        return None

    # ---------- Runtime prompt migration 开关 ----------

    def _load_runtime_flags(self) -> Dict[str, Any]:
        """
        Read optional runtime flags from:
        data/feature_flags/runtime_flags.json
        """
        flag_path = self.flags_root / "feature_flags" / "runtime_flags.json"
        if not flag_path.exists():
            return {}
        try:
            data = json.loads(flag_path.read_text(encoding="utf-8") or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            logger.warning("Failed to read runtime feature flags.", exc_info=True)
            return {}

    @staticmethod
    def _parse_bool(raw: Any, default: bool = False) -> bool:
        if raw is None:
            return default
        if isinstance(raw, bool):
            return raw
        text = str(raw).strip().lower()
        if text in ("1", "true", "yes", "on"):
            return True
        if text in ("0", "false", "no", "off"):
            return False
        return default

    def is_runtime_flag_enabled(self, name: str, default: bool = False) -> bool:
        """
        Resolve runtime flag by precedence:
        1) ENV: QUENTIN_FF_<NAME>
        2) data/feature_flags/runtime_flags.json
        3) default
        """
        import os

        cleaned = str(name or "").strip().upper()
        if not cleaned:
            return bool(default)

        env_key = f"QUENTIN_FF_{cleaned}"
        env_val = os.getenv(env_key)
        if env_val is not None:
            return self._parse_bool(env_val, default=default)

        file_flags = self._load_runtime_flags()
        if cleaned in file_flags:
            return self._parse_bool(file_flags.get(cleaned), default=default)

        return bool(default)

    def is_prompt_migration_enabled(self, name: str, default: bool = False) -> bool:
        cleaned = str(name or "").strip().upper()
        if not cleaned:
            return bool(default)
        if cleaned not in PROMPT_MIGRATION_FLAGS:
            return self.is_runtime_flag_enabled(cleaned, default=default)
        return self.is_runtime_flag_enabled(cleaned, default=default)

    def get_prompt_migration_flags(self, default: bool = False) -> Dict[str, bool]:
        result: Dict[str, bool] = {}
        for flag in PROMPT_MIGRATION_FLAGS:
            result[flag] = self.is_prompt_migration_enabled(flag, default=default)
        return result


# 默认单例
feature_flags = FeatureFlagManager()
