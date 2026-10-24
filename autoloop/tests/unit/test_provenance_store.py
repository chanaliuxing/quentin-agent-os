from app.models import ProvenanceRelation
from app.provenance import ProvenanceStore


def test_provenance_store_records_event_and_edge(tmp_path):
    store = ProvenanceStore(base_dir=tmp_path / "provenance")
    event = store.record_event(
        run_id="run_01",
        phase_id="phase_01",
        artifact_id="artifact_c",
        event_type="validated",
        payload={"ok": True},
    )
    edge = store.record_edge(
        run_id="run_01",
        src_artifact_id="artifact_a",
        dst_artifact_id="artifact_c",
        relation=ProvenanceRelation.DERIVED_FROM,
    )
    upstream = store.find_upstream_artifacts(run_id="run_01", artifact_id="artifact_c")

    assert event.artifact_id == "artifact_c"
    assert edge.src_artifact_id == "artifact_a"
    assert upstream == ["artifact_a"]
