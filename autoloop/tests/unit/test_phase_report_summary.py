from pathlib import Path

import pytest

from app.config import settings
from app.temporal.activities import write_phase_report_activity


@pytest.mark.asyncio
async def test_write_phase_report_summary_reflects_failed_tests(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()

    report_path = await write_phase_report_activity(
        project_id="p1",
        phase_id="phase_01",
        results={"module_main": {"dev": "ok", "qa": "ok"}},
        overlap_report={"overlaps_count": 0},
        test_results={"status": "failed", "tests_run": 1, "tests_passed": 0, "tests_failed": 1},
    )

    report_text = Path(report_path).read_text(encoding="utf-8")
    assert "failed acceptance gate" in report_text
    assert "completed successfully" not in report_text
    assert "Acceptance: rejected" in report_text
    assert "Execution: tests_failed" in report_text


@pytest.mark.asyncio
async def test_write_phase_report_summary_fails_when_results_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()

    report_path = await write_phase_report_activity(
        project_id="p1",
        phase_id="phase_01",
        results={"module_main": {"dev": "No result file found", "qa": "ok"}},
        overlap_report={"overlaps_count": 0},
        test_results={"status": "success", "tests_run": 1, "tests_passed": 1, "tests_failed": 0},
    )

    report_text = Path(report_path).read_text(encoding="utf-8")
    assert "missing_results=True" in report_text
    assert "Acceptance: rejected" in report_text
    assert "Orchestration: completed" in report_text
    assert "completed successfully" not in report_text


@pytest.mark.asyncio
async def test_write_phase_report_summary_honors_explicit_acceptance_status(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()

    report_path = await write_phase_report_activity(
        project_id="p1",
        phase_id="phase_01",
        results={"module_main": {"planner": "ok", "reviewer": "ok", "dev": "ok", "qa": "ok"}},
        overlap_report={"overlaps_count": 0},
        test_results={
            "status": "success",
            "tests_run": 1,
            "tests_passed": 1,
            "tests_failed": 0,
            "acceptance_status": "rejected",
            "orchestration_status": "completed",
            "execution_status": "tests_passed",
        },
    )

    report_text = Path(report_path).read_text(encoding="utf-8")
    assert "Acceptance: rejected" in report_text
    assert "completed successfully" not in report_text


@pytest.mark.asyncio
async def test_write_phase_report_includes_required_test_failure_details(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()

    report_path = await write_phase_report_activity(
        project_id="p1",
        phase_id="phase_01",
        results={"module_main": {"planner": "ok", "reviewer": "ok", "dev": "ok", "qa": "ok"}},
        overlap_report={"overlaps_count": 0},
        test_results={
            "status": "failed",
            "tests_run": 4,
            "tests_passed": 3,
            "tests_failed": 1,
            "acceptance_status": "rejected",
            "failed_required_tests": ["unit"],
            "required_test_failure_details": {
                "unit": ["AttributeError: module 'app.main' has no attribute 'MockTemporalWorker'"]
            },
        },
    )
    report_text = Path(report_path).read_text(encoding="utf-8")
    assert "## Required Test Diagnostics" in report_text
    assert "Failed required tests: unit" in report_text
    assert "MockTemporalWorker" in report_text
