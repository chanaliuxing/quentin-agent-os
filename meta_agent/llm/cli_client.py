# meta_agent/llm/cli_client.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Literal
import subprocess
import textwrap
import json
import shlex
import os


LLMProvider = Literal["codex", "gemini"]


@dataclass
class CliModelConfig:
    provider: LLMProvider
    cmd: List[str]
    model: Optional[str] = None
    extra_args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    timeout_sec: int = 120


class CliLLMClient:
    def __init__(self, config: CliModelConfig) -> None:
        self.config = config

    def _run_cli(self, args: List[str], input_text: str) -> str:
        cmd = self.config.cmd + args
        env = os.environ.copy()
        env.update(self.config.env)

        try:
            proc = subprocess.run(
                cmd, input=input_text.encode("utf-8"),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=self.config.timeout_sec,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            raise RuntimeError(f"CLI LLM error for {' '.join(cmd)}: {e}")

        if proc.returncode != 0:
            err_preview = proc.stderr.decode("utf-8", errors="ignore")[:1000]
            raise RuntimeError(f"CLI LLM failed with code {proc.returncode}: {err_preview}")

        return proc.stdout.decode("utf-8", errors="ignore")

    def generate(self, system: str, user: str) -> str:
        prompt = textwrap.dedent(f"""
            [SYSTEM]
            {system}

            [USER]
            {user}
            """).strip()

        args: List[str] = []
        if self.config.model:
            args += ["--model", self.config.model]
        args += self.config.extra_args

        return self._run_cli(args, input_text=prompt)

    def generate_json(self, system: str, user: str) -> Dict:
        raw = self.generate(system, user)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            try:
                start = raw.index("{")
                end = raw.rindex("}") + 1
                return json.loads(raw[start:end])
            except (ValueError, json.JSONDecodeError) as e:
                raise RuntimeError(f"CLI JSON parse failed, raw preview: {raw[:800]}") from e


def make_codex_client(model: str = "gpt-4.1-mini") -> CliLLMClient:
    cfg = CliModelConfig(
        provider="codex",
        cmd=["codex", "chat"],
        model=model,
        extra_args=["--format", "text"],
    )
    return CliLLMClient(cfg)


def make_gemini_client(model: str = "gemini-2.0-flash") -> CliLLMClient:
    cfg = CliModelConfig(
        provider="gemini",
        cmd=["gemini", "pro"],
        model=model,
        extra_args=["--format", "text"],
    )
    return CliLLMClient(cfg)
