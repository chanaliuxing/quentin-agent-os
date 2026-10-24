# Config and Extend – Project Quentin

本篇介绍如何配置 `Project Quentin`，以及如何接入你自己的 `LLM` 或扩展新的领域适配器。

## 1. 配置系统 `quentin/config/settings.py`

`Project Quentin` 的全局配置集中在 `quentin/config/settings.py` 文件中，主要通过 `Settings` 类进行管理。你可以通过修改这个文件中的默认值，或在运行时传入自定义的 `Settings` 对象来控制系统行为。

### 主要配置项：

*   **`env`** (`EnvName`)：运行环境，可以是 `"sandbox"`、`"staging"` 或 `"production"`。这会影响 `SafetyKernel` 的行为，例如是否允许自编程。
*   **`llm`** (`LLMConfig`)：`LLM` 相关的配置。
    *   `provider`：指定使用的 `LLM` 服务提供商（`"dummy"`、`"ollama"`、`"openai"` 等）。
    *   `model`：默认使用的 `LLM` 模型名称。
    *   `extra`：用于传递给 `LLM` 客户端的额外参数，例如 `ollama` 的 `base_url`，或 `openai` 的 `api_key`。
*   **`memory`** (`MemoryConfig`)：`Memory Fabric` 的配置，包括 `STS/MTS/LTS` 记忆的衰减阈值、晋升阈值等。
*   **`budget`** (`BudgetConfig`)：实验和自编程的预算控制，例如每天允许运行的最大实验次数。

## 2. 如何接入你自己的 LLM 后端

仓库默认使用一个 `DummyLLMClient`，不连接任何真实 `LLM`。要让 `Project Quentin` 真正工作，你需要将它连接到你自己的 `LLM` 后端。

### 步骤：

1.  **实现 `LLMClient` 接口**：
    *   在 `quentin/infra/llm/` 目录下创建一个新的文件，例如 `openai_client.py` 或 `your_custom_client.py`。
    *   实现 `quentin/infra/llm/base.py` 中定义的 `LLMClient` 抽象类：
        ```python
        from quentin.infra.llm.base import LLMClient
        # ... 其他你需要的库，如 openai, httpx

        class MyCustomLLMClient(LLMClient):
            def __init__(self, model: str, api_key: str):
                self.model = model
                self.api_key = api_key
                self.name = f"my_custom:{model}"
                # ... 初始化你的 LLM SDK

            async def generate(self, messages, **kwargs) -> str:
                # ... 调用你的 LLM API，返回文本
                pass

            async def embed(self, texts, **kwargs) -> List[List[float]]:
                # ... 调用你的 embedding API，返回向量
                pass
        ```
2.  **在 `backend_call` 中集成**：
    *   打开 `quentin/runtime/agent_runtime.py`。
    *   在 `create_from_settings` 方法内部，找到 `backend_call` 异步函数。
    *   根据传入的 `model_name`，调用你实现的 `LLMClient` 或直接使用 `LLM SDK`。

    ```python
    # quentin/runtime/agent_runtime.py 片段
    # ...
    # 在 create_from_settings 内部
    
    # 示例：实例化你的 LLM 客户端
    my_openai_client = MyCustomLLMClient(model="gpt-4o", api_key=settings.llm.extra.get("openai_api_key"))
    
    async def backend_call(model_name: str, messages: List[Dict[str, Any]], extra_kwargs: Dict[str, Any]) -> str:
        # 根据 model_name 路由到不同的客户端
        if model_name.startswith("gpt"):
            return await my_openai_client.generate(messages, **extra_kwargs)
        elif model_name.startswith("ollama"):
            # ... 调用 Ollama 客户端
            pass
        # ... 其他客户端
        raise NotImplementedError(f"No backend for model: {model_name}")
    
    from quentin.routing.model_router import ModelRouter, ModelInfo

    router = ModelRouter(backend_call=backend_call)
    # ...
    ```
3.  **注册模型 `ModelConfig`**：
    *   使用 `router.register_model()` 注册你希望通过 `ModelRouter` 路由的模型。
    *   使用 `ModelInfo` 描述模型能力：`name`、`kind/provider`、`tags`（如 `fast`、`cheap`、`safe`）、`cost_per_1k_tokens`、`latency_hint_ms` 等。
    ```python
    router.register_model(
        ModelInfo(
            name="gpt-4o",
            kind="openai",
            tags=["fast", "safe", "code"],
            cost_per_1k_tokens=0.005,
            latency_hint_ms=800,
        )
    )
    ```

## 2.1 Embedding Provider 与回退

`Memory Fabric` 的 embedding 支持多 provider 与回退机制，均通过环境变量配置：

- `MEM_EMBED_PROVIDER`: `ollama` / `openai` / `gemini` / `disabled` / `fallback`
- `MEM_EMBED_FALLBACKS`: 逗号分隔优先级（例如 `openai,gemini,ollama,disabled`）
- `MEM_EMBED_MODEL`: 默认 embedding 模型名（用于 `ollama`）
- `MEM_EMBED_DIM`: 向量维度（默认 768）
- `MEM_EMBED_TIMEOUT` / `MEM_EMBED_RETRIES`

Provider 专属变量：

- OpenAI: `OPENAI_API_KEY`, `OPENAI_EMBED_MODEL`, `OPENAI_BASE_URL`, `OPENAI_EMBED_TIMEOUT`, `OPENAI_EMBED_RETRIES`
- Gemini: `GEMINI_API_KEY`, `GEMINI_EMBED_MODEL`, `GEMINI_BASE_URL`, `GEMINI_EMBED_TIMEOUT`, `GEMINI_EMBED_RETRIES`

当上游 provider 不可用时，会自动降级到下一个 provider，最终回退到 `disabled` 并返回空向量。

## 2.2 Session Delta Memory（增量 STS 写入）

用于长任务过程中把关键摘要写入 STS 的可选能力（默认关闭，prod 默认不启用）。

- `QUENTIN_SESSION_DELTAS`: `true/false` 启用开关
- `QUENTIN_SESSION_DELTAS_THROTTLE_SEC`: 最小写入间隔（默认 5 秒）
- `QUENTIN_SESSION_DELTAS_MIN_EVENTS`: 至少累计 N 次事件后写入（默认 1）
- `QUENTIN_SESSION_DELTAS_MAX_CHARS`: 每次写入最大字符数（默认 800）
- `QUENTIN_SESSION_DELTAS_ALLOW_PROD`: 允许在 prod 环境写入（默认 false）

## 2.3 Safety Feature Flags（默认保守）

- `QUENTIN_EXTERNAL_CONTENT_SHIELD`: 外部内容注入防护（默认 true）
- `QUENTIN_SKILL_MD_ENABLED`: 启用 SKILL.md SOP 插件（默认 false）
- `QUENTIN_SELFPROG_ISOLATED_WORKDIR`: 自编程临时工作区隔离（默认 false）
- `QUENTIN_INTERACTIVE_SHELL_ENABLED`: 交互式 shell 工具开关（默认 false）
- `QUENTIN_WAKE_ENABLED`: 允许 `qctl wake` 发送后台事件（默认 true）

## 3. 如何接入新的领域 `Domain`

`Project Quentin` 的设计是领域无关的，你可以轻松扩展新的领域，例如 `LegalBot`、`Trading`、`WebAutomation` 等。

### 步骤：

1.  **新建领域目录**：
    *   在 `quentin/domain/` 目录下为你的新领域创建一个子目录，例如 `quentin/domain/web_automation/`。
    *   在该目录下创建 `__init__.py` 和 `adapters.py`。
2.  **实现 `DomainAdapter`**：
    *   你的领域核心是实现 `quentin/domain/base.py` 中定义的 `DomainAdapter` 抽象类。
    *   `register_tools(tool_manager)`：在此方法中，注册你的领域特有的 `Tool` 或 `Skill`。例如，`WebAutomation` 领域可以注册 `click_element`、`fill_form` 等操作。
    *   `normalize_task(raw_task)`：将外部（例如 `CLI` 或 `API`）传入的原始任务描述，转换为 `Project Quentin` 内部的标准任务格式（包含 `task_id`、`domain`、`goal` 等）。
    ```python
    # quentin/domain/web_automation/adapters.py
    from quentin.domain.base import DomainAdapter
    # ... 导入你的领域工具
    
    class WebAutomationAdapter(DomainAdapter):
        name = "web_automation"
    
        def register_tools(self, tool_manager):
            # 注册领域特有工具
            tool_manager.register("CLICK_ELEMENT", my_web_tool.click_element)
            tool_manager.register("FILL_FORM", my_web_tool.fill_form)
    
        async def normalize_task(self, raw_task: Dict[str, Any]) -> Dict[str, Any]:
            # 将原始任务转换为标准任务
            return {
                "task_id": raw_task.get("task_id", "web-task"),
                "domain": "web_automation",
                "goal": raw_task["goal"],
                "meta": {"url": raw_task.get("url", "about:blank")},
            }
    ```
3.  **集成到 `Planner` / `Executor`**：
    *   根据你的领域特性，在 `quentin/cognitive/loop_impl.py`（Planner/Reflection 路径）或 `quentin/execution/skill_executor.py`（执行器路径）中添加逻辑，以便在 `task["domain"]` 匹配你的新领域时，调用你的领域适配器提供的功能。
    *   对于 `Planner`，你可以让它调用一个领域专用的规划器。
    *   对于 `Executor`，你需要确保 `ToolManager` 已经注册了你的工具。

4.  **配置 `MultiAgent` 的 `domain_model_policies` (可选)**：
    *   在 `Settings.llm.extra` 中，你可以为特定领域配置 `LLM` 模型白名单。例如，`"legal"` 领域可能只允许使用经过法律领域微调的 `LLM`。
    ```python
    # quentin/config/settings.py
    # ...
    @dataclass
    class LLMConfig:
        # ...
        extra: Dict[str, Any] = field(
            default_factory=lambda: {"domain_model_policies": {"legal": ["legal_llm_v2", "gpt-4o"]}}
        )
    ```
5.  **构建领域相关的 `EvalDataset` 和 `Variant` (可选)**：
    *   为了对你的新领域进行评测和实验，你可以创建领域特定的 `EvalDataset`。
    *   为你的领域规划策略创建 `VariantConfig`，并通过 `ExperimentOrchestrator` 进行 A/B 测试。

通过以上步骤，你就可以将 `Project Quentin` 扩展到任何你感兴趣的领域，并开始观察和研究它在该领域的自我进化。
