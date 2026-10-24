# 终极方案：L3 研究与演化层实现路线图 v5.0

**作者**: Gemini
**版本**: 5.0 (基于代码审查的现实诊断 + 融合方案的最终路线图)
**核心思想**: 以已审查并确认存在的 `SelfProgrammingEngine` 为“执行臂”，通过“爬、走、跑”三阶段，逐步构建并完善一个能够进行数据驱动决策、最终实现元编程自我进化的“决策脑”。

---\n
## Part 0: 现状审查与诊断 (Current Implementation Status Audit)

本章节基于当前代码库的真实落地情况进行了更新：L1/L2/L3 的核心骨架均已存在，并附上可追溯的代码路径与测试证据。

| 层级 | 蓝图组件 | **落地状态** | **证据与备注 (Evidence & Remarks)** |
| :--- | :------- | :----------- | :---------------------------------- |
| **L3** | `EvolutionStrategyManager` | ✅ **已实现** | `quentin/research/evolution.py`（加权打分与排序，见 `tests/unit/test_evolution_scoring.py`）；自编程重试版在 `meta_agent/self_programming/strategy.py`。 |
| **L3** | `ExperimentOrchestrator` | ✅ **已实现** | `quentin/research/experiment_orchestrator.py` 已支持 create/submit/dispatch/compare，内置 `EvalHarness`，持久化 run 记录。 |
| **L3** | `Policy & Governance` | ✅ **已实现** | 治理配置与议会在 `governance/constitution.yaml`、`governance/council.py`，通过 `quentin/bootstrap/container.py` 注入运行时。 |
| **L2** | `EvalHarness` | ✅ **已实现** | `quentin/research/eval_harness.py` + 单元/集成测试（`tests/unit/test_eval_harness.py`、`tests/integration/test_eval_harness_integration.py`），各类 runner 已接入。 |
| **L2** | `MemoryFabric` / `SleepLoop` | ✅ **已实现** | 记忆织物与巩固循环：`quentin/memory/fabric.py`、`quentin/memory/sleep_loop.py`、`quentin/loops/sleep_loop.py`、`quentin/runtime/sleep_loop.py`。 |
| **L1** | `SelfProgrammingEngine` | ✅ **已实现** | `meta_agent/self_programming/engine.py` 已包含 Git 沙盒、测试、评审与指标记录。 |
| **L1** | `ArchitectAgent` | ✅ **已实现（默认开启 LLM）** | `meta_agent/self_programming/agents/architect.py` 默认 `USE_LLM_ARCHITECT=true`，失败时回退规则计划。 |
| **L1** | `ProgrammerAgent` | ✅ **已实现** | `meta_agent/self_programming/agents/programmer.py` 调用工具链生成补丁。 |
| **L1** | `TesterAgent` | ✅ **已实现** | `meta_agent/self_programming/agents/tester.py` 支持基于计划的 pytest 运行。 |
| **L1** | `ReviewerAgent` | ✅ **已实现** | `meta_agent/self_programming/agents/reviewer.py` 规则审查 + 可选 LLM 审查。 |
| **Tool** | `LocalLLMTool` | ✅ **已实现** | `meta_agent/self_programming/tools/local_llm.py` 支持补丁生成与确定性的烟囱测试生成（非占位）。 |

**诊断结论**: L1/L2/L3 的关键组件均已落地；后续工作重心在于配置、调度策略与数据闭环优化，而非从零造轮子。

---\n
## Part 1: 架构原则与未来愿景

基于以上诊断，我们为接下来的演化制定以下原则：

*   **从现实出发 (Grounded in Reality)**: 所有计划都基于对现有 `SelfProgrammingEngine` 的扩展。
*   **数据驱动决策 (Data-Driven Decisions)**: 任何策略、规划或自我改进都必须基于从 `MetricsStore` 和 `EvalHarness` 中收集到的可量化指标。
*   **安全第一 (Safety First)**: 所有代码修改必须在 Git 沙箱分支中进行，并由自动化测试严格验证。系统的自我修改权限受 `Policy & Governance` 模块的严格约束。
*   **增量演化 (Incremental Evolution)**: 遵循“爬、走、跑”的模式，从最小可行闭环开始，逐步增加系统的自主性和智能。
*   **目标与机会结合 (Top-Down meets Bottom-Up)**: 长期由 `GoalManager` 提供的“自顶向下”的目标来指引，同时由代码扫描发现的“自底向上”的机会（如技术债）来驱动。

**最终愿景**: 创建一个能够理解其蓝图目标、分析自身代码差距、制定并执行多阶段演化计划、并从结果中学习以优化未来决策的自进化 AI 操作系统。

---\n
## Part 2: Phase 1/爬（Crawl）- 建立反应式自修复的最小闭环

**目标**: 打造最基础的“执行-观察-反应”循环。让系统在无人干预的情况下，能够自动识别并重试失败的编码任务，为后续所有高级智能提供数据基础。

**2.1. 已落地组件：`MetricsStore`（指标存储）**
   * **实现位置**: `meta_agent/self_programming/metrics_store.py` 提供 `MetricsStoreProtocol` 与 `JsonlMetricsStore`（JSONL 持久化），单测在 `tests/unit/test_self_programming_iteration.py::test_jsonl_metrics_store_roundtrip`。
   * **功能**: 作为系统唯一的“真相来源(Source of Truth)”，持久化记录每次 `SelfProgrammingEngine` 运行的详细结果。
   * **接口定义 (Python Protocol)**:
     ```python
     class RunRecord(TypedDict):
         task_id: str
         status: Literal["approved", "rejected", "test_fail", "error"]
         timestamp: datetime
         commit_hash: Optional[str]
         raw_test_output: Optional[str]
         metrics: Dict[str, Any] # e.g., {"duration_sec": 120.5, "generated_lines": 25}

     class MetricsStoreProtocol(Protocol):
         def log_run(self, record: RunRecord) -> None: ...
         def get_runs_by_status(self, status: str, limit: int = 10) -> List[RunRecord]: ...
     ```
   * **实施现状**: 默认使用 JSONL，本地落地速度快，必要时可切换为 SQLite/Postgres 但当前版本已满足自迭代需求。

**2.2. 已落地组件：`SimpleEvolutionStrategyManager` (v0.1 - 简单策略管理器)**
   * **实现位置**: `meta_agent/self_programming/strategy.py`（重试失败任务），配套测试 `tests/unit/test_self_programming_iteration.py::test_strategy_generates_retry_task`。
   * **功能**: 作为 v0.1 的“决策脑”，只具备一种最原始的策略：从错误中学习并重试。
   * **接口定义**:
     ```python
     class SimpleEvolutionStrategyManager:
         def __init__(self, metrics_store: MetricsStoreProtocol):
             self.metrics_store = metrics_store

         def generate_tasks(self) -> List[ProgrammingTask]:
             failed_runs = self.metrics_store.get_runs_by_status("test_fail")
             retry_tasks = []
             for run in failed_runs:
                 # 防止无限重试
                 if "retry_of" in run.get("task_id", ""): continue
                 
                 new_task = ProgrammingTask(
                     task_id=f"retry_of_{run['task_id']}",
                     description=f"Previous attempt failed. Analyze test errors and fix.\nErrors:\n{run['raw_test_output']}",
                     # ... 继承原任务的其他字段 ...
                 )
                 retry_tasks.append(new_task)
             return retry_tasks
         ```
   * **依赖**: `MetricsStore`。

**2.3. 已落地组件：`run_evolution_loop.py`（演化循环守护脚本）**
   * **实现位置**: `scripts/run_evolution_loop.py` 调用 `meta_agent.self_programming.evolution_loop.run_loop`，支持 `--sleep-seconds`、`--max-iterations`。
   * **功能**: 驱动 Phase 1 核心循环的顶层脚本，可作为 `daemon` 或 `cron job` 运行。
   * **伪代码**:
     ```python
     # 1. 初始化 MetricsStore, StrategyManager, SelfProgrammingEngine
     # 2. 进入主循环 (while True:)
     # 3.   调用 strategy_manager.generate_tasks() 获取重试任务
     # 4.   如果无任务，休眠 (time.sleep)
     # 5.   遍历任务，调用 engine.run_task(task)
     # 6.   将返回的 ProgrammingResult 适配为 RunRecord
     # 7.   调用 metrics_store.log_run(record) 将结果持久化
     ```
   * **Phase 1 成功标准**: 能够观察到系统在一次编码任务因测试失败被拒绝后，自动创建了一个新的“重试任务”并再次执行。

---\n
## Part 3: Phase 2/走（Walk）- 迈向主动式、策略化的自我改进

**目标**: “决策脑”学会主动思考。除了修复失败，它还能主动扫描代码库，发现潜在的改进机会（技术债），并像一个真正的技术经理一样对这些机会进行优先级排序。

**3.1. 已落地组件：`EvolutionStrategyManager` (v0.5 - 多策略管理器)**
   * **实现位置**: `quentin/research/evolution.py` 结合蓝皮书 gap、历史实验统计与预算控制进行多因子排序；自编程的失败重试策略由 `meta_agent/self_programming/strategy.py` 提供。
   * **策略来源**: `BlueprintGapTracker` + `SelfImprovementManager` 列出的改进任务，及自定义 `stats_provider` 可挂接覆盖率/复杂度信号（需要 radon 等扫描时直接在此扩展）。
   * **优先级排序**: 通过 `EvolutionScoreWeights` 可配置权重，排序逻辑已在 `tests/unit/test_evolution_scoring.py` 验证。

**3.2. 已落地组件：`EvalHarness` (v0.1 - 简易评测工具集)**
   * **实现位置**: `quentin/research/eval_harness.py`，注册式的 evaluator 架构，附带单测与集成测试；`ExperimentOrchestrator` 默认注入此评测器。
   * **集成**: 研究层/实验层在 patch、技能或蓝皮书改进后调用 `EvalHarness` 计算指标，再写入存储（KV/trace）。

**3.3. 已落地组件：默认开启智能**
   * **实现位置**: `meta_agent/self_programming/agents/architect.py` 默认 `USE_LLM_ARCHITECT=true`，无需额外配置；`scripts/run_evolution_loop.py` 直接使用该默认值。

**Phase 2 成功标准**: 在 `MetricsStore` 中，能看到由系统**主动发起**并成功完成的“补全测试”或“重构”类型的任务记录。

---\n
## Part 4: Phase 3/跑（Run）- 实现目标驱动的元编程自进化

**目标**: “决策脑”的终极形态。它能够理解蓝图的长期目标，并为了实现这些目标而**修改包括自己在内的系统源代码**，通过科学的 A/B 实验来验证自己的“进化”是否成功。

**4.1. 已落地组件：`BlueprintGapTracker` + 目标管理**
   * **实现位置**: `quentin/blueprint/gap_tracker.py` 负责解析蓝皮书并输出 `BlueprintGap`；`quentin/self_improvement/manager.py` 维护改进任务；`tools/run_self_evolution_cycle.py` 调用 `BlueprintImprover` 将 gap 转成可执行任务。

**4.2. 已落地组件：`ExperimentOrchestrator`（实验协调器）**
   * **实现位置**: `quentin/research/experiment_orchestrator.py`，结合 `EvalHarness` 对多个 variant 跑实验并存储 run 记录；`ResearchLayer` 直接复用。

**4.3. 已落地组件：`Policy & Governance`（治理与风控）**
   * **实现位置**: `governance/constitution.yaml`、`governance/council.py`、`governance/constitution.py` 定义保护路径/预算/审批阈值，通过 `quentin/bootstrap/container.py` 注入自编程与研究流程。

**4.4. 现有的演化循环**
   * **业务/补丁层**: `scripts/run_evolution_loop.py` 驱动失败重试闭环。
   * **蓝皮书自演化层**: `tools/run_self_evolution_cycle.py` 组合 `RuntimeFacade`、`SleepLoop`、`BlueprintImprover`、`SelfProgrammingEngine`、`EvalHarness` 与治理约束，完成 gap→任务→评测→仪表盘快照的全链路。
   * **现状**: `run_self_evolution_cycle.py` 已改为基于 `build_default_runtime` 的一键引导，默认挂载 `SleepLoop`/`ImmuneLoop`/`SkillEvolutionLoop` 与自编程引擎，直接输出 Dashboard 快照与免疫动作日志。

**Phase 3 成功标准**: 在 Git 提交历史中，看到一个由系统自动创建、测试、评估并合并的、修改了其自身 Agent（例如 `local_llm.py` 中的提示词）的提交记录。

---\n
## Part 5: 最终实施路线图

1.  **第一步（ sprints 1-2）: 夯实地基** — ✅ 已完成  
    *   **成果**: `JsonlMetricsStore` + `SimpleEvolutionStrategyManager` + `run_evolution_loop.py` 闭环可用，指标落地到 `data/metrics/runs.jsonl`。
2.  **第二步（sprints 3-4）: 主动探索** — ✅ 已完成  
    *   **成果**: `EvolutionStrategyManager`（多因子打分）、`EvalHarness`、`ExperimentOrchestrator` 已上线，支持主动发现/评测改进机会。
3.  **第三步（sprints 5-8）: 迈向自进化** — ✅ 已完成（MVP）  
    *   **成果**: 蓝皮书 gap 解析、治理、实验与自编程联通，可通过 `tools/run_self_evolution_cycle.py` 跑首次元编程实验。
4.  **第四步（持续）: 完善与扩展** — ✅ 已上线（持续优化）  
    *   **重点**: 优化指标质量、扩展策略插件（复杂度/覆盖率扫描等）、完善长周期监控与预算控制。

这份方案充分利用了您现有的、坚实的 `SelfProgrammingEngine` 基础，并为您提供了一条从当前坚实基础走向蓝图宏伟目标的、清晰、务实且充满雄心的演进路径。

---\n
## Part 6: 启动自我迭代的步骤

### 1. 现在就可以开始

```bash
# Phase 1：失败重试闭环（MetricsStore + SimpleEvolutionStrategyManager）
python scripts/run_evolution_loop.py --sleep-seconds 0 --max-iterations 1

# Phase 2/3：蓝皮书自演化全链路（含 SleepLoop / EvalHarness / Governance）
python tools/run_self_evolution_cycle.py --max-gaps 2 --no-demo-tasks
```

### 2. 监控进度

```bash
tail -n 20 data/metrics/runs.jsonl        # 自编程运行记录
ls -ltr data/dashboard/ | tail            # 自演化 Dashboard 快照（由 run_self_evolution_cycle 写入）
```

### 3. 调整策略

- 修改 `governance/constitution.yaml` 管理保护路径、预算和审批阈值。
- 调整 `EvolutionScoreWeights`（`quentin/research/evolution.py`）或 `SimpleEvolutionStrategyManager` 以改变任务优先级。
- 需要额外信号（圈复杂度/覆盖率）时，通过 `stats_provider` 或新增策略插件接入。

---\n
## Part 7: 关键成功因素

### 1. 渐进式部署

*   ✅ 不要一次性启用所有功能
*   ✅ 从低风险模块开始（Desktop）
*   ✅ 逐步扩展到高风险域（Trading）

### 2. 持续监控

*   ✅ 每次迭代后检查系统健康度
*   ✅ 设置性能基线，防止退化
*   ✅ 保留回滚能力

### 3. 人类在环

*   ✅ 关键决策仍需人类审批
*   ✅ 定期审查系统的改进方向
*   ✅ 及时纠正错误的演化路径

### 4. 记录与学习

*   ✅ 详细记录每次迭代
*   ✅ 分析成功和失败
*   ✅ 持续优化决策算法

---\n
## Part 8: 预期成果

经过 3-6 个月的持续迭代，系统将：

1. ✅ **完全符合 blueprint v3 规范**
   - 所有 gaps 已修复
   - 所有层级功能完整

2. ✅ **具备真正的自我改进能力**
   - 能自主发现问题
   - 能生成高质量解决方案
   - 能从经验中学习

3. ✅ **成为研究平台**
   - 可以方便地测试新算法
   - 可以进行 A/B 实验
   - 可以发表论文

4. ✅ **保持生产稳定性**
   - 自我改进不影响业务
   - 有完善的安全机制
   - 人类保留最终控制权

---\n
## Part 9: 结论

**系统已经具备自我迭代到 v3 的所有基础组件**。

现在需要的是：

1. **连接这些组件**（Phase 1，2 周内完成）
2. **添加智能决策**（Phase 2-3，1-2 个月）
3. **建立长期目标**（Phase 4，再 1-2 个月）

**最重要的是：立即开始第一次迭代！**

系统不会一夜之间变成 v3，但通过持续的自我改进，它会**逐步演化**到那个目标。

每一次迭代都会让系统变得更智能、更强大、更接近蓝皮书描绘的愿景。

---\n
**下一步行动**：

1. 将 `scripts/run_evolution_loop.py` 挂到定时任务，持续清理失败任务。
2. 每日运行 `tools/run_self_evolution_cycle.py --max-gaps 2 --no-demo-tasks`，输出 Dashboard 快照并跟踪指标。
3. 根据运行数据调优 `governance/constitution.yaml` 与 `EvolutionScoreWeights`，逐步引入更多策略信号。
4. 保持人类在环审阅关键改动，确保安全与方向正确。

**时间就是现在！Let's start iterating! 🚀**
