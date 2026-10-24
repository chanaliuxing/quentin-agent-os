# meta_agent/research/headless_browser.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Literal
import subprocess
import json
import os

from quentin.traces.core import JsonlTraceRecorder

trace = JsonlTraceRecorder(repo_root=".")


Provider = Literal["chatgpt", "gemini", "web_research"] # Added 'web_research'


@dataclass
class HeadlessConfig:
    provider: Provider
    script_path: str
    env: Dict[str, str] = field(default_factory=dict)
    timeout_sec: int = 600


class HeadlessBrowserClient:
    def __init__(self, configs: List[HeadlessConfig]) -> None:
        self._by_provider: Dict[Provider, HeadlessConfig] = {c.provider: c for c in configs}

    def run(self, provider: Provider, query: str, max_tokens: int = 2000) -> str:
        if provider not in self._by_provider:
            raise ValueError(f"No headless config for provider={provider}")

        cfg = self._by_provider[provider]
        env = os.environ.copy()
        env.update(cfg.env)

        # Handle max_tokens for web_research differently if script doesn't take it
        cmd = ["python", cfg.script_path, "--query", query]
        if provider != "web_research": # Only pass max_tokens for chat-like providers
            cmd.extend(["--max-tokens", str(max_tokens)])


        trace.record_event(event_type="headless_research_start", trace_id=str(provider), payload={"provider": provider, "script": cfg.script_path})

        try:
            proc = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=cfg.timeout_sec, env=env
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            trace.record_event(event_type="headless_research_error", trace_id=str(provider), payload={"provider": provider, "error": repr(e)})
            raise RuntimeError(f"Headless script failed: {e}")


        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="ignore")[:1000]
            trace.record_event(event_type="headless_research_error", trace_id=str(provider), payload={"provider": provider, "error": err})
            raise RuntimeError(f"Headless script failed with code {proc.returncode}: {err}")

        out = proc.stdout.decode("utf-8", errors="ignore")
        trace.record_event(event_type="headless_research_done", trace_id=str(provider), payload={"provider": provider, "output_preview": out[:400]})
        return out


def default_headless_client() -> HeadlessBrowserClient:
    """
    You can modify the script paths here according to your actual implementation.
    """
    configs = [
        HeadlessConfig(
            provider="chatgpt",
            script_path="scripts/headless_chatgpt_research.py",
            env={"CHATGPT_STORAGE_STATE": os.getenv("CHATGPT_STORAGE_STATE", "")},
        ),
        HeadlessConfig(
            provider="gemini",
            script_path="scripts/headless_gemini_research.py",
            env={"GEMINI_STORAGE_STATE": os.getenv("GEMINI_STORAGE_STATE", "")},
        ),
        HeadlessConfig( # Added new web_research config
            provider="web_research",
            script_path="scripts/headless_web_research.py",
            timeout_sec=180 # Web research might take longer
        ),
    ]
    return HeadlessBrowserClient(configs)
