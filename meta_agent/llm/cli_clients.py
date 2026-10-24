# meta_agent/llm/cli_clients.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import os
import subprocess
import json
import textwrap
import shutil


class CLIModelError(Exception):
    pass


@dataclass
class CLIModelConfig:
    bin_name: str
    args: List[str]
    env: Dict[str, str]


class CLIModelClient:
    def __init__(self, config: CLIModelConfig) -> None:
        self.config = config

    def generate(self, system: str, user: str, **kwargs: Any) -> str:
        prompt = self._build_prompt(system, user, kwargs)
        cmd = [self.config.bin_name] + self.config.args

        proc = subprocess.run(
            cmd,
            input=prompt.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, **self.config.env},
            check=False,
        )
        if proc.returncode != 0:
            raise CLIModelError(
                f"CLI model failed: code={proc.returncode}, stderr={proc.stderr.decode('utf-8', errors='ignore')}"
            )
        out = proc.stdout.decode("utf-8", errors="ignore").strip()
        return out

    def _build_prompt(self, system: str, user: str, extra: Dict[str, Any]) -> str:
        buf = []
        if system:
            buf.append("system:\n" + textwrap.dedent(system).strip())
        if user:
            buf.append("\nuser:\n" + textwrap.dedent(user).strip())
        if extra:
            buf.append("\nextra:\n" + json.dumps(extra, ensure_ascii=False, indent=2))
        return "\n\n".join(buf)


class StubCLIModelClient(CLIModelClient):
    """Deterministic stub for non-interactive or unavailable CLI environments."""

    def __init__(self, label: str = "stub") -> None:
        self.label = label

    def generate(self, system: str, user: str, **kwargs: Any) -> str:
        payload = {
            "stub": True,
            "label": self.label,
            "system": system.strip() if system else "",
            "user": user.strip() if user else "",
        }
        return json.dumps(payload, ensure_ascii=False)


def make_codex_cli_client() -> CLIModelClient:
    bin_name = os.getenv("CODEX_CLI_BIN", "codex")
    args_raw = os.getenv("CODEX_CLI_ARGS", "[]")
    env_raw = os.getenv("CODEX_CLI_ENV", "{}")
    try:
        args = json.loads(args_raw)
    except Exception:
        args = []
    try:
        env = json.loads(env_raw)
    except Exception:
        env = {}
    if not shutil.which(bin_name):
        return StubCLIModelClient(label="codex_cli_stub")
    return CLIModelClient(
        CLIModelConfig(
            bin_name=bin_name,
            args=args,
            env=env,
        )
    )


def make_gemini_cli_client() -> CLIModelClient:
    bin_name = os.getenv("GEMINI_CLI_BIN", "gemini")
    args_raw = os.getenv("GEMINI_CLI_ARGS", "[]")
    env_raw = os.getenv("GEMINI_CLI_ENV", "{}")
    try:
        args = json.loads(args_raw)
    except Exception:
        args = []
    try:
        env = json.loads(env_raw)
    except Exception:
        env = {}
    if not shutil.which(bin_name):
        return StubCLIModelClient(label="gemini_cli_stub")
    return CLIModelClient(
        CLIModelConfig(
            bin_name=bin_name,
            args=args,
            env=env,
        )
    )


def make_claude_cli_client() -> CLIModelClient:
    bin_name = os.getenv("CLAUDE_CLI_BIN", "claude")
    args_raw = os.getenv("CLAUDE_CLI_ARGS", "[]")
    env_raw = os.getenv("CLAUDE_CLI_ENV", "{}")
    try:
        args = json.loads(args_raw)
    except Exception:
        args = []
    try:
        env = json.loads(env_raw)
    except Exception:
        env = {}
    if not shutil.which(bin_name):
        return StubCLIModelClient(label="claude_cli_stub")
    return CLIModelClient(
        CLIModelConfig(
            bin_name=bin_name,
            args=args,
            env=env,
        )
    )
