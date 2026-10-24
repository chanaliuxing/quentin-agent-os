import unittest
from unittest.mock import MagicMock
from quentin.blueprint.gap_tracker import BlueprintGapTracker, CapabilityStatus
from quentin.blueprint.spec import BlueprintSpec, BlueprintCapability

class TestBlueprintGapTracker(unittest.TestCase):
    def test_scan_gaps(self):
        # 1. Setup mock spec
        spec = BlueprintSpec(
            version="test-v1",
            codename="Test Spec",
            capabilities=[
                BlueprintCapability(id="cap.1", section="sec1", name="Cap 1", description="Desc 1", required=True),
                BlueprintCapability(id="cap.2", section="sec1", name="Cap 2", description="Desc 2", required=True),
                BlueprintCapability(id="cap.3", section="sec2", name="Cap 3", description="Desc 3", required=False), # Not required
                BlueprintCapability(id="cap.4", section="sec2", name="Cap 4", description="Desc 4", required=True),
            ]
        )

        # 2. Setup mock registry
        registry = MagicMock()
        registry.get.side_effect = lambda cap_id: {
            "cap.1": CapabilityStatus(capability_id="cap.1", status="done"),
            "cap.2": CapabilityStatus(capability_id="cap.2", status="missing"),
            "cap.3": CapabilityStatus(capability_id="cap.3", status="missing"), # Not required, so should be partial/unknown depending on logic
            "cap.4": CapabilityStatus(capability_id="cap.4", status="partial"),
        }.get(cap_id)

        # 3. Init tracker
        tracker = BlueprintGapTracker(spec=spec, registry=registry)

        # 4. Scan
        report = tracker.scan()

        # 5. Assertions
        # Cap 1: done -> ok
        self.assertEqual(len(report.ok), 1)
        self.assertEqual(report.ok[0].capability.id, "cap.1")

        # Cap 2: missing & required -> missing
        # Cap 3: missing & not required -> partial (based on current logic in gap_tracker.py: "else: partial.append(gap)")
        # Cap 4: partial -> partial
        
        missing_ids = [g.capability.id for g in report.missing]
        self.assertIn("cap.2", missing_ids)
        self.assertNotIn("cap.3", missing_ids) 

        partial_ids = [g.capability.id for g in report.partial]
        self.assertIn("cap.4", partial_ids)
        self.assertIn("cap.3", partial_ids)

if __name__ == "__main__":
    unittest.main()
