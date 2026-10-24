from typing import List, Tuple
from .templates import Evidence


class CapabilityScorer:
    """
    Additive scorer with thresholds and strong-evidence gate.
    Rules (P0):
    - Strong evidence: method_found / function_found (+0.5)
    - Weak: file_exists (+0.1), class_found (+0.1), generic_defs (+0.05), legacy_implemented (+0.2)
    - Penalty: placeholder_detected (-0.3), parse_error (-0.2)
    - No strong evidence => at most partial
    - file_missing with module_hint => default gap (low confidence)
    """

    STRONG_KEYS = {"method_found", "function_found", "test_pass", "runtime_signal_seen"}

    def evaluate(self, evidences: List[Evidence]) -> Tuple[str, float]:
        total_score = 0.0
        strong_hit = False
        file_missing = False

        for e in evidences:
            if e.source != "meta":
                total_score += e.score
            if e.key in self.STRONG_KEYS:
                strong_hit = True
            if e.key == "file_missing":
                file_missing = True

        confidence = max(0.0, min(1.0, total_score))

        if file_missing:
            return "gap", min(confidence, 0.2)

        if confidence >= 0.85 and strong_hit:
            status = "implemented"
        elif confidence >= 0.45:
            status = "partial"
        elif confidence >= 0.15:
            status = "unknown"
        else:
            status = "gap"

        # Gate: implemented requires strong evidence (method/function/test/runtime)
        if status == "implemented" and not strong_hit:
            status = "partial"
        return status, confidence
