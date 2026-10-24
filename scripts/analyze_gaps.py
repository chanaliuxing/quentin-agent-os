import sys
from pathlib import Path
import asyncio

# Add repo root to sys.path
repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root))

from quentin.blueprint.spec import BlueprintSpecLoader, load_default_spec_v3
from quentin.blueprint.gap_tracker import CapabilitiesRegistry, BlueprintGapTracker
from quentin.blueprint.capability_scanner import CapabilityScanner

async def analyze_blueprint_gaps():
    print("--- Starting Blueprint Gap Analysis ---")

    # 1. Load the Blueprint Specification
    # Using the default spec defined in code, which is what BlueprintSpecLoader would eventually provide
    # Or we can load from a file if BlueprintSpecLoader supports it.
    # The container uses BlueprintSpecLoader(path="blueprints/meta_agent_v3.yaml")
    # For this demo, let's use load_default_spec_v3 for simplicity, or mock the loader.
    # From the BlueprintGapTracker.__init__ in gap_tracker.py, it takes a 'spec' object directly.
    # So we can just load the default.
    spec = load_default_spec_v3()
    print(f"Loaded Blueprint Spec version: {spec.version}, codename: {spec.codename}")
    print(f"Total capabilities in spec: {len(spec.capabilities)}")

    # 2. Initialize CapabilitiesRegistry
    # This registry will store and load the current status from data/blueprint/capabilities.json
    registry = CapabilitiesRegistry(repo_root=repo_root)
    print(f"Initialized CapabilitiesRegistry. Current entries: {len(registry._items)}")

    # 3. Run CapabilityScanner to update the registry
    # This simulates how the system discovers its current capabilities
    scanner = CapabilityScanner(spec=spec, registry=registry, repo_root=repo_root)
    print("Running CapabilityScanner to update registry based on codebase...")
    scan_report = scanner.scan_and_update_registry()
    print(f"CapabilityScanner completed. Found {len(scan_report.probe_results)} probe results.")
    print(f"Registry entries after scan: {len(registry._items)}") # Should be updated

    # 4. Initialize and Run BlueprintGapTracker
    tracker = BlueprintGapTracker(spec=spec, registry=registry, repo_root=repo_root)
    print("Running BlueprintGapTracker to identify gaps...")
    gap_report = tracker.scan()

    print("\n--- Blueprint Gap Report ---")
    print(f"Spec Version: {gap_report.spec_version}")
    print(f"Summary: {gap_report.to_dict()['stats']}")

    if gap_report.missing:
        print("\nMissing Capabilities:")
        for gap in gap_report.missing:
            print(f"- [{gap.capability.id}] {gap.capability.name}: {gap.capability.description} (Status: {gap.status.status})")
            if gap.status.evidence:
                print(f"  Evidence: {gap.status.evidence}")

    if gap_report.partial:
        print("\nPartial Capabilities:")
        for gap in gap_report.partial:
            print(f"- [{gap.capability.id}] {gap.capability.name}: {gap.capability.description} (Status: {gap.status.status})")
            if gap.status.evidence:
                print(f"  Evidence: {gap.status.evidence}")

    if gap_report.unknown:
        print("\nUnknown Capabilities:")
        for gap in gap_report.unknown:
            print(f"- [{gap.capability.id}] {gap.capability.name}: {gap.capability.description} (Status: {gap.status.status})")
            if gap.status.evidence:
                print(f"  Evidence: {gap.status.evidence}")

    if gap_report.ok:
        print(f"\nOK Capabilities: {len(gap_report.ok)} found.")
        # Optionally print details for OK capabilities
        # for gap in gap_report.ok:
        #     print(f"- [{gap.capability.id}] {gap.capability.name}: (Status: {gap.status.status})")

    print("\n--- Analysis Complete ---")

if __name__ == "__main__":
    asyncio.run(analyze_blueprint_gaps())
