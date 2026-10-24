from __future__ import annotations

import importlib


def test_bedrock_client_imports_without_syntax_error() -> None:
    # Regression guard: bedrock_client previously had unterminated f-strings that
    # broke CLI imports at module import time.
    importlib.import_module("quentin.infra.llm.bedrock_client")


def test_qctl_imports_without_syntax_error() -> None:
    # Ensure the CLI entrypoint can import (it transitively imports infra.llm).
    importlib.import_module("quentin.cli.qctl")

