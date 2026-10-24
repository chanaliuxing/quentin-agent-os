from pathlib import Path


def test_image_tool_cli_fallback_when_pytesseract_missing(tmp_path: Path, monkeypatch) -> None:
    # Create a tiny valid image; content doesn't matter because OCR is mocked.
    from PIL import Image

    img_path = tmp_path / "x.png"
    Image.new("RGB", (40, 20), color=(255, 255, 255)).save(img_path)

    import shutil
    import subprocess

    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/tesseract")

    class _Res:
        def __init__(self) -> None:
            self.stdout = "HELLO\n"
            self.stderr = ""
            self.returncode = 0

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _Res())

    # Force the pytesseract import to fail so we deterministically exercise the CLI fallback.
    import builtins

    real_import = builtins.__import__

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "pytesseract":
            raise ImportError("forced for test")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import)

    from quentin.tools.execution_parity import image_tool

    out = image_tool({"path": str(img_path), "ocr_mode": "tesseract"})
    assert out["status"] == "ok"
    assert out["ocr_engine"] == "tesseract_cli"
    assert "HELLO" in (out.get("ocr_text") or "")
