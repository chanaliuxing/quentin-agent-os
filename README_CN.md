# Project Quentin – Meta-Agent v3 (Research-Integrated Edition)

[English](README.md) | [简体中文](README_CN.md)

> **基线开源声明（12个月阶段性成果）**  
> 本代码库为历时 12 个月持续研发的基础架构基线开源版本。商用版本与深度生产环境迭代保留于独立私有仓库维护。本项目依据 MIT 协议开源。

> 一个可自我迭代、可持续学习、可自编程的 **通用智能体操作系统骨架**。  
> 你只需要：
> - 接入任意 LLM（本地 / 云端均可）
> -（可选）挂上你自己的领域工具（Desktop / Legal / Trading / ……）
>  
> 就可以开始做：**自我学习、自演化、自改代码** 的实验。

---

## ✨ 核心目标

本仓库实现的是《Meta-Agent 工程落地蓝皮书 v3》的工程骨架：

1. **通用性**  
   - 不绑定任何具体领域：Desktop / Legal / Trading / Research ……都只是 Domain。  
   - 不绑定任何具体 LLM：只需要实现一个统一的 `call_llm` 接口即可。

2. **自进化能力**（在安全边界内）  
   - 持续记忆：三层 MemoryFabric（STS/MTS/LTS）+ 巩固 / 衰减机制。  
   - 自编程：Self-Programming Engine + Patch 流水线（生成 → 测试 → 评估）。  
   - 技能进化：从 Trace → Episode → Skill Mining → Skill Library。

3. **研究友好**  
   - 所有核心闭环（认知 / 免疫 / 睡眠 / 演化）都有明确的输入 / 输出 / 指标。  
   - 自带 Observability API：一键接入 Grafana 或前端仪表盘。  
   - Research Layer 提供 ExperimentOrchestrator / EvolutionStrategy / Budget / Policy 骨架，方便替换论文里的算法，做 A/B 测试。

---

## 🏗 总体架构概览

四层逻辑 + 三环境 + 安全内核：

```mermaid
flowchart TD
    subgraph L3[ L3 Research & Evolution ]
      R1[Experiment Orchestrator]
      R2[Evolution Strategy Manager]
      R3[Budget Controller]
      R4[Policy Engine]
    end

    subgraph L2[ L2 Meta Layer ]
      M1[Self-Improvement Manager]
      M2[Eval Harness (接口)]
      M3[Multi-Agent Coordinator]
      M4[Log & Metrics Store]
    end

    subgraph L1[ L1 Base Layer ]
      B1[Cognitive Loop]
      B2[Planner]
      B3[Executor]
      B4[Critic]
      B5[Memory Fabric (STS/MTS/LTS)]
      B6[Skill Library & Skill Miner]
      B7[Sleep Loop]
      B8[Immune Loop]
      B9[Model Router]
      B10[Tool Manager]
    end

    subgraph L0[ L0 Infra & Kernel ]
      K1[Safety Kernel]
      K2[KVStore / DB / Vector Store]
      K3[Runtime (Docker / Local)]
    end

    R1 --> M1
    R2 --> M1
    M1 --> B6
    M1 --> B3
    B1 --> B4 --> B5
    B7 --> B5
    B7 --> B6
    B8 --> R1
    B9 --> M3
    B3 --> B10
    L1 --> L0
    L2 --> L1
    L3 --> L2
```

三种环境（逻辑概念）：

- **Sandbox**：所有自编程 / 实验 / 新算法 **必须** 从这里起步。
- **Staging**：通过评估的 patch / 技能在小流量下联机验证。
- **Production**：面向真实任务，严格受 SafetyKernel + PolicyEngine 控制。

⚠️ **安全内核（kernel）不可被自编程引擎修改。**

### Feature Flags（默认保守）

- `QUENTIN_EXTERNAL_CONTENT_SHIELD`: 外部内容注入防护（默认 true）
- `QUENTIN_SKILL_MD_ENABLED`: 启用 SKILL.md SOP 插件（默认 false）
- `QUENTIN_SELFPROG_ISOLATED_WORKDIR`: 自编程临时工作区隔离（默认 false）
- `QUENTIN_INTERACTIVE_SHELL_ENABLED`: 交互式 shell 工具开关（默认 false）
- `QUENTIN_WAKE_ENABLED`: 允许 `qctl wake` 发送后台事件（默认 true）

📂 **目录结构**
```text
quentin/
  cli/
    qctl.py                    # 命令行入口
  runtime/
    settings.py
    agent_runtime.py           # 所有模块的汇合点
  infra/
    logging.py                 # Tracer
    storage/
      kv_store.py              # KV 抽象
  kernel/
    safety.py                  # SafetyKernel
  memory/
    schemas.py                 # MemoryRecord / MemoryTier / MemoryKind
    fabric.py                  # MemoryFabric v1
  traces/
    schemas.py                 # TraceSpan / TraceEpisode
    episode_builder.py         # spans -> episodes
    episode_provider.py        # KVTraceEpisodeProvider
  cognitive/
    loop.py                    # CognitiveLoop（认知循环）
  immune/
    schemas.py
    loop.py                    # ImmuneLoop（免疫循环）
  sleep/
    loop.py                    # SleepLoop（记忆巩固 / 技能挖掘）
  skills/
    schemas.py
    library.py                 # SkillLibrary
    miner.py                   # SkillMiner
  models/
    router.py                  # ModelRouter v1
  agents/
    roles.py                   # Speed / Safety / Cost / Expert Agents
    coordinator.py             # MultiAgentCoordinator
  planning/
    planner.py                 # HierarchicalPlanner
  execution/
    executor.py                # Executor
  tools/
    manager.py                 # ToolManager
  critic/
    critic.py                  # Critic & Reflexion 接口
  self_programming/
    schemas.py
    engine.py                  # SelfProgrammingEngine（含 list_patches）
    manager.py                 # SelfImprovementManager
  research/
    experiment_schemas.py
    experiment_orchestrator.py # ExperimentOrchestrator
    evolution_strategy.py      # EvolutionStrategyManager
    budget.py                  # BudgetController
    policy.py                  # PolicyEngine
  observability/
    service.py                 # ObservabilityService
    api.py                     # FastAPI app ( /overview /models /memory ... )
docs/
  architecture.md              # 架构说明
README.md
```

## 🚀 快速开始

### 1. 安装依赖
建议使用 Python 3.10+ 和虚拟环境（venv / conda 均可）：
```bash
pip install -e .
```

### 2. 基本检查：metrics-overview
```bash
qctl metrics-overview
```
预期输出（示意）：
```json
{
  "timestamp": "2026-03-01T08:00:00",
  "model": { "models": {...}, "total_calls": 0 },
  "memory": { "tiers": {"STS": 0, "MTS": 0, "LTS": 0}, "total": 0 },
  "immune": { "cases": 0, ... },
  "patches": { "patches": 0, ... },
  "experiments": { "experiments": 0, ... },
  "skills": { "skills": 0, ... },
  "sleep": { "episodes": 0, ... }
}
```

### 3. 启动观测 API
```bash
qctl serve-observability --host 0.0.0.0 --port 8000
```
浏览器访问：
- `http://localhost:8000/health`
- `http://localhost:8000/overview`
- `http://localhost:8000/models`

可以在 Grafana 中直接把 `http://localhost:8000/overview` 配成 JSON Datasource 构建监控看板。

---

## 🔌 接入自定义 LLM

当前骨架对 LLM 完全解耦，实现统一调用接口即可：

1. **ModelRouter**：注册模型元数据与计费/延迟信息
2. **BaseRoleAgent.run**：对接真实 LLM 客户端（Ollama / vLLM / OpenAI / Anthropic）
3. **Planner / Critic / SelfProgrammingEngine**：按需调用对应模型角色

---

## 🧠 四大闭环协同机制

1. **认知循环（Cognitive Loop）**：任务拆解 → 规划 → 执行 → 批判性复盘 → 结构化回写 Trace 与 MemoryFabric。
2. **免疫循环（Immune Loop）**：实时监测异常与指标退化，触发降级熔断并捕获 ImmuneCase。
3. **睡眠循环（Sleep Loop）**：离线聚合 Episode，运行 SkillMiner 抽取稳定技能，执行 STS → MTS → LTS 巩固与遗忘。
4. **自编程演化循环（Self-Programming Loop）**：在隔离沙箱中生成 Patch Proposal，跑通单元测试与回归套件后提交评审。

---

## 🔐 安全与边界

1. **SafetyKernel 强约束**：受保护核心模块只读，仅允许 `/mutable/` 目录下授权模块由自编程引擎演化。
2. **PolicyEngine 环境门禁**：Production 环境严格禁止无人工审核的自动补丁热加载。
3. **可审计性**：全链路保留不可篡改 Trace 记录与回滚能力。

---

## 📄 开源许可

本项目依据 [MIT 许可证](LICENSE) 分发。  
Copyright (c) 2026 Wei Zhang
