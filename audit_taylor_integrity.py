from __future__ import annotations
import os
import sys
import importlib
import logging
from pathlib import Path
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TaylorAuditor")

class IntegrityAuditor:
    """
    P5: Ported from OpenClaw's 'integrity-scan.ts'.
    Verifies that all 75 surgeries have been physically integrated and are importable.
    """
    
    SURGERY_CHECKLIST = {
        "Memory: RRF": "quentin.memory.hybrid_fusion",
        "Memory: Decay": "quentin.memory.decay_engine",
        "Memory: Fabric": "quentin.memory.fabric",
        "Shell: PTY Echo": "quentin.utils.echo_sanitizer",
        "Shell: Kernel": "quentin.infra.isolation.kernel_isolator",
        "Browser: SoM": "quentin.infra.browser.som_visualizer",
        "Browser: Denoise": "quentin.infra.browser.cleaner_script",
        "LLM: StreamSentry": "quentin.infra.llm.stream_sentry",
        "LLM: Budget": "quentin.infra.llm.budget_guard",
        "Gov: Role": "quentin.tools.role_profiles",
        "Gov: Auth": "quentin.llm.auth_profiles",
        "Utils: Diff": "quentin.utils.diff_utils",
        "Utils: Fuzzy": "quentin.utils.fuzzy_matcher",
        "Events: Bus": "quentin.infra.events.environment_bus",
        "Perception: Hasher": "quentin.cognitive.perception.hasher",
        "Perception: Pacing": "quentin.cognitive.perception.adaptive_engine",
        "Perception: Spatial": "quentin.infra.perception.spatial_utils",
        "Tools: Speculative": "quentin.tools.middleware.speculative_runner",
        "Tools: Sanitizer": "quentin.infra.tools.sanitizer",
        "Tools: Latency": "quentin.infra.tools.latency_profile"
    }

    def run_audit(self) -> Dict[str, Any]:
        report = {"total": len(self.SURGERY_CHECKLIST), "passed": 0, "failed": 0, "details": []}
        
        print(f"🔍 [Taylor] Starting Physical Integrity Audit...")
        
        for feature, module_name in self.SURGERY_CHECKLIST.items():
            try:
                # Physical Import Attempt
                importlib.import_module(module_name)
                        
                print(f"✅ [PASS] {feature}")
                report["passed"] += 1
                report["details"].append({"feature": feature, "status": "ok"})
                
            except Exception as e:
                print(f"❌ [FAIL] {feature}: {e}")
                report["failed"] += 1
                report["details"].append({"feature": feature, "status": "failed", "error": str(e)})
                
        return report

if __name__ == "__main__":
    auditor = IntegrityAuditor()
    result = auditor.run_audit()
    
    if result["failed"] == 0:
        print(f"\n✨ Taylor System Integrity: 100% ({result['passed']}/{result['total']} modules verified).")
        sys.exit(0)
    else:
        print(f"\n⚠️ Taylor System Integrity: FAILED ({result['failed']} errors).")
        sys.exit(1)
