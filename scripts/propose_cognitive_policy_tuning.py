from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import yaml


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _extract_rates(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    pred: List[float] = []
    mis: List[float] = []
    for r in rows:
        payload = r.get("payload") if isinstance(r.get("payload"), dict) else {}
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else payload
        if not isinstance(metrics, dict):
            continue
        if metrics.get("prediction_error_rate") is not None:
            try:
                pred.append(float(metrics.get("prediction_error_rate")))
            except Exception:
                pass
        if metrics.get("context_misclass_rate") is not None:
            try:
                mis.append(float(metrics.get("context_misclass_rate")))
            except Exception:
                pass
    pred_avg = (sum(pred) / len(pred)) if pred else 0.0
    mis_avg = (sum(mis) / len(mis)) if mis else 0.0
    return {"prediction_error_rate_avg": float(pred_avg), "context_misclass_rate_avg": float(mis_avg)}


def _propose(base: Dict[str, Any], rates: Dict[str, float]) -> Dict[str, Any]:
    p = float(rates.get("prediction_error_rate_avg") or 0.0)
    c = float(rates.get("context_misclass_rate_avg") or 0.0)
    out = dict(base)

    if p >= 0.5:
        out["enable_expectation_engine"] = False
        out["enable_situation_to_skill"] = False
    elif p <= 0.2 and c <= 0.2:
        out["enable_expectation_engine"] = True
        out["enable_situation_to_skill"] = True

    if c >= 0.35:
        out["attention_target_ratio"] = 0.12
    elif c <= 0.15:
        out["attention_target_ratio"] = 0.18
    else:
        out["attention_target_ratio"] = float(base.get("attention_target_ratio", 0.15))

    # Keep bounds strict.
    try:
        out["attention_target_ratio"] = max(0.05, min(0.3, float(out["attention_target_ratio"])))
    except Exception:
        out["attention_target_ratio"] = 0.15
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Propose cognitive policy tuning from trace metrics.")
    parser.add_argument("--events", default="data/traces/events.jsonl")
    parser.add_argument("--policy-path", default="config/cognitive_policies.yaml")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    events_path = Path(args.events)
    policy_path = Path(args.policy_path)
    rows = _read_jsonl(events_path)
    rates = _extract_rates(rows)

    base = {
        "enable_situation_classifier": True,
        "enable_attention_filter": True,
        "enable_expectation_engine": False,
        "enable_situation_to_skill": False,
        "attention_target_ratio": 0.15,
        "prediction_error_fallback_to_planner": True,
        "debug_use_full_context": False,
        "enable_gist_injection": True,
        "gist_top_k": 3,
    }
    if policy_path.exists():
        try:
            obj = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
            cp = obj.get("cognitive_policies") if isinstance(obj, dict) else None
            if isinstance(cp, dict):
                base.update(cp)
        except Exception:
            pass

    proposed = _propose(base, rates)
    out = {"rates": rates, "proposed": proposed}
    print(json.dumps(out, ensure_ascii=False))

    if args.apply:
        body = {"cognitive_policies": proposed}
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text(yaml.safe_dump(body, sort_keys=False, allow_unicode=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
