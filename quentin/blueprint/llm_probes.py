from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import logging

from quentin.blueprint.spec import BlueprintCapability
from quentin.orchestrator.council import MultiModelCouncil

logger = logging.getLogger(__name__)


# 针对不同 capability，给出“可能相关的代码文件”提示
# 以后可以扩展 / 配置化
CAPABILITY_FILE_HINTS: Dict[str, List[str]] = {
    "research.experiment-orchestrator": [
        "quentin/l3/research/experiments.py",
    ],
    "obs.eval-harness": [
        "quentin/eval/harness.py",
    ],
    "blueprint.spec.machine-readable": [
        "quentin/blueprint/spec.py",
    ],
    "blueprint.gap-tracking": [
        "quentin/blueprint/gap_tracker.py",
    ],
    "blueprint.auto-improvement-plans": [
        "quentin/blueprint/improver.py",
    ],
    "research.budget-controller": [
        "quentin/l3/research/layer.py",
    ],
    "research.auto-experiment-selection": [
        "quentin/l3/research/layer.py",
    ],
    "arch.layers.four-layer-logic": [
        "quentin/runtime/system.py",
        "quentin/l3/research/layer.py",
    ],
    "obs.traces-metrics-logs": [
        "quentin/traces/core.py",
        "quentin/traces/logging.py",
    ],
    "loops.cognitive.trace-required": [
        "quentin/runtime/system.py",
        "quentin/traces/core.py",
    ],
}


@dataclass
class LLMProbeResult:
    """
    LLM / 多模型会议 对某个 capability 的判断结果。
    """
    capability_id: str
    status_guess: str
    confidence: float
    evidence: str
    raw_answer: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class LLMBasedCapabilityProbe:
    """
    基于 LLM / MultiModelCouncil 的能力探测器。

    用法：
      probe = LLMBasedCapabilityProbe(repo_root=".", llm=..., council=...)
      result = probe.probe_capability(capability)
    """

    def __init__(
        self,
        *,
        repo_root: str | Path,
        llm: Optional[Any] = None,
        council: Optional[MultiModelCouncil] = None,
        max_bytes: int = 16_000,
    ) -> None:
        if llm is None and council is None:
            raise ValueError("Either llm or council must be provided for LLMBasedCapabilityProbe.")
        self.repo_root = Path(repo_root).resolve()
        self.llm = llm
        self.council = council
        self.max_bytes = max_bytes

    # --------------------------------------------------
    # 对外：批量探测
    # --------------------------------------------------
    def probe_all(
        self,
        capabilities: List[BlueprintCapability],
        *,
        only_cap_ids: Optional[List[str]] = None,
    ) -> List[LLMProbeResult]:
        results: List[LLMProbeResult] = []
        for cap in capabilities:
            if only_cap_ids is not None and cap.id not in only_cap_ids:
                continue
            try:
                pr = self.probe_capability(cap)
            except Exception:
                logger.exception("LLMBasedCapabilityProbe: error probing cap=%s", cap.id)
                continue
            if pr is not None:
                results.append(pr)
        return results

    # --------------------------------------------------
    # 对外：单条能力探测
    # --------------------------------------------------
    def probe_capability(self, cap: BlueprintCapability) -> Optional[LLMProbeResult]:
        file_paths, code_snippet = self._collect_code_context(cap.id)
        prompt = self._build_prompt(cap, file_paths, code_snippet)

        if self.council is not None:
            deliberation = self.council.deliberate(
                question=prompt,
                context={
                    "task": "blueprint_capability_probe",
                    "capability_id": cap.id,
                    "section": cap.section,
                },
            )
            raw = deliberation.final_answer
        else:
            raw = _call_llm(self.llm, prompt)

        if raw is None:
            return None

        try:
            # Try to find JSON block if marked
            if "```json" in raw:
                parts = raw.split("```json")
                if len(parts) > 1:
                    raw = parts[1].split("```")[0].strip()
            elif "```" in raw:
                 parts = raw.split("```")
                 if len(parts) > 1:
                    raw = parts[1].strip()

            data = json.loads(raw)
        except Exception:
            logger.warning(
                "LLMBasedCapabilityProbe: LLM answer not valid JSON for cap=%s, raw=%.200r",
                cap.id,
                raw,
            )
            return None

        # 期待的 JSON 字段：
        # {
        #   "status_guess": "done|partial|missing|unknown",
        #   "confidence": 0.0~1.0,
        #   "evidence": ""
        # }
        status_guess = str(data.get("status_guess", "unknown")).lower()
        if status_guess not in ("done", "partial", "missing", "unknown"):
            status_guess = "unknown"

        try:
            confidence = float(data.get("confidence", 0.5))
        except Exception:
            confidence = 0.5
        # clamp
        confidence = max(0.0, min(1.0, confidence))

        evidence = str(data.get("evidence", "")).strip()
        if not evidence:
            evidence = "No detailed evidence provided by LLM."

        return LLMProbeResult(
            capability_id=cap.id,
            status_guess=status_guess,
            confidence=confidence,
            evidence=evidence,
            raw_answer=raw,
        )

    # --------------------------------------------------
    # 内部：收集代码上下文
    # --------------------------------------------------
    def _collect_code_context(self, capability_id: str) -> tuple[List[str], str]:
        hints = CAPABILITY_FILE_HINTS.get(capability_id, [])
        existing_files: List[str] = []
        chunks: List[str] = []

        remaining = self.max_bytes

        for rel in hints:
            path = self.repo_root / rel
            if not path.exists() or not path.is_file():
                continue
            try:
                b = path.read_bytes()
            except Exception:
                continue

            if remaining <= 0:
                break

            snippet_bytes = b[: remaining]
            remaining -= len(snippet_bytes)
            try:
                snippet = snippet_bytes.decode("utf-8", errors="replace")
            except Exception:
                snippet = ""
            existing_files.append(str(path.relative_to(self.repo_root)))
            chunks.append(f"""# File: {path.relative_to(self.repo_root)}
{snippet}
""")

        if not existing_files:
            return [], "## No code files found for this capability.\n"

        return existing_files, "\n\n".join(chunks)

    # --------------------------------------------------
    # 内部：Prompt 设计（中英混合）
    # --------------------------------------------------
    def _build_prompt(
        self,
        cap: BlueprintCapability,
        file_paths: List[str],
        code_snippet: str,
    ) -> str:
        cap_json = json.dumps(cap.to_dict(), ensure_ascii=False, indent=2)
        files_desc = ", ".join(file_paths) if file_paths else "（未找到相关文件）"

        return (
            "你是一个经验丰富的系统架构师 + 代码审查专家，任务是：\n"
            "根据『蓝皮书能力定义』以及『给定的代码片段』，判断这个能力在当前代码仓库中是否已经被实现。\n\n"
            "【蓝皮书能力定义 Blueprint Capability】\n"
            f"{cap_json}\n\n"
            "【可能相关的代码文件列表】\n"
            f"{files_desc}\n\n"
            "【相关代码片段 Code Snippet（可能被截断，仅供你判断）】\n"
            "---------------- CODE BEGIN ----------------\n"
            f"{code_snippet}\n"
            "---------------- CODE END ------------------\n\n"
            "请你给出极为简洁的、机器可读的判断结果，用 JSON 格式输出：\n"
            "{\n"
            '  "status_guess": "done" | "partial" | "missing" | "unknown",\n'
            '  "confidence": 0.0~1.0,\n'
            '  "evidence": "用1-2句话说明你为什么这么判断，可以中英文混合"\n'
            "}\n\n"
            "要求：\n"
            "  - 不要输出任何解释性文字，只输出一个 JSON 对象。\n"
            "  - 如果代码基本符合蓝皮书要求，选 \"done\" 并给出相对高的 confidence（>=0.7）。\n"
            "  - 如果只实现了部分关键点，选 \"partial\"。\n"
            "  - 如果基本找不到相关实现，选 \"missing\" 或 \"unknown\"（取决于你对判断的把握）。\n"
        )


def _call_llm(llm: Any, prompt: str) -> Optional[str]:
    """
    通用 LLM 调用适配器：
      - llm.complete(prompt=...)
      - llm.generate(prompt=...)
      - llm(prompt)
    """
    if llm is None:
        return None

    from quentin.llm.context_budget import apply_context_budget
    guarded_prompt, guard = apply_context_budget(prompt_text=prompt)
    if guard.should_block:
        raise ValueError(
            f"context budget blocked: reason={guard.reason} total={guard.total_tokens} window={guard.tokens}"
        )
    try:
        if hasattr(llm, "complete"):
            return llm.complete(prompt=guarded_prompt)
        if hasattr(llm, "generate"):
            # Adapt to OllamaLLM which expects messages
            try:
                 return llm.generate(prompt=guarded_prompt)
            except TypeError:
                 return llm.generate(messages=[{"role": "user", "content": guarded_prompt}])
            except Exception:
                 pass
        if callable(llm):
            return llm(guarded_prompt)
    except Exception:
        logger.exception("LLMBasedCapabilityProbe: error calling LLM")
        return None

    raise RuntimeError("LLM client has no complete/generate/callable interface")
