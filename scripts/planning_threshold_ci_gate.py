from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Any


VERIFY_KEYS = (
    "QUENTIN_VERIFY_STRATEGY_SWITCH_MIN",
    "QUENTIN_VERIFY_INTERRUPT_EFFECTIVENESS_MIN",
    "QUENTIN_VERIFY_RESET_RECOVERY_MIN",
    "QUENTIN_VERIFY_PROGRESS_SYNC_COMPLIANCE_MIN",
    "QUENTIN_VERIFY_ATTEMPT_BAND_COVERAGE_MIN",
)


def _read_env(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    out: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _approval_allows(path: Path) -> tuple[bool, Dict[str, Any]]:
    if not path.exists():
        return False, {"reason": "approval_file_missing"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False, {"reason": "approval_file_invalid_json"}
    if not isinstance(data, dict):
        return False, {"reason": "approval_file_not_object"}
    if not bool(data.get("approved", False)):
        return False, {"reason": "approved_flag_false"}
    expires_at = str(data.get("expires_at") or "").strip()
    if expires_at:
        try:
            if date.today() > date.fromisoformat(expires_at):
                return False, {"reason": "approval_expired", "expires_at": expires_at}
        except Exception:
            return False, {"reason": "approval_invalid_expires_at", "expires_at": expires_at}
    return True, {
        "reason": "approved_override",
        "expires_at": expires_at,
        "ticket": str(data.get("ticket") or ""),
        "owner": str(data.get("owner") or ""),
    }


@dataclass
class GateResult:
    ok: bool
    status: str
    max_delta: float
    over_limit: list[Dict[str, Any]]
    compared: list[Dict[str, Any]]
    approval: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "status": str(self.status),
            "max_delta": float(self.max_delta),
            "over_limit": list(self.over_limit),
            "compared": list(self.compared),
            "approval": dict(self.approval),
        }


def run_gate(
    *,
    env_path: Path,
    patch_path: Path,
    approval_path: Path,
    max_delta: float,
) -> GateResult:
    base = _read_env(env_path)
    patch = _read_env(patch_path)
    compared: list[Dict[str, Any]] = []
    over_limit: list[Dict[str, Any]] = []
    for key in VERIFY_KEYS:
        b = _to_float(base.get(key))
        p = _to_float(patch.get(key))
        if b is None or p is None:
            continue
        delta = abs(p - b)
        item = {"key": key, "current": b, "recommended": p, "delta": delta}
        compared.append(item)
        if delta > max_delta:
            over_limit.append(item)

    if not compared:
        return GateResult(
            ok=True,
            status="no_comparable_keys",
            max_delta=max_delta,
            over_limit=[],
            compared=[],
            approval={"reason": "not_required"},
        )
    if not over_limit:
        return GateResult(
            ok=True,
            status="within_delta_limit",
            max_delta=max_delta,
            over_limit=[],
            compared=compared,
            approval={"reason": "not_required"},
        )

    allowed, approval = _approval_allows(approval_path)
    if allowed:
        return GateResult(
            ok=True,
            status="over_limit_but_approved",
            max_delta=max_delta,
            over_limit=over_limit,
            compared=compared,
            approval=approval,
        )
    return GateResult(
        ok=False,
        status="over_limit_without_approval",
        max_delta=max_delta,
        over_limit=over_limit,
        compared=compared,
        approval=approval,
    )


def main() -> int:
    p = argparse.ArgumentParser(description="CI gate for threshold recommendation drift.")
    p.add_argument("--env", default=".env", help="Current env file")
    p.add_argument("--patch", default="generated/benchmarks/planning_threshold_env_patch.env", help="Recommended env patch file")
    p.add_argument("--approval", default="config/planning_threshold_gate_approval.json", help="Manual approval json file")
    p.add_argument("--report", default="generated/benchmarks/planning_threshold_gate_report.json", help="Gate report json")
    p.add_argument("--max-delta", type=float, default=0.08, help="Allowed absolute drift before requiring approval")
    args = p.parse_args()

    result = run_gate(
        env_path=Path(args.env),
        patch_path=Path(args.patch),
        approval_path=Path(args.approval),
        max_delta=max(0.0, float(args.max_delta)),
    )
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result.to_dict(), ensure_ascii=False))
    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
