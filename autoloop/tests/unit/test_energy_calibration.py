from app.control.calibration import EnergyCalibrator


def test_energy_calibrator_persists_state(tmp_path):
    path = tmp_path / "control" / "energy_calibration.json"
    calibrator = EnergyCalibrator(state_path=path, alpha=0.5)
    low_before = calibrator.overlap_penalty("low")
    calibrator.update(weighted_score=0.2, succeeded=False)

    calibrator_reloaded = EnergyCalibrator(state_path=path, alpha=0.5)
    low_after = calibrator_reloaded.overlap_penalty("low")
    assert path.exists()
    assert low_before != low_after
