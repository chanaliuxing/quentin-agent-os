import pytest


def test_mkdir_rejects_file_like_paths():
    from quentin.infra.tools.sanitizer import sanitizer

    with pytest.raises(ValueError) as e:
        sanitizer.sanitize("mkdir", {"path": "extensions/tools/gemini_cli/manifest.yaml"})
    assert "looks like a file" in str(e.value)


def test_mkdir_allows_directory_paths():
    from quentin.infra.tools.sanitizer import sanitizer

    out = sanitizer.sanitize("mkdir", {"path": "extensions/tools/gemini_cli"})
    assert out["path"] == "extensions/tools/gemini_cli"
