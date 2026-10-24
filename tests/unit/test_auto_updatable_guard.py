from pathlib import Path

from meta_agent.patches.models import PatchProposal
from meta_agent.patches.safe_applier import SafePatchApplier


def test_safe_patch_applier_blocks_non_auto_updatable(tmp_path: Path) -> None:
    # Minimal repo layout
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "auto_updatable.json").write_text('{"require_marker": true, "paths": []}\n', encoding="utf-8")
    (tmp_path / "quentin" / "mutable").mkdir(parents=True, exist_ok=True)

    # Create a mutable file WITHOUT marker
    target = tmp_path / "quentin" / "mutable" / "no_marker.py"
    target.write_text("print('hi')\n", encoding="utf-8")

    patch = PatchProposal(
        id="patch-1",
        target_files=["quentin/mutable/no_marker.py"],
        diff="",
        intent="test",
        metadata={},
    )

    applier = SafePatchApplier(repo_root=tmp_path)
    res = applier.apply_patch(patch)
    assert res.allow_apply is False
    assert any("auto_updatable" in r or "marker" in r for r in (res.reasons or []))

