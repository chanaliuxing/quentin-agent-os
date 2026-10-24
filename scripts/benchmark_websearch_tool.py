from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import parse_qs, urlparse


@dataclass
class ScoreWeights:
    manifest: int = 20
    logic_load: int = 20
    contract: int = 20
    functional: int = 30
    quality: int = 10


@dataclass
class BenchmarkConfig:
    pass_score: int = 75
    fail_on_critical_missing: bool = True
    weights: ScoreWeights = field(default_factory=ScoreWeights)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def _load_py_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("web_search_logic", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to create module spec for {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self) -> dict[str, Any]:
        return self._payload


def _fake_requests_get(url: str, timeout: int | None = None) -> _FakeResponse:
    _ = timeout
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    q = (qs.get("q") or [""])[0]
    num_str = (qs.get("num") or ["5"])[0]
    try:
        num = max(1, int(num_str))
    except Exception:
        num = 5
    if "simulate_error" in q:
        return _FakeResponse(500, {"error": "simulated backend failure"})
    items = [
        {
            "title": f"{q} title {idx}",
            "link": f"https://example.com/{q}/{idx}",
            "snippet": f"{q} snippet {idx}",
        }
        for idx in range(1, num + 1)
    ]
    return _FakeResponse(200, {"items": items})


def _install_fake_requests() -> Any:
    prev = sys.modules.get("requests")
    fake = ModuleType("requests")
    fake.get = _fake_requests_get  # type: ignore[attr-defined]
    sys.modules["requests"] = fake
    return prev


def _restore_requests(prev: Any) -> None:
    if prev is None:
        sys.modules.pop("requests", None)
    else:
        sys.modules["requests"] = prev


def _check_manifest(manifest_path: Path) -> dict[str, Any]:
    out = {
        "exists": manifest_path.exists(),
        "parse_ok": False,
        "required_fields_ok": False,
        "output_trust_untrusted": False,
        "entrypoint_ok": False,
    }
    if not manifest_path.exists():
        return out
    text = _safe_read(manifest_path)
    data: dict[str, Any] = {}
    try:
        import yaml  # type: ignore

        parsed = yaml.safe_load(text)
        if isinstance(parsed, dict):
            data = parsed
            out["parse_ok"] = True
    except Exception:
        for line in text.splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            data[k.strip()] = v.strip()
        out["parse_ok"] = bool(data)
    required = ("name", "id", "description", "entrypoint")
    out["required_fields_ok"] = all(str(data.get(k) or "").strip() for k in required)
    out["output_trust_untrusted"] = str(data.get("output_trust") or "").strip().lower() == "untrusted"
    entry = str(data.get("entrypoint") or "").strip()
    out["entrypoint_ok"] = entry in {"logic.py", "logic:run", "logic:perform_search"} or entry.startswith("logic")
    return out


def _check_quality(logic_text: str) -> dict[str, Any]:
    lower = logic_text.lower()
    return {
        "no_placeholder_api_key": "your_api_key" not in lower and "your_cx_id" not in lower,
        "no_interactive_input": "input(" not in lower,
        "no_hardcoded_main_only": "__name__ == '__main__'" not in lower and '__name__ == "__main__"' not in lower,
    }


def _check_logic(tool_dir: Path) -> dict[str, Any]:
    logic_path = tool_dir / "logic.py"
    out: dict[str, Any] = {
        "exists": logic_path.exists(),
        "import_ok": False,
        "has_run": False,
        "has_perform_search": False,
        "functional_valid_query_ok": False,
        "functional_result_schema_ok": False,
        "functional_max_results_respected": False,
        "functional_empty_query_safe": False,
        "errors": [],
    }
    if not logic_path.exists():
        return out

    logic_text = _safe_read(logic_path)
    try:
        mod = _load_py_module(logic_path)
        out["import_ok"] = True
    except Exception as e:
        out["errors"].append(f"import failed: {e}")
        return out

    out["has_run"] = callable(getattr(mod, "run", None))
    out["has_perform_search"] = callable(getattr(mod, "perform_search", None))
    search_fn = getattr(mod, "perform_search", None)
    if not callable(search_fn):
        return out

    prev_requests = _install_fake_requests()
    try:
        result = search_fn("openai", 3)
        out["functional_valid_query_ok"] = isinstance(result, list)
        if isinstance(result, list) and result:
            schema_ok = all(isinstance(item, dict) and {"title", "url", "snippet"}.issubset(set(item.keys())) for item in result)
            out["functional_result_schema_ok"] = bool(schema_ok)
            out["functional_max_results_respected"] = len(result) <= 3

        try:
            empty_result = search_fn("", 5)
            out["functional_empty_query_safe"] = isinstance(empty_result, (list, dict, str))
        except Exception:
            out["functional_empty_query_safe"] = False
    except Exception as e:
        out["errors"].append(f"functional call failed: {e}")
    finally:
        _restore_requests(prev_requests)

    out["quality_checks"] = _check_quality(logic_text)
    return out


def _ratio(flags: list[bool]) -> float:
    if not flags:
        return 0.0
    return sum(1 for x in flags if x) / len(flags)


def _score(manifest: dict[str, Any], logic: dict[str, Any], cfg: BenchmarkConfig) -> dict[str, Any]:
    w = cfg.weights
    manifest_flags = [
        bool(manifest.get("exists")),
        bool(manifest.get("parse_ok")),
        bool(manifest.get("required_fields_ok")),
        bool(manifest.get("output_trust_untrusted")),
        bool(manifest.get("entrypoint_ok")),
    ]
    logic_load_flags = [bool(logic.get("exists")), bool(logic.get("import_ok"))]
    contract_flags = [bool(logic.get("has_run") or logic.get("has_perform_search"))]
    functional_flags = [
        bool(logic.get("functional_valid_query_ok")),
        bool(logic.get("functional_result_schema_ok")),
        bool(logic.get("functional_max_results_respected")),
        bool(logic.get("functional_empty_query_safe")),
    ]
    quality_map = logic.get("quality_checks") or {}
    quality_flags = [bool(quality_map.get("no_placeholder_api_key")), bool(quality_map.get("no_interactive_input")), bool(quality_map.get("no_hardcoded_main_only"))]

    scores = {
        "manifest": round(w.manifest * _ratio(manifest_flags), 2),
        "logic_load": round(w.logic_load * _ratio(logic_load_flags), 2),
        "contract": round(w.contract * _ratio(contract_flags), 2),
        "functional": round(w.functional * _ratio(functional_flags), 2),
        "quality": round(w.quality * _ratio(quality_flags), 2),
    }
    total = round(sum(scores.values()), 2)
    critical_fail = (not manifest.get("exists")) or (not logic.get("exists")) or (not logic.get("import_ok"))
    passed = total >= cfg.pass_score and (not cfg.fail_on_critical_missing or not critical_fail)
    return {"scores": scores, "total": total, "passed": passed, "critical_fail": critical_fail}


def _load_previous(path: Path | None) -> dict[str, Any] | None:
    if not path or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _compare(current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    cur = float(((current.get("score") or {}).get("total")) or 0.0)
    if not previous:
        return {"baseline_found": False, "delta_total": None, "improved": None}
    prev = float(((previous.get("score") or {}).get("total")) or 0.0)
    delta = round(cur - prev, 2)
    return {"baseline_found": True, "previous_total": prev, "current_total": cur, "delta_total": delta, "improved": delta > 0}


def run_benchmark(tool_dir: Path, *, config: BenchmarkConfig, previous_report: Path | None = None) -> dict[str, Any]:
    manifest = _check_manifest(tool_dir / "manifest.yaml")
    logic = _check_logic(tool_dir)
    score = _score(manifest, logic, config)
    report = {
        "generated_at": _now(),
        "tool_dir": str(tool_dir),
        "manifest": manifest,
        "logic": logic,
        "score": score,
    }
    report["comparison"] = _compare(report, _load_previous(previous_report))
    return report


def main() -> int:
    p = argparse.ArgumentParser(description="Benchmark WebSearch tool quality and compare with baseline.")
    p.add_argument("--tool-dir", default="extensions/tools/web_search", help="Tool directory path")
    p.add_argument("--previous-report", default="", help="Previous benchmark report path")
    p.add_argument("--output", default="generated/benchmarks/web_search_benchmark_report.json", help="Output report path")
    p.add_argument("--pass-score", type=int, default=75, help="Pass threshold")
    args = p.parse_args()

    cfg = BenchmarkConfig(pass_score=args.pass_score)
    report = run_benchmark(
        Path(args.tool_dir),
        config=cfg,
        previous_report=Path(args.previous_report) if args.previous_report else None,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(out), "total": report["score"]["total"], "passed": report["score"]["passed"], "comparison": report["comparison"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
