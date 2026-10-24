# Project Quentin – Research API 指南

> 面向研究者 / 工程师  
> 如何把你的算法 / 策略 / 论文方法接到这个通用智能体系统中。

---

## 0. 快速总览

核心改装点：

1. **EvalHarness** – 自定义评测逻辑（离线数据集 / 在线 A/B）。
2. **ExperimentOrchestrator + VariantRegistry** – 管理实验和变体。
3. **MultiAgentCoordinator + ModelRouter** – 做 bandit / RL 的模型路由。
4. **SelfProgrammingEngine + SelfImprovementManager** – 自编程与 patch 评估。
5. **SleepLoop / ImmuneLoop** – 长期记忆巩固和异常检测。

所有这些组件都可以在 **不改变公共 Schema 的前提下** 被替换或扩展。

---

## 1. 实验系统（Experiments）

### 1.1 数据模型

文件：`quentin/experiments/schemas.py`

- `ExperimentConfig` – 创建实验的配置：
  - `name / description`
  - `eval_kind` – `"offline" | "online" | "custom"`
  - `dataset` – 任意字符串标识（如 `"desktop_dev_small"`)
  - `variants: List[VariantConfig]`

- `VariantConfig`：
  - `variant_id` – 唯一 ID
  - `kind` – 如 `"model_router" | "planner" | "patch_toggle"`
  - `params` – 任意参数字典（由具体模块解释）

- `ExperimentRecord`：
  - 持久化的实验记录：= config + `status` + `runs`

- `ExperimentRunResult`：
  - 一次运行的结果：`metrics / status / error / meta`

### 1.2 Orchestrator API（Python）

文件：`quentin/experiments/orchestrator.py`

```python
from quentin.experiments.orchestrator import ExperimentOrchestrator
from quentin.experiments.schemas import ExperimentConfig, VariantConfig

orch: ExperimentOrchestrator = ...

cfg = ExperimentConfig(
    name="my_new_algo_vs_baseline",
    eval_kind="offline",
    dataset="my_dataset_v1",
    variants=[
        VariantConfig(
            variant_id="baseline",
            kind="planner",
            params={"impl": "planner_v1"},
        ),
        VariantConfig(
            variant_id="my_algo",
            kind="planner",
            params={"impl": "planner_meta_rl"},
        ),
    ],
)

exp = await orch.create_experiment(cfg)
exp = await orch.run_experiment(exp.experiment_id)
compare = await orch.compare_variants(exp.experiment_id, metric="score")
results = await orch.export_results(exp.experiment_id)
```

### 1.3 HTTP 接口（FastAPI）
文件：`quentin/observability/api.py`

- `GET /experiments`
- `GET /experiments/{id}`
- `POST /experiments`
- `POST /experiments/{id}/run`
- `GET /experiments/{id}/compare?metric=score`
- `GET /experiments/{id}/export`

请求 / 响应 payload 直接使用 `ExperimentConfig` / `ExperimentRecord` 的 JSON 结构。

### 1.4 CLI
文件：`quentin/cli/qctl.py`

- `qctl exp-create-dummy`
- `qctl exp-run --id EXP_ID`
- `qctl exp-list`
- `qctl exp-show --id EXP_ID`
- `qctl exp-compare --id EXP_ID --metric score`

---

## 2. 评测框架（EvalHarness）
文件：`quentin/eval/harness.py`

默认实现是一个 **占位版**，只返回：
```python
metrics = {
  "score": 0.0,
  "notes": "EvalHarness v1 placeholder",
  ...
}
```

### 2.1 如何替换为你的评测逻辑？
直接修改 `EvalHarness.run_variant`：

```python
class EvalHarness:
    async def run_variant(self, exp: ExperimentRecord, variant: VariantConfig) -> ExperimentRunResult:
        # 1. 根据 exp.eval_kind / dataset 选择评测策略
        # 2. 把 variant.params 传给你的算法
        # 3. 返回 metrics = {"score": ..., "other_metric": ...}

        metrics = await my_eval_algo(exp, variant)

        run = ExperimentRunResult(
            run_id=...,
            experiment_id=exp.experiment_id,
            variant_id=variant.variant_id,
            status=ExperimentRunStatus.succeeded,
            metrics=metrics,
            ...
        )
        return run
```

**建议：**
- `metric="score"` 尽量统一为 “越大越好” 的指标；
- 如果是多指标，可以用 `metrics = {"score": 综合分, "acc": x, "latency": y}`；
- 所有评测过程建议写 Trace，便于调试和研究。

---

## 3. 模型路由 & 多智能体（Routing & Multi-Agent）

### 3.1 ModelUsageRecord & Stats
文件：`quentin/routing/schemas.py`

`ModelUsageRecord` 记录每一次模型调用的元信息：
```json
{
  "usage_id": "usage_xxx",
  "model_name": "gpt-4",
  "provider": "openai",
  "domain": "legal",
  "role": "planner",
  "success": true,
  "latency_sec": 0.32,
  "tokens_in": 1024,
  "tokens_out": 256,
  "cost": 0.0012,
  "reward": 0.8,
  "meta": {
    "task_id": "...",
    "goal": "..."
  }
}
```

ModelRouter 提供：
```python
stats = await model_router.get_stats(limit=1000)
# stats["models"] 里是每个模型的 calls / success_rate / avg_latency / avg_cost
```
你可以用这些数据训练 bandit / 策略网络。

### 3.2 MultiAgentCoordinator
文件：`quentin/multi_agent/coordinator.py`

主要接口：
```python
decision = await multi_agent.choose_model(
    candidates=["gpt-4", "deepseek-r1"],
    task_meta={"domain": "legal"},
)

print(decision.chosen_model)
print(decision.votes)  # Speed / Cost / Safety / Domain-Expert 的打分详情
```

### 3.3 在你的算法中挂接
- **想做 bandit / RL routing**：
  在 `MultiAgentCoordinator` 中替换聚合逻辑（或增加一个新角色），用你训练的策略来输出 score。

- **想做 多策略对比实验**：
  给不同 routing 策略分配不同的 variant_id，挂到 `ExperimentOrchestrator` 上跑 batch 任务。

---

## 4. 自编程（Self-Programming）

### 4.1 PatchRecord
文件：`quentin/self_programming/schemas.py`

核心字段：
```json
{
  "patch_id": "patch_xxx",
  "target_file": "mutable/skills/foo.py",
  "description": "Improve retry logic",
  "apply_mode": "text_replace",
  "search": "old code snippet",
  "replace": "new code snippet",
  "status": "proposed | testing | ready | applied | rolled_back | rejected",
  "test_summary": { ... },
  "eval_summary": { ... },
  "meta": { "immune_case_id": "..." }
}
```

### 4.2 SelfProgrammingEngine API
文件：`quentin/self_programming/engine.py`

- **创建手工补丁（当前 v1）**：
  ```python
  patch = await engine.propose_manual_text_patch(
      target_file="mutable/skills/my_skill.py",
      description="Simplify loop and add logging",
      search="old_snippet",
      replace="new_snippet",
      allow_auto_apply=False,
  )
  ```
- **跑测试（语法检查）**：
  ```python
  patch = await engine.run_tests(patch.patch_id)
  ```
- **应用补丁（需要 SafetyKernel 允许）**：
  ```python
  patch = await engine.apply_patch(patch.patch_id, auto=False)
  ```
- **回滚**：
  ```python
  patch = await engine.rollback_patch(patch.patch_id)
  ```

### 4.3 与实验系统对接
`SelfImprovementManager` 提供：
```python
exp_id = await self_improvement.create_experiment_for_patch(patch)
# ExperimentConfig 中会有两个 variant：
# - baseline（use_patch=False）
# - patched（use_patch=True）
```
业务侧可以在执行任务时读取当前 variant 配置，决定是否加载 patch 版本的模块，从而完成 A/B 对比。

---

## 5. ImmuneLoop & Self-Improvement

### 5.1 ImmuneCase
文件：`quentin/immune/schemas.py`（约定）

ImmuneLoop 会根据系统指标产生 `ImmuneCase`，用于定位“有问题的模块”。

`SelfImprovementManager` 提供：
```python
cases = await self_improvement.suggest_hotspots(limit_cases=10)
# 你可以将这些 case 作为研究对象，分析问题原因。

patch = await self_improvement.open_patch_for_case(
    case_id=cases[0].case_id,
    target_file="mutable/skills/my_skill.py",
    description="Fix issue identified in immune case",
    search="old",
    replace="new",
)
```

---

## 6. SleepLoop & Memory Fabric
SleepLoop（文件：`quentin/sleep/loop.py`）是接研究算法的最佳位置之一：

- **你可以在这里接入：**
  - 表征学习模型（用 Trace 训练新 embedding）。
  - 聚类 / pattern mining（自动发现新技能）。
  - 记忆巩固策略（何时升 MTS / LTS，何时遗忘）。

- **建议做法：**
  1. 设计一个 `SleepJob` 接口（按时间窗口处理 Trace / Memory）。
  2. 把你的算法封装成一个 `SleepJob`，注册到 SleepLoop 中。
  3. 定期（定时任务或 CLI）触发 SleepLoop 运行。

---

## 7. Observability（可观测性与 Dashboard）
文件：`quentin/observability/service.py` / `api.py`

提供以下统计：
- **任务执行情况**：成功率 / 错误率 / 平均耗时 / 成本等
- **Memory Fabric**：STS / MTS / LTS 的条目数、命中率、迁移速度
- **Routing**：模型调用次数 / 成功率 / 平均延迟 / 成本
- **Patches**：patch 数量 / ready / applied / rejected
- **Experiments**：实验数量 / 完成 / 失败 / 最近一次最佳变体

**你可以：**
- 在前端（Grafana / 自写 Dashboard）调用 Observability API；
- 或直接在分析脚本中 import `ObservabilityService`，做二次分析。

---

## 8. 如何接入你的论文 / 算法？

### 8.1 替换 Planner / Critic
- 定义一个新 Planner 实现，挂在 CognitiveLoop 中。
- 在 ExperimentConfig 里，将不同 Planner 作为 variants，对比表现。

### 8.2 新的模型路由算法
- 在 `MultiAgentCoordinator` 中增加一个新“角色”或替换聚合逻辑。
- 用 `ModelUsageRecord` 做训练数据，训练 bandit / policy network。
- 用 `ExperimentOrchestrator` 对比不同路由策略。

### 8.3 新的自编程方法
- 在 `SelfProgrammingEngine` 外面加一层：
  - 根据 Trace / ImmuneCase / Metrics，用 LLM / 代码生成器自动构建 `PatchRecord`。
  - 使用现有的测试 / 回滚 / 实验框架，避免破坏系统。

---

## 9. 安全与边界

- **Self-Programming 只能触碰 allowed_roots 下的文件：**
  - 默认是 `["mutable", "quentin/skills"]`。
- **安全内核（SafetyKernel）不可被修改：**
  - 仅通过公开方法读取 / 调整状态。
- **高风险域（如 Trading / Legal）：**
  - 推荐在业务 Adapter 层再加一层白名单、风险控制和人工 Gate。

---

本文件的目的，是让你在 **不破坏整体架构** 的前提下，  
可以方便地把你的研究成果（算法 / 策略 / 模型）挂进这个通用智能体系统。

**你可以把它当成一个「研究版操作系统」，需要什么模块，就在对应的“挂载点”里写你的代码。**