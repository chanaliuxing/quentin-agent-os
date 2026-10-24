import time
import json
from quentin.security.redteam.scenario_library import ScenarioLibrary
from quentin.security.blueteam.response_orchestrator import BlueTeamResponseOrchestrator

def main():
    library = ScenarioLibrary()
    orchestrator = BlueTeamResponseOrchestrator()
    
    print("Starting Red vs Blue exercise...")
    for scenario in library.get_all():
        print(f"Running scenario {scenario.id}: {scenario.name}")
        
        start = time.perf_counter()
        # Simulation: System suppresses high risk payloads
        suppressed = True if "rm" in scenario.payload or "governance" in scenario.payload else False
        latency = (time.perf_counter() - start) * 1000
        
        orchestrator.capture_outcome(scenario.id, suppressed, latency)
        
    summary = orchestrator.get_summary()
    print(f"Exercise Complete. Suppression Rate: {summary['suppression_rate']:.2%}")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
