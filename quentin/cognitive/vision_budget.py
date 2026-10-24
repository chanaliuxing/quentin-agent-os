from __future__ import annotations

import os
import json
from datetime import datetime, UTC
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "1" if default else "0")
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class VisionTokenBudget:
    total_tokens: int
    screenshot_tokens: int
    ui_tree_tokens: int
    ocr_tokens: int
    strategy: str = "vision_budget_v1"
    task_class: str = "general"
    feedback_applied: bool = False
    feedback_sample_size: int = 0
    feedback_avg_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _feedback_path() -> Path:
    raw = str(os.getenv("QUENTIN_VISION_BUDGET_FEEDBACK_PATH", "data/metrics/vision_budget_feedback.jsonl") or "").strip()
    p = Path(raw)
    if p.is_absolute():
        return p
    return (Path.cwd() / p).resolve()


def _read_feedback_rows(*, limit: int = 500) -> List[Dict[str, Any]]:
    path = _feedback_path()
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                try:
                    row = json.loads(s)
                except Exception:
                    continue
                if isinstance(row, dict):
                    out.append(row)
    except Exception:
        return []
    if limit > 0 and len(out) > limit:
        return out[-limit:]
    return out


def _safe_score(value: Any, default: float = 0.0) -> float:
    try:
        return float(max(0.0, min(1.0, float(value))))
    except Exception:
        return float(default)


def _extract_judge_score(metadata: Dict[str, Any] | None) -> float | None:
    md = metadata if isinstance(metadata, dict) else {}
    direct_keys = (
        "judge_score",
        "quality_judge_score",
        "done_confidence",
        "vision_judge_score",
    )
    for k in direct_keys:
        if k in md:
            try:
                return _safe_score(md.get(k), 0.0)
            except Exception:
                continue
    nested = md.get("judge_signals") if isinstance(md.get("judge_signals"), dict) else {}
    for k in ("judge_score", "done_confidence", "quality_score", "confidence"):
        if k in nested:
            try:
                return _safe_score(nested.get(k), 0.0)
            except Exception:
                continue
    return None


def _blend_effective_score(*, outcome_score: float, judge_score: float | None) -> float:
    base = _safe_score(outcome_score, 0.0)
    if judge_score is None:
        return base
    weight = _safe_score(os.getenv("QUENTIN_VISION_BUDGET_JUDGE_WEIGHT", "0.45"), 0.45)
    return (1.0 - weight) * base + weight * _safe_score(judge_score, 0.0)


def record_vision_budget_feedback(
    *,
    domain: str,
    task_class: str,
    budget: Dict[str, Any],
    outcome_score: float,
    success: bool,
    metadata: Dict[str, Any] | None = None,
) -> None:
    if not _env_bool("QUENTIN_VISION_BUDGET_FEEDBACK_ENABLED", True):
        return
    b = budget if isinstance(budget, dict) else {}
    total = max(1, int(b.get("total_tokens") or 0))
    shot = int(b.get("screenshot_tokens") or 0)
    ui = int(b.get("ui_tree_tokens") or 0)
    ocr = int(b.get("ocr_tokens") or 0)
    raw_score = _safe_score(outcome_score, 0.0)
    judge_score = _extract_judge_score(metadata)
    effective_score = _blend_effective_score(outcome_score=raw_score, judge_score=judge_score)
    row = {
        "timestamp": datetime.now(UTC).isoformat(),
        "domain": str(domain or "").strip().lower() or "unknown",
        "task_class": str(task_class or "").strip().lower() or "general",
        "outcome_score": raw_score,
        "judge_score": judge_score,
        "effective_outcome_score": effective_score,
        "success": bool(success),
        "budget": {
            "total_tokens": total,
            "screenshot_tokens": shot,
            "ui_tree_tokens": ui,
            "ocr_tokens": ocr,
            "screenshot_ratio": float(shot) / float(total),
            "ui_tree_ratio": float(ui) / float(total),
            "ocr_ratio": float(ocr) / float(total),
        },
        "metadata": dict(metadata or {}),
    }
    path = _feedback_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def summarize_vision_budget_feedback(*, limit: int = 800) -> Dict[str, Any]:
    rows = _read_feedback_rows(limit=limit)
    out: Dict[str, Any] = {
        "total_rows": len(rows),
        "avg_outcome_score": 0.0,
        "avg_effective_outcome_score": 0.0,
        "judge_signal_coverage": 0.0,
        "by_task_class": [],
        "source": str(_feedback_path()),
    }
    if not rows:
        return out
    total_score = 0.0
    total_effective_score = 0.0
    judge_rows = 0
    buckets: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        score = _safe_score(r.get("outcome_score"), 0.0)
        effective = _safe_score(r.get("effective_outcome_score", score), score)
        total_score += score
        total_effective_score += effective
        if r.get("judge_score") is not None:
            judge_rows += 1
        tc = str(r.get("task_class") or "general")
        b = buckets.setdefault(
            tc,
            {"task_class": tc, "count": 0, "score_sum": 0.0, "effective_score_sum": 0.0, "judge_rows": 0},
        )
        b["count"] += 1
        b["score_sum"] += score
        b["effective_score_sum"] += effective
        if r.get("judge_score") is not None:
            b["judge_rows"] += 1
    out["avg_outcome_score"] = float(total_score) / float(len(rows))
    out["avg_effective_outcome_score"] = float(total_effective_score) / float(len(rows))
    out["judge_signal_coverage"] = float(judge_rows) / float(len(rows))
    by = []
    for b in buckets.values():
        c = max(1, int(b["count"]))
        by.append(
            {
                "task_class": b["task_class"],
                "count": int(b["count"]),
                "avg_outcome_score": float(b["score_sum"]) / float(c),
                "avg_effective_outcome_score": float(b["effective_score_sum"]) / float(c),
                "judge_signal_coverage": float(int(b["judge_rows"])) / float(c),
            }
        )
    by.sort(key=lambda x: (-int(x["count"]), str(x["task_class"])))
    out["by_task_class"] = by
    return out


def _feedback_adjustment(*, domain: str, task_class: str) -> Dict[str, Any]:
    if not _env_bool("QUENTIN_VISION_BUDGET_FEEDBACK_ENABLED", True):
        return {"applied": False, "sample_size": 0, "avg_score": 0.0, "delta": {"screenshot": 0.0, "ui_tree": 0.0, "ocr": 0.0}}
    rows = _read_feedback_rows(limit=int(os.getenv("QUENTIN_VISION_BUDGET_FEEDBACK_LOOKBACK", "600") or "600"))
    d = str(domain or "").strip().lower()
    tc = str(task_class or "").strip().lower()
    filtered = [
        r for r in rows
        if str(r.get("domain") or "").strip().lower() == d
        and str(r.get("task_class") or "").strip().lower() == tc
    ]
    min_samples = max(4, int(os.getenv("QUENTIN_VISION_BUDGET_FEEDBACK_MIN_SAMPLES", "8") or "8"))
    if len(filtered) < min_samples:
        return {"applied": False, "sample_size": len(filtered), "avg_score": 0.0, "delta": {"screenshot": 0.0, "ui_tree": 0.0, "ocr": 0.0}}
    avg = sum(_safe_score(r.get("effective_outcome_score", r.get("outcome_score")), 0.0) for r in filtered) / float(len(filtered))
    delta = {"screenshot": 0.0, "ui_tree": 0.0, "ocr": 0.0}
    if avg < 0.60:
        if tc == "doc_ocr":
            delta = {"screenshot": -0.06, "ui_tree": -0.02, "ocr": 0.08}
        elif tc in {"debug_ui", "layout_compare"}:
            delta = {"screenshot": 0.06, "ui_tree": -0.03, "ocr": -0.03}
        else:
            delta = {"screenshot": -0.03, "ui_tree": 0.05, "ocr": -0.02}
    elif avg > 0.88:
        delta = {"screenshot": -0.01, "ui_tree": 0.01, "ocr": 0.0}
    return {"applied": any(abs(v) > 1e-6 for v in delta.values()), "sample_size": len(filtered), "avg_score": float(avg), "delta": delta}


def allocate_vision_token_budget(*, domain: str, metadata: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not _env_bool("QUENTIN_VISION_BUDGET_ENABLED", True):
        return {}

    md = metadata or {}
    base_total = int(os.getenv("QUENTIN_VISION_BUDGET_TOTAL_TOKENS", "5000") or "5000")
    domain_key = str(domain or "").strip().lower()
    if domain_key == "mobile":
        base_total = int(os.getenv("QUENTIN_VISION_BUDGET_TOTAL_TOKENS_MOBILE", str(base_total)) or str(base_total))
    elif domain_key == "web":
        base_total = int(os.getenv("QUENTIN_VISION_BUDGET_TOTAL_TOKENS_WEB", str(base_total)) or str(base_total))
    elif domain_key == "desktop":
        base_total = int(os.getenv("QUENTIN_VISION_BUDGET_TOTAL_TOKENS_DESKTOP", str(base_total)) or str(base_total))

    if bool(md.get("high_visual_complexity", False)):
        base_total = int(base_total * 1.2)
    task_class = str(md.get("vision_task_class") or md.get("task_class") or "general").strip().lower()
    entropy = float(md.get("screenshot_entropy", 0.5) or 0.5)
    adaptive_enabled = _env_bool("QUENTIN_VISION_BUDGET_ADAPTIVE_ENABLED", True)

    screenshot_ratio = float(os.getenv("QUENTIN_VISION_BUDGET_SCREENSHOT_RATIO", "0.65") or "0.65")
    ui_tree_ratio = float(os.getenv("QUENTIN_VISION_BUDGET_UI_TREE_RATIO", "0.25") or "0.25")
    if adaptive_enabled:
        if task_class == "debug_ui":
            screenshot_ratio = max(screenshot_ratio, 0.72)
            ui_tree_ratio = min(ui_tree_ratio, 0.20)
        elif task_class == "doc_ocr":
            screenshot_ratio = max(0.55, screenshot_ratio - 0.05)
            ui_tree_ratio = min(ui_tree_ratio, 0.18)
        elif task_class == "layout_compare":
            screenshot_ratio = max(screenshot_ratio, 0.76)
            ui_tree_ratio = min(ui_tree_ratio, 0.16)

        # Low-entropy screenshot: down-budget screenshot branch and allocate to OCR/UI.
        low_entropy_threshold = float(os.getenv("QUENTIN_VISION_BUDGET_LOW_ENTROPY_THRESHOLD", "0.25") or "0.25")
        if entropy <= low_entropy_threshold:
            screenshot_ratio = max(0.40, screenshot_ratio - 0.12)
            ui_tree_ratio = min(0.35, ui_tree_ratio + 0.06)

    adj = _feedback_adjustment(domain=domain_key, task_class=task_class)
    if bool(adj.get("applied", False)):
        delta = adj.get("delta") if isinstance(adj.get("delta"), dict) else {}
        screenshot_ratio += float(delta.get("screenshot") or 0.0)
        ui_tree_ratio += float(delta.get("ui_tree") or 0.0)
        # ocr is derived from residual; keep non-negative via normalization below.

    screenshot_ratio = max(0.35, min(0.82, screenshot_ratio))
    ui_tree_ratio = max(0.10, min(0.40, ui_tree_ratio))
    if (screenshot_ratio + ui_tree_ratio) > 0.90:
        # Keep some OCR floor.
        overflow = (screenshot_ratio + ui_tree_ratio) - 0.90
        ui_tree_ratio = max(0.10, ui_tree_ratio - overflow)

    ocr_ratio = max(0.0, 1.0 - screenshot_ratio - ui_tree_ratio)

    screenshot_tokens = max(200, int(base_total * screenshot_ratio))
    ui_tree_tokens = max(100, int(base_total * ui_tree_ratio))
    ocr_tokens = max(50, base_total - screenshot_tokens - ui_tree_tokens)

    return VisionTokenBudget(
        total_tokens=base_total,
        screenshot_tokens=screenshot_tokens,
        ui_tree_tokens=ui_tree_tokens,
        ocr_tokens=ocr_tokens,
        task_class=task_class,
        feedback_applied=bool(adj.get("applied", False)),
        feedback_sample_size=int(adj.get("sample_size") or 0),
        feedback_avg_score=float(adj.get("avg_score") or 0.0),
    ).to_dict()
