import pytest
from quentin.security.redteam.scenario_library import ScenarioLibrary
from quentin.security.blueteam.response_orchestrator import BlueTeamResponseOrchestrator

def test_red_blue_pipeline():
    lib = ScenarioLibrary()
    blue = BlueTeamResponseOrchestrator()
    
    # Run a mock exercise
    for s in lib.get_all():
        suppressed = True if "rm" in s.payload else False
        blue.capture_outcome(s.id, suppressed, 10.0)
        
    summary = blue.get_summary()
    assert summary["total_exercises"] == len(lib.get_all())
    assert summary["suppression_rate"] > 0
