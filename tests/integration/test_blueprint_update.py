import unittest
import tempfile
import shutil
import os
from pathlib import Path
import json

from quentin.blueprint.spec import BlueprintSpec, BlueprintCapability
from quentin.blueprint.gap_tracker import CapabilitiesRegistry
from quentin.blueprint.capability_scanner import CapabilityScanner

class TestBlueprintUpdate(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for the repo
        self.test_dir = tempfile.mkdtemp()
        self.repo_root = Path(self.test_dir)
        
        # Setup data directory
        (self.repo_root / "data" / "blueprint").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_scan_and_update(self):
        # 1. Setup a spec with a capability we want to test
        # We use 'arch.layers.four-layer-logic' which checks for 
        # 'quentin.runtime.system' and 'quentin.l3.research.layer'
        cap = BlueprintCapability(
            id="arch.layers.four-layer-logic",
            section="architecture",
            name="Four Layer Logic",
            description="Test Capability",
            required=True
        )
        spec = BlueprintSpec(
            version="test",
            codename="Test",
            capabilities=[cap]
        )

        # 2. Create dummy modules to satisfy the static probe
        # quentin/runtime/system.py
        runtime_dir = self.repo_root / "quentin" / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        (runtime_dir / "system.py").touch()
        (runtime_dir / "__init__.py").touch()

        # quentin/l3/research/layer.py
        research_dir = self.repo_root / "quentin" / "l3" / "research"
        research_dir.mkdir(parents=True, exist_ok=True)
        # Ensure package structure exists for import probes.
        (self.repo_root / "quentin" / "l3" / "__init__.py").touch()
        (research_dir / "layer.py").touch()
        (research_dir / "__init__.py").touch()
        
        # quentin/__init__.py
        (self.repo_root / "quentin" / "__init__.py").touch()

        # 3. Initialize Registry and Scanner
        # We need to ensure python path includes our temp repo so importlib works
        import sys
        sys.path.insert(0, str(self.repo_root))
        
        # Force reload of quentin modules from our temp dir; save originals to restore later
        saved_modules = {k: v for k, v in sys.modules.items() if k.startswith("quentin")}
        for key in list(sys.modules.keys()):
            if key.startswith("quentin"):
                del sys.modules[key]
        
        try:
            registry = CapabilitiesRegistry(repo_root=self.repo_root)
            # Ensure initial state is unknown (file doesn't exist or empty)
            self.assertIsNone(registry.get("arch.layers.four-layer-logic"))

            scanner = CapabilityScanner(
                repo_root=self.repo_root,
                spec=spec,
                registry=registry
            )

            # 4. Run Scan
            report = scanner.scan_and_update_registry()

            # 5. Verify Registry Update
            status = registry.get("arch.layers.four-layer-logic")
            self.assertIsNotNone(status)
            # The static probe checks for importability. Since we created empty files,
            # and added to sys.path, it should import successfully (or at least find modules).
            # Note: _run_static_import_probes uses importlib.import_module.
            # Empty files are valid modules.
            
            # Depending on logic, it might be "done" or "partial".
            # The probe says: if mod_runtime and mod_research: status="done"
            self.assertEqual(status.status, "done")
            self.assertIn("Found quentin.runtime.system", status.evidence)

            # 6. Verify Persistence
            json_path = self.repo_root / "data" / "blueprint" / "capabilities.json"
            self.assertTrue(json_path.exists())
            
            with open(json_path, 'r') as f:
                data = json.load(f)
                saved_caps = data.get("capabilities", [])
                self.assertEqual(len(saved_caps), 1)
                self.assertEqual(saved_caps[0]["capability_id"], "arch.layers.four-layer-logic")
                self.assertEqual(saved_caps[0]["status"], "done")

        finally:
            sys.path.pop(0)
            # Purge temp quentin modules and restore originals to avoid polluting other tests
            for key in list(sys.modules.keys()):
                if key.startswith("quentin"):
                    del sys.modules[key]
            sys.modules.update(saved_modules)

if __name__ == "__main__":
    unittest.main()
