# quentin/memory/processors/summarizer.py
from __future__ import annotations
import json
import logging
import os
from typing import List, Dict, Optional
from dataclasses import dataclass

from quentin.memory.models import MemoryRecord
# 引用你现有的基础设施
from quentin.infra.llm.ollama_client import OllamaClient 
from quentin.infra.llm.stub_client import StubClient

logger = logging.getLogger(__name__)

@dataclass
class Insight:
    title: str
    content: str
    tags: List[str]
    relations: Dict[str, float] # e.g. {"related_topic": 0.9}
    
class Summarizer:
    def __init__(self, llm_client=None):
        # 默认使用 Ollama，也可以注入其他 Client。
        # In offline/canary mode, force the deterministic stub to avoid network hangs.
        if llm_client is not None:
            self.client = llm_client
            return
        force_stub = str(os.getenv("QUENTIN_LLM_FORCE_STUB", "0") or "0").strip().lower() in {"1", "true", "yes", "on"}
        if force_stub:
            self.client = StubClient(name="stub-model", provider="stub")
        else:
            self.client = OllamaClient()

    async def distill(self, records: List[MemoryRecord]) -> Optional[Insight]:
        """
        将一组相似的 STS 记录提炼为一条结构化的 MTS Insight。
        """
        if not records:
            return None
            
        # 构造上下文
        context_lines = []
        for r in records:
            # 截断过长内容，保留时间戳
            content_snippet = r.content[:500] 
            context_lines.append(f"- [{r.created_at}] {content_snippet}")
        
        context_str = "\n".join(context_lines[:20]) # 限制条数防止 Token 溢出
        
        prompt = f"""
You are a Memory Consolidation AI. 
Analyze the following short-term memory fragments and distill them into a single, high-value insight for long-term storage.

Fragments:
{context_str}

Instructions:
1. Ignore trivial logs or temporary errors.
2. Identify the core task, lesson learned, or key fact.
3. Output strictly in JSON format.

JSON Schema:
{{
  "title": "Short descriptive title",
  "insight": "Comprehensive summary and key takeaways",
  "tags": ["tag1", "tag2"]
}}
"""
        try:
            # 调用 LLM
            response = await self.client.generate([{"role": "user", "content": prompt}])
            response_text = str(getattr(response, "text", response) or "")
            
            # 清洗 JSON (处理 markdown 代码块)
            cleaned_text = self._clean_json(response_text)
            data = json.loads(cleaned_text)
            
            return Insight(
                title=data.get("title", "Untitled Insight"),
                content=data.get("insight", ""),
                tags=data.get("tags", []),
                relations={}
            )
        except Exception as e:
            logger.error(f"Summarizer distill failed: {e}")
            return None

    async def merge(self, existing_record: MemoryRecord, new_insight: Insight) -> Insight:
        """
        将新的 Insight 合并到现有的 MTS 记录中（语义去重）。
        """
        prompt = f"""
You are a Memory Manager. Merge a new insight into an existing memory record.
Keep the history but prioritize the newer, more accurate information if there's a conflict.

Existing Memory:
{existing_record.content}

New Insight:
{new_insight.content}

Instructions:
1. Create a unified description.
2. Maintain relevant tags from both.
3. Output strictly in JSON.

JSON Schema:
{{
  "title": "Merged title",
  "insight": "Merged content",
  "tags": ["tag1", "tag2"]
}}
"""
        try:
            response = await self.client.generate([{"role": "user", "content": prompt}])
            response_text = str(getattr(response, "text", response) or "")
            cleaned_text = self._clean_json(response_text)
            data = json.loads(cleaned_text)
            
            return Insight(
                title=data.get("title", new_insight.title),
                content=data.get("insight", new_insight.content),
                tags=data.get("tags", []),
                relations=existing_record.relations # 保留原有关系
            )
        except Exception as e:
            logger.error(f"Summarizer merge failed: {e}")
            # 失败回退：直接追加
            return Insight(
                title=existing_record.metadata.get("title", "Merged"),
                content=f"{existing_record.content}\n\n[Update]: {new_insight.content}",
                tags=list(set(existing_record.tags + new_insight.tags)),
                relations=existing_record.relations
            )

    def _clean_json(self, text: str) -> str:
        if "```json" in text:
            return text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            return text.split("```")[1].split("```")[0].strip()
        return text.strip()
