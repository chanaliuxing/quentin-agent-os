# meta_agent/llm/ollama_client.py

from __future__ import annotations
from typing import Optional, Dict, Any
import json
import http.client
import os

from meta_agent.llm.client import LLMClient, LLMRequest


class OllamaClient(LLMClient):
    def __init__(self, host: str = "localhost", port: int = 11434) -> None:
        self.host = host
        self.port = port

    def generate(self, req: LLMRequest) -> str:
        if os.getenv("LLM_STUB", "0").strip().lower() in ("1", "true", "yes", "on"):
            # Return a stub response that satisfies common JSON schema expectations
            return json.dumps({
                "should_apply": True,
                "risk_level": "low",
                "reason": "llm_stub: automatically approved for offline testing",
                "best_guess_file_path": "quentin/mutable/stub.py",
                "status": "ok",
                "result": "llm_stub"
            })

        timeout_sec = float(os.environ.get("META_AGENT_OLLAMA_TIMEOUT_SEC", "30") or 30)
        conn = http.client.HTTPConnection(self.host, self.port, timeout=timeout_sec)
        body = {
            "model": req.model,
            "prompt": req.prompt,
            "stream": False,
            "options": {
                "temperature": req.temperature,
                "num_predict": req.max_tokens,
            },
        }
        conn.request(
            "POST",
            "/api/generate",
            body=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        if resp.status != 200:
            raise RuntimeError(f"Ollama error {resp.status}: {resp.read().decode()}")
        raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        return data.get("response", "")
