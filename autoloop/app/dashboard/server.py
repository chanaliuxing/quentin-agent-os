import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from collections import Counter

from app.config import settings
from app.evidence import EvidenceStore
from app.review import latest_human_review, list_human_reviews


def build_dashboard_snapshot(project_root: Path | None = None) -> dict[str, Any]:
    root = (project_root or settings.project_root).resolve()
    phases_dir = root / settings.autoloop_phases_dir
    runtime_dir = root / settings.autoloop_data_dir
    phase_reports = sorted(phases_dir.glob("phase_*/phase_report.md"))
    hooks = sorted((runtime_dir / "hooks").glob("*.json"))
    evidence_store = EvidenceStore(runtime_dir / "evidence")
    latest_evidence_path, latest_evidence = evidence_store.latest_record()
    recent_evidence = evidence_store.recent_records(limit=3)
    taxonomy_records = evidence_store.recent_records(limit=200)
    evidence_files = sorted((runtime_dir / "evidence").rglob("*.json"))
    human_reviews = list_human_reviews(runtime_dir / "hooks")
    latest_review = latest_human_review(runtime_dir / "hooks")
    failure_type_counter = Counter(
        record.failure_type for _, record in taxonomy_records if str(record.failure_type).strip()
    )
    stage_counter = Counter(
        record.first_failure_stage for _, record in taxonomy_records if str(record.first_failure_stage).strip()
    )
    owner_counter = Counter(
        record.owner_agent for _, record in taxonomy_records if str(record.owner_agent).strip()
    )
    return {
        "project_root": str(root),
        "phases_dir": str(phases_dir),
        "runtime_dir": str(runtime_dir),
        "phase_reports": [str(path) for path in phase_reports],
        "hooks": [str(path) for path in hooks],
        "evidence_files": [str(path) for path in evidence_files],
        "latest_evidence_file": str(latest_evidence_path) if latest_evidence_path else None,
        "latest_evidence": latest_evidence.model_dump(mode="json") if latest_evidence else None,
        "latest_failure_stage": (latest_evidence.first_failure_stage if latest_evidence else ""),
        "latest_failure_signature": (latest_evidence.failure_signature if latest_evidence else ""),
        "latest_failure_owner": (latest_evidence.owner_agent if latest_evidence else ""),
        "latest_trace_id": (latest_evidence.trace_id if latest_evidence else ""),
        "recent_failure_signatures": [
            {
                "file": str(path),
                "failure_signature": record.failure_signature,
                "owner_agent": record.owner_agent,
                "trace_id": record.trace_id,
                "created_at": record.created_at.isoformat(),
            }
            for path, record in recent_evidence
        ],
        "failure_taxonomy": {
            "sample_size": len(taxonomy_records),
            "failure_type_distribution": dict(failure_type_counter),
            "failure_stage_distribution": dict(stage_counter),
            "owner_distribution": dict(owner_counter),
            "top_failure_types": failure_type_counter.most_common(5),
        },
        "human_review_hooks": human_reviews,
        "latest_human_review": latest_review,
        "phase_count": len(phase_reports),
        "hook_count": len(hooks),
        "evidence_count": len(evidence_files),
        "human_review_count": len(human_reviews),
    }


class DashboardHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json({"status": "ok"})
            return
        if self.path == "/snapshot":
            self._send_json(build_dashboard_snapshot())
            return
        self._send_json({"error": "not_found"}, status=404)


def run_dashboard_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    server.serve_forever()
