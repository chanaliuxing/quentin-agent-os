from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Dict, Any, List


MeetingType = Literal["planning", "reflection", "debugging", "patch_review", "generic"]


@dataclass
class LLMRoleConfig:
    """
    一个参会角色 = (使用哪个模型 + 扮演什么人格 + 对会议负责什么观点)
    """
    id: str
    name: str
    model: str
    purpose: str         # 用中文/英文描述角色职责
    style: str           # 风格说明：谨慎/发散/挑错/风险优先等
    default_temperature: float = 0.3
    weight: float = 1.0  # 在 vote/aggregation 中的权重


def default_roles_for_local_ollama() -> Dict[MeetingType, List[LLMRoleConfig]]:
    """
    针对你当前本地模型，预设几种会议组合：
    - planning: 规划/拆解任务
    - reflection: 复盘/反省
    - debugging: 调试/定位 bug
    - patch_review: 自编程 patch 审核
    """
    import os
    main_model = os.getenv("LLM_MODEL")
    if not main_model:
         raise ValueError("Environment variable LLM_MODEL must be set.")
    critic_model = os.getenv("LLM_MODEL_CRITIC") or main_model
    skeptic_model = os.getenv("LLM_MODEL_SKEPTIC") or main_model

    return {
        "planning": [
            LLMRoleConfig(
                id="planner_qwen_main",
                name="Qwen Planner",
                model=main_model,
                purpose="给出结构化、分步骤、可执行的计划，偏严谨、清晰。",
                style="严谨、结构化、倾向分解任务而不是一步到位。",
                default_temperature=0.2,
                weight=1.2,
            ),
            LLMRoleConfig(
                id="deepseek_debater",
                name="DeepSeek Debater",
                model=critic_model,
                purpose="从不同角度提出问题、补充边缘情况，防止思路太保守。",
                style="发散、喜欢提出不同假设 and 可能的坑点。",
                default_temperature=0.4,
                weight=1.0,
            ),
            LLMRoleConfig(
                id="uncensored_skeptic",
                name="Uncensored Skeptic",
                model=skeptic_model,
                purpose="在安全边界内尽量提出『极端情况 / 反例 / 难点』，提醒风险。",
                style="爱挑毛病，优先指出可能失败之处。",
                default_temperature=0.5,
                weight=0.8,
            ),
        ],
        "reflection": [
            LLMRoleConfig(
                id="reflector_qwen",
                name="Qwen Reflector",
                model=main_model,
                purpose="基于失败记录，做结构化复盘，抽象教训。",
                style="冷静分析，抽象原则和可迁移经验。",
                default_temperature=0.25,
                weight=1.2,
            ),
            LLMRoleConfig(
                id="deepseek_postmortem",
                name="DeepSeek Postmortem",
                model=critic_model,
                purpose="从过程层面挖掘『在哪里想偏了』『有哪些盲点』。",
                style="重过程，善于拆解推理路径。",
                default_temperature=0.4,
                weight=1.0,
            ),
        ],
        "debugging": [
            LLMRoleConfig(
                id="qwen_debugger",
                name="Qwen Debugger",
                model=main_model,
                purpose="阅读报错/堆栈/代码片段，给出直接的修复建议。",
                style="实用主义，优先给出可运行的修改方案。",
                default_temperature=0.25,
                weight=1.2,
            ),
            LLMRoleConfig(
                id="deepseek_bug_hunter",
                name="DeepSeek Bug Hunter",
                model=critic_model,
                purpose="从设计/边界条件角度挖掘潜在 bug 和隐含假设。",
                style="喜欢质疑设计假设和边界情况。",
                default_temperature=0.35,
                weight=1.0,
            ),
        ],
        "patch_review": [
            LLMRoleConfig(
                id="qwen_reviewer",
                name="Qwen Code Reviewer",
                model=main_model,
                purpose="从可读性、正确性和可维护性角度审查 patch。",
                style="中庸风格，给出 balanced review。",
                default_temperature=0.25,
                weight=1.0,
            ),
            LLMRoleConfig(
                id="deepseek_risk_checker",
                name="DeepSeek Risk Checker",
                model=critic_model,
                purpose="专门找『可能破坏现有系统』和『隐含风险』的地方。",
                style="偏悲观，优先指出风险和不确定性。",
                default_temperature=0.35,
                weight=1.2,
            ),
        ],
        "generic": [
            LLMRoleConfig(
                id="qwen_generalist",
                name="Qwen Generalist",
                model=main_model,
                purpose="通用问题的主回答者。",
                style="稳健、解释清楚。",
                default_temperature=0.25,
                weight=1.0,
            ),
            LLMRoleConfig(
                id="deepseek_second_opinion",
                name="DeepSeek Second Opinion",
                model=critic_model,
                purpose="作为第二意见，避免单一模型过度自信。",
                style="倾向于指出另一种做法或不同观点。",
                default_temperature=0.35,
                weight=1.0,
            ),
        ],
    }
