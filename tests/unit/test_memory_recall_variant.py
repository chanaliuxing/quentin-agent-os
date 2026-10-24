from quentin.memory.models import MemoryQuery
from quentin.memory.recall_variants import MemoryRecallVariant


def test_variant_applies_query_fields() -> None:
    base = MemoryQuery(text="x", top_k=5)
    variant = MemoryRecallVariant(mode="hybrid", alpha=0.7, k_text=3, k_vec=4, min_text_score=0.1, min_vec_score=0.2)
    q = variant.apply(base)
    assert q.mode == "hybrid"
    assert q.alpha == 0.7
    assert q.k_text == 3
    assert q.k_vec == 4
    assert q.min_text_score == 0.1
    assert q.min_vec_score == 0.2
