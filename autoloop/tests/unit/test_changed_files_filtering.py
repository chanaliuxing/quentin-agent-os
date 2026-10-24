from app.temporal.workflow import _collect_changed_files_from_results


def test_collect_changed_files_filters_phase_result_artifacts():
    results = {
        "module_main": {
            "dev": """
            {
              "contract_version": "1.0",
              "generated_at": "2026-03-09T00:00:00",
              "module_name": "module_main",
              "status": "success",
              "files_changed": [
                "app/module_main/pipeline.py",
                "tests/unit/test_module_main_pipeline.py",
                "phases/phase_01/results/module_main_dev.md",
                "runtime/evidence/run/phase_01/execution_summary.json"
              ],
              "implementation_notes": "ok"
            }
            """,
        }
    }

    assert _collect_changed_files_from_results(results) == [
        "app/module_main/pipeline.py",
        "tests/unit/test_module_main_pipeline.py",
    ]
