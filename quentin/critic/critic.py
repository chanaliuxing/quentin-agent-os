from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class Critic:
    """
    Critic & Self-Correction v1：

    - review：根据 execution_summary 生成 lessons_learned
    - v1 返回一个简单的模板结果

    以后可以：
    - 接 LLM 做反思（Reflexion）
    - 生成结构化错误原因 / 修复建议
    """

    async def review(self, execution_summary: Dict[str, Any]) -> Dict[str, Any]:
        ok = execution_summary.get("success", True)
        if ok:
            comment = "Execution succeeded. No major issues detected."
        else:
            comment = "Execution failed. Please investigate steps and errors."

        return {
            "lessons_learned": comment,
            "raw_summary": execution_summary,
        }
