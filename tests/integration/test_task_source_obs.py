# tests/integration/test_task_source_obs.py

import pytest
import os
import json
from unittest.mock import AsyncMock, patch
from quentin.runtime.task_queue import TaskQueue
from quentin.runtime.task_sources import run_task_sources_once

@pytest.mark.asyncio
async def test_run_task_sources_obs_integration(tmp_path):
    repo_root = tmp_path
    (repo_root / "data").mkdir()
    (repo_root / "data" / "tasks").mkdir()
    
    # Mock overview with anomalies
    mock_overview = {
        "timestamp": "2026-02-08T12:00:00Z",
        "domain": {
            "task": {"by_domain_env": [{"domain": "core", "environment": "sandbox", "tasks": 10, "success_rate": 0.5}]},
            "actions": {"by_domain_env_action": []}
        },
        "memory": {
            "events": {"recall": {"avg_latency_ms": 5000.0}},
            "embedding_failure_rate": 0.0
        },
        "patches": {"by_status": {}},
        "tools": {"by_tool": []},
        "release": {},
        "experiments": {}
    }
    
    with patch("quentin.observability.service.ObservabilityService.get_overview", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_overview
        
        # Disable other sources to focus on obs
        os.environ["QUENTIN_TASK_SOURCE_BLUEPRINT"] = "0"
        os.environ["QUENTIN_TASK_SOURCE_PATCHFLOW"] = "0"
        os.environ["QUENTIN_TASK_SOURCE_OBS"] = "1"
        
        report = await run_task_sources_once(repo_root=str(repo_root))
        
        assert report.enqueued >= 2 # task_failure_spike and memory_latency_spike
        
        queue = TaskQueue(repo_root=str(repo_root))
        items = queue.load_all()
        
        kinds = [it.metadata.get("kind") for it in items]
        assert "anomaly_remediation" in kinds
        
        # Check details
        anomaly_tasks = [it for it in items if it.metadata.get("kind") == "anomaly_remediation"]
        anomaly_kinds = [it.metadata.get("anomaly_kind") for it in anomaly_tasks]
        assert "task_failure_spike" in anomaly_kinds
        assert "memory_latency_spike" in anomaly_kinds
