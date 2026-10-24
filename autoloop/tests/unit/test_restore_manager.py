from app.rollback.checkpoints import CheckpointRef
from app.rollback.restore import RestoreManager


def test_restore_manager_saves_and_restores_artifacts(tmp_path):
    manager = RestoreManager(base_dir=tmp_path / "checkpoints")
    checkpoint = CheckpointRef(
        checkpoint_id="checkpoint_phase_01_1",
        run_id="run_01",
        phase_id="phase_01",
        snapshot={"artifacts": {"a": 1}},
    )
    manager.save_artifact_snapshot(checkpoint=checkpoint, artifacts={"a": 2, "b": 3})
    restored = manager.restore_artifacts(checkpoint=checkpoint)

    assert restored == {"a": 2, "b": 3}
