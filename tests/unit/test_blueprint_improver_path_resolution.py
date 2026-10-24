from quentin.blueprint.improver import resolve_existing_file_path


def test_resolve_existing_file_path_never_guesses_nonexistent() -> None:
    # Non-existent evidence paths should never be returned.
    p = resolve_existing_file_path(
        repo_root=".",
        evidence="maybe in quentin/does/not/exist.py and /abs/path.py",
        section=None,
    )
    assert p is None


def test_resolve_existing_file_path_section_fallback_is_existing() -> None:
    # Section-based fallback returns a real file if present.
    p = resolve_existing_file_path(
        repo_root=".",
        evidence=None,
        section="memory",
    )
    assert p in {"quentin/memory/fabric.py", "quentin/memory/sleep_loop.py"}

