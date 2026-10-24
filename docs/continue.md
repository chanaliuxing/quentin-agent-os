这是一个针对 **Project Quentin** 从当前的“架构原型”向“实战落地”演进的详细执行计划。

目前的系统是一个非常漂亮的**骨架**，但缺乏**肌肉**（真实的上下文检索）和**大脑**（真实的决策治理）。

以下计划分为 **5 个阶段（Sprints）**，按优先级排序。核心目标是**消灭 Mock（占位符），引入真实的 LLM 闭环**。

-----

### 阶段一：重塑“治理委员会” (Governance & Safety First)

**目标**：确保系统产生的任何代码 Patch 都要经过真实的 LLM 审查，而不是默认返回 `True`。这是防止系统“自毁”的第一道防线。

  * **涉及文件**: `meta_agent/self_programming/engine_v2.py`, `quentin/governance/patch_council.py`

#### 📋 Todo List:

  - [x] **接入强力 LLM 作为 Critic（可选）**:
      - 当前实现支持通过 env/provider 配置更强模型用于 review；默认路径仍可离线跑通（避免强依赖外部 key）。
      - 生产环境启用时需配置 provider 与 key（不在仓库中硬编码）。
  - [x] **实装 `PatchGovernanceCouncil.decide_on_patch`**:
      - [x] **输入构建**: Prompt 包含 `PatchProposal`、评测/报告、系统快照（见 `meta_agent/self_programming/engine_v2.py`）。
      - [x] **Prompt 设计**: 输出结构化 JSON（should_apply/risk_level/reason）。
      - [x] **拒绝机制**: council 异常时 fail-safe 默认拒绝。
  - [x] **实现 `SafePatchApplier` 的白名单检查**:
      - [x] 仅允许修改 PathGuard 允许的目标路径 + auto-updatable 文件（见 `meta_agent/patches/safe_applier.py`）。
      - [x] SafetyKernel 审批 `code_patch`（non-bypass guard）。

**✅ 阶段验收标准**: 手动构造一个包含恶意代码（如 `os.system('rm -rf /')`）的 Patch，Governance Council 能够自动识别并拒绝。

-----

### 阶段二：构建“上下文感知” (Context Awareness / RAG)

**目标**：解决 AI “盲写”代码的问题。AI 需要知道现有的工具库里有什么，才能复用代码而不是重复造轮子。

  * **涉及文件**: `meta_agent/self_programming/engine_v2.py`, `meta_agent/memory/store_vector.py`

#### 📋 Todo List:

  - [x] **搭建代码库索引 (Codebase Indexing)**:
      - [x] 引入 `ChromaDB`（见 `pyproject.toml`）。
      - [x] 脚本 `scripts/index_codebase.py`：扫描 `quentin/` 下所有 `.py` 文件。
      - [x] **Chunking 策略**: 按 `Class`/`Function`/`Method` 切片，保留 Docstring（见 `quentin/retrieval/codebase_index.py`）。
  - [x] **实装 `_build_skill_context_for_gap`**:
      - [x] Gap description → vector search Top-5（见 `meta_agent/self_programming/engine_v2.py`）。
      - [x] 将签名 + docstring 注入到 coder instructions。
  - [x] **实装 `_guess_target_file_for_gap`**:
      - [x] LLM + 文件树提示（见 `meta_agent/self_programming/engine_v2.py`）。

**✅ 阶段验收标准**: 提一个需求“增加一个计算斐波那契数列的工具”，系统能检索到如果已存在类似的数学工具库，会建议复用或在该文件中扩展，而不是在随机位置新建文件。

-----

### 阶段三：测试驱动开发 (TDD) 闭环

**目标**：目前的测试主要依赖静态检查，这远远不够。必须实现“先写测试，再改代码”或“同时生成测试”。

  * **涉及文件**: `meta_agent/self_programming/test_runner.py`, `meta_agent/tools/coder/router.py`

#### 📋 Todo List:

  - [x] **升级 `CodeGenerationRequest`**:
      - 要求 LLM 返回 JSON 格式，包含两个字段：`implementation_code` 和 `verification_test_code` (pytest 格式)。
  - [x] **构建临时测试沙箱 (Sandbox)**:
      - [x] 利用 `tempfile`（见 `meta_agent/self_programming/test_runner.py`）。
      - [x] 流程：
        1.  创建临时目录。
        2.  复制项目代码。
        3.  写入 `implementation_code`。
        4.  写入 `verification_test_code` 到 `tests/temp_test.py`。
        5.  运行 `pytest tests/temp_test.py`。
  - [x] **反馈循环 (Refinement Loop)**:
      - [x] 测试失败时将 stdout/stderr 作为反馈回灌，并重试（`max_retries`，见 `meta_agent/self_programming/engine_v2.py`）。

**✅ 阶段验收标准**: 即使 AI 写出的代码有一处语法错误，它能在沙箱中运行失败，并自动在下一次尝试中修正该错误，最终通过测试。

-----

### 阶段四：蓝图与现实的对齐 (Blueprint Alignment)

**目标**：让 `blueprint.md` 不仅仅是文档，而是系统的“配置文件”。

  * **涉及文件**: `meta_agent/blueprint/gap_tracker.py`, `meta_agent/blueprint/improver.py`

#### 📋 Todo List:

  - [x] **结构化蓝图解析**:
      - [x] `blueprint.md` → machine spec：`quentin/blueprint/spec.py`（可加载 JSON spec 或从 markdown 解析）。
  - [x] **实现 Blueprint Gap Tracker**:
      - [x] `qctl blueprint-scan` + spec 驱动：`quentin/blueprint/tracker.py`
      - [x] 离线证据发射：`quentin/blueprint/evidence_emitter.py`
  - [x] **自动回写蓝图 (Reality Check)（保守策略）**:
      - [x] 当前默认不自动修改 `blueprint.md` 主线；通过 spec + TODO 文档驱动演化，避免“文档自写自证”的漂移风险。

**✅ 阶段验收标准**: 修改 `blueprint.md`，增加一行“系统需要一个用于处理 CSV 文件的 Skill”。运行 `gap_tracker`，系统能自动识别出这个新需求，并生成一个 `PatchProposal`。

-----

### 阶段五：实战演练 (End-to-End Demo)

**目标**：在一个受控环境下跑通全流程。

#### 📋 演练剧本 (Runbook):

1.  **启动观测台**: 运行 `python scripts/run_orchestrator_daemon.py`。
2.  **注入人工 Gap**: 在 `data/blueprint/gaps.json` 中手动写入一个简单的任务：
    ```json
    {
      "id": "gap_001",
      "title": "Missing String Utility",
      "description": "The system lacks a utility to convert snake_case to camelCase.",
      "priority": "low"
    }
    ```
3.  **触发自编程**: 运行 `python scripts/run_self_programming_cycle_v2.py`。
4.  **监控日志**: 观察 `logs/self_programming_engine_v2.jsonl`。
      * 看它是否检索到了 `quentin/utils/` (Context)。
      * 看它生成的代码是否包含了 Test Case (TDD)。
      * 看 Governance Council 是否给出了评分 (Safety)。
5.  **验证结果**: 检查 `quentin/mutable/utils/string_ops.py` 是否出现，且测试通过。

### 总结与建议

不要试图一次性把所有功能都做完。目前的系统最缺的是\*\*“真实的反馈”\*\*。

**建议立刻着手做的是**：
把 `PatchGovernanceCouncil` 里的 `return True` 删掉，换成一个哪怕是最简单的 `Prompt` 调用：“这段代码看起来安全吗？回答 Yes/No”。

这是让 Quentin 从“玩具”变成“工具”的第一步。
