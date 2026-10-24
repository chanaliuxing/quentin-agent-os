from __future__ import annotations

from typing import Any, Dict
import json
import re


class SimpleCritic:
    """
    极简 Critic，占位实现：
      - 通过 LLM 对一次执行的 summary 做简单打分 / 反思
      - 以后可以由蓝皮书自迭代去升级为更复杂的多指标 Critic
    """

    def __init__(self, llm: Any, enabled: bool = True) -> None:
        self.llm = llm
        self.enabled = enabled

    def evaluate(self, summary: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if not self.enabled:
            return {
                "score": 1.0,
                "confidence": 1.0,
                "failure_reason_category": "none",
                "actionable_suggestions": [],
                "comment": "Critic is disabled.",
            }

        prompt = (
            "你是一个批判性思考的评审者，请对下面这段执行总结做简短评价：\n\n" 
            f"{summary}\n\n"
            "请用 JSON 输出：\n"
            "{\n"
            '  "score": 0~1 的浮点数,\n'
            '  "confidence": 0~1 的浮点数,\n'
            '  "failure_reason_category": "none|planning|execution|tool|llm|policy|budget|unknown",\n'
            '  "actionable_suggestions": ["..."],\n'
            '  "comment": "一句话点评"\n'
            "}\n"
            "不要输出其它文字。"
        )
        try:
            # Adapt to OllamaLLMClient which expects complete() or __call__
            if hasattr(self.llm, "complete"):
                raw = self.llm.complete(prompt)
            elif callable(self.llm):
                raw = self.llm(prompt)
            else:
                raw = ""
        except Exception:
            return {
                "score": 0.5,
                "confidence": 0.3,
                "failure_reason_category": "llm",
                "actionable_suggestions": [],
                "comment": "LLM critic error.",
            }

        # Try to parse JSON with mild robustness (strip code fences, locate first {...}).
        text = str(raw or "").strip()
        if "```" in text:
            text = re.split(r"```(?:json)?", text, maxsplit=1)[-1]
            text = text.split("```", 1)[0].strip()
        if "{" in text and "}" in text:
            text = text[text.find("{") : text.rfind("}") + 1]
        try:
            obj = json.loads(text)
        except Exception:
            # Fallback: heuristic classification.
            lowered = summary.lower()
            category = "unknown"
            if "policy" in lowered or "denied" in lowered:
                category = "policy"
            elif "budget" in lowered:
                category = "budget"
            elif "tool" in lowered:
                category = "tool"
            elif "llm" in lowered or "model" in lowered:
                category = "llm"
            elif "plan" in lowered:
                category = "planning"
            elif "error" in lowered or "failed" in lowered:
                category = "execution"
            return {
                "score": 0.5,
                "confidence": 0.2,
                "failure_reason_category": category,
                "actionable_suggestions": [],
                "comment": (str(raw or "")[:200] or "critic_parse_error"),
            }

        score = obj.get("score", 0.5)
        confidence = obj.get("confidence", 0.5)
        category = obj.get("failure_reason_category", "unknown")
        suggestions = obj.get("actionable_suggestions", [])
        if not isinstance(suggestions, list):
            suggestions = [str(suggestions)]
        return {
            "score": float(score) if isinstance(score, (int, float)) else 0.5,
            "confidence": float(confidence) if isinstance(confidence, (int, float)) else 0.5,
            "failure_reason_category": str(category),
            "actionable_suggestions": [str(s) for s in suggestions][:8],
            "comment": str(obj.get("comment", ""))[:500],
        }
