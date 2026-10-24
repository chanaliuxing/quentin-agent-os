from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import json
import logging
import re

try:
    import requests
except ImportError:
    # P0: Provide a clear diagnostic error for missing core dependencies
    raise ImportError(
        "Missing dependency: 'requests' is not installed in the current environment. "
        "Please run 'pip install requests' to resolve this. "
        "This library is required for OllamaLLMClient to communicate with the local LLM server."
    ) from None

logger = logging.getLogger(__name__)

@dataclass
class OllamaModelConfig:
    name: str              # Model name from env or config
    base_url: str = "http://localhost:11434"
    temperature: float = 0.3
    top_p: float = 0.9
    num_ctx: int = 8192
    num_predict: int = 1024

@dataclass
class ChatMessage:
    role: str   # \"system\" | \"user\" | \"assistant\"
    content: str

class OllamaLLMClient:
    def __init__(self, config: Optional[OllamaModelConfig] = None) -> None:
        self.config = config or OllamaModelConfig(name=os.getenv("LLM_MODEL", "qwen3-vl:latest"))
        base = (self.config.base_url or "").rstrip("/")
        for suffix in ("/api/generate", "/api/chat", "/api/embeddings"):
            if base.endswith(suffix):
                base = base[: -len(suffix)].rstrip("/")
        self.config.base_url = base or "http://localhost:11434"
        self._generate_url = f"{self.config.base_url}/api/generate"
        self._chat_url = f"{self.config.base_url}/api/chat"

    def complete(self, prompt: str, *, model: Optional[str] = None, timeout: Optional[float] = None, **extra_params: Any) -> str:
        payload: Dict[str, Any] = {
            "model": model or self.config.name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "top_p": self.config.top_p,
                "num_ctx": self.config.num_ctx,
                "num_predict": self.config.num_predict,
            },
        }
        if extra_params:
            payload.update(extra_params)

        self._maybe_guard_llm_call(model=(model or self.config.name), prompt=prompt)

        try:
            current_timeout = timeout if timeout is not None else 600.0
            resp = requests.post(self._generate_url, json=payload, timeout=current_timeout)
            resp.raise_for_status()
        except Exception as e:
            logger.exception("OllamaLLMClient.complete error: %s", e)
            raise

        data = resp.json()
        text = data.get("response", "") or ""
        if not text:
            msg = data.get("message") or {}
            if isinstance(msg, dict):
                text = msg.get("content", "") or ""
        if not text and data.get("thinking"):
            text = data.get("thinking", "")
        return text

    def generate(self, *, model: str, prompt: str, **extra_params: Any) -> str:
        return self.complete(prompt, model=model, **extra_params)

    def _maybe_guard_llm_call(self, *, model: str, prompt: str) -> None:
        # P0: Aggressive billing/policy bypass for local development
        if os.getenv("QUENTIN_BILLING_BYPASS", "0").strip().lower() in {"1", "true", "yes", "on"}:
            return

        kernel = getattr(self, "safety_kernel", None)
        if kernel is None:
            return
        try:
            from quentin.kernel.policy import ActionRequest
            from quentin.llm.context_budget import estimate_tokens
            action = ActionRequest.new(
                actor=getattr(self, "actor", "ollama_client"),
                action_type="llm_call",
                domain=getattr(self, "domain", "core"),
                environment=getattr(self, "environment", "sandbox"),
                risk_level=getattr(self, "risk_level", "medium"),
                estimated_cost_tokens=int(estimate_tokens(prompt)),
                estimated_cost_usd=0.0,
                description=f"llm_call:ollama:{model}",
                metadata={"provider": "ollama", "model": model},
            )
            guard = kernel.guard_action(action)
            if not guard.allow:
                raise PermissionError(f"safety_kernel denied llm_call: {guard.reason}")
        except PermissionError:
            raise
        except Exception as exc:
            raise RuntimeError(f"safety_kernel error for llm_call: {exc}") from exc

    def chat(
        self, 
        messages: List[ChatMessage], 
        *, 
        model: Optional[str] = None, 
        timeout: Optional[float] = None, 
        **extra_params: Any
    ) -> str:
        payload: Dict[str, Any] = {
            "model": model or self.config.name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "top_p": self.config.top_p,
                "num_ctx": self.config.num_ctx,
                "num_predict": self.config.num_predict,
            },
        }
        if "temperature" in extra_params:
            payload["options"]["temperature"] = extra_params.pop("temperature")
        if extra_params:
            payload.update(extra_params)

        try:
            text = "\n".join([m.content for m in messages])
        except Exception:
            text = str(messages)
        self._maybe_guard_llm_call(model=(model or self.config.name), prompt=text)

        try:
            current_timeout = timeout if timeout is not None else 600.0
            resp = requests.post(self._chat_url, json=payload, timeout=current_timeout)
            resp.raise_for_status()
        except Exception as e:
            logger.exception("OllamaLLMClient.chat error: %s", e)
            raise

        data = resp.json()
        msg = data.get("message") or {}
        return msg.get("content", "")

    def chat_with_tools(
        self, 
        *, 
        messages: List[Dict[str, Any]] | List[ChatMessage], 
        tools: List[Dict[str, Any]], 
        model: Optional[str] = None, 
        timeout: Optional[float] = None, 
        **extra_params: Any
    ) -> Dict[str, Any]:
        target_model = model or self.config.name
        
        # P1: Pre-check for known models that don't support tools (e.g. VL models)
        # 增加更广泛的匹配，防止 qwen2.5vl 或 deepseek-vl 触发 400 错误
        if any(kw in target_model.lower() for kw in ("vl", "vision", "multimodal")):
            logger.info(f"OllamaLLMClient: Model {target_model} likely does not support tools. Falling back to text.")
            return self._chat_as_text_fallback(messages, target_model, timeout, **extra_params)

        normalized_messages: List[Dict[str, Any]] = []
        for item in messages:
            if isinstance(item, dict):
                normalized_messages.append({"role": str(item.get("role") or "user"), "content": str(item.get("content") or "")})
            elif isinstance(item, ChatMessage):
                normalized_messages.append({"role": item.role, "content": item.content})

        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": normalized_messages,
            "tools": tools,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "top_p": self.config.top_p,
                "num_ctx": self.config.num_ctx,
                "num_predict": self.config.num_predict,
            },
        }
        if extra_params:
            payload.update(extra_params)

        prompt_text = "\n".join([m.get("content", "") for m in normalized_messages])
        self._maybe_guard_llm_call(model=target_model, prompt=prompt_text)

        current_timeout = timeout if timeout is not None else 600.0
        try:
            resp = requests.post(self._chat_url, json=payload, timeout=current_timeout)
            resp.raise_for_status()
        except Exception as e:
            # P1: 400 error fallback for "does not support tools"
            status_code = getattr(getattr(e, 'response', None), 'status_code', None)
            if status_code == 400:
                body = ""
                try: 
                    if hasattr(e, 'response'):
                        body = e.response.text.lower()
                except: pass
                if any(msg in body for msg in ("support tools", "unexpected field \"tools\"", "unknown field \"tools\"")):
                    logger.warning(f"OllamaLLMClient: Model {target_model} does not support tools. Falling back to text.")
                    return self._chat_as_text_fallback(messages, target_model, timeout, **extra_params)
            
            error_msg = str(e)
            try:
                if 'resp' in locals() and resp is not None:
                    error_msg = f"Ollama /api/chat error {resp.status_code}: {resp.text[:2000]}"
            except: pass
            raise RuntimeError(error_msg) from e

        data = resp.json() or {}
        message = data.get("message") or {}
        if not isinstance(message, dict):
            message = {}
        tool_calls = message.get("tool_calls") or data.get("tool_calls") or []
        if not isinstance(tool_calls, list):
            tool_calls = []

        return {
            "content": str(message.get("content") or ""),
            "tool_calls": tool_calls,
            "message": message,
            "raw": data,
        }

    def _chat_as_text_fallback(self, messages: List[Any], model: str, timeout: Optional[float], **extra_params: Any) -> Dict[str, Any]:
        """Heuristic fallback when tools aren't supported."""
        # Convert messages to string or single chat call
        content = self.chat(messages, model=model, timeout=timeout, **extra_params)
        return {
            "content": content,
            "tool_calls": [], # Higher layers must now parse JSON from content if needed
            "message": {"role": "assistant", "content": content},
            "raw": {"fallback": True}
        }

    def __call__(self, prompt: str, **extra_params: Any) -> str:
        return self.complete(prompt, **extra_params)

    @staticmethod
    def extract_json(text: str) -> Any:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if blocks:
            for block in reversed(blocks):
                try:
                    return json.loads(block.strip())
                except json.JSONDecodeError:
                    continue
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = text[start : end + 1]
            try:
                return json.loads(snippet)
            except json.JSONDecodeError:
                logger.warning("Failed to parse inner JSON segment even after extraction attempt.")
        raise ValueError("No valid JSON found in LLM output after all extraction attempts.")

OllamaClient = OllamaLLMClient
OllamaChatClient = OllamaLLMClient
OllamaClientConfig = OllamaModelConfig
