import json
from pathlib import Path

from app.config import settings
from app.temporal.workflow import _write_human_review_hook


def test_write_human_review_hook_creates_expected_payload(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_data_dir", "runtime")
    settings.ensure_dirs()

    hook_path = _write_human_review_hook(
        project_id="p1",
        phase_id="phase_01",
        prd_path=str(tmp_path / "blueprint.md"),
        acceptance_status="rejected",
        failed_modules=["module_main"],
        evidence_file=str(tmp_path / "runtime" / "evidence" / "run" / "phase" / "evidence.json"),
        replan_rounds=3,
    )
    payload = json.loads(Path(hook_path).read_text(encoding="utf-8"))

    assert Path(hook_path).exists()
    assert payload["status"] == "human_review_required"
    assert payload["phase_id"] == "phase_01"
    assert payload["prd_path"].endswith("blueprint.md")
    assert payload["acceptance_status"] == "rejected"
    assert payload["failed_modules"] == ["module_main"]
