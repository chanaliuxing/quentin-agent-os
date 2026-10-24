import json

from app.temporal.activities import _evaluate_dev_path_guard
from app.utils import ensure_phase_dirs, get_contract_file


def test_evaluate_dev_path_guard_rejects_invalid_claims(monkeypatch, tmp_path):
    from app.config import settings

    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()
    ensure_phase_dirs("phase_01")

    change_spec_file = get_contract_file("phase_01", "module_main", "change_spec")
    change_spec_file.write_text(
        json.dumps({"allowed_paths": ["app/**/*.py"]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    result = _evaluate_dev_path_guard(
        phase_id="phase_01",
        module_name="module_main",
        contract_payload={"files_changed": ["README.md"]},
        repo_root=tmp_path,
    )
    assert result["ok"] is False
    assert "README.md" in result["invalid_paths"]


def test_evaluate_dev_path_guard_accepts_valid_claims(monkeypatch, tmp_path):
    from app.config import settings

    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()
    ensure_phase_dirs("phase_01")

    change_spec_file = get_contract_file("phase_01", "module_main", "change_spec")
    change_spec_file.write_text(
        json.dumps({"allowed_paths": ["app/**/*.py"]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    result = _evaluate_dev_path_guard(
        phase_id="phase_01",
        module_name="module_main",
        contract_payload={"files_changed": ["app/services/main.py"]},
        repo_root=tmp_path,
    )
    assert result["ok"] is True


def test_evaluate_dev_path_guard_ignores_result_artifacts(monkeypatch, tmp_path):
    from app.config import settings

    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "autoloop_phases_dir", "phases")
    settings.ensure_dirs()
    ensure_phase_dirs("phase_01")

    change_spec_file = get_contract_file("phase_01", "module_main", "change_spec")
    change_spec_file.write_text(
        json.dumps({"allowed_paths": ["app/**/*.py", "tests/**"]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    result = _evaluate_dev_path_guard(
        phase_id="phase_01",
        module_name="module_main",
        contract_payload={
            "files_changed": [
                "app/services/main.py",
                "phases/phase_01/results/module_main_dev.md",
            ]
        },
        repo_root=tmp_path,
    )
    assert result["ok"] is True
    assert result["invalid_paths"] == []
    assert result["ignored_paths"] == ["phases/phase_01/results/module_main_dev.md"]
