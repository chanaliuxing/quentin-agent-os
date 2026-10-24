from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

from quentin.cognitive.perception.schemas import SituationAssessment


class SituationClassifier(Protocol):
    def classify(self, *, ctx: Dict[str, Any]) -> SituationAssessment: ...


@dataclass
class RuleBasedSituationClassifier:
    """
    v0 situation classifier: conservative, rule-first, cheap.

    Expected ctx keys (best-effort):
    - url, window_title, app_name, ui_tree, logs_excerpt, system_event_prompt
    """

    def classify(self, *, ctx: Dict[str, Any]) -> SituationAssessment:
        url = str(ctx.get("url") or "").strip().lower()
        title = str(ctx.get("window_title") or ctx.get("app_title") or "").strip().lower()
        app = str(ctx.get("app_name") or "").strip().lower()
        logs = str(ctx.get("logs_excerpt") or ctx.get("system_event_prompt") or "").strip().lower()
        ui_tree = ctx.get("ui_tree")

        # Login / auth expired
        login_markers = ("login", "sign in", "log in", "reauth", "expired", "two-factor", "2fa")
        if any(m in url for m in login_markers) or any(m in title for m in login_markers) or any(m in logs for m in login_markers):
            return SituationAssessment(
                situation_id="login_or_auth",
                confidence=0.65,
                features={"url": url[:200], "window_title": title[:200], "app": app[:80]},
            )

        # Error modal / failure signals
        error_markers = ("error", "failed", "permission denied", "forbidden", "unauthorized", "timeout")
        if any(m in logs for m in error_markers) or any(m in title for m in error_markers):
            return SituationAssessment(
                situation_id="error_or_blocked",
                confidence=0.55,
                features={"window_title": title[:200], "app": app[:80]},
            )

        # Desktop automation hint
        if app in {"finder", "system events"} or ("desktop" in logs):
            return SituationAssessment(
                situation_id="desktop_generic",
                confidence=0.45,
                features={"app": app[:80], "window_title": title[:200]},
            )

        # UI tree presence hint (but we keep it generic to avoid overfitting)
        if isinstance(ui_tree, dict) and ui_tree:
            return SituationAssessment(
                situation_id="ui_tree_present",
                confidence=0.35,
                features={"has_ui_tree": True, "app": app[:80]},
            )

        return SituationAssessment(
            situation_id="unknown_text_only",
            confidence=0.25,
            features={"app": app[:80]},
        )

