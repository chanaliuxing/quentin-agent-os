from pathlib import Path
from meta_agent.patches.models import PatchProposal
from quentin.infra.unified_diff import PatchApplyError, apply_file_patch, select_file_patches_for_targets

class PatchApplier:
    """
    Applies patches to the codebase.
    """
    def __init__(self, repo_root: str = "."):
        self.repo_root = Path(repo_root)

    def apply_patch(self, patch: PatchProposal) -> bool:
        """
        Applies the patch.
        """
        print(f"Applying patch {patch.id} to {patch.target_files}")
        
        new_content = patch.metadata.get("new_content")
        if new_content is not None:
            # Direct overwrite strategy
            for target_file in patch.target_files:
                abs_path = (self.repo_root / target_file).resolve()
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                abs_path.write_text(new_content, encoding="utf-8")
                print(f"Wrote new content to {abs_path}")
            return True

        diff_text = patch.get_unified_diff() or ""
        if not diff_text.strip():
            print("Warning: Empty diff and no new_content; skipping application.")
            return False

        try:
            pairs = select_file_patches_for_targets(diff_text, patch.target_files or [])
        except PatchApplyError as e:
            print(f"Warning: Diff application failed to select patches: {e}")
            return False

        for target_path, file_patch in pairs:
            abs_path = (self.repo_root / target_path).resolve()
            old_text = abs_path.read_text(encoding="utf-8") if abs_path.exists() else ""

            # Handle deletion patches
            if file_patch.new_path is None and file_patch.old_path is not None:
                if abs_path.exists():
                    abs_path.unlink()
                    print(f"Deleted file {abs_path}")
                continue

            try:
                new_text = apply_file_patch(old_text, file_patch)
            except PatchApplyError as e:
                print(f"Warning: Failed to apply unified diff for {target_path}: {e}")
                return False

            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(new_text, encoding="utf-8")
            print(f"Applied unified diff to {abs_path}")

        return True
