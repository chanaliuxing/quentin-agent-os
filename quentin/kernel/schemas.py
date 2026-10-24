from __future__ import annotations
from typing import Literal, Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator
from datetime import datetime
from enum import Enum # Import Enum here


# Canonical env names (blueprint v3): sandbox / staging / prod.
# "production" is a backward-compatible alias.
EnvName = Literal["sandbox", "staging", "prod", "production"]


class MemoryTier(str, Enum):
    """
    Memory Fabric 三层：
    - STS: Short-Term Store（会话/任务级，分钟~小时）
    - MTS: Mid-Term Store（项目/版本级，天~周）
    - LTS: Long-Term Store（跨项目稳定知识，周~年）
    """
    STS = "STS"
    MTS = "MTS"
    LTS = "LTS"


class MemoryUpdatePolicy(BaseModel):
    """
    更新策略：
    - promotion_rule: 用哪个 promotion 策略（名字）
    - decay_rule: 用哪个 decay 策略（名字）
    - consolidation_batch: 归档批次（nightly / weekly / manual）
    具体规则由 MemoryPolicyEngine 解释。
    """
    promotion_rule: str = "default_promotion_v1"
    decay_rule: str = "default_decay_v1"
    consolidation_batch: str = "nightly"


class MemoryRecord(BaseModel):
    """
    单条记忆记录（逻辑层 schema）：
    - content: 任意可序列化内容，最简单先用 text
    - tier: 当前所在记忆层
    - strength: “重要性/置信度”粗略分数
    - metadata: domain / tags / relations 等
    - access_count / last_access_at: 用于 promotion / decay
    """
    memory_id: str
    tier: MemoryTier = MemoryTier.STS
    content: Any
    domain: str = "generic" # Added domain field
    metadata: Dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_access_at: datetime = Field(default_factory=datetime.utcnow)
    access_count: int = 0
    strength: float = 0.0

    update_policy: MemoryUpdatePolicy = Field(
        default_factory=MemoryUpdatePolicy
    )





class TraceSpan(BaseModel):
    span_id: str
    parent_id: Optional[str] = None
    timestamp: datetime
    layer: str                # "L0" / "L1" / "L2" / "L3"
    module: str               # "planner" / "executor" / ...
    event: str                # "task_started" / "llm_call" ...
    input: Any | None = None
    output: Any | None = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class TaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"


class TaskConfig(BaseModel):
    """
    一次任务的高层描述：
    - goal: 想让智能体完成什么
    - input: 初始输入（可以是任意结构）
    - domain: 属于哪个领域（generic/desktop/legal/trading/...）
    """
    task_id: str
    goal: str
    input: Dict[str, Any] = Field(default_factory=dict)
    domain: str = "generic"
    meta: Dict[str, Any] = Field(default_factory=dict)


class PlanStep(BaseModel):
    step_id: str
    description: str
    tool: str = "noop"  # 由 Executor 解释
    params: Dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    plan_id: str
    task_id: str
    steps: List[PlanStep] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StepTrace(BaseModel):
    step_id: str
    tool: str
    input: Dict[str, Any] = Field(default_factory=dict)
    output: Dict[str, Any] = Field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: datetime = Field(default_factory=datetime.utcnow)
    meta: Dict[str, Any] = Field(default_factory=dict)


class ExecutionSummary(BaseModel):
    """
    一次任务整体执行情况，用于：
    - 写 Trace / Log
    - 生成 lessons_learned
    - 给 SelfImprovementManager 做分析
    """
    task_id: str
    task_goal: str
    domain: str
    status: TaskStatus
    started_at: datetime
    finished_at: datetime
    steps: List[StepTrace] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)

    lessons_learned: Optional[str] = None
    root_cause: Optional[str] = None
    improvement_hints: List[str] = Field(default_factory=list)


class ImprovementCandidate(BaseModel):
    """
    自我改进候选：
    - module_path：怀疑需要改进的模块（planner/某个tool/某个router策略）
    - reason：自然语言说明
    - evidence：一些指标/trace 聚合信息
    """
    candidate_id: str
    task_id: str
    domain: str
    module_path: str
    reason: str
    evidence: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "open"  # open / in_progress / done / rejected

# --- NEW SCHEMAS FROM AI/17.MD ---
class VariantKind(str, Enum):
    planner = "planner"
    memory_policy = "memory_policy"
    model_router = "model_router"
    self_programming = "self_programming"
    other = "other"


class VariantSpec(BaseModel):
    """
    描述一个“可替换策略”的变体：
    - kind: 属于哪一类策略（planner/memory/...）
    - config: 用于 runner 的配置（可以是任意 JSON）
    """
    variant_id: str
    kind: VariantKind
    name: str
    description: str = ""
    config: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_default: bool = False
    meta: Dict[str, Any] = Field(default_factory=dict)


class EvalRunSummary(BaseModel):
    """
    一次评测运行的结果：
    - 对哪个 variant
    - 使用了哪个 dataset（可选）
    - 得到了哪些 metrics
    """
    eval_id: str
    experiment_id: Optional[str] = None
    variant_id: str
    dataset_id: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: datetime = Field(default_factory=datetime.utcnow)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    success: bool = True
    meta: Dict[str, Any] = Field(default_factory=dict)


class ExperimentStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    planned = "planned"





class Experiment(BaseModel):
    """
    一个实验：用一组 Variant 在一个 Dataset 上做评测。
    对于自编程 Patch，我们可以把每个 Patch 看成一个 Variant。
    """
    experiment_id: str
    name: str
    purpose: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: ExperimentStatus = ExperimentStatus.pending

    variants: List[str] = Field(default_factory=list)   # variant_id 列表
    dataset_id: Optional[str] = None

    eval_runs: List[EvalRunSummary] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)


class ExperimentConfig(BaseModel):
    """
    一个实验配置：
    - 在某个 task_type 上，用同一个 dataset 对多个 variant 做对比
    """
    experiment_id: str
    name: str
    description: str = ""
    task_type: str = "generic"
    dataset_id: str
    variant_ids: List[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: ExperimentStatus = ExperimentStatus.planned


class ExperimentResult(BaseModel):
    """
    实验结果：
    - 聚合多个 variant 的 EvalRunSummary
    """
    experiment_id: str
    task_type: str
    dataset_id: str
    created_at: datetime
    finished_at: datetime
    per_variant: Dict[str, EvalRunSummary] = Field(default_factory=dict)


# --- NEW SCHEMAS FROM AI/18.MD ---
class SafetyMode(str, Enum):
    normal = "normal"
    degraded = "degraded"
    frozen = "frozen"


class SafetyState(BaseModel):
    """
    安全内核的当前状态：
    - mode: 正常 / 降级 / 冻结
    - self_programming_enabled: 是否允许自编程
    - exploration_level: 探索强度（0~1），供路由策略使用
    """
    mode: SafetyMode = SafetyMode.normal
    self_programming_enabled: bool = True
    degraded: bool = False # New field
    exploration_level: float = 1.0
    last_updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_incident_at: Optional[datetime] = None # New field
    meta: Dict[str, Any] = Field(default_factory=dict)


class ImmuneEventSeverity(str, Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class ImmuneEvent(BaseModel):
    """
    一次免疫事件：检测到异常并采取了某些动作。
    """
    event_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    severity: ImmuneEventSeverity
    description: str
    metrics_snapshot: Dict[str, Any] = Field(default_factory=dict)
    actions_taken: List[str] = Field(default_factory=list)


# --- NEW SCHEMAS FROM AI/19.MD ---
class SkillStatus(str, Enum):
    draft = "draft"
    active = "active"
    deprecated = "deprecated"


class SkillDefinition(BaseModel):
    """
    自动/人工抽取的“技能”定义：
    - 本质上是一个可复用的 Plan 模板（若干步骤的宏）
    - 为了简单起见，steps 存的是字典结构，Planner 再转成 PlanStep
    """
    skill_id: str
    name: str
    description: str = ""
    domain: str = "generic"

    pattern_goal: str = ""         # 这个技能对应的典型 goal 描述
    tags: List[str] = Field(default_factory=list)

    # 每个步骤结构类似 PlanStep 序列化后的结构：
    # { "description": str, "tool": str, "params": {...} }
    steps: List[Dict[str, Any]] = Field(default_factory=list)

    created_from_task_ids: List[str] = Field(default_factory=list)

    status: SkillStatus = SkillStatus.draft
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # 统计信息 / 评估指标
    stats: Dict[str, Any] = Field(default_factory=dict)


# --- NEW SCHEMAS FROM AI/20.MD ---
class AgentRole(str, Enum):
    speed = "speed"
    safety = "safety"
    cost = "cost"
    domain_expert = "domain_expert"


class AgentCritique(BaseModel):
    """
    单个 Agent 对某个方案的评估意见。
    """
    agent_role: AgentRole
    score: float                   # 0~1 之间的评分
    rationale: str                 # 文本说明
    suggested_changes: Optional[str] = None  # 对 plan / 决策的修改建议
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AggregatedDecision(BaseModel):
    """
    Multi-Agent 协作后得到的最终决策摘要：
    - 目前用于对 Plan 或 Routing 决策做「多视角投票」
    """
    decision_id: str
    target_type: str               # e.g. "plan", "routing"
    target_id: str                 # e.g. plan_id 或 route_id
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # 聚合后的评分（例如按权重平均）
    score_overall: float
    scores_by_role: Dict[str, float] = Field(default_factory=dict)

    critiques: List[AgentCritique] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)


class ModelRoutingRecord(BaseModel):
    """
    一次模型路由调用的记录，用于数据驱动优化策略：
    - 哪个 task_type
    - 选了哪个模型
    - 花了多少 token / 时间
    - 是否成功
    """
    routing_id: str
    task_type: str
    model_name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    latency_sec: float
    input_tokens: int = 0
    output_tokens: int = 0
    cost_estimate: float = 0.0
    success: bool = True

    meta: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"protected_namespaces": ()}


# --- NEW SCHEMAS FROM AI/22.MD ---
class SleepCycleReport(BaseModel):
    """
    一次 Sleep / Consolidation 循环的汇总报告
    """
    cycle_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # 本轮处理了多少历史任务
    processed_tasks: int
    # 新产生的“语义总结”条目数量（先存在 SleepLoop 自己的命名空间）
    new_semantic_entries: int
    # 调用 SkillMiner 新挖出来的技能数量
    new_skills: int
    # （预留）本轮触发了多少自编程 patch
    triggered_patches: int
    # （预留）本轮触发了多少实验（Experiment）
    triggered_experiments: int

    meta: Dict[str, Any] = Field(default_factory=dict)


# --- NEW SCHEMAS FROM AI/23.MD ---



class ExperimentVariant(BaseModel):
    """
    通用 Variant 定义：
    - target_type：实验挂载的目标类型，比如 "planner" / "router" / "critic" / "tool" / "prompt"
    - config：具体参数（由你自己解释这堆 config 怎么给模块用）
    """
    variant_id: str
    name: str
    description: str = ""
    target_type: str

    config: Dict[str, Any] = Field(default_factory=dict)
    # Backward-compatible alias used by older code/tests.
    params: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    meta: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _coerce_params_and_config(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        cfg = data.get("config")
        params = data.get("params")
        if isinstance(params, dict) and (not isinstance(cfg, dict) or not cfg):
            data["config"] = params
        if isinstance(cfg, dict) and (not isinstance(params, dict) or not params):
            data["params"] = cfg
        return data


# Redefining Experiment to match ai/23.md
class Experiment(BaseModel):
    """
    一次实验（Experiment）定义：
    - target_type: 实验针对的模块类型（planner/router/…）
    - target_selector: 更细的定位方式，例如 "base.planner.DefaultPlanner"
    - variant_ids: 本实验要比较的 variant 列表（在 VariantRegistry 里事先注册）
    """
    experiment_id: str
    name: str
    description: str = ""
    target_type: str
    target_selector: str = ""

    status: ExperimentStatus = ExperimentStatus.pending
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # 本实验包含哪些 variant
    variant_ids: List[str] = Field(default_factory=list)

    # 在线实验可以用这个（variant_id -> 流量占比），
    # 目前我们只在离线评测里存着，不强制使用
    traffic_allocation: Dict[str, float] = Field(default_factory=dict)

    max_runs: int = 0           # 允许的最大 run 次数（离线）
    completed_runs: int = 0

    # 聚合结果：variant_id -> {"runs": int, "avg_metrics": {...}}
    results: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    meta: Dict[str, Any] = Field(default_factory=dict)


class ExperimentResult(BaseModel):
    """
    单次 run 的结果（某个 Experiment 下某个 Variant 的一轮评测）
    """
    experiment_id: str
    variant_id: str
    run_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    metrics: Dict[str, Any] = Field(default_factory=dict)  # 数值型指标
    raw: Dict[str, Any] = Field(default_factory=dict)      # 原始输出（日志/trace等）


# --- NEW SCHEMAS FROM AI/24.MD ---
class ToolKind(str, Enum):
    """
    工具类型：
    - builtin: 内置纯 Python 工具
    - llm: 通过 LLM 进行“函数调用式”工具（例如 ReAct 工具）
    - external: 需要调用外部系统 / API 的工具
    """
    builtin = "builtin"
    llm = "llm"
    external = "external"


class ToolSpec(BaseModel):
    """
    工具的声明性定义：
    - name: 全局唯一（建议用 domain 前缀，如 "generic.echo"）
    - description: 给 Planner / LLM 使用的自然语言描述
    - kind: ToolKind
    - input_schema / output_schema: OPTIONAL -> 给 LLM / UI 做校验和提示
    """
    name: str
    description: str
    kind: ToolKind = ToolKind.builtin
    domain: str = "generic"

    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)

    meta: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ToolCallRequest(BaseModel):
    """
    调用工具时的标准请求结构：
    - tool_name: ToolSpec.name
    - payload: 输入参数（可以是 dict / str / list，尽量统一成 dict）
    """
    tool_name: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    trace_id: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class ToolCallResult(BaseModel):
    """
    调用工具后的标准返回：
    - success: 是否成功
    - output: 结果（可以任意结构，但尽量是 dict/json friendly）
    - error: 如果失败，这里存错误信息
    """
    tool_name: str
    success: bool
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


# --- NEW SCHEMAS FROM AI/25.MD ---
class PatchStatus(str, Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    discarded = "discarded"


class PatchCandidate(BaseModel):
    """
    LLM 生成的“补丁候选”：
    - module_path: 要修改的模块（相对于 mutable 根目录）
    - diff: 统一 diff（MVP 中可以先放占位文本）
    """
    patch_id: str
    module_path: str
    description: str

    base_version: Optional[str] = None  # 可以存 git commit / 文件 hash
    diff: str

    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by_model: Optional[str] = None
    suggested_tests: List[str] = Field(default_factory=list)

    meta: Dict[str, Any] = Field(default_factory=dict)


class PatchEvaluation(BaseModel):
    """
    在 sandbox 中跑测试的结果
    """
    patch_id: str
    run_id: str

    status: PatchStatus = PatchStatus.pending

    test_command: str = "pytest"
    exit_code: int = 0
    passed: bool = False

    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None

    stdout: str = ""
    stderr: str = ""

    metrics: Dict[str, Any] = Field(default_factory=dict)


class PatchReport(BaseModel):
    """
    聚合视角：一个 patch + 多次评估的完整报告
    """
    patch_id: str
    module_path: str
    description: str

    status: PatchStatus
    candidate: PatchCandidate
    evaluations: List[PatchEvaluation] = Field(default_factory=list)

    selected: bool = False            # 是否被选为“推荐方案”
    deployed_to: List[str] = Field(default_factory=list)  # ["sandbox", "staging", ...]

    created_at: datetime = Field(default_factory=datetime.utcnow)
    meta: Dict[str, Any] = Field(default_factory=dict)
