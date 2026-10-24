from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

import quentin.tools.execution_parity as _execution_parity  # noqa: E402

from quentin.observability.anomaly_detector import AnomalyTaskGenerator  # noqa: E402
from quentin.observability.dashboard import ObservabilityDashboard  # noqa: E402
from quentin.observability.service import ObservabilityService  # noqa: E402
from quentin.runtime.task_queue import TaskQueue  # noqa: E402
from quentin.tools.execution_parity import (  # noqa: E402
    agent_step_tool,
    canvas_tool,
    channels_listener_tool,
    cron_tool,
    discord_actions,
    gateway_tool,
    image_tool,
    message_tool,
    nodes_tool,
    session_status_tool,
    slack_actions,
    telegram_actions,
    whatsapp_actions,
    web_fetch_tool,
    web_search_tool,
    web_readability_tool,
)
from quentin.tools.shell import shell_poll_results, shell_run_command, shell_send_signal  # noqa: E402


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    xs = sorted(float(v) for v in values)
    if len(xs) == 1:
        return float(xs[0])
    k = (len(xs) - 1) * (float(pct) / 100.0)
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    if f == c:
        return float(xs[f])
    d0 = xs[f] * (c - k)
    d1 = xs[c] * (k - f)
    return float(d0 + d1)


def _clamp01(x: float) -> float:
    return float(max(0.0, min(1.0, float(x))))


def _ctx(repo_root: Path) -> Any:
    return SimpleNamespace(metadata={"repo_root": str(repo_root.resolve())})


@dataclass(frozen=True)
class BenchThresholds:
    # Performance (p95 thresholds, ms)
    web_readability_p95_ms_max: float = 20.0
    web_fetch_p95_ms_max: float = 35.0
    web_search_p95_ms_max: float = 15.0
    message_tool_p95_ms_max: float = 45.0
    gateway_tool_p95_ms_max: float = 20.0
    agent_step_p95_ms_max: float = 35.0
    image_tool_p95_ms_max: float = 80.0
    canvas_tool_p95_ms_max: float = 25.0
    nodes_tool_p95_ms_max: float = 35.0
    cron_tool_p95_ms_max: float = 35.0
    session_status_p95_ms_max: float = 80.0
    observability_overview_p95_ms_max: float = 250.0
    observability_overview_stress_ms_max: float = 800.0

    # Robustness / trend thresholds
    lease_contention_winners_max: int = 1
    # Max time to interrupt a long-running background process via SIGINT.
    shell_sigint_interrupt_p95_ms_max: float = 500.0
    # Max time to stop a SIGINT-resistant background process via graceful ladder.
    shell_graceful_stop_p95_ms_max: float = 1200.0
    dead_letter_growth_ratio_max: float = 3.0


@dataclass
class MetricSummary:
    runs: int
    avg_ms: float
    p50_ms: float
    p95_ms: float
    max_ms: float


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class BenchmarkConfig:
    iters: int = 30
    concurrency: int = 8
    stress_dead_letters: int = 5000
    stress_lease_events: int = 5000
    stress_canvas_components: int = 1000
    seed: int = 13
    thresholds: BenchThresholds = field(default_factory=BenchThresholds)


@dataclass
class BenchmarkReport:
    generated_at: str
    repo_root: str
    bench_root: str
    config: Dict[str, Any]
    metrics: Dict[str, Any]
    checks: Dict[str, Any]
    scores: Dict[str, Any]
    issues: List[Dict[str, Any]]
    pass_gate: bool


@dataclass
class _PatchedHttpPost:
    orig: Any

    def close(self) -> None:
        try:
            _execution_parity._http_post_json = self.orig
        except Exception:
            pass


def _patch_vision_api_stub(*, ocr_text: str = "bench ocr text", confidence: float = 0.95) -> _PatchedHttpPost:
    orig = getattr(_execution_parity, "_http_post_json", None)

    def _stub_post(url: str, payload: Dict[str, Any], timeout: float = 15.0) -> Dict[str, Any]:
        _ = (url, payload, timeout)
        body = json.dumps({"ocr_text": str(ocr_text or ""), "confidence": float(confidence)}, ensure_ascii=False)
        return {"status_code": 200, "body": body}

    _execution_parity._http_post_json = _stub_post
    return _PatchedHttpPost(orig=orig)


def _summarize_samples(samples_ms: List[float]) -> MetricSummary:
    xs = list(samples_ms)
    return MetricSummary(
        runs=len(xs),
        avg_ms=float(statistics.mean(xs)) if xs else 0.0,
        p50_ms=float(_percentile(xs, 50)),
        p95_ms=float(_percentile(xs, 95)),
        max_ms=float(max(xs)) if xs else 0.0,
    )


def _time_many(iters: int, fn: Callable[[], Any]) -> Tuple[List[float], List[Any]]:
    samples: List[float] = []
    outs: List[Any] = []
    for _ in range(max(1, int(iters))):
        t0 = time.perf_counter()
        out = fn()
        dt = (time.perf_counter() - t0) * 1000.0
        samples.append(float(dt))
        outs.append(out)
    return samples, outs


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _mk_png_1x1(path: Path) -> None:
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc`\x00\x00"
        b"\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def compute_execution_score(report: Dict[str, Any], thresholds: BenchThresholds) -> Dict[str, Any]:
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}

    perf_rows: List[Tuple[str, float, float]] = []
    for key, max_ms in [
        ("web_readability", thresholds.web_readability_p95_ms_max),
        ("web_fetch", thresholds.web_fetch_p95_ms_max),
        ("web_search", thresholds.web_search_p95_ms_max),
        ("message_tool", thresholds.message_tool_p95_ms_max),
        ("gateway_tool", thresholds.gateway_tool_p95_ms_max),
        ("agent_step", thresholds.agent_step_p95_ms_max),
        ("image_tool", thresholds.image_tool_p95_ms_max),
        ("canvas_tool", thresholds.canvas_tool_p95_ms_max),
        ("nodes_tool", thresholds.nodes_tool_p95_ms_max),
        ("cron_tool", thresholds.cron_tool_p95_ms_max),
        ("session_status", thresholds.session_status_p95_ms_max),
        ("observability_overview", thresholds.observability_overview_p95_ms_max),
    ]:
        p95 = float(((metrics.get(key) or {}).get("p95_ms") or 0.0))
        if p95 <= 0:
            continue
        # Full score at/under threshold; degrade smoothly when above.
        score = 1.0 if p95 <= max_ms else (max_ms / p95)
        perf_rows.append((key, float(score), p95))
    perf_score = float(statistics.mean([r[1] for r in perf_rows])) if perf_rows else 0.0

    correctness = list((checks.get("correctness") or {}).get("results") or [])
    robustness = list((checks.get("robustness") or {}).get("results") or [])
    observability = list((checks.get("observability") or {}).get("results") or [])

    def _pass_rate(rows: List[Dict[str, Any]]) -> float:
        if not rows:
            return 0.0
        ok = sum(1 for r in rows if bool((r or {}).get("passed")))
        return float(ok / max(1, len(rows)))

    correctness_score = _pass_rate(correctness)
    robustness_score = _pass_rate(robustness)
    observability_score = _pass_rate(observability)

    overall = (
        (0.35 * perf_score)
        + (0.35 * correctness_score)
        + (0.20 * robustness_score)
        + (0.10 * observability_score)
    )
    return {
        "performance": _clamp01(perf_score),
        "correctness": _clamp01(correctness_score),
        "robustness": _clamp01(robustness_score),
        "observability": _clamp01(observability_score),
        "overall": _clamp01(overall),
        "perf_breakdown": [
            {"metric": k, "score": _clamp01(s), "p95_ms": float(p95)} for k, s, p95 in perf_rows
        ],
    }


def run_benchmark(
    *,
    repo_root: Path,
    output: Path,
    history: Optional[Path] = None,
    previous: Optional[Path] = None,
    config: Optional[BenchmarkConfig] = None,
    keep_workdir: bool = False,
    min_overall_score: float = 0.80,
) -> Dict[str, Any]:
    cfg = config or BenchmarkConfig()
    random.seed(int(cfg.seed))
    os.environ.setdefault("QUENTIN_CANVAS_ACK_TIMEOUT_SEC", "120")

    previous_report: Dict[str, Any] = {}
    if previous is not None and previous.exists():
        try:
            raw = json.loads(previous.read_text(encoding="utf-8"))
            previous_report = raw if isinstance(raw, dict) else {}
        except Exception:
            previous_report = {}

    td_obj: Optional[tempfile.TemporaryDirectory[str]] = None
    bench_root = None
    if keep_workdir:
        bench_root = (repo_root / "generated" / "benchmarks" / f"exec_bench_workdir_{int(time.time())}").resolve()
        bench_root.mkdir(parents=True, exist_ok=True)
    else:
        td_obj = tempfile.TemporaryDirectory(prefix="exec_bench_")
        bench_root = Path(td_obj.name).resolve()

    ctx = _ctx(bench_root)
    issues: List[Dict[str, Any]] = []

    vision = _patch_vision_api_stub()
    try:
        # -------------------- Microbench: web readability
        html_cases = {
            "github_issue": (
                "https://github.com/org/repo/issues/1",
                "<html><body><header>Top</header><nav>Side</nav><main><article><h1>Issue</h1><p>Body</p></article></main><footer>Foot</footer></body></html>",
                ["Issue", "Body"],
                ["Top", "Foot"],
            ),
            "github_pr": (
                "https://github.com/org/repo/pull/1",
                "<html><body><header>Header</header><main><article><h1>PR Title</h1><p>Diff</p></article></main><div class=\"Layout-sidebar\">Sidebar Noise</div><footer>Footer</footer></body></html>",
                ["PR Title", "Diff"],
                ["Sidebar Noise", "Footer"],
            ),
            "devto": (
                "https://dev.to/a/b",
                "<html><body><aside class=\"crayons-layout__sidebar-left\">left</aside><article><h1>Dev</h1><p>Body</p></article><div id=\"comments-container\">comments</div></body></html>",
                ["Dev", "Body"],
                ["comments"],
            ),
            "stackoverflow": (
                "https://stackoverflow.com/questions/1/x",
                "<html><body><aside class=\"left-sidebar\">left</aside><article><h1>Q</h1><p>A</p></article><div id=\"comments\">noise</div></body></html>",
                ["Q", "A"],
                ["noise"],
            ),
            "medium": (
                "https://medium.com/@x/y",
                "<html><body><div class=\"metabar\">meta</div><article><h1>Story</h1><p>Body</p></article><section aria-label=\"Responses\">responses section</section></body></html>",
                ["Story", "Body"],
                ["meta", "responses section"],
            ),
            "reddit": (
                "https://www.reddit.com/r/test/comments/abc/post/",
                "<html><body><aside>sidebar</aside><article><h1>Post</h1><p>Body</p></article><div class=\"premium-banner\">ads</div><shreddit-comments>comments</shreddit-comments></body></html>",
                ["Post", "Body"],
                ["ads", "comments"],
            ),
            "nytimes": (
                "https://www.nytimes.com/2020/01/01/us/test.html",
                "<html><body><header>NY Header</header><article><h1>NY Title</h1><p>NY Body</p></article><div data-testid=\"ad\">ad</div><footer>NY Footer</footer></body></html>",
                ["NY Title", "NY Body"],
                ["ad", "NY Header", "NY Footer"],
            ),
            "substack": (
                "https://example.substack.com/p/test",
                "<html><body><aside>Aside</aside><article><h1>Substack Post</h1><p>Body</p></article><div class=\"subscribe-widget\">subscribe</div><section id=\"comments\">comments</section></body></html>",
                ["Substack Post", "Body"],
                ["subscribe", "comments", "Aside"],
            ),
            "wikipedia": (
                "https://en.wikipedia.org/wiki/Test",
                "<html><body><div id=\"mw-navigation\">nav</div><div id=\"mw-panel\">panel</div><article><h1>Wiki Title</h1><p>Wiki body</p></article><div class=\"mw-footer\">foot</div></body></html>",
                ["Wiki Title", "Wiki body"],
                ["nav", "panel", "foot"],
            ),
            "arxiv": (
                "https://arxiv.org/abs/0000.00000",
                "<html><body><div id=\"header\">Header</div><article><h1>Arxiv paper</h1><p>Abstract</p></article><div class=\"extra-services\">extras</div><div id=\"footer\">Footer</div></body></html>",
                ["Arxiv paper", "Abstract"],
                ["Header", "Footer", "extras"],
            ),
            "hackernews": (
                "https://news.ycombinator.com/item?id=1",
                "<html><body><center>chrome</center><table class=\"fatitem\"><tr><td>fat</td></tr></table><article><h1>HN Story</h1><p>Text</p></article></body></html>",
                ["HN Story", "Text"],
                ["chrome", "fat"],
            ),
            "generic": (
                "https://example.com/x",
                "<html><body><header>Header</header><nav>Nav</nav><article><h1>Gen</h1><p>Body</p></article><footer>Footer</footer></body></html>",
                ["Gen", "Body"],
                ["Header", "Nav", "Footer"],
            ),
        }

        web_samples: List[float] = []
        correctness_checks: List[CheckResult] = []

        def _web_call(url: str, html: str) -> Dict[str, Any]:
            return web_readability_tool({"url": url, "html": html, "apply_site_patch": True, "max_chars": 6000}, None)

        for site, (url, html, keep_tokens, drop_tokens) in html_cases.items():
            samples, outs = _time_many(cfg.iters, lambda u=url, h=html: _web_call(u, h))
            web_samples.extend(samples)
            last = outs[-1] if outs else {}
            content = str((last or {}).get("content") or "")
            ok = True
            missing: List[str] = []
            present: List[str] = []
            for t in keep_tokens:
                if t not in content:
                    ok = False
                    missing.append(t)
            for t in drop_tokens:
                if t in content:
                    ok = False
                    present.append(t)
            correctness_checks.append(
                CheckResult(
                    name=f"web_patch_{site}",
                    passed=ok,
                    detail=json.dumps({"missing": missing, "present": present}, ensure_ascii=False),
                )
            )

        web_summary = _summarize_samples(web_samples)
        if web_summary.p95_ms > cfg.thresholds.web_readability_p95_ms_max:
            issues.append(
                {
                    "severity": "medium",
                    "kind": "perf",
                    "metric": "web_readability.p95_ms",
                    "value_ms": web_summary.p95_ms,
                    "threshold_ms": cfg.thresholds.web_readability_p95_ms_max,
                }
            )

        # -------------------- Microbench: web fetch (offline extraction + SSRF/caching logic)
        fetch_samples: List[float] = []

        def _fetch_call(url: str, html: str) -> Dict[str, Any]:
            return web_fetch_tool(
                {
                    "url": url,
                    "html": html,  # offline path (no network)
                    "extract_mode": "text",
                    "max_chars": 6000,
                    "cache_enabled": True,
                    "cache_ttl_sec": 600,
                    "apply_site_patch": True,
                },
                ctx,
            )

        for site, (url, html, keep_tokens, drop_tokens) in html_cases.items():
            samples, outs = _time_many(cfg.iters, lambda u=url, h=html: _fetch_call(u, h))
            fetch_samples.extend(samples)
            last = outs[-1] if outs else {}
            content = str((last or {}).get("content") or "")
            ok = True
            missing: List[str] = []
            present: List[str] = []
            for t in keep_tokens:
                if t not in content:
                    ok = False
                    missing.append(t)
            for t in drop_tokens:
                if t in content:
                    ok = False
                    present.append(t)
            correctness_checks.append(
                CheckResult(
                    name=f"web_fetch_extract_{site}",
                    passed=ok,
                    detail=json.dumps({"missing": missing, "present": present}, ensure_ascii=False),
                )
            )

        fetch_summary = _summarize_samples(fetch_samples)
        if fetch_summary.p95_ms > cfg.thresholds.web_fetch_p95_ms_max:
            issues.append(
                {
                    "severity": "medium",
                    "kind": "perf",
                    "metric": "web_fetch.p95_ms",
                    "value_ms": fetch_summary.p95_ms,
                    "threshold_ms": cfg.thresholds.web_fetch_p95_ms_max,
                }
            )

        # -------------------- Microbench: web search (offline corpus)
        web_corpus = [
            {"title": "OpenAI API Quickstart", "url": "https://example.com/openai-quickstart", "snippet": "Use OpenAI API quickstart with Python."},
            {"title": "Cron scheduling guide", "url": "https://example.com/cron-guide", "snippet": "Cron expression and scheduling examples."},
            {"title": "Discord threading best practices", "url": "https://example.com/discord-threading", "snippet": "How to organize message threads in Discord."},
            {"title": "Web readability extraction", "url": "https://example.com/readability", "snippet": "Extract clean content from noisy HTML pages."},
        ]

        def _search_call(q: str) -> Dict[str, Any]:
            return web_search_tool({"query": q, "max_results": 3, "corpus": web_corpus}, ctx)

        search_samples, search_outs = _time_many(cfg.iters, lambda: _search_call("openai quickstart"))
        search_summary = _summarize_samples(search_samples)
        last_search = search_outs[-1] if search_outs else {}
        srows = list((last_search or {}).get("results") or [])
        correctness_checks.append(
            CheckResult(
                name="web_search_returns_ranked_results",
                passed=bool(srows and "openai" in str((srows[0] or {}).get("title") or "").lower()),
            )
        )
        empty_out = web_search_tool({"query": "", "max_results": 5, "corpus": web_corpus}, ctx)
        correctness_checks.append(
            CheckResult(
                name="web_search_empty_query_safe",
                passed=isinstance(empty_out, dict) and list(empty_out.get("results") or []) == [],
            )
        )
        if search_summary.p95_ms > cfg.thresholds.web_search_p95_ms_max:
            issues.append(
                {
                    "severity": "medium",
                    "kind": "perf",
                    "metric": "web_search.p95_ms",
                    "value_ms": search_summary.p95_ms,
                    "threshold_ms": cfg.thresholds.web_search_p95_ms_max,
                }
            )

        # -------------------- Microbench: unified message tool
        def _message_call() -> Dict[str, Any]:
            return asyncio.run(
                message_tool(
                    {
                        "platform": "discord",
                        "action": "send",
                        "text": "bench message",
                        "channel_id": "bench-c1",
                        "dry_run": True,
                    },
                    ctx,
                )
            )

        _ = _message_call()  # warmup adapter/loading path
        message_samples, message_outs = _time_many(cfg.iters, _message_call)
        message_summary = _summarize_samples(message_samples)
        last_message = message_outs[-1] if message_outs else {}
        correctness_checks.append(
            CheckResult(
                name="message_tool_send_routes",
                passed=(
                    isinstance(last_message, dict)
                    and str(last_message.get("status") or "") == "ok"
                    and str(last_message.get("platform") or "") == "discord"
                ),
            )
        )
        msg_fetch = asyncio.run(message_tool({"platform": "discord", "action": "fetch_thread", "thread_id": "discord:bench-c1"}, ctx))
        correctness_checks.append(
            CheckResult(
                name="message_tool_fetch_thread",
                passed=(isinstance(msg_fetch, dict) and int(msg_fetch.get("count") or 0) >= 1),
            )
        )
        msg_d1 = asyncio.run(
            message_tool(
                {
                    "platform": "discord",
                    "action": "send",
                    "text": "bench dedupe",
                    "channel_id": "bench-c2",
                    "dry_run": True,
                    "idempotency_key": "bench-msg-idem-1",
                },
                ctx,
            )
        )
        msg_d2 = asyncio.run(
            message_tool(
                {
                    "platform": "discord",
                    "action": "send",
                    "text": "bench dedupe",
                    "channel_id": "bench-c2",
                    "dry_run": True,
                    "idempotency_key": "bench-msg-idem-1",
                },
                ctx,
            )
        )
        correctness_checks.append(
            CheckResult(
                name="message_tool_idempotency_dedupes",
                passed=(str(msg_d1.get("status") or "") == "ok" and bool(msg_d2.get("deduped"))),
            )
        )
        if message_summary.p95_ms > cfg.thresholds.message_tool_p95_ms_max:
            issues.append(
                {
                    "severity": "medium",
                    "kind": "perf",
                    "metric": "message_tool.p95_ms",
                    "value_ms": message_summary.p95_ms,
                    "threshold_ms": cfg.thresholds.message_tool_p95_ms_max,
                }
            )

        # -------------------- Microbench: gateway tool
        def _gateway_call() -> Dict[str, Any]:
            return gateway_tool({"action": "status"}, ctx)

        _ = _gateway_call()  # warmup import path / FastAPI module load
        gateway_samples, gateway_outs = _time_many(cfg.iters, _gateway_call)
        gateway_summary = _summarize_samples(gateway_samples)
        last_gateway = gateway_outs[-1] if gateway_outs else {}
        correctness_checks.append(
            CheckResult(
                name="gateway_tool_status_shape",
                passed=(
                    isinstance(last_gateway, dict)
                    and str(last_gateway.get("status") or "") in {"ok", "error"}
                    and ("provider_count" in last_gateway or "error" in last_gateway)
                ),
            )
        )
        gw_in = gateway_tool({"action": "inbound", "platform": "discord", "text": "hi", "metadata": {"channel_id": "gw-c1"}}, ctx)
        correctness_checks.append(
            CheckResult(
                name="gateway_tool_inbound_accepts",
                passed=(isinstance(gw_in, dict) and str(gw_in.get("status") or "") in {"accepted", "error"}),
            )
        )
        gw_d1 = gateway_tool(
            {
                "action": "outbound",
                "platform": "discord",
                "channel_id": "gw-c2",
                "text": "hello",
                "dry_run": True,
                "idempotency_key": "bench-gw-idem-1",
            },
            ctx,
        )
        gw_d2 = gateway_tool(
            {
                "action": "outbound",
                "platform": "discord",
                "channel_id": "gw-c2",
                "text": "hello",
                "dry_run": True,
                "idempotency_key": "bench-gw-idem-1",
            },
            ctx,
        )
        correctness_checks.append(
            CheckResult(
                name="gateway_tool_outbound_idempotency_dedupes",
                passed=(str(gw_d1.get("status") or "") == "ok" and bool(gw_d2.get("deduped"))),
            )
        )
        if gateway_summary.p95_ms > cfg.thresholds.gateway_tool_p95_ms_max:
            issues.append(
                {
                    "severity": "medium",
                    "kind": "perf",
                    "metric": "gateway_tool.p95_ms",
                    "value_ms": gateway_summary.p95_ms,
                    "threshold_ms": cfg.thresholds.gateway_tool_p95_ms_max,
                }
            )

        # -------------------- Microbench: agent step tool
        def _agent_step_call() -> Dict[str, Any]:
            return agent_step_tool(
                {
                    "action": "execute",
                    "tool": "web.search",
                    "args": {"query": "openai quickstart", "max_results": 2, "corpus": web_corpus},
                    "max_retries": 1,
                },
                ctx,
            )

        step_samples, step_outs = _time_many(cfg.iters, _agent_step_call)
        step_summary = _summarize_samples(step_samples)
        last_step = step_outs[-1] if step_outs else {}
        correctness_checks.append(
            CheckResult(
                name="agent_step_executes_tool",
                passed=(
                    isinstance(last_step, dict)
                    and str(last_step.get("tool") or "") == "web.search"
                    and int(last_step.get("attempt_count") or 0) >= 1
                ),
            )
        )
        fail_step = agent_step_tool({"action": "execute", "tool": "missing.tool", "args": {}, "max_retries": 1}, ctx)
        correctness_checks.append(
            CheckResult(
                name="agent_step_rejects_unknown_tool",
                passed=(isinstance(fail_step, dict) and str(fail_step.get("status") or "") == "error"),
            )
        )
        if step_summary.p95_ms > cfg.thresholds.agent_step_p95_ms_max:
            issues.append(
                {
                    "severity": "medium",
                    "kind": "perf",
                    "metric": "agent_step.p95_ms",
                    "value_ms": step_summary.p95_ms,
                    "threshold_ms": cfg.thresholds.agent_step_p95_ms_max,
                }
            )

        # -------------------- Microbench: image tool (auto fallback to local vision)
        img_path = bench_root / "data" / "bench" / "tiny.png"
        _mk_png_1x1(img_path)

        def _img_call() -> Dict[str, Any]:
            return image_tool(
                {
                    "path": str(img_path),
                    "ocr_mode": "auto",
                    "ocr_min_confidence": 0.5,
                    "vision_endpoint": "http://stub.local/vision",
                    "text_hint": "",
                },
                ctx,
            )

        t0 = time.perf_counter()
        _ = _img_call()  # warmup import/paths; treat as cold-start sample
        img_cold_ms = (time.perf_counter() - t0) * 1000.0
        img_samples, img_outs = _time_many(cfg.iters, _img_call)
        img_summary = _summarize_samples(img_samples)
        last_img = img_outs[-1] if img_outs else {}
        correctness_checks.append(
            CheckResult(
                name="image_tool_auto_fallback",
                passed=(str((last_img or {}).get("ocr_engine") or "") == "vision_api"),
                detail=str((last_img or {}).get("ocr_engine") or ""),
            )
        )
        if img_summary.p95_ms > cfg.thresholds.image_tool_p95_ms_max:
            issues.append(
                {
                    "severity": "medium",
                    "kind": "perf",
                    "metric": "image_tool.p95_ms",
                    "value_ms": img_summary.p95_ms,
                    "threshold_ms": cfg.thresholds.image_tool_p95_ms_max,
                }
            )

        # -------------------- Capability: image_tool tesseract OCR (optional)
        tess_summary = _summarize_samples([])
        tess_detail: Dict[str, Any] = {"available": False}
        try:
            from PIL import Image, ImageDraw  # type: ignore

            ocr_path = bench_root / "data" / "bench" / "ocr_text.png"
            ocr_path.parent.mkdir(parents=True, exist_ok=True)
            im = Image.new("RGB", (320, 96), (255, 255, 255))
            dr = ImageDraw.Draw(im)
            dr.text((12, 28), "Bench OCR 123", fill=(0, 0, 0))
            im.save(ocr_path)

            def _tess_call() -> Dict[str, Any]:
                return image_tool(
                    {
                        "path": str(ocr_path),
                        "ocr_mode": "tesseract",
                        "ocr_allow_fallback": False,
                        "ocr_min_confidence": 0.0,
                        "text_hint": "",
                    },
                    ctx,
                )

            tess_samples, tess_outs = _time_many(3, _tess_call)
            tess_summary = _summarize_samples(tess_samples)
            last_tess = tess_outs[-1] if tess_outs else {}
            eng = str((last_tess or {}).get("ocr_engine") or "")
            txt = str((last_tess or {}).get("ocr_text") or "")
            available = eng in {"tesseract", "tesseract_cli"}
            tess_detail = {"available": available, "ocr_engine": eng, "sample": txt[:200]}
            if available:
                low = txt.lower()
                acc_ok = ("bench" in low) and ("123" in low)
                correctness_checks.append(CheckResult(name="image_tool_tesseract_accuracy", passed=bool(acc_ok)))
                if not acc_ok:
                    issues.append(
                        {
                            "severity": "medium",
                            "kind": "quality",
                            "metric": "image_tool.tesseract.accuracy",
                            "detail": tess_detail,
                        }
                    )
            else:
                issues.append(
                    {
                        "severity": "medium",
                        "kind": "capability_missing",
                        "metric": "image_tool.tesseract",
                        "detail": tess_detail,
                    }
                )
        except Exception as e:
            tess_detail = {"available": False, "error": str(e)}
            issues.append(
                {
                    "severity": "medium",
                    "kind": "capability_missing",
                    "metric": "image_tool.tesseract",
                    "detail": tess_detail,
                }
            )

        # -------------------- Microbench: canvas tool
        def _canvas_one() -> Dict[str, Any]:
            c1 = canvas_tool({"action": "create", "type": "ActionCard", "props": {"title": "bench"}}, ctx)
            cid = str((c1.get("component") or {}).get("component_id") or "")
            if cid:
                canvas_tool({"action": "transition", "component_id": cid, "status": "running"}, ctx)
                canvas_tool({"action": "ack", "component_id": cid, "ack_type": "clicked"}, ctx)
                canvas_tool({"action": "check_ack_timeouts", "timeout_sec": 0}, ctx)
                bad = canvas_tool({"action": "transition", "component_id": cid, "status": "pending"}, ctx)
                ok_bad = str(bad.get("status") or "") == "error"
                return {"cid": cid, "invalid_edge_blocked": ok_bad}
            return {"cid": "", "invalid_edge_blocked": False}

        canvas_samples, canvas_outs = _time_many(cfg.iters, _canvas_one)
        canvas_summary = _summarize_samples(canvas_samples)
        correctness_checks.append(
            CheckResult(
                name="canvas_invalid_edge_blocked",
                passed=bool((canvas_outs[-1] or {}).get("invalid_edge_blocked")) if canvas_outs else False,
            )
        )
        if canvas_summary.p95_ms > cfg.thresholds.canvas_tool_p95_ms_max:
            issues.append(
                {
                    "severity": "medium",
                    "kind": "perf",
                    "metric": "canvas_tool.p95_ms",
                    "value_ms": canvas_summary.p95_ms,
                    "threshold_ms": cfg.thresholds.canvas_tool_p95_ms_max,
                }
            )

        # -------------------- Microbench: nodes_tool (leases + leader)
        nodes_tool({"action": "upsert", "node_id": "n1", "host": "127.0.0.1"}, ctx)
        nodes_tool({"action": "upsert", "node_id": "n2", "host": "127.0.0.2"}, ctx)

        def _nodes_one() -> Dict[str, Any]:
            # Acquire/renew a normal lease.
            nodes_tool({"action": "acquire_lease", "lease_key": "task::bench", "node_id": "n1", "lease_ttl_sec": 30}, ctx)
            nodes_tool({"action": "renew_lease", "lease_key": "task::bench", "node_id": "n1", "lease_ttl_sec": 30}, ctx)
            # Elect leader and fence an old epoch.
            e1 = nodes_tool({"action": "elect_leader", "group_key": "bench", "node_id": "n1", "priority": 1, "quorum": 2}, ctx)
            epoch = int(((e1.get("lease") or {}).get("epoch") or 0))
            e2 = nodes_tool({"action": "elect_leader", "group_key": "bench", "node_id": "n2", "priority": 9, "quorum": 2}, ctx)
            fenced = nodes_tool({"action": "elect_leader", "group_key": "bench", "node_id": "n1", "priority": 10, "quorum": 2, "expected_epoch": epoch}, ctx)
            return {"epoch1": epoch, "epoch2": int(((e2.get("lease") or {}).get("epoch") or 0)), "fenced": str(fenced.get("reason") or "")}

        nodes_samples, nodes_outs = _time_many(cfg.iters, _nodes_one)
        nodes_summary = _summarize_samples(nodes_samples)
        if nodes_outs:
            last_nodes = nodes_outs[-1]
            ok_epoch = int(last_nodes.get("epoch2") or 0) >= int(last_nodes.get("epoch1") or 0) + 1
            ok_fence = str(last_nodes.get("fenced") or "") == "fenced_out"
        else:
            ok_epoch = False
            ok_fence = False
        correctness_checks.append(CheckResult(name="leader_epoch_increments", passed=ok_epoch))
        correctness_checks.append(CheckResult(name="leader_fencing_blocks_old_epoch", passed=ok_fence))
        if nodes_summary.p95_ms > cfg.thresholds.nodes_tool_p95_ms_max:
            issues.append(
                {
                    "severity": "medium",
                    "kind": "perf",
                    "metric": "nodes_tool.p95_ms",
                    "value_ms": nodes_summary.p95_ms,
                    "threshold_ms": cfg.thresholds.nodes_tool_p95_ms_max,
                }
            )

        # -------------------- Microbench: cron_tool
        cron_tool(
            {
                "action": "schedule",
                "name": "bench_due",
                "task_input": "echo bench",
                "interval": "1s",
                "domain": "maintenance",
                "environment": "sandbox",
                "session_id": "bench",
                "priority": 1,
            },
            ctx,
        )
        # Make at least one run_due() deterministically enqueue without waiting for wall-clock time.
        try:
            cron_db = bench_root / "data" / "cron_tasks.json"
            raw = json.loads(cron_db.read_text(encoding="utf-8"))
            node = dict((raw or {}).get("bench_due") or {})
            now_ts = time.time()
            node["last_run"] = float(now_ts - 120)
            node["next_fire_ts"] = float(now_ts - 1)
            raw["bench_due"] = node
            cron_db.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        cron_samples, cron_outs = _time_many(cfg.iters, lambda: cron_tool({"action": "run_due", "max_tasks": 5}, ctx))
        cron_summary = _summarize_samples(cron_samples)
        correctness_checks.append(
            CheckResult(
                name="cron_run_due_enqueues",
                passed=any(int((o or {}).get("enqueued_count") or 0) >= 1 for o in (cron_outs or [])),
            )
        )
        if cron_summary.p95_ms > cfg.thresholds.cron_tool_p95_ms_max:
            issues.append(
                {
                    "severity": "medium",
                    "kind": "perf",
                    "metric": "cron_tool.p95_ms",
                    "value_ms": cron_summary.p95_ms,
                    "threshold_ms": cfg.thresholds.cron_tool_p95_ms_max,
                }
            )

        # -------------------- Microbench: session status
        status_samples, status_outs = _time_many(cfg.iters, lambda: session_status_tool({}, ctx))
        status_summary = _summarize_samples(status_samples)
        correctness_checks.append(
            CheckResult(
                name="session_status_has_canvas_fields",
                passed=bool(status_outs and "canvas_ack_pending_count" in (status_outs[-1] or {})),
            )
        )
        if status_summary.p95_ms > cfg.thresholds.session_status_p95_ms_max:
            issues.append(
                {
                    "severity": "medium",
                    "kind": "perf",
                    "metric": "session_status.p95_ms",
                    "value_ms": status_summary.p95_ms,
                    "threshold_ms": cfg.thresholds.session_status_p95_ms_max,
                }
            )

        # -------------------- Correctness: cron semantics + catch-up
        cron_semantics: Dict[str, Any] = {}
        try:
            from datetime import datetime as _dt, timedelta as _td, timezone as _tz

            base_now = _dt(2026, 2, 3, 12, 0, tzinfo=_tz.utc).timestamp()
            expr = "0 0 1 * 1"
            nf = _execution_parity._next_fire_from_cron(expr, now_ts=base_now, max_scan_minutes=60 * 24 * 40)
            dt_now = _dt.fromtimestamp(base_now, tz=_tz.utc)

            def _next_weekday_midnight(after: _dt, weekday: int) -> _dt:
                delta = (weekday - after.weekday()) % 7
                if delta == 0:
                    delta = 7
                target = (after + _td(days=delta)).date()
                return _dt(target.year, target.month, target.day, 0, 0, tzinfo=_tz.utc)

            def _next_first_of_month_midnight(after: _dt) -> _dt:
                y = after.year
                m = after.month + 1
                if m == 13:
                    y += 1
                    m = 1
                return _dt(y, m, 1, 0, 0, tzinfo=_tz.utc)

            next_mon = _next_weekday_midnight(dt_now, 0)  # Monday
            next_dom1 = _next_first_of_month_midnight(dt_now)
            expected = min(next_mon, next_dom1).timestamp()
            cron_semantics["dom_dow_or"] = {"expr": expr, "now_ts": base_now, "expected_ts": expected, "next_ts": nf}
            correctness_checks.append(
                CheckResult(
                    name="cron_dom_dow_or_semantics",
                    passed=(isinstance(nf, (int, float)) and abs(float(nf) - float(expected)) < 60.0),
                    detail=json.dumps(cron_semantics["dom_dow_or"], ensure_ascii=False),
                )
            )

            # Sunday=7 should behave like Sunday=0.
            sat_noon = _dt(2026, 2, 7, 12, 0, tzinfo=_tz.utc).timestamp()
            nf_sun7 = _execution_parity._next_fire_from_cron("0 0 * * 7", now_ts=sat_noon, max_scan_minutes=60 * 24 * 10)
            # Next day midnight.
            expected_sun = _dt(2026, 2, 8, 0, 0, tzinfo=_tz.utc).timestamp()
            cron_semantics["sun7"] = {"now_ts": sat_noon, "expected_ts": expected_sun, "next_ts": nf_sun7}
            correctness_checks.append(
                CheckResult(
                    name="cron_sunday_7_supported",
                    passed=(isinstance(nf_sun7, (int, float)) and abs(float(nf_sun7) - float(expected_sun)) < 60.0),
                    detail=json.dumps(cron_semantics["sun7"], ensure_ascii=False),
                )
            )

            # @hourly should produce minute==0 on the next hour boundary.
            now2 = _dt(2026, 2, 7, 12, 34, tzinfo=_tz.utc).timestamp()
            nf_hourly = _execution_parity._next_fire_from_cron("@hourly", now_ts=now2, max_scan_minutes=60 * 24 * 2)
            expected_hourly = _dt(2026, 2, 7, 13, 0, tzinfo=_tz.utc).timestamp()
            cron_semantics["hourly"] = {"now_ts": now2, "expected_ts": expected_hourly, "next_ts": nf_hourly}
            correctness_checks.append(
                CheckResult(
                    name="cron_special_hourly_supported",
                    passed=(isinstance(nf_hourly, (int, float)) and abs(float(nf_hourly) - float(expected_hourly)) < 60.0),
                    detail=json.dumps(cron_semantics["hourly"], ensure_ascii=False),
                )
            )
        except Exception as e:
            cron_semantics["error"] = str(e)
            correctness_checks.append(CheckResult(name="cron_semantics_checks", passed=False, detail=str(e)))

        cron_catch_up: Dict[str, Any] = {}
        try:
            cron_tool(
                {
                    "action": "schedule",
                    "name": "bench_catch_up",
                    "task_input": "echo catch_up",
                    "interval": "1s",
                    "domain": "maintenance",
                    "environment": "sandbox",
                    "session_id": "bench",
                    "priority": 1,
                    "misfire_policy": "catch_up",
                },
                ctx,
            )
            db = bench_root / "data" / "cron_tasks.json"
            raw = json.loads(db.read_text(encoding="utf-8"))
            node = dict((raw or {}).get("bench_catch_up") or {})
            now_ts = time.time()
            node["last_run"] = float(now_ts - 20)
            node["next_fire_ts"] = float(now_ts - 5)
            raw["bench_catch_up"] = node
            db.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
            out_cu = cron_tool({"action": "run_due", "max_tasks": 25, "max_catch_up": 50}, ctx)
            cu_n = int((out_cu or {}).get("enqueued_count") or 0)
            cron_catch_up = {"enqueued_count": cu_n}
            correctness_checks.append(
                CheckResult(
                    name="cron_catch_up_enqueues_multiple",
                    passed=(cu_n >= 2),
                    detail=json.dumps(cron_catch_up, ensure_ascii=False),
                )
            )
        except Exception as e:
            cron_catch_up = {"error": str(e)}
            correctness_checks.append(CheckResult(name="cron_catch_up_enqueues_multiple", passed=False, detail=str(e)))

        # -------------------- Correctness: cron run history
        try:
            out_runs = cron_tool({"action": "runs", "name": "bench_catch_up", "limit": 20}, ctx)
            rows = list((out_runs or {}).get("runs") or [])
            has = any(isinstance(r, dict) and str(r.get("name") or "") == "bench_catch_up" for r in rows)
            correctness_checks.append(CheckResult(name="cron_runs_history_records", passed=bool(has)))
        except Exception as e:
            correctness_checks.append(CheckResult(name="cron_runs_history_records", passed=False, detail=str(e)))

        # -------------------- Correctness: communication threading + dedupe (offline simulation)
        comm_summary: Dict[str, Any] = {}
        try:
            def _comm_thread_path(p: str) -> Path:
                return bench_root / "data" / "channels" / f"{p}_threads.json"

            def _load_thread(p: str, tid: str) -> List[Dict[str, Any]]:
                path = _comm_thread_path(p)
                if not path.exists():
                    return []
                data = json.loads(path.read_text(encoding="utf-8"))
                node = ((data or {}).get("threads") or {}).get(tid) or {}
                msgs = list(node.get("messages") or [])
                return msgs

            def _outbound_count(p: str) -> int:
                path = bench_root / "data" / "channels" / f"outbound_{p}.jsonl"
                if not path.exists():
                    return 0
                return len([ln for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()])

            def _run_comm_case(p: str, *, meta: Dict[str, Any], thread_id: str) -> Dict[str, Any]:
                channels_listener_tool({"action": "clear_dead_letters", "platform": p}, ctx)
                r1 = channels_listener_tool(
                    {
                        "action": "inject",
                        "platform": p,
                        "text": "hello",
                        "sender_id": "u1",
                        "message_id": "m1",
                        "metadata": meta,
                        "auto_reply": True,
                        "auto_reply_mode": "template",
                        "auto_reply_template": "ACK:{text}",
                        "auto_reply_send": False,
                    },
                    ctx,
                )
                rdup = channels_listener_tool(
                    {
                        "action": "inject",
                        "platform": p,
                        "text": "hello",
                        "sender_id": "u1",
                        "message_id": "m1",
                        "metadata": meta,
                        "auto_reply": True,
                        "auto_reply_mode": "template",
                        "auto_reply_template": "ACK:{text}",
                        "auto_reply_send": False,
                    },
                    ctx,
                )
                _ = channels_listener_tool(
                    {
                        "action": "inject",
                        "platform": p,
                        "text": "world",
                        "sender_id": "u2",
                        "message_id": "m2",
                        "metadata": meta,
                        "auto_reply": True,
                        "auto_reply_mode": "template",
                        "auto_reply_template": "ACK:{text}",
                        "auto_reply_send": False,
                    },
                    ctx,
                )
                _ = channels_listener_tool(
                    {
                        "action": "inject",
                        "platform": p,
                        "text": "hello EDIT",
                        "sender_id": "u1",
                        "message_id": "m1",
                        "event_kind": "edit",
                        "metadata": meta,
                        "auto_reply": False,
                    },
                    ctx,
                )
                _ = channels_listener_tool(
                    {
                        "action": "inject",
                        "platform": p,
                        "text": "",
                        "sender_id": "u2",
                        "message_id": "m2",
                        "event_kind": "delete",
                        "metadata": meta,
                        "auto_reply": False,
                    },
                    ctx,
                )
                msgs = _load_thread(p, thread_id)
                agent_msgs = [m for m in msgs if str(m.get("role") or "") == "agent"]
                out_n = _outbound_count(p)
                return {
                    "deduped": bool(rdup.get("deduped")),
                    "total_messages": len(msgs),
                    "agent_messages": len(agent_msgs),
                    "has_edit": any("hello EDIT" in str(m.get("text") or "") for m in msgs),
                    "has_delete": any(str(m.get("text") or "") == "[deleted]" for m in msgs),
                    "outbound_count": out_n,
                    "thread_id": thread_id,
                }

            comm_summary["discord"] = _run_comm_case("discord", meta={"channel_id": "c1"}, thread_id="discord:c1")
            comm_summary["slack"] = _run_comm_case("slack", meta={"channel_id": "c2"}, thread_id="slack:c2")
            comm_summary["telegram"] = _run_comm_case("telegram", meta={"chat_id": "chat1"}, thread_id="telegram:chat1")
            comm_summary["whatsapp"] = _run_comm_case("whatsapp", meta={"thread_id": "wa:thread1"}, thread_id="wa:thread1")

            for plat, node in comm_summary.items():
                correctness_checks.append(CheckResult(name=f"channels_dedupe_{plat}", passed=bool(node.get("deduped"))))
                correctness_checks.append(CheckResult(name=f"channels_edit_{plat}", passed=bool(node.get("has_edit"))))
                correctness_checks.append(CheckResult(name=f"channels_delete_{plat}", passed=bool(node.get("has_delete"))))
                correctness_checks.append(CheckResult(name=f"channels_auto_reply_{plat}", passed=(int(node.get("agent_messages") or 0) == 2)))
                correctness_checks.append(CheckResult(name=f"channels_outbound_{plat}", passed=(int(node.get("outbound_count") or 0) == 2)))

            # Dead-letter path: force a thread-store write failure.
            bad_platform = "benchsim"
            bad_path = bench_root / "data" / "channels" / f"{bad_platform}_threads.json"
            bad_path.parent.mkdir(parents=True, exist_ok=True)
            if bad_path.exists():
                try:
                    bad_path.unlink()
                except Exception:
                    pass
            bad_path.mkdir(exist_ok=True)
            _ = channels_listener_tool({"action": "clear_dead_letters", "platform": bad_platform}, ctx)
            _ = channels_listener_tool(
                {
                    "action": "inject",
                    "platform": bad_platform,
                    "text": "x",
                    "sender_id": "u",
                    "message_id": "m1",
                    "metadata": {"thread_id": "t1"},
                    "auto_reply": False,
                },
                ctx,
            )
            dl = channels_listener_tool({"action": "dead_letters", "platform": bad_platform, "limit": 5}, ctx)
            dl_count = int((dl or {}).get("count") or 0)
            comm_summary["dead_letter"] = {"platform": bad_platform, "count": dl_count}
            correctness_checks.append(CheckResult(name="channels_dead_letter_records_failure", passed=(dl_count >= 1)))
            redrive = channels_listener_tool({"action": "redrive_dead_letters", "platform": bad_platform, "limit": 10}, ctx)
            redrive_ok = int((redrive or {}).get("replayed") or 0) >= 1
            comm_summary["dead_letter_redrive"] = {
                "replayed": int((redrive or {}).get("replayed") or 0),
                "succeeded": int((redrive or {}).get("succeeded") or 0),
                "failed": int((redrive or {}).get("failed") or 0),
            }
            correctness_checks.append(CheckResult(name="channels_dead_letter_redrive_attempts", passed=redrive_ok))
            try:
                bad_path.rmdir()
            except Exception:
                pass
        except Exception as e:
            comm_summary["error"] = str(e)
            correctness_checks.append(CheckResult(name="channels_threading_bench", passed=False, detail=str(e)))

        # -------------------- Robustness: lease contention (concurrency)
        robust_checks: List[CheckResult] = []

        def _race_once() -> Dict[str, Any]:
            nodes_tool({"action": "release_lease", "lease_key": "task::race", "node_id": "n1"}, ctx)
            nodes_tool({"action": "release_lease", "lease_key": "task::race", "node_id": "n2"}, ctx)

            def _attempt(i: int) -> Dict[str, Any]:
                return nodes_tool({"action": "acquire_lease", "lease_key": "task::race", "node_id": f"r{i}", "lease_ttl_sec": 20}, ctx)

            with concurrent.futures.ThreadPoolExecutor(max_workers=int(cfg.concurrency)) as ex:
                outs = list(ex.map(_attempt, range(int(cfg.concurrency))))
            winners = sum(1 for o in outs if bool((o or {}).get("acquired")))
            return {"winners": winners}

        import concurrent.futures

        race_samples, race_outs = _time_many(max(3, cfg.iters // 5), _race_once)
        race_summary = _summarize_samples(race_samples)
        winners_ok = bool(race_outs) and all(int((r or {}).get("winners") or 0) <= cfg.thresholds.lease_contention_winners_max for r in race_outs)
        robust_checks.append(CheckResult(name="lease_contention_single_winner", passed=winners_ok))

        # -------------------- Robustness: PTY/Shell signal forwarding (SIGINT)
        # OpenClaw parity: agent can "press Ctrl+C" on a stuck long-running command.
        def _sigint_once() -> Dict[str, Any]:
            start = shell_run_command(
                {"command": "sleep 10", "yield_seconds": 0.05, "timeout_seconds": 30},
                ctx,
            )
            proc_id = str(start.get("proc_id") or "").strip()
            if not proc_id:
                return {"ok": False, "reason": "missing_proc_id", "start": start}
            if not bool(start.get("is_running")):
                return {"ok": False, "reason": "not_running", "start": start}

            t0 = time.perf_counter()
            shell_send_signal({"proc_id": proc_id, "signal": "SIGINT"}, ctx)
            exit_code = None
            stopped = False
            # Wait up to 2s for the process to exit.
            for _ in range(80):
                st = shell_poll_results({"proc_id": proc_id, "max_output_chars": 2000}, ctx)
                if not bool(st.get("is_running")):
                    exit_code = st.get("exit_code")
                    stopped = True
                    break
                time.sleep(0.025)
            dt_ms = (time.perf_counter() - t0) * 1000.0

            if not stopped:
                # Ensure cleanup to avoid leaving background processes behind in failed benches.
                try:
                    shell_send_signal({"proc_id": proc_id, "signal": "SIGTERM"}, ctx)
                except Exception:
                    pass
                try:
                    shell_send_signal({"proc_id": proc_id, "signal": "SIGKILL"}, ctx)
                except Exception:
                    pass
            return {"ok": bool(stopped), "interrupt_ms": float(dt_ms), "exit_code": exit_code}

        sig_samples, sig_outs = _time_many(3, _sigint_once)
        sig_summary = _summarize_samples(sig_samples)
        sig_ok = bool(sig_outs) and all(bool((o or {}).get("ok")) for o in sig_outs)
        sig_p95 = float(sig_summary.p95_ms or 0.0)
        sig_budget_ok = sig_p95 <= float(cfg.thresholds.shell_sigint_interrupt_p95_ms_max)
        robust_checks.append(CheckResult(name="shell_sigint_interrupts_background_proc", passed=bool(sig_ok and sig_budget_ok)))
        if sig_p95 > cfg.thresholds.shell_sigint_interrupt_p95_ms_max:
            issues.append(
                {
                    "severity": "medium",
                    "kind": "robustness_perf",
                    "metric": "shell_sigint_interrupt.p95_ms",
                    "value_ms": sig_p95,
                    "threshold_ms": cfg.thresholds.shell_sigint_interrupt_p95_ms_max,
                }
            )

        # -------------------- Robustness: graceful stop ladder (SIGINT -> SIGTERM -> SIGKILL)
        def _graceful_once() -> Dict[str, Any]:
            cmd = (
                "python -c 'import signal,time;"
                "signal.signal(signal.SIGINT, lambda *a, **k: None);"
                "time.sleep(10)'"
            )
            start = shell_run_command({"command": cmd, "yield_seconds": 0.05, "timeout_seconds": 30}, ctx)
            proc_id = str(start.get("proc_id") or "").strip()
            if not proc_id or not bool(start.get("is_running")):
                return {"ok": False, "reason": "not_running", "start": start}

            t0 = time.perf_counter()
            shell_send_signal(
                {
                    "proc_id": proc_id,
                    "action": "graceful_stop",
                    "signal_ladder": ["SIGINT", "SIGTERM", "SIGKILL"],
                    "signal_wait_ms": [50, 50],
                },
                ctx,
            )
            stopped = False
            exit_code = None
            for _ in range(120):
                st = shell_poll_results({"proc_id": proc_id, "max_output_chars": 2000}, ctx)
                if not bool(st.get("is_running")):
                    stopped = True
                    exit_code = st.get("exit_code")
                    break
                time.sleep(0.025)
            dt_ms = (time.perf_counter() - t0) * 1000.0
            return {"ok": bool(stopped), "interrupt_ms": float(dt_ms), "exit_code": exit_code}

        graceful_samples, graceful_outs = _time_many(3, _graceful_once)
        graceful_summary = _summarize_samples(graceful_samples)
        graceful_ok = bool(graceful_outs) and all(bool((o or {}).get("ok")) for o in graceful_outs)
        graceful_p95 = float(graceful_summary.p95_ms or 0.0)
        graceful_budget_ok = graceful_p95 <= float(cfg.thresholds.shell_graceful_stop_p95_ms_max)
        robust_checks.append(CheckResult(name="shell_graceful_stop_ladder", passed=bool(graceful_ok and graceful_budget_ok)))
        if graceful_p95 > cfg.thresholds.shell_graceful_stop_p95_ms_max:
            issues.append(
                {
                    "severity": "medium",
                    "kind": "robustness_perf",
                    "metric": "shell_graceful_stop.p95_ms",
                    "value_ms": graceful_p95,
                    "threshold_ms": cfg.thresholds.shell_graceful_stop_p95_ms_max,
                }
            )

        # -------------------- Observability: overview + anomaly remediation
        obs_checks: List[CheckResult] = []
        svc = ObservabilityService(runtime=None, repo_root=bench_root)

        async def _overview() -> Dict[str, Any]:
            return await svc.get_overview()

        ov_samples_ms: List[float] = []
        ov_outs: List[Dict[str, Any]] = []
        for _ in range(max(1, int(cfg.iters // 3))):
            t0 = time.perf_counter()
            ov = asyncio.run(_overview())
            ov_ms = (time.perf_counter() - t0) * 1000.0
            ov_samples_ms.append(float(ov_ms))
            ov_outs.append(ov)
        ov_summary = _summarize_samples(ov_samples_ms)
        if ov_summary.p95_ms > cfg.thresholds.observability_overview_p95_ms_max:
            issues.append(
                {
                    "severity": "medium",
                    "kind": "perf",
                    "metric": "observability_overview.p95_ms",
                    "value_ms": ov_summary.p95_ms,
                    "threshold_ms": cfg.thresholds.observability_overview_p95_ms_max,
                }
            )
        last_ov = ov_outs[-1] if ov_outs else {}
        obs_checks.append(CheckResult(name="observability_has_communication", passed=("communication" in last_ov)))

        # Stress: large dead letters + lease events + canvas.
        now = time.time()
        listener_state = bench_root / "data" / "channels" / "listener_state.json"
        listener_state.parent.mkdir(parents=True, exist_ok=True)
        dead_letters = [{"ts": now - (i % 60), "platform": "discord", "error": "bench"} for i in range(int(cfg.stress_dead_letters))]
        listener_state.write_text(json.dumps({"seen": {}, "dead_letters": dead_letters}, ensure_ascii=False, indent=2), encoding="utf-8")
        lease_events = bench_root / "data" / "metrics" / "lease_events.jsonl"
        lease_events.parent.mkdir(parents=True, exist_ok=True)
        lease_events.write_text(
            "".join(
                json.dumps({"ts": now - (i % 60), "kind": "leader_blocked_higher_priority"}, ensure_ascii=False) + "\n"
                for i in range(int(cfg.stress_lease_events))
            ),
            encoding="utf-8",
        )
        leases_file = bench_root / "data" / "nodes_leases.json"
        leases_file.parent.mkdir(parents=True, exist_ok=True)
        leases_file.write_text(
            json.dumps(
                {
                    "leases": {
                        "lease_expired": {"lease_key": "lease_expired", "node_id": "n1", "expires_at": now - 10, "epoch": 0},
                        "leader::bench": {"lease_key": "leader::bench", "group_key": "bench", "node_id": "n2", "expires_at": now + 10, "epoch": 7},
                    }
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        comps_path = bench_root / "data" / "canvas_components.json"
        comps = {}
        for i in range(int(cfg.stress_canvas_components)):
            cid = f"bench_c{i}"
            comps[cid] = {"component_id": cid, "status": "running", "updated_at": 1}
        comps_path.parent.mkdir(parents=True, exist_ok=True)
        comps_path.write_text(json.dumps({"components": comps}, ensure_ascii=False, indent=2), encoding="utf-8")

        t0 = time.perf_counter()
        stress_ov = asyncio.run(_overview())
        stress_ms = (time.perf_counter() - t0) * 1000.0
        if stress_ms > cfg.thresholds.observability_overview_stress_ms_max:
            issues.append(
                {
                    "severity": "high",
                    "kind": "perf_stress",
                    "metric": "observability_overview.stress_ms",
                    "value_ms": float(stress_ms),
                    "threshold_ms": cfg.thresholds.observability_overview_stress_ms_max,
                }
            )
        obs_checks.append(
            CheckResult(
                name="observability_dead_letter_trend_present",
                passed=bool((((stress_ov.get("communication") or {}).get("dead_letters") or {}).get("trend") or {})),
            )
        )
        obs_checks.append(
            CheckResult(
                name="observability_leases_present",
                passed=("leases" in ((stress_ov.get("communication") or {}))),
            )
        )

        # Anomaly generator should enqueue remediation tasks for drift/trend.
        queue = TaskQueue(repo_root=str(bench_root))
        gen = AnomalyTaskGenerator(obs_service=svc, task_queue=queue)
        task_ids = asyncio.run(gen.check_and_generate())
        items = queue.load_all(limit=2000)
        kinds = [str((it.metadata or {}).get("anomaly_kind") or "") for it in items]
        obs_checks.append(CheckResult(name="anomaly_generator_enqueues_tasks", passed=bool(task_ids)))
        robust_checks.append(CheckResult(name="anomaly_tasks_include_lease", passed=("lease_renew_drift" in kinds)))
        robust_checks.append(CheckResult(name="anomaly_tasks_include_dead_letter_trend", passed=("dead_letter_growth_trend" in kinds)))

        # Dashboard surface check (no heavy memory scanning).
        class _EmptyStore:
            def search(self, query):  # noqa: ANN001
                _ = query
                return []

        class _EmptyFabric:
            def __init__(self) -> None:
                self.store = _EmptyStore()

        dash = ObservabilityDashboard(memory_fabric=_EmptyFabric(), repo_root=bench_root)
        dm_samples, dm_outs = _time_many(cfg.iters // 3 or 1, dash.collect_metrics)
        obs_checks.append(CheckResult(name="dashboard_has_comm_fields", passed=("listener_count" in asdict(dm_outs[-1])) if dm_outs else False))

        # -------------------- Assemble report
        correctness_pass = sum(1 for c in correctness_checks if c.passed)
        robustness_pass = sum(1 for c in robust_checks if c.passed)
        observability_pass = sum(1 for c in obs_checks if c.passed)

        for c in correctness_checks:
            if not c.passed:
                issues.append({"severity": "high", "kind": "check", "category": "correctness", "name": c.name, "detail": c.detail})
        for c in robust_checks:
            if not c.passed:
                issues.append({"severity": "high", "kind": "check", "category": "robustness", "name": c.name, "detail": c.detail})
        for c in obs_checks:
            if not c.passed:
                issues.append({"severity": "high", "kind": "check", "category": "observability", "name": c.name, "detail": c.detail})

        report_dict: Dict[str, Any] = {
            "generated_at": _now_utc_iso(),
            "repo_root": str(repo_root.resolve()),
            "bench_root": str(bench_root),
            "config": {
                "iters": int(cfg.iters),
                "concurrency": int(cfg.concurrency),
                "stress_dead_letters": int(cfg.stress_dead_letters),
                "stress_lease_events": int(cfg.stress_lease_events),
                "stress_canvas_components": int(cfg.stress_canvas_components),
                "seed": int(cfg.seed),
                "thresholds": asdict(cfg.thresholds),
                "min_overall_score": float(min_overall_score),
            },
            "metrics": {
                "web_readability": asdict(web_summary),
                "web_fetch": asdict(fetch_summary),
                "web_search": asdict(search_summary),
                "message_tool": asdict(message_summary),
                "gateway_tool": asdict(gateway_summary),
                "agent_step": asdict(step_summary),
                "image_tool": asdict(img_summary),
                "image_tool_cold_start": {"cold_ms": float(img_cold_ms)},
                "image_tool_tesseract": asdict(tess_summary),
                "image_tool_tesseract_detail": dict(tess_detail),
                "canvas_tool": asdict(canvas_summary),
                "nodes_tool": asdict(nodes_summary),
                "cron_tool": asdict(cron_summary),
                "cron_semantics": dict(cron_semantics),
                "cron_catch_up": dict(cron_catch_up),
                "session_status": asdict(status_summary),
                "communication_threading": dict(comm_summary),
                "observability_overview": asdict(ov_summary),
                "observability_overview_stress": {"stress_ms": float(stress_ms), "config": {"dead_letters": int(cfg.stress_dead_letters), "lease_events": int(cfg.stress_lease_events), "canvas_components": int(cfg.stress_canvas_components)}},
                "lease_contention": asdict(race_summary),
                "shell_sigint_interrupt": asdict(sig_summary),
                "shell_graceful_stop": asdict(graceful_summary),
            },
            "checks": {
                "correctness": {
                    "passed": correctness_pass,
                    "total": len(correctness_checks),
                    "results": [asdict(c) for c in correctness_checks],
                },
                "robustness": {
                    "passed": robustness_pass,
                    "total": len(robust_checks),
                    "results": [asdict(c) for c in robust_checks],
                },
                "observability": {
                    "passed": observability_pass,
                    "total": len(obs_checks),
                    "results": [asdict(c) for c in obs_checks],
                },
            },
        }

        scores = compute_execution_score(report_dict, cfg.thresholds)
        report_dict["scores"] = scores

        # Gate: overall score + no failed correctness checks.
        pass_gate = bool(scores.get("overall", 0.0) >= float(min_overall_score)) and correctness_pass == len(correctness_checks)
        report_dict["pass"] = pass_gate
        report_dict["issues"] = issues

        # Compare previous overall score if present.
        prev_score = None
        try:
            prev_score = float((previous_report.get("scores") or {}).get("overall")) if previous_report else None
        except Exception:
            prev_score = None
        report_dict["previous_overall_score"] = prev_score
        report_dict["improved_vs_previous"] = True if prev_score is None else (float(scores.get("overall") or 0.0) >= prev_score)

        _write_json(output, report_dict)
        if history is not None:
            _append_jsonl(history, report_dict)
        return report_dict
    finally:
        try:
            vision.close()
        except Exception:
            pass
        if td_obj is not None:
            try:
                td_obj.cleanup()
            except Exception:
                pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Execution-layer benchmark (tools + robustness + observability).")
    ap.add_argument("--repo-root", default=".", help="Repository root")
    ap.add_argument(
        "--output",
        default="generated/benchmarks/execution_layer_benchmark_report.json",
        help="Output report path",
    )
    ap.add_argument(
        "--history",
        default="generated/benchmarks/execution_layer_benchmark_history.jsonl",
        help="Optional history jsonl path",
    )
    ap.add_argument(
        "--previous",
        default="generated/benchmarks/execution_layer_benchmark_prev.json",
        help="Optional previous report path",
    )
    ap.add_argument("--iters", type=int, default=30, help="Iterations per microbench")
    ap.add_argument("--concurrency", type=int, default=8, help="Concurrency for contention bench")
    ap.add_argument("--stress-dead-letters", type=int, default=5000)
    ap.add_argument("--stress-lease-events", type=int, default=5000)
    ap.add_argument("--stress-canvas", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--min-score", type=float, default=0.80)
    ap.add_argument("--keep-workdir", action="store_true", help="Keep bench workdir under generated/benchmarks/")
    args = ap.parse_args()

    cfg = BenchmarkConfig(
        iters=int(args.iters),
        concurrency=int(args.concurrency),
        stress_dead_letters=int(args.stress_dead_letters),
        stress_lease_events=int(args.stress_lease_events),
        stress_canvas_components=int(args.stress_canvas),
        seed=int(args.seed),
    )

    repo_root = Path(args.repo_root).resolve()
    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = (repo_root / out_path).resolve()
    hist = Path(args.history) if str(args.history).strip() else None
    if hist is not None and not hist.is_absolute():
        hist = (repo_root / hist).resolve()
    prev = Path(args.previous) if str(args.previous).strip() else None
    if prev is not None and not prev.is_absolute():
        prev = (repo_root / prev).resolve()

    report = run_benchmark(
        repo_root=repo_root,
        output=out_path,
        history=hist,
        previous=prev,
        config=cfg,
        keep_workdir=bool(args.keep_workdir),
        min_overall_score=float(args.min_score),
    )
    print(
        json.dumps(
            {
                "pass": bool(report.get("pass")),
                "overall_score": float((report.get("scores") or {}).get("overall") or 0.0),
                "performance": float((report.get("scores") or {}).get("performance") or 0.0),
                "correctness": float((report.get("scores") or {}).get("correctness") or 0.0),
                "robustness": float((report.get("scores") or {}).get("robustness") or 0.0),
                "observability": float((report.get("scores") or {}).get("observability") or 0.0),
                "issues": int(len(list(report.get("issues") or []))),
                "output": str(out_path),
            },
            ensure_ascii=False,
        )
    )
    return 0 if bool(report.get("pass")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
