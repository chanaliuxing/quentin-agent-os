这是一个针对 **`quentin/runtime/agent_runtime.py`** 和 **`quentin/self_programming/engine.old.py`** 这两个“风险文件”的详细重构与落地（Refactoring & Implementation）方案。

我们的目标是将它们从“原型/单体代码”转变为“工程化/模块化”的架构，以支撑系统长期的自我迭代。

-----

### 文件一：`quentin/runtime/agent_runtime.py` (解耦方案)

**核心问题**：
该文件目前是“依赖地狱”。它在 `create_from_settings` 方法中硬编码初始化了 L0 到 L3 的所有组件。这导致任何底层组件（如 `SkillMiner` 或 `MemoryFabric`）的构造函数变更都会波及此文件，且极难进行单元测试。

**落地目标**：引入 **依赖注入 (Dependency Injection)** 和 **构建者模式 (Builder Pattern)**。

#### ✅ 执行步骤

1.  **引入轻量级 DI 容器**
    不要让 `AgentRuntime` 自己 `new` 对象。创建一个 `quentin/bootstrap/container.py` 来管理单例和依赖。

    ```python
    # quentin/bootstrap/container.py
    from dependency_injector import containers, providers
    from quentin.kernel.safety_kernel import SafetyKernel
    from quentin.memory.fabric import MemoryFabric
    # ... imports

    class Container(containers.DeclarativeContainer):
        config = providers.Configuration()

        # L0 Infra
        kv_store = providers.Singleton(KVStore)
        tracer = providers.Singleton(Tracer)
        
        # L0 Kernel
        safety_kernel = providers.Singleton(
            SafetyKernel, 
            kv=kv_store, 
            tracer=tracer
        )

        # L1 Base
        memory_fabric = providers.Singleton(MemoryFabric)
        
        # ... 更多组件定义
    ```

2.  **重构 `AgentRuntime` 为纯粹的协调者**
    `AgentRuntime` 不应再负责对象的创建，只负责持有和调度。

    ```python
    # quentin/runtime/agent_runtime.py (Refactored)
    @dataclass
    class AgentRuntime:
        # 只声明接口，不关心实现
        cognitive_loop: CognitiveLoop
        immune_loop: ImmuneLoop
        # ...

        def start(self):
            """启动所有守护进程/循环"""
            self.cognitive_loop.start_background()
            self.immune_loop.start_background()
    ```

3.  **拆分 L3 层（Evolution）**
    目前 `AgentRuntime` 混合了“代理运行（L1/L2）”和“代理进化（L3）”。建议将 L3 剥离，由更上层的 `EvolutionaryOrchestrator` 持有 `AgentRuntime`，而不是反过来。

      * **落地动作**: 在 `AgentRuntime` 中移除 `research_manager`, `evolution_strategy` 等 L3 组件。它们应该在 `meta_agent/evolution/orchestrator.py` 中被管理。

-----

### 文件二：`quentin/self_programming/engine.old.py` (拆解方案)

**核心问题**：
这是一个典型的“上帝类 (God Class)”。它混合了 **KV存储** (`_save_patch`)、**安全校验** (`_ensure_allowed_path`)、**语法检查** (`_syntax_check`) 和 **业务流程** (`apply_patch`)。
虽然被标记为 `.old`，但其中包含的“安全路径检查”和“回滚机制”是 V2 版本缺失的关键逻辑，必须迁移并拆解。

**落地目标**：将功能拆散到单一职责的类中，彻底废弃 `.old` 文件，强化 `meta_agent/self_programming/engine_v2.py`。

#### ✅ 执行步骤

1.  **提取安全守卫 (Security Guard)**
    将 `.old` 文件中的 `_ensure_allowed_path` 逻辑迁移到一个独立的安全服务中。

      * **新文件**: `quentin/kernel/path_guard.py`
      * **功能**: 专门负责校验路径是否在 `mutable/` 白名单内，防止路径遍历攻击。
      * **代码迁移来源**: 中的 `_ensure_allowed_path` 方法。

2.  **提取沙箱运行器 (Sandbox/Test Runner)**
    将 `.old` 文件中的 `_syntax_check` 升级为更强大的测试运行器。

      * **新文件**: `meta_agent/self_programming/sandbox.py`
      * **功能**:
          * 接收代码字符串。
          * 在一个临时目录 (`tempfile`) 中写入。
          * 运行 `py_compile` (来自 `.old` 的逻辑) 和 `pytest` (新增逻辑)。
      * **代码迁移来源**: 中的 `_syntax_check` 方法。

3.  **提取补丁仓库 (Patch Repository)**
    将 `.old` 中直接操作 `kv` 的逻辑封装起来。

      * **新文件**: `meta_agent/patches/store.py`
      * **功能**: `save_patch(record)`, `get_patch(id)`, `list_patches()`.
      * **代码迁移来源**: 中的 `_save_patch` 和 `list_patches`。

4.  **强化应用与回滚 (Applier & Rollback)**
    将 `.old` 中非常宝贵的“备份与回滚”逻辑迁移到 V2 的 `SafePatchApplier` 中。

      * **目标文件**: `meta_agent/patches/safe_applier.py`
      * **新增逻辑**:
          * 在 `apply_patch` 之前，强制执行 `backup_path = target.with_suffix(".bak")`。
          * 新增 `rollback(patch_id)` 方法，读取 `.bak` 文件覆盖回去。
      * **代码迁移来源**: 中的 `apply_patch` (备份部分) 和 `rollback_patch`。

5.  **最终形态：Engine V3**
    当上述组件拆分完毕后，`SelfProgrammingEngine` (在 `engine_v2.py` 或 `engine.py` 中) 将变得非常干净：

    ```python
    class SelfProgrammingEngine:
        def __init__(self, guard, store, sandbox, applier):
            self.guard = guard
            self.store = store
            self.sandbox = sandbox
            self.applier = applier

        async def run(self, gap):
            # 1. Generate Code (LLM)
            code = await self.llm.gen(gap)
            
            # 2. Security Check (PathGuard)
            if not self.guard.is_safe(gap.files): return

            # 3. Sandbox Verify (Sandbox)
            if not self.sandbox.verify(code): return

            # 4. Apply with Backup (Applier)
            self.applier.apply(code, backup=True)
            
            # 5. Persist Record (Store)
            self.store.save(gap, code)
    ```

### 总结

您不需要重写整个系统，只需要做**两次外科手术**：

1.  **对 `AgentRuntime` 做“吸脂手术”**：把所有依赖创建逻辑抽离到 DI 容器，把 L3 逻辑抽离到上层。
2.  **对 `engine.old.py` 做“器官移植手术”**：把它的安全、存储、回滚逻辑分别移植到新的独立模块中，然后删除尸体。

完成这两步，您的代码库将从“Demo 级”跃升为“Production Ready 级”。