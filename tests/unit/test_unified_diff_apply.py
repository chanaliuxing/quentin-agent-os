from quentin.infra.unified_diff import (
    PatchApplyError,
    apply_unified_diff_to_text,
    select_file_patches_for_targets,
    apply_file_patch,
)


def test_apply_unified_diff_to_text_basic_edit() -> None:
    original = "a\nb\nc\n"
    diff = (
        "--- a/test.txt\n"
        "+++ b/test.txt\n"
        "@@ -1,3 +1,4 @@\n"
        " a\n"
        "-b\n"
        "+B\n"
        " c\n"
        "+d\n"
    )
    out = apply_unified_diff_to_text(original, diff)
    assert out == "a\nB\nc\nd\n"


def test_apply_unified_diff_headerless_single_hunk() -> None:
    original = "hello\n"
    diff = "@@ -1,1 +1,1 @@\n-hello\n+world\n"
    out = apply_unified_diff_to_text(original, diff)
    assert out == "world\n"


def test_select_file_patches_for_targets_requires_match() -> None:
    diff = (
        "--- a/x.txt\n"
        "+++ b/x.txt\n"
        "@@ -1,1 +1,1 @@\n"
        "-a\n"
        "+b\n"
    )
    pairs = select_file_patches_for_targets(diff, targets=["x.txt"])
    assert len(pairs) == 1
    path, fp = pairs[0]
    assert path == "x.txt"
    assert apply_file_patch("a\n", fp) == "b\n"


def test_apply_unified_diff_raises_on_mismatch() -> None:
    original = "a\n"
    diff = "@@ -1,1 +1,1 @@\n-x\n+y\n"
    try:
        apply_unified_diff_to_text(original, diff)
        assert False, "expected PatchApplyError"
    except PatchApplyError:
        pass

