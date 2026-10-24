from typing import List, Dict
from .base import LLMClient


class DummyLLMClient(LLMClient):
    """
    通用占位 LLM：
    - generate: 简单 echo / mock，便于开发与测试
    - embed: 返回零向量
    以后任何人接入 OpenAI / Ollama / 自己的本地模型，只需要替换 Settings.llm.provider。
    """

    def __init__(self, name: str = "dummy"):
        self.name = name

    async def generate(self, messages: List[Dict[str, str]], **kwargs) -> str:
        last = messages[-1]["content"] if messages else ""
        return f"[DUMMY-RESPONSE] {last[:200]}"

    async def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        return [[0.0] * 3 for _ in texts]
