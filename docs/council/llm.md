# 终版方案：CouncilManager v3（生产落地版）

## 1) 目标与约束

**目标**：系统自主决定讨论轮数（1～max_rounds），能收敛，能容错，成本可控。
**硬约束**：

* 永不无限循环（max_rounds + stalled_rounds）
* 上下文不爆（working_memory 固定预算）
* 输出可机器执行（严格 schema + 解析修复 + 校验）

---

## 2) 核心状态机

每轮：

1. 根据 `next_round_plan` 定向提问（可跳过不相关成员）
2. 收集成员结构化回复
3. Moderator 产生结构化决策：`verdict/open_issues/next_plan/summary/progress`
4. 更新 working_memory
5. 停机条件：

   * verdict != debate ✅
   * 或 rounds 用完 ✅
   * 或 stalled 连续触发 ✅
   * 或预算耗尽（可选）✅

---

## 3) 数据结构（建议用 Pydantic 强校验）

> dataclass 可以用，但生产更建议 pydantic：默认值、类型校验、条件约束更强。

### 3.1 成员回复（建议结构化）

```python
class MemberReply(BaseModel):
    member_id: str
    stance: Literal["approve", "reject", "revise", "neutral"]
    key_points: list[str] = []
    risks: list[str] = []
    missing_info: list[str] = []
    proposed_changes: list[str] = []
    confidence: float = Field(ge=0.0, le=1.0, default=0.6)
    raw: str  # 原始文本留档
```

### 3.2 Moderator 每轮输出（关键）

```python
class NextQuestion(BaseModel):
    target: str  # "all" or member_id
    question: str

class ModeratorOutput(BaseModel):
    verdict: Literal["approve", "reject", "revise", "debate"]
    debate_type: Optional[Literal["conflict", "needs_info", "quality_gap"]] = None

    open_issues: list[str] = []
    next_round_plan: list[NextQuestion] = []
    current_summary: str

    # 进展信号：用于 stall 判断
    progress_notes: list[str] = []          # 新增事实/缩小分歧/完成验证等
    resolved_issues: list[str] = []         # 本轮解决的 issue
    newly_added_issues: list[str] = []      # 本轮新增的 issue（防止 issue 反复抖动）
    confidence: float = Field(ge=0.0, le=1.0, default=0.6)

    # 非 debate 必须有 final_answer（强约束）
    final_answer: Optional[Any] = None
```

> 强约束规则：

* 如果 verdict != debate：`final_answer` 必须非空
* 如果 verdict == debate：`next_round_plan` 必须非空（否则 fallback 到全员追问）

---

## 4) Working Memory（会议纪要）格式与预算

把 summary 固定成“可控结构”，避免 LLM 写散文：

**推荐格式（短、好用、可演进）**：

```text
Agreed:
- ...
Open issues:
- [ISSUE-1] ...
- [ISSUE-2] ...
Evidence/Constraints:
- ...
Decision boundary:
- ...
```

并加入预算控制：

* `summary_max_chars`（例如 1800～3000 chars）
* Moderator prompt 要求：超预算必须压缩

---

## 5) 关键实现策略（你可以直接照这个落地）

### 5.1 运行循环（伪代码但足够贴近你的 manager.py）

```python
max_rounds = cfg.max_rounds or 3
stall_rounds = cfg.stall_rounds or 2
stalled_count = 0

working_memory = initial_summary(question)
open_issues = []
next_round_plan = [{"target": "all", "question": question.prompt}]

for r in range(1, max_rounds+1):
    replies = execute_round(plan=next_round_plan, memory=working_memory)

    mod = moderate(memory=working_memory, open_issues=open_issues, replies=replies)

    # 更新记忆
    working_memory = clamp_summary(mod.current_summary, cfg.summary_max_chars)

    # stall 判定：连续 N 轮“open_issues 本质不变 + 无 progress”
    progressed = bool(mod.progress_notes or mod.resolved_issues or mod.newly_added_issues)
    if issues_equivalent(open_issues, mod.open_issues) and not progressed:
        stalled_count += 1
    else:
        stalled_count = 0

    open_issues = mod.open_issues

    if mod.verdict != "debate":
        return final_decision(mod, replies, memory=working_memory)

    if stalled_count >= stall_rounds:
        # 强制收敛：通常落到 revise（列出未解项 + 建议下一步）
        forced = force_revise(mod, reason="stalled")
        return final_decision(forced, replies, memory=working_memory)

    if r == max_rounds:
        forced = force_revise(mod, reason="max_rounds")
        return final_decision(forced, replies, memory=working_memory)

    next_round_plan = normalize_plan(mod.next_round_plan, cfg.members)
```

### 5.2 issues_equivalent（不要只用 set 相等）

最低配：忽略大小写 + 去标点 + 去序号后比 set
中配：用简单的关键词相似度（Jaccard）
高配：embedding 相似度（可选）

> 你先上最低配 + stalled_rounds=2，就会比 Gemini v2 稳很多。

### 5.3 定向 plan 执行：支持“一个人多个问题”

把 `targets` 改成 `member_id -> list[question]`，每个成员可以合并成一个 multi-question prompt（减少 token）。

---

## 6) Prompt（决定收敛质量的 80%）

### 6.1 Member Prompt（强制结构化）

核心：**只回答被点名的问题，不要复述 summary**，并输出 JSON（或半结构）方便 Moderator 判断。

示例（system）：

* 你是某领域专家委员。请只针对主持人的问题给出结论与依据，不要重复已在 Summary 的内容。

示例（user）：

* Summary: ...
* Question(s): ...
* Output JSON:

```json
{
  "stance": "approve|reject|revise|neutral",
  "key_points": ["..."],
  "risks": ["..."],
  "missing_info": ["..."],
  "proposed_changes": ["..."],
  "confidence": 0.0-1.0
}
```

### 6.2 Moderator Prompt（必须带“硬约束”）

关键句一定要写清楚：

* 你在维护会议纪要（current_summary）
* 你必须输出 **纯 JSON**
* verdict 规则（何时 debate）
* debate 时必须给 next_round_plan（尽量定向，不要 all）
* 非 debate 必须给 final_answer
* summary 不得复制粘贴成员原话，必须综合

---

## 7) JSON 容错：不要只靠 “再说一遍 JSON”

你现在的 `_call_llm_with_retry` 很接近可用，但建议再加两点：

1. **schema 校验**：parse 成 pydantic，不合格就 retry
2. **两阶段修复**：

   * 第一次 retry：加“ONLY JSON”
   * 第二次 retry：把模型输出当作输入，让它“修复为符合 schema 的 JSON”（修复器提示词）

这样比单纯重试稳定很多。

---

## 8) 返回结果（对外接口要稳定）

最终的 `CouncilDecision.final` 建议统一成：

```json
{
  "verdict": "...",
  "final_answer": ...,
  "reasoning": "...",
  "open_issues": [...],
  "summary": "...",
  "stop_reason": "consensus|max_rounds|stalled|budget"
}
```

同时保留 `arbiter_raw`、每轮简档（便于你做审计/回放/训练）。

---

## 9) 测试计划（你贴的 checklist 我补强到“可回归”）

### Unit（Fake LLM）

* 永远 debate + 不给 plan → 应触发 fallback plan
* 输出非 JSON → 触发修复器 → 最终可解析
* 两轮 issues 等价且无 progress → stalled 触发
* verdict=approve 但无 final_answer → 视为无效输出 → retry/修复

### Integration（真 LLM）

* “故意制造冲突”的 patch：安全委员 reject、性能委员 approve → debate → 定向追问 → revise/reject 收敛
* “缺信息”的 case：needs_info → plan 指定谁去补充/或输出缺口清单 → max_rounds 后 revise

---

# 你现在这版 Gemini v2，我建议你这样“改到能直接用”

最小改动清单（不大动架构）：

1. `ModeratorDecision` 加上 `final_answer: Any | None`，并在 parse 时读取
2. `next_round_plan` 的 targets 改成 list，避免覆盖
3. stall：改成 **连续 2 轮**，且要求“无 progress”才算 stalled
4. `current_summary` 强制预算（chars/token）
5. `_moderate_discussion` 用 pydantic 校验输出（失败走修复器）
下面给你一份**可直接复制落地**的 “Patch 文档 + 关键代码块”，把你当前 Council 从“一轮讨论 Demo”升级到**可自适应多轮讨论、可收敛、可控成本、可容错**的生产级实现（Moderator with Working Memory + Targeted Plan + Stall Detection + JSON 修复）。

---

# PatchProposal: Council Multi-Round Moderator v3

## 1. Patch 标题

**Upgrade CouncilManager to Multi-Round Moderator v3 (Working Memory + Targeted Plan + Stall Control + Robust JSON)**

## 2. 动机

当前 Council 只能一轮汇总，存在：

* 分歧/信息缺失时无法继续推进
* raw history 堆叠导致 token 爆炸
* LLM JSON 输出脆弱导致整轮崩溃
* “debate” 可能无限循环、或过早终止

本 Patch 目标：让系统**自行决定需要几轮讨论**（1～max_rounds），并通过机制确保收敛与稳定。

## 3. 范围

修改/新增：

* `quentin/council/manager.py`：核心状态机 + 定向提问 + 记忆更新 + stall 控制 + JSON 修复
* `quentin/council/schema.py`（新增）：Moderator/Member 结构化输出模型（Pydantic）
* `quentin/config/councils.yaml`（可选增强）：增加 max_rounds、stall_rounds、summary_max_chars、moderator 模型参数
* `tests/test_council_manager_v3.py`（建议新增）：回归测试（Fake LLM）

## 4. 对外行为变化

CouncilDecision 的 `final` 建议统一为：

```json
{
  "verdict": "approve|reject|revise",
  "final_answer": {... or string ...},
  "reasoning": "...",
  "open_issues": ["..."],
  "summary": "...",
  "stop_reason": "consensus|max_rounds|stalled|json_error"
}
```

## 5. 关键设计点

* **四态 verdict**：approve / reject / revise / debate
* **Working Memory**：每轮只输入摘要（minutes）+ 本轮回复
* **定向提问**：next_round_plan 支持点名提问；不相关成员本轮跳过
* **防死锁**：连续 `stall_rounds` 轮 issues 等价且无进展信号 → 强制 revise
* **强健 JSON**：解析失败 → retry → repair（让 LLM 修复为符合 schema 的 JSON）

---

# 代码落地

## A) 新增：`quentin/council/schema.py`

> 需要 `pydantic`（建议加入依赖）。如果你不想加依赖我也能给你 dataclass 手写校验版；但生产建议 pydantic。

```python
# quentin/council/schema.py
from __future__ import annotations

from typing import Any, Optional, Literal, List
from pydantic import BaseModel, Field, model_validator

Verdict = Literal["approve", "reject", "revise", "debate"]
DebateType = Optional[Literal["conflict", "needs_info", "quality_gap"]]

class NextQuestion(BaseModel):
    target: str  # "all" or member_id
    question: str

class MemberReply(BaseModel):
    member_id: str
    stance: Literal["approve", "reject", "revise", "neutral"] = "neutral"
    key_points: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    missing_info: List[str] = Field(default_factory=list)
    proposed_changes: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    raw: str = ""

class ModeratorOutput(BaseModel):
    verdict: Verdict
    reasoning: str = ""

    debate_type: DebateType = None
    open_issues: List[str] = Field(default_factory=list)
    next_round_plan: List[NextQuestion] = Field(default_factory=list)

    # Working memory
    current_summary: str

    # Progress signals for stall detection
    progress_notes: List[str] = Field(default_factory=list)
    resolved_issues: List[str] = Field(default_factory=list)
    newly_added_issues: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)

    # Must exist if verdict != debate
    final_answer: Optional[Any] = None

    @model_validator(mode="after")
    def _validate_constraints(self):
        if self.verdict == "debate":
            # debate should propose next steps
            if not self.next_round_plan:
                # allow empty plan but caller will fallback; not fatal
                pass
        else:
            # non-debate must have final_answer
            if self.final_answer is None:
                raise ValueError("final_answer is required when verdict is not 'debate'")
        return self
```

---

## B) 修改：`quentin/council/manager.py`（核心实现）

下面是一套“可直接抄进你文件”的实现骨架。你只需要把它融入你现有类（保留你现有的配置加载、call_llm、成员列表结构即可）。

### 1) 工具函数（建议放在 manager.py 顶部或类里）

````python
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from quentin.council.schema import ModeratorOutput, MemberReply, NextQuestion

logger = logging.getLogger(__name__)

def _strip_code_fences(raw: str) -> str:
    raw = raw.strip()
    if "```" in raw:
        # try common patterns
        if "```json" in raw:
            raw = raw.split("```json", 1)[1]
        else:
            raw = raw.split("```", 1)[1]
        raw = raw.split("```", 1)[0].strip()
    return raw.strip()

def _normalize_issue(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[\[\]\(\)\{\}#:\-_/]", " ", s)
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _issues_equivalent(old_issues: List[str], new_issues: List[str]) -> bool:
    if not old_issues and not new_issues:
        return False
    a = {_normalize_issue(x) for x in old_issues if x and x.strip()}
    b = {_normalize_issue(x) for x in new_issues if x and x.strip()}
    return a == b

def _clamp_text(s: str, max_chars: int) -> str:
    if max_chars <= 0:
        return s
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 20] + "\n...[TRUNCATED]..."
````

### 2) History 结构（保留审计回放）

```python
@dataclass
class DiscussionRound:
    round_index: int
    asked_plan: List[Dict[str, str]]
    member_replies: List[Dict[str, Any]]
    moderator_output: Dict[str, Any]
    summary: str
    open_issues: List[str]
```

### 3) run_council：多轮状态机 + stall 控制 + 强制收敛

```python
class CouncilManager:
    # ... 你原来的 __init__ / _load_config 不动 ...

    def run_council(self, council_name: str, question) -> Any:
        cfg = self._councils.get(council_name)
        if not cfg:
            raise ValueError(f"Council not found: {council_name}")

        max_rounds = getattr(cfg, "max_rounds", 3)
        stall_rounds = getattr(cfg, "stall_rounds", 2)
        summary_max_chars = getattr(cfg, "summary_max_chars", 2200)

        history: List[DiscussionRound] = []
        working_memory = self._initial_summary(question)
        open_issues: List[str] = []
        stalled_count = 0

        next_round_plan = [{"target": "all", "question": question.prompt}]

        last_raw_moderator = ""

        for round_idx in range(1, max_rounds + 1):
            logger.info(f"--- Council '{council_name}' Round {round_idx}/{max_rounds} ---")

            # 1) Interviews (targeted)
            member_replies = self._execute_round_interviews(
                cfg=cfg,
                question=question,
                plan=next_round_plan,
                working_memory=working_memory,
            )

            # 2) Moderate
            mod, raw = self._moderate_discussion(
                cfg=cfg,
                question=question,
                replies=member_replies,
                old_memory=working_memory,
                old_issues=open_issues,
            )
            last_raw_moderator = raw

            # 3) Update working memory (clamped)
            working_memory = _clamp_text(mod.current_summary, summary_max_chars)

            # 4) Stall detection (requires equivalence + no progress signals)
            progressed = bool(mod.progress_notes or mod.resolved_issues or mod.newly_added_issues)
            if _issues_equivalent(open_issues, mod.open_issues) and not progressed:
                stalled_count += 1
            else:
                stalled_count = 0

            open_issues = mod.open_issues

            history.append(DiscussionRound(
                round_index=round_idx,
                asked_plan=next_round_plan,
                member_replies=[r.model_dump() for r in member_replies],
                moderator_output=mod.model_dump(),
                summary=working_memory,
                open_issues=open_issues,
            ))

            # 5) Stop conditions
            if mod.verdict != "debate":
                return self._build_council_decision(cfg, question, mod, history, stop_reason="consensus", arbiter_raw=last_raw_moderator)

            if stalled_count >= stall_rounds:
                forced = self._force_revise(mod, reason="stalled")
                return self._build_council_decision(cfg, question, forced, history, stop_reason="stalled", arbiter_raw=last_raw_moderator)

            if round_idx == max_rounds:
                forced = self._force_revise(mod, reason="max_rounds")
                return self._build_council_decision(cfg, question, forced, history, stop_reason="max_rounds", arbiter_raw=last_raw_moderator)

            # 6) Prepare next plan
            next_round_plan = self._normalize_next_plan(mod.next_round_plan, cfg)

        # theoretically unreachable
        forced = self._force_revise(None, reason="unexpected_exit", open_issues=open_issues, summary=working_memory)
        return self._build_council_decision(cfg, question, forced, history, stop_reason="unexpected_exit", arbiter_raw=last_raw_moderator)
```

### 4) 定向提问：支持一个成员多个问题，不覆盖

```python
    def _execute_round_interviews(self, cfg, question, plan, working_memory: str) -> List[MemberReply]:
        """
        plan: [{"target":"all|member_id", "question":"..."}]
        """
        # Expand plan -> member_id -> list[question]
        targets: Dict[str, List[str]] = {}

        for item in plan or []:
            t = (item.get("target") or "all").strip()
            q = (item.get("question") or "").strip()
            if not q:
                continue

            if t == "all":
                for m in cfg.members:
                    targets.setdefault(m.member_id, []).append(q)
            else:
                targets.setdefault(t, []).append(q)

        replies: List[MemberReply] = []

        for member in cfg.members:
            qs = targets.get(member.member_id)
            if not qs:
                continue  # skip irrelevant members for cost control

            # Merge multiple questions into one prompt (cheaper)
            merged_q = "\n".join([f"{i+1}. {qq}" for i, qq in enumerate(qs)])

            context_prompt = (
                f"--- Previous Discussion Summary ---\n{working_memory}\n\n"
                f"--- Questions For You ---\n{merged_q}\n\n"
                f"--- Output JSON schema ---\n"
                f'{{"stance":"approve|reject|revise|neutral","key_points":[],"risks":[],"missing_info":[],"proposed_changes":[],"confidence":0.0}}'
            )

            raw_text = self._ask_member(cfg, member, question, extra_context=context_prompt)

            # Try to parse as JSON; fallback to raw
            parsed = self._parse_member_reply(member.member_id, raw_text)
            replies.append(parsed)

        return replies

    def _parse_member_reply(self, member_id: str, raw_text: str) -> MemberReply:
        raw = _strip_code_fences(raw_text)
        try:
            data = json.loads(raw)
            return MemberReply(
                member_id=member_id,
                stance=data.get("stance", "neutral"),
                key_points=data.get("key_points", []) or [],
                risks=data.get("risks", []) or [],
                missing_info=data.get("missing_info", []) or [],
                proposed_changes=data.get("proposed_changes", []) or [],
                confidence=float(data.get("confidence", 0.6) or 0.6),
                raw=raw_text,
            )
        except Exception:
            # Non-JSON member response still acceptable; keep raw for moderator
            return MemberReply(member_id=member_id, raw=raw_text)
```

> 注意：你现有 `_ask_member` 可能返回的是 Reply 对象而非字符串。你可以让 `_ask_member` 返回 raw string，或者在这里 `raw_text = reply.raw_text`。

---

### 5) Moderator：强 schema + retry + repair

```python
    def _moderate_discussion(
        self,
        cfg,
        question,
        replies: List[MemberReply],
        old_memory: str,
        old_issues: List[str],
    ) -> Tuple[ModeratorOutput, str]:

        system_prompt = self._moderator_system_prompt()
        user_payload = {
            "topic": getattr(question, "topic", ""),
            "original_prompt": getattr(question, "prompt", ""),
            "previous_summary": old_memory,
            "previous_open_issues": old_issues,
            "member_replies": [r.model_dump() for r in replies],
        }

        raw = self._call_llm_json_with_retry(
            llm_cfg=self._get_moderator_router_config(cfg, question),
            system_prompt=system_prompt,
            user_prompt=json.dumps(user_payload, ensure_ascii=False),
            retries=2,
        )

        try:
            data = json.loads(_strip_code_fences(raw))
            mod = ModeratorOutput.model_validate(data)
            return mod, raw
        except Exception as e:
            logger.error(f"ModeratorOutput validation failed: {e}")
            # last resort: force revise with minimal answer
            forced = self._force_revise(
                None,
                reason="json_error",
                open_issues=old_issues,
                summary=old_memory,
            )
            return forced, raw

    def _moderator_system_prompt(self) -> str:
        return (
            "You are the Moderator of a critical AI council.\n"
            "Your job is to drive the council to a concrete decision efficiently.\n\n"
            "Rules:\n"
            "1) Output PURE JSON only. No markdown, no commentary.\n"
            "2) Maintain concise meeting minutes in current_summary. Do NOT copy member replies.\n"
            "3) If consensus is clear -> verdict = approve/reject/revise, and MUST provide final_answer.\n"
            "4) If disagreement remains or info missing -> verdict = debate.\n"
            "   - debate_type must be one of conflict/needs_info/quality_gap.\n"
            "   - Provide open_issues and next_round_plan with targeted questions.\n"
            "   - Avoid asking 'all' if only one member needs to clarify.\n"
            "5) Provide progress signals when possible: progress_notes/resolved_issues/newly_added_issues.\n\n"
            "JSON Schema:\n"
            "{\n"
            '  "verdict": "approve|reject|revise|debate",\n'
            '  "reasoning": "string",\n'
            '  "debate_type": "conflict|needs_info|quality_gap|null",\n'
            '  "open_issues": ["..."],\n'
            '  "next_round_plan": [{"target":"member_id|all","question":"..."}],\n'
            '  "current_summary": "short meeting minutes",\n'
            '  "progress_notes": ["..."],\n'
            '  "resolved_issues": ["..."],\n'
            '  "newly_added_issues": ["..."],\n'
            '  "confidence": 0.0,\n'
            '  "final_answer": {} \n'
            "}\n"
            "Constraint: final_answer must be present when verdict is not debate."
        )
```

### 6) JSON retry + repair（比“只加一句输出 JSON”稳定很多）

```python
    def _call_llm_json_with_retry(self, llm_cfg, system_prompt: str, user_prompt: str, retries: int = 2) -> str:
        from quentin.llm.client import call_llm

        last = ""
        for i in range(retries + 1):
            raw = call_llm(llm_cfg, user_prompt=user_prompt, system_prompt=system_prompt).strip()
            last = raw
            cleaned = _strip_code_fences(raw)
            try:
                json.loads(cleaned)
                return cleaned
            except Exception:
                if i < retries:
                    user_prompt = user_prompt + "\n\nIMPORTANT: Output PURE JSON only. No markdown. Must be valid JSON."
                    continue

        # Repair step: ask model to repair its own output to valid JSON
        repaired = self._repair_json(llm_cfg, last)
        return repaired

    def _repair_json(self, llm_cfg, bad_raw: str) -> str:
        from quentin.llm.client import call_llm

        repair_system = (
            "You are a JSON repair tool.\n"
            "You will be given an invalid or non-conforming output.\n"
            "Return ONLY valid JSON that conforms to the required schema.\n"
            "No markdown.\n"
        )
        repair_user = json.dumps({
            "invalid_output": bad_raw,
            "instruction": "Fix it into valid JSON only, keep the meaning as much as possible, fill missing fields minimally."
        }, ensure_ascii=False)

        raw = call_llm(llm_cfg, user_prompt=repair_user, system_prompt=repair_system).strip()
        cleaned = _strip_code_fences(raw)
        # if still invalid, raise
        json.loads(cleaned)
        return cleaned
```

---

### 7) 强制收敛：max_rounds / stalled / json_error → revise

```python
    def _force_revise(
        self,
        mod: Optional[ModeratorOutput],
        reason: str,
        open_issues: Optional[List[str]] = None,
        summary: Optional[str] = None,
    ) -> ModeratorOutput:
        open_issues = open_issues if open_issues is not None else (mod.open_issues if mod else [])
        summary = summary if summary is not None else (mod.current_summary if mod else "No summary available.")

        final_answer = {
            "status": "needs_revision",
            "unresolved_issues": open_issues,
            "recommended_next_steps": [
                "Address unresolved issues one by one with evidence or tests.",
                "Assign owners for each issue and rerun council after updates."
            ],
            "system_stop_reason": reason,
        }

        return ModeratorOutput(
            verdict="revise",
            reasoning=(mod.reasoning if mod else "") + f" [SYSTEM: forced termination due to {reason}]",
            debate_type=None,
            open_issues=open_issues,
            next_round_plan=[],
            current_summary=summary,
            progress_notes=[],
            resolved_issues=[],
            newly_added_issues=[],
            confidence=0.5,
            final_answer=final_answer,
        )
```

### 8) Next plan 规范化：避免 target 写错导致没人被问

```python
    def _normalize_next_plan(self, plan: List[NextQuestion], cfg) -> List[Dict[str, str]]:
        member_ids = {m.member_id for m in cfg.members}
        out: List[Dict[str, str]] = []

        for item in plan or []:
            t = (item.target or "all").strip()
            q = (item.question or "").strip()
            if not q:
                continue
            if t != "all" and t not in member_ids:
                # unknown target -> fallback to all
                t = "all"
            out.append({"target": t, "question": q})

        if not out:
            out = [{"target": "all", "question": "Please clarify key disagreements and propose a concrete resolution."}]

        return out
```

### 9) 初始 summary + 最终输出组装

```python
    def _initial_summary(self, question) -> str:
        topic = getattr(question, "topic", "")
        prompt = getattr(question, "prompt", "")
        return (
            f"Agreed:\n- (none yet)\n"
            f"Open issues:\n- (none yet)\n"
            f"Evidence/Constraints:\n- Topic: {topic}\n"
            f"- Original question: {prompt}\n"
            f"Decision boundary:\n- Aim for approve/reject/revise; use debate only when needed.\n"
        )

    def _build_council_decision(self, cfg, question, mod: ModeratorOutput, history: List[DiscussionRound], stop_reason: str, arbiter_raw: str):
        return {
            "council_name": cfg.name,
            "topic": getattr(question, "topic", ""),
            "created_at": datetime.utcnow().isoformat(),
            "final": {
                "verdict": mod.verdict,
                "final_answer": mod.final_answer,
                "reasoning": mod.reasoning,
                "open_issues": mod.open_issues,
                "summary": mod.current_summary,
                "stop_reason": stop_reason,
            },
            "rounds": [h.__dict__ for h in history],
            "arbiter_raw": arbiter_raw,
        }
```

---

## C) 配置：`quentin/config/councils.yaml`（建议）

给每个 council 加：

```yaml
max_rounds: 4
stall_rounds: 2
summary_max_chars: 2200

moderator:
  model: gpt-4.1-mini   # 举例，按你项目实际 router 配
  temperature: 0.1
members:
  - member_id: safety
  - member_id: perf
  - member_id: maintainer
```

> 温度建议 Moderator 低（0.0–0.2）保证 JSON 稳定；成员可以稍高一点点（0.2–0.5）促进观点多样性。

---

# 测试（建议你直接加）

## `tests/test_council_manager_v3.py`（示例思路）

* Fake call_llm：

  1. 连续输出 debate 且 issues 不变、无 progress → 应 stalled 强制 revise
  2. 输出非 JSON → repair 后通过
  3. 输出 approve 但缺 final_answer → 校验失败 → retry/repair → 最终可落为 revise 或补齐

我可以按你现有测试框架（pytest/unittest）给你写完整可跑的测试文件；但不需要你再解释需求了。

---

# 你现在要做的三步落地（最短路径）

1. 新建 `quentin/council/schema.py`（上面已给）并确保安装 `pydantic`
2. 按我给的 manager.py 模块把 **run_council / _moderate_discussion / _call_llm_json_with_retry / _execute_round_interviews** 接进去
3. councils.yaml 加上 max_rounds / stall_rounds / summary_max_chars（默认值也行）

---

我已经完全替换了这个文件 `quentin/council/manager.py`

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Literal, Tuple
from pathlib import Path
from datetime import datetime
import logging
import json
import re
import yaml # added yaml import

from quentin.models.router import ModelRouter
from quentin.llm.client import call_llm

logger = logging.getLogger(__name__)


# ---------- 数据结构 ----------

@dataclass
class CouncilMemberConfig:
    """
    一个 council 成员（一个具体模型/角色）的配置。
    - member_id        : 成员 ID（如 "deepseek_r1", "qwen_7b"）
    - router_mode      : 传给 ModelRouter 的 mode（可用来区分不同模型）
    - router_task_type : 传给 ModelRouter 的 task_type
    - role             : 角色标签（speed/safety/cost/domain_expert/...）
    - weight           : 决策时的权重（目前仅做记录，后续可用）
    """
    member_id: str
    router_mode: str
    router_task_type: str
    role: str = "general"
    weight: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CouncilConfig:
    """
    某个 council 的整体配置。
    - name                     : council 名称（如 "planner", "done", "patch"）
    - description              : 文档说明
    - members                  : 成员列表
    - decision_mode            : 决策模式（当前实现 "arbiter_llm" / "first"）
    - arbiter_router_mode      : 仲裁 LLM 的 router_mode
    - arbiter_router_task_type : 仲裁 LLM 的 task_type
    """
    name: str
    description: str
    members: List[CouncilMemberConfig]
    decision_mode: str = "arbiter_llm"
    arbiter_router_mode: Optional[str] = None
    arbiter_router_task_type: Optional[str] = None

    # --- Moderator (multi-round) options ---
    # decision_mode == "moderator_v2" enables multi-round discussions driven by the Moderator LLM.
    max_rounds: int = 3                # hard stop to avoid infinite loops
    stall_rounds: int = 2              # stop if open_issues doesn't change for N consecutive rounds
    summary_max_chars: int = 1800      # working_memory budget (token control)
    json_retries: int = 2              # retries when moderator output is not valid JSON

    moderator_router_mode: Optional[str] = None
    moderator_router_task_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "decision_mode": self.decision_mode,
            "arbiter_router_mode": self.arbiter_router_mode,
            "arbiter_router_task_type": self.arbiter_router_task_type,
            "max_rounds": self.max_rounds,
            "stall_rounds": self.stall_rounds,
            "summary_max_chars": self.summary_max_chars,
            "json_retries": self.json_retries,
            "moderator_router_mode": self.moderator_router_mode,
            "moderator_router_task_type": self.moderator_router_task_type,
            "members": [m.to_dict() for m in self.members],
        }


@dataclass
class CouncilQuestion:
    """
    进 council“开会”的问题。
    - topic      : 议题类型，如 "planner", "reflection", "done_check", "patch_review"
    - importance : 重要性（low/normal/high），以后可以用来动态调整成员/轮数
    - prompt     : 面向 LLM 的自然语言提问（简要）
    - payload    : 结构化内容（goal/plan/metrics/patch diff 等）
    """
    topic: str
    importance: str
    prompt: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CouncilMemberReply:
    """
    某一个成员对问题的回答。
    - member_id : 成员 ID
    - raw_output: LLM 原始字符串
    - parsed    : 尝试解析出的 JSON（若失败为 None）
    - error     : 若失败或不规范，这里记录错误原因
    """
    member_id: str
    raw_output: str
    parsed: Optional[Dict[str, Any]]
    error: Optional[str]
    round_index: int = 1
    asked_question: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CouncilDecision:
    """
    整个 council 的决策结果。
    - council_name  : 哪个 council（planner/done/...）
    - topic         : 问题类型
    - final         : 最终决策 JSON（由仲裁器或简单规则生成）
    - member_replies: 所有成员的回复
    - arbiter_raw   : 仲裁 LLM 原始输出（如果用了 arbiter_llm）
    - created_at    : 时间戳
    """
    council_name: str
    topic: str
    final: Dict[str, Any]
    member_replies: List[CouncilMemberReply]
    arbiter_raw: Optional[str]
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "council_name": self.council_name,
            "topic": self.topic,
            "final": self.final,
            "member_replies": [r.to_dict() for r in self.member_replies],
            "arbiter_raw": self.arbiter_raw,
            "created_at": self.created_at,
        }



@dataclass
class ModeratorDecision:
    """
    主持人（Moderator）每一轮的裁决输出（结构化 JSON）。
    - verdict        : approve/reject/revise/debate
    - reasoning      : 简短理由
    - debate_type    : conflict/needs_info/quality_gap（可选）
    - open_issues    : 仍未解决的争议点列表（用于下一轮定向提问 + stall 检测）
    - next_round_plan: 下一轮提问计划 [{target: member_id|all, question: "..."}]
    - current_summary: 压缩后的会议纪要（Working Memory），下一轮只带这个，不再堆全量 history
    - final_answer   : 非 debate 时的最终聚合答案
    """
    verdict: Literal["approve", "reject", "revise", "debate"]
    reasoning: str = ""
    debate_type: Optional[Literal["conflict", "needs_info", "quality_gap"]] = None
    open_issues: List[str] = field(default_factory=list)
    next_round_plan: List[Dict[str, str]] = field(default_factory=list)
    current_summary: str = ""
    final_answer: Any = None


# ---------- CouncilManager 实现 ----------

class CouncilManager:
    """
    通用多 AI 议会管理器。

    使用方式：
    - 初始化时读取 config/councils.yaml 或 councils.json；
    - run_council("planner", question) → CouncilDecision。

    注意：
    - 成员采用 ModelRouter.route(...) 获取 LLM 配置；
    - 真正在哪个模型上跑，由 ModelRouter 里的路由逻辑决定；
    - 你可以在 router_mode 上区分不同本地模型（例如 "planner_deepseek_r1" / "planner_qwen_7b"），
      再在 ModelRouter 中为这些 mode 映射到 Ollama 的不同模型。
    """

    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        model_router: Optional[ModelRouter] = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.model_router = model_router or ModelRouter()
        self._councils: Dict[str, CouncilConfig] = {}
        self._load_config()

    # ----- 对外主入口 -----

    def run_council(self, council_name: str, question: CouncilQuestion) -> CouncilDecision:
        cfg = self._councils.get(council_name)
        if cfg is None:
            logger.warning("CouncilManager: council '%s' not found, using fallback single-member config.", council_name)
            cfg = self._build_fallback_config(council_name, question.topic)

        logger.info(
            "CouncilManager: running council '%s' on topic '%s' with %d members",
            council_name,
            question.topic,
            len(cfg.members),
        )

        # Multi-round moderator mode (LLM decides whether to continue debating)
        if str(cfg.decision_mode).lower() in ("moderator_v2", "moderator", "moderated"):
            return self._run_council_moderated(cfg, question, council_name=council_name)

        member_replies: List[CouncilMemberReply] = []
        for member in cfg.members:
            reply = self._ask_member(cfg, member, question)
            member_replies.append(reply)

        final, arbiter_raw = self._aggregate_decision(cfg, question, member_replies)

        decision = CouncilDecision(
            council_name=cfg.name,
            topic=question.topic,
            final=final,
            member_replies=member_replies,
            arbiter_raw=arbiter_raw,
            created_at=datetime.utcnow().isoformat(),
        )
        return decision


# ----- Moderator (multi-round) -----

def _run_council_moderated(self, cfg: CouncilConfig, question: CouncilQuestion, council_name: str) -> CouncilDecision:
    """
    多轮讨论模式：由 Moderator LLM 决定是否需要继续讨论。
    关键特性：
    - 四态裁决：approve/reject/revise/debate
    - Working Memory：每轮只带 summary，避免上下文爆炸
    - 定向提问：next_round_plan 支持点名提问，提高效率
    - Stall Detection：open_issues 连续 N 轮无变化则强制终止
    """
    max_rounds = int(getattr(cfg, "max_rounds", 3) or 3)
    stall_rounds = int(getattr(cfg, "stall_rounds", 2) or 2)
    summary_max_chars = int(getattr(cfg, "summary_max_chars", 1800) or 1800)

    working_memory = "Initial state. No discussion yet."
    open_issues: List[str] = []
    next_round_plan: List[Dict[str, str]] = [{"target": "all", "question": question.prompt}]

    all_replies: List[CouncilMemberReply] = []
    arbiter_raw_output: Optional[str] = None
    final_decision: Optional[Dict[str, Any]] = None

    prev_fp: Optional[Tuple[str, ...]] = None
    stalled_count = 0

    for round_idx in range(1, max_rounds + 1):
        logger.info("CouncilManager(moderator): '%s' round %d/%d", council_name, round_idx, max_rounds)

        # 1) 定向征询
        round_replies = self._execute_round_interviews(cfg, question, next_round_plan, working_memory, round_idx)
        all_replies.extend(round_replies)

        # 2) 主持人裁决（产出结构化 JSON + 新 summary）
        mod, raw = self._moderate_discussion(cfg, question, round_replies, working_memory, open_issues)
        arbiter_raw_output = raw

        # 3) 更新 working memory（截断防止膨胀）
        if mod.current_summary:
            working_memory = self._truncate(mod.current_summary, summary_max_chars)

        # 4) Stall Detection（连续 stall_rounds 轮 open_issues 无变化）
        open_issues = mod.open_issues or []
        fp = self._issues_fingerprint(open_issues)
        if fp and fp == prev_fp:
            stalled_count += 1
        else:
            stalled_count = 0
        prev_fp = fp

        if stall_rounds >= 2 and stalled_count >= (stall_rounds - 1):
            logger.warning("CouncilManager(moderator): stalled on issues=%s, forcing termination.", open_issues)
            mod.verdict = "revise"
            mod.reasoning = (mod.reasoning or "") + " [SYSTEM: stalled, forced termination]"
            final_decision = self._moderator_to_final(mod, working_memory, round_idx, strategy="moderator_v2")
            break

        # 5) 路由：debate -> 下一轮；否则结束
        if mod.verdict == "debate":
            if round_idx >= max_rounds:
                logger.warning("CouncilManager(moderator): max_rounds reached, forcing termination.")
                mod.verdict = "revise"
                mod.reasoning = (mod.reasoning or "") + " [SYSTEM: max_rounds reached, forced termination]"
                final_decision = self._moderator_to_final(mod, working_memory, round_idx, strategy="moderator_v2")
                break

            next_round_plan = self._sanitize_next_round_plan(cfg, mod.next_round_plan)
            if not next_round_plan:
                next_round_plan = [{"target": "all", "question": "Please address the open issues and converge on a final decision."}]
            continue

        # 非 debate：approve/reject/revise
        final_decision = self._moderator_to_final(mod, working_memory, round_idx, strategy="moderator_v2")
        break

    if final_decision is None:
        # 极端 fallback：回退到单轮 arbiter 聚合（或 first）
        final_decision, arbiter_raw_output = self._aggregate_decision(cfg, question, all_replies)

    decision = CouncilDecision(
        council_name=cfg.name,
        topic=question.topic,
        final=final_decision,
        member_replies=all_replies,
        arbiter_raw=arbiter_raw_output,
        created_at=datetime.utcnow().isoformat(),
    )
    return decision

def _execute_round_interviews(
    self,
    cfg: CouncilConfig,
    root_question: CouncilQuestion,
    plan: List[Dict[str, str]],
    working_memory: str,
    round_index: int,
) -> List[CouncilMemberReply]:
    """执行一轮访谈（支持点名提问）。"""
    # 将 plan 展开为 {member_id -> question}
    targets: Dict[str, str] = {}
    member_ids = {m.member_id for m in cfg.members}

    for item in plan or []:
        target = str(item.get("target") or "all")
        q = str(item.get("question") or "").strip()
        if not q:
            continue

        if target == "all":
            for m in cfg.members:
                targets[m.member_id] = q
        elif target in member_ids:
            # 若同一成员多条问题，拼接
            targets[target] = (targets.get(target, "") + ("\n" if targets.get(target) else "") + q).strip()
        else:
            # 未知 target：降级为 all
            for m in cfg.members:
                targets[m.member_id] = q

    if not targets:
        # 没有有效计划：默认问所有人原始问题
        for m in cfg.members:
            targets[m.member_id] = root_question.prompt

    replies: List[CouncilMemberReply] = []
    for member in cfg.members:
        if member.member_id not in targets:
            continue  # 定向跳过，节省 token
        reply = self._ask_member(
            cfg,
            member,
            root_question,
            prompt_override=targets[member.member_id],
            extra_context=working_memory,
            round_index=round_index,
        )
        replies.append(reply)
    return replies

def _moderate_discussion(
    self,
    cfg: CouncilConfig,
    question: CouncilQuestion,
    replies: List[CouncilMemberReply],
    previous_summary: str,
    previous_open_issues: List[str],
) -> Tuple[ModeratorDecision, str]:
    """主持人核心：输出结构化决策 + 新的会议纪要（Working Memory）。"""
    mod_cfg = self._get_moderator_router_config(cfg, question)

    # 控制摘要长度（提示词里也约束一次）
    summary_budget = int(getattr(cfg, "summary_max_chars", 1800) or 1800)

    system_prompt = (
        "You are the MODERATOR (chair) of a multi-agent council.\n"
        "Your goal is to drive the council to a concrete, high-quality decision efficiently.\n"
        "You maintain meeting minutes (a concise summary) to avoid token explosion.\n\n"
        "Rules:\n"
        "1) If members largely AGREE and the path is clear -> verdict must be approve/reject/revise (NOT debate).\n"
        "2) If there is significant DISAGREEMENT, missing information, or quality gap -> verdict must be debate.\n"
        "3) If verdict is debate, you MUST provide: open_issues (non-empty) and next_round_plan (non-empty).\n"
        "4) current_summary must be a synthesized minutes (do NOT copy-paste member replies).\n"
        f"5) current_summary must be <= {summary_budget} characters (hard cap).\n\n"
        "Return PURE JSON only. No markdown. No extra text.\n\n"
        "JSON schema (single object):\n"
        "{\n"
        "  \"verdict\": \"approve\"|\"reject\"|\"revise\"|\"debate\",\n"
        "  \"reasoning\": \"string\",\n"
        "  \"debate_type\": \"conflict\"|\"needs_info\"|\"quality_gap\"|null,\n"
        "  \"open_issues\": [\"issue1\", \"issue2\"],\n"
        "  \"next_round_plan\": [{\"target\": \"member_id\"|\"all\", \"question\": \"...\"}],\n"
        "  \"current_summary\": \"concise meeting minutes\",\n"
        "  \"final_answer\": <required if verdict != debate>\n"
        "}\n"
    )

    payload = {
        "council_name": cfg.name,
        "topic": question.topic,
        "original_question": question.to_dict(),
        "previous_summary": previous_summary,
        "previous_open_issues": previous_open_issues or [],
        "new_member_replies": [r.to_dict() for r in replies],
    }

    raw = self._call_llm_json_with_retry(
        mod_cfg,
        system_prompt=system_prompt,
        user_prompt=json.dumps(payload, ensure_ascii=False, indent=2),
        retries=int(getattr(cfg, "json_retries", 2) or 2),
    )

    # 解析 + 轻量校验
    obj = self._safe_json_loads(raw) or {}
    verdict = str(obj.get("verdict") or "debate").lower().strip()
    if verdict not in ("approve", "reject", "revise", "debate"):
        verdict = "debate"

    open_issues = obj.get("open_issues") or []
    if not isinstance(open_issues, list):
        open_issues = []
    open_issues = [str(x).strip() for x in open_issues if str(x).strip()]

    next_plan = obj.get("next_round_plan") or []
    if not isinstance(next_plan, list):
        next_plan = []

    current_summary = str(obj.get("current_summary") or "").strip()
    if current_summary:
        current_summary = self._truncate(current_summary, summary_budget)

    final_answer = obj.get("final_answer", None)
    if verdict != "debate" and final_answer is None:
        # 兜底：挑一个最像“最终答案”的成员输出
        final_answer = self._pick_best_member_answer(replies)

    mod = ModeratorDecision(
        verdict=verdict,  # type: ignore[arg-type]
        reasoning=str(obj.get("reasoning") or "").strip(),
        debate_type=obj.get("debate_type"),
        open_issues=open_issues,
        next_round_plan=next_plan,
        current_summary=current_summary or previous_summary,
        final_answer=final_answer,
    )

    # 强制 debate 必须有 open_issues/plan（否则降级补全）
    if mod.verdict == "debate":
        if not mod.open_issues:
            mod.open_issues = ["Unresolved disagreements or missing information (moderator did not specify)."]
        mod.next_round_plan = self._sanitize_next_round_plan(cfg, mod.next_round_plan)
        if not mod.next_round_plan:
            mod.next_round_plan = [{"target": "all", "question": "Please address the listed open_issues and converge."}]

    return mod, raw

def _moderator_to_final(self, mod: ModeratorDecision, summary: str, rounds_used: int, strategy: str) -> Dict[str, Any]:
    return {
        "verdict": mod.verdict,
        "answer": mod.final_answer,
        "reasoning": mod.reasoning,
        "debate_type": mod.debate_type,
        "open_issues": mod.open_issues,
        "summary": summary,
        "rounds_used": rounds_used,
        "strategy": strategy,
    }

def _sanitize_next_round_plan(self, cfg: CouncilConfig, plan: Any) -> List[Dict[str, str]]:
    """清洗 next_round_plan：确保 target 合法、question 非空。"""
    if not isinstance(plan, list):
        return []
    valid_member_ids = {m.member_id for m in cfg.members}
    cleaned: List[Dict[str, str]] = []
    for item in plan:
        if not isinstance(item, dict):
            continue
        target = str(item.get("target") or "all").strip()
        question = str(item.get("question") or "").strip()
        if not question:
            continue
        if target != "all" and target not in valid_member_ids:
            target = "all"
        cleaned.append({"target": target, "question": question})
    return cleaned

def _pick_best_member_answer(self, replies: List[CouncilMemberReply]) -> Any:
    """当 moderator 没给 final_answer 时的兜底：优先选择非错误、且 verdict 更明确的答案。"""
    # 优先顺序：approve/reject/revise/plan/undecided
    priority = {"approve": 0, "reject": 1, "revise": 2, "plan": 3, "undecided": 4}
    best = None
    best_p = 999
    for r in replies:
        if r.parsed is None or r.error is not None:
            continue
        v = str(r.parsed.get("verdict") or "undecided").lower().strip()
        p = priority.get(v, 99)
        if best is None or p < best_p:
            best = r.parsed.get("answer")
            best_p = p
    return best

def _issues_fingerprint(self, issues: List[str]) -> Tuple[str, ...]:
    norm = sorted({self._normalize_issue(x) for x in (issues or []) if self._normalize_issue(x)})
    return tuple(norm)

def _normalize_issue(self, s: str) -> str:
    s2 = re.sub(r"\s+", " ", str(s or "").strip().lower())
    return s2[:200]

def _truncate(self, s: str, max_chars: int) -> str:
    s = str(s or "")
    if max_chars <= 0:
        return s
    return s if len(s) <= max_chars else (s[: max_chars - 12] + " …[truncated]")

def _clean_llm_output(self, raw: str) -> str:
    raw = (raw or "").strip()
    # remove fenced code block if present
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.S | re.I)
    if m:
        raw = m.group(1).strip()
    return raw

def _extract_json_object(self, raw: str) -> str:
    """尽量从输出中提取第一个完整 JSON 对象。"""
    s = raw
    start = s.find("{")
    if start == -1:
        raise ValueError("no '{' found")
    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    # fallback: best-effort first-last
    end = s.rfind("}")
    if end != -1 and end > start:
        return s[start : end + 1]
    raise ValueError("unterminated JSON object")

def _safe_json_loads(self, raw: str) -> Optional[Dict[str, Any]]:
    try:
        cleaned = self._clean_llm_output(raw)
        obj_str = self._extract_json_object(cleaned)
        obj = json.loads(obj_str)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None

def _call_llm_json_with_retry(self, cfg: Any, system_prompt: str, user_prompt: str, retries: int = 2) -> str:
    """调用 LLM 并尽量保证输出是可解析 JSON（失败则带修复提示重试）。"""
    last_raw = ""
    for i in range(max(0, int(retries)) + 1):
        raw = call_llm(cfg, user_prompt=user_prompt, system_prompt=system_prompt).strip()
        last_raw = raw
        if self._safe_json_loads(raw) is not None:
            return self._clean_llm_output(raw)
        # retry with stricter instruction
        user_prompt = (
            user_prompt
            + "\n\nIMPORTANT: Your previous response was NOT valid JSON. Output PURE JSON only. "
              "No markdown, no backticks, no commentary. Follow the schema exactly."
        )
    return self._clean_llm_output(last_raw)

def _get_moderator_router_config(self, council_cfg: CouncilConfig, question: CouncilQuestion):
    """Moderator 路由：优先 moderator_router_*，其次沿用 arbiter_router_*，再 fallback 到首成员。"""
    if council_cfg.moderator_router_mode and council_cfg.moderator_router_task_type:
        return self.model_router.route(
            mode=council_cfg.moderator_router_mode,
            task_type=council_cfg.moderator_router_task_type,
        )
    # fallback to arbiter config if present
    if council_cfg.arbiter_router_mode and council_cfg.arbiter_router_task_type:
        return self.model_router.route(
            mode=council_cfg.arbiter_router_mode,
            task_type=council_cfg.arbiter_router_task_type,
        )
    return self._get_arbiter_router_config(council_cfg, question)

    # ----- 成员问答 -----

    def _ask_member(
        self,
        council_cfg: CouncilConfig,
        member: CouncilMemberConfig,
        question: CouncilQuestion,
        prompt_override: Optional[str] = None,
        extra_context: Optional[str] = None,
        round_index: int = 1,
    ) -> CouncilMemberReply:
        """
        让单个成员（某个模型）对同一问题给出 JSON 答案。
        约定返回结构：
        {
          "verdict": "approve" | "reject" | "revise" | "plan_variant" | ...,
          "answer": {...},   # 具体方案/结论
          "reasoning": "自然语言解释"
        }
        """
        prompt_text = prompt_override if prompt_override is not None else question.prompt
        payload = {
            "council_name": council_cfg.name,
            "council_topic": question.topic,
            "round_index": round_index,
            "extra_context": extra_context,
            "member": member.to_dict(),
            "question": {
                "prompt": prompt_text,
                "payload": question.payload,
                "importance": question.importance,
            },
        }
        user_prompt = json.dumps(payload, ensure_ascii=False, indent=2)

        system_prompt = (
            "You are one member of a multi-agent council.\n"
            "You must respond STRICTLY with a single JSON object, no extra text.\n"
            "If extra_context is provided, it is the meeting summary. Do not repeat it unless you disagree.\n"
            "Schema:\n"
            "{\n"
            "  \"verdict\": \"approve\" | \"reject\" | \"revise\" | \"plan\" | \"undecided\",\n"
            "  \"answer\": <any JSON-serializable structure>,\n"
            "  \"reasoning\": \"short explanation of your judgement\"\n"
            "}\n"
            "Your goal is to provide a clear, honest opinion based on the question.\n"
        )

        try:
            cfg = self.model_router.route(
                mode=member.router_mode,
                task_type=member.router_task_type,
            )
            raw = call_llm(cfg, user_prompt=user_prompt, system_prompt=system_prompt).strip()
        except Exception as e:
            logger.exception("CouncilManager._ask_member: LLM call failed for member %s", member.member_id)
            return CouncilMemberReply(
                member_id=member.member_id,
                raw_output="",
                parsed=None,
                error=f"llm_error: {e}",
                round_index=round_index,
                asked_question=prompt_text,
            )

        # 尝试解析 JSON
        try:
            first = raw.find("{")
            last = raw.rfind("}")
            if first != -1 and last != -1 and last > first:
                raw_json = raw[first : last + 1]
            else:
                raw_json = raw
            obj = json.loads(raw_json)
            return CouncilMemberReply(
                member_id=member.member_id,
                raw_output=raw,
                parsed=obj,
                error=None,
                round_index=round_index,
                asked_question=prompt_text,
                round_index=round_index,
                asked_question=prompt_text,
            )
        except Exception:
            logger.exception("CouncilManager._ask_member: failed to parse member %s output as JSON", member.member_id)
            return CouncilMemberReply(
                member_id=member.member_id,
                raw_output=raw,
                parsed=None,
                error="parse_error",
            )

    # ----- 决策聚合 -----

    def _aggregate_decision(
        self,
        council_cfg: CouncilConfig,
        question: CouncilQuestion,
        replies: List[CouncilMemberReply],
    ) -> tuple[Dict[str, Any], Optional[str]]:
        """
        当前实现两种模式：
        - decision_mode == "first"        : 直接采用第一个无错误成员的结果；
        - decision_mode == "arbiter_llm"  : 通过仲裁 LLM 综合所有成员意见。
        """
        if council_cfg.decision_mode == "first":
            for r in replies:
                if r.parsed is not None and r.error is None:
                    return (
                        {
                            "verdict": r.parsed.get("verdict", "undecided"),
                            "answer": r.parsed.get("answer"),
                            "reasoning": r.parsed.get("reasoning"),
                            "strategy": "first_non_error",
                        },
                        None,
                    )
            # 如果都失败，给个保底
            return (
                {
                    "verdict": "undecided",
                    "answer": None,
                    "reasoning": "all members failed or produced invalid JSON",
                    "strategy": "first_non_error",
                },
                None,
            )

        # 默认：arbiter_llm
        arbiter_raw: Optional[str] = None
        try:
            arb_cfg = self._get_arbiter_router_config(council_cfg, question)
            payload = {
                "council_name": council_cfg.name,
                "topic": question.topic,
                "question": question.to_dict(),
                "member_replies": [r.to_dict() for r in replies],
            }
            user_prompt = json.dumps(payload, ensure_ascii=False, indent=2)
            system_prompt = (
                "You are the ARBITER of a multi-agent council.\n"
                "You receive the original question and multiple member replies.\n"
                "Your job is to synthesize a SINGLE final decision.\n"
                "You MUST respond strictly as one JSON object:\n"
                "{\n"
                "  \"verdict\": \"approve\" | \"reject\" | \"revise\" | \"plan\" | \"undecided\",\n"
                "  \"answer\": <aggregated or selected answer>,\n"
                "  \"reasoning\": \"why you chose this answer over others\",\n"
                "  \"member_consistency\": {\n"
                "    \"summary\": \"short summary of agreement/disagreement\",\n"
                "    \"votes\": {\n"
                "      \"approve\": <int>,\n"
                "      \"reject\": <int>,\n"
                "      \"revise\": <int>,\n"
                "      \"plan\": <int>,\n"
                "      \"undecided\": <int>\n"
                "    }\n"
                "  }\n"
                "}\n"
                "Do not output anything outside this JSON.\n"
            )
            arbiter_raw = call_llm(arb_cfg, user_prompt=user_prompt, system_prompt=system_prompt).strip()
            # 解析仲裁结果
            first = arbiter_raw.find("{")
            last = arbiter_raw.rfind("}")
            if first != -1 and last != -1 and last > first:
                raw_json = arbiter_raw[first : last + 1]
            else:
                raw_json = arbiter_raw
            obj = json.loads(raw_json)
            return obj, arbiter_raw
        except Exception:
            logger.exception("CouncilManager._aggregate_decision: arbiter LLM failed, fallback to simple rule.")
            # 简单 fallback：看成员中出现最多的 verdict
            counts: Dict[str, int] = {}
            chosen_answer: Any = None
            chosen_reason = "fallback_majority_verdict"
            for r in replies:
                if r.parsed is None:
                    continue
                v = r.parsed.get("verdict", "undecided")
                counts[v] = counts.get(v, 0) + 1
                # 顺便记一个 answer（这里简单取第一个）
                if chosen_answer is None:
                    chosen_answer = r.parsed.get("answer")
            if not counts:
                return (
                    {
                        "verdict": "undecided",
                        "answer": None,
                        "reasoning": "all members invalid and arbiter failed",
                        "member_consistency": {"summary": "no valid replies", "votes": {}},
                    },
                    arbiter_raw,
                )
            majority_verdict = max(counts.items(), key=lambda kv: kv[1])[0]
            return (
                {
                    "verdict": majority_verdict,
                    "answer": chosen_answer,
                    "reasoning": chosen_reason,
                    "member_consistency": {"summary": "fallback majority", "votes": counts},
                },
                arbiter_raw,
            )

    def _get_arbiter_router_config(self, council_cfg: CouncilConfig, question: CouncilQuestion):
        """
        决定用哪个路由配置跑仲裁 LLM。
        优先使用 council 配置里的 arbiter_router_mode/task_type，
        否则 fallback 到第一个成员的 router_mode/router_task_type。
        """
        if council_cfg.arbiter_router_mode and council_cfg.arbiter_router_task_type:
            return self.model_router.route(
                mode=council_cfg.arbiter_router_mode,
                task_type=council_cfg.arbiter_router_task_type,
            )
        if council_cfg.members:
            m = council_cfg.members[0]
            return self.model_router.route(
                mode=m.router_mode,
                task_type=m.router_task_type,
            )
        # 极端情况：没有成员，给个默认
        return self.model_router.route(mode="council_arbiter_default", task_type=question.topic or "core")

    # ----- 配置加载 -----

    def _load_config(self) -> None:
        """
        优先读 config/councils.yaml，其次 config/councils.json。
        如果都不存在，则构造一个内建默认配置（单成员 council）。
        """
        cfg_dir = self.repo_root / "config"
        yaml_path = cfg_dir / "councils.yaml"
        json_path = cfg_dir / "councils.json"

        data: Optional[Dict[str, Any]] = None

        if yaml_path.exists():
            try:
                with yaml_path.open("r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                logger.info("CouncilManager: loaded councils config from %s", yaml_path)
            except Exception:
                logger.exception("CouncilManager: failed to load YAML config %s", yaml_path)

        elif json_path.exists():
            try:
                with json_path.open("r", encoding="utf-8") as f:
                    data = json.load(f) or {}
                logger.info("CouncilManager: loaded councils config from %s", json_path)
            except Exception:
                logger.exception("CouncilManager: failed to load JSON config %s", json_path)

        if data is None:
            logger.warning("CouncilManager: no councils config file found, using built-in defaults.")
            self._councils = {}
            return

        # 支持两种格式：顶层就是 {name: {...}}，或者 {councils: {name: {...}}}
        councils_data = data.get("councils") if isinstance(data, dict) else None
        if not councils_data and isinstance(data, dict):
            councils_data = data

        if not isinstance(councils_data, dict):
            logger.warning("CouncilManager: invalid councils config format, using empty config.")
            self._councils = {}
            return

        councils: Dict[str, CouncilConfig] = {}
        for name, cfg in councils_data.items():
            if not isinstance(cfg, dict):
                continue
            members_cfg = cfg.get("members") or []
            members: List[CouncilMemberConfig] = []
            for m in members_cfg:
                try:
                    members.append(
                        CouncilMemberConfig(
                            member_id=str(m.get("member_id")),
                            router_mode=str(m.get("router_mode") or name),
                            router_task_type=str(m.get("router_task_type") or "core"),
                            role=str(m.get("role") or "general"),
                            weight=float(m.get("weight") or 1.0),
                        )
                    )
                except Exception:
                    logger.exception("CouncilManager: invalid member config in council %s", name)
                    continue

            council = CouncilConfig(
                name=name,
                description=str(cfg.get("description") or ""),
                members=members,
                decision_mode=str(cfg.get("decision_mode") or "arbiter_llm"),
                arbiter_router_mode=cfg.get("arbiter", {}).get("router_mode"),
                arbiter_router_task_type=cfg.get("arbiter", {}).get("router_task_type"),
                max_rounds=int(cfg.get("max_rounds") or 3),
                stall_rounds=int(cfg.get("stall_rounds") or 2),
                summary_max_chars=int(cfg.get("summary_max_chars") or 1800),
                json_retries=int(cfg.get("json_retries") or 2),
                moderator_router_mode=cfg.get("moderator", {}).get("router_mode"),
                moderator_router_task_type=cfg.get("moderator", {}).get("router_task_type"),
            )
            councils[name] = council

        self._councils = councils

    def _build_fallback_config(self, name: str, topic: str) -> CouncilConfig:
        """
        当没有配置时，构造一个“单成员 council”，
        相当于退化成单模型决策，但调用路径仍然统一走 CouncilManager。
        """
        member = CouncilMemberConfig(
            member_id=f"{name}_default_member",
            router_mode=f"{name}_council_default",
            router_task_type=topic or "core",
            role="general",
            weight=1.0,
        )
        return CouncilConfig(
            name=name,
            description=f"Fallback single-member council for {name}",
            members=[member],
            decision_mode="first",
            max_rounds=1,
            stall_rounds=1,
            summary_max_chars=1800,
            json_retries=1,
        )
