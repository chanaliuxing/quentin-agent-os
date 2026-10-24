graph TD
    %% =======================
    %% 样式定义
    %% =======================
    classDef l3 fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef l2 fill:#fff3e0,stroke:#ef6c00,stroke-width:2px;
    classDef l1 fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef l0 fill:#eceff1,stroke:#455a64,stroke-width:2px,stroke-dasharray: 5 5;
    classDef user fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px;
    classDef memory fill:#fff9c4,stroke:#fbc02d,stroke-width:2px;
    
    %% =======================
    %% L3: 研究与演化层 (The Brain / Scientist)
    %% =======================
    subgraph L3_Research [🧬 L3: Research & Evolution Layer - 进化策略]
        direction TB
        ExpOrch[⚗️ Experiment Orchestrator<br/>实验编排]:::l3
        EvoMgr[📈 Evolution Strategy Manager<br/>进化决策]:::l3
        Budget[💰 Budget & Cost Controller]:::l3
        Governance[⚖️ Policy & Governance<br/>宪法与合规]:::l3
        
        EvoMgr -->|1. 发起实验| ExpOrch
        ExpOrch -->|2. 分配资源| Budget
        Governance -.->|约束| EvoMgr
    end

    %% =======================
    %% L2: Meta 层 (The Immune System / Manager)
    %% =======================
    subgraph L2_Meta [🛡️ L2: Meta Layer - 评估与监控]
        direction TB
        SelfImp[🔧 Self-Improvement Manager<br/>自改总调度]:::l2
        Immune[🚑 Immune System<br/>异常检测 & 止损]:::l2
        EvalHarness[📏 Eval Harness<br/>评测与打分]:::l2
        MultiAgent[🤝 Multi-Agent Coordinator<br/>多智能体协调]:::l2
        
        Immune -->|提交 ImmuneCase| SelfImp
        SelfImp -->|请求优化| EvoMgr
        EvoMgr -->|下发 Patch 任务| SelfImp
    end

    %% =======================
    %% L1: 执行层 (The Body / Worker)
    %% =======================
    subgraph L1_Base [⚡️ L1: Base Layer - 认知与执行]
        direction TB
        Router[🚦 Task Router]:::l1
        Planner[📝 Planner]:::l1
        Executor[🛠️ Executor]:::l1
        Critic[🧐 Critic]:::l1
        ModelRouter[🧠 Model Router]:::l1
        
        User((👤 User Task)):::user --> Router
        Router --> Planner
        Planner -->|Plan| Executor
        Executor -->|Result| Critic
        Critic -->|Feedback| Planner
        
        %% 链接外部模型
        Planner -.-> ModelRouter
        Executor -.-> ModelRouter
    end

    %% =======================
    %% 记忆与数据 (Shared Fabric)
    %% =======================
    subgraph Memory_System [🧠 Memory Fabric & Storage]
        STS[📝 Short-Term Store]:::memory
        MTS[🗂️ Mid-Term Store]:::memory
        LTS[📚 Long-Term Store]:::memory
        TraceDB[(💾 Trace / Metrics Store)]:::memory
        
        STS -->|Sleep Loop 巩固| MTS
        MTS -->|复用沉淀| LTS
    end

    %% =======================
    %% L0: 基础设施 (The Kernel)
    %% =======================
    subgraph L0_Infra [🧱 L0: Infra & Kernel Layer]
        Safety[🔒 Safety Kernel<br/>权限/回滚/风控]:::l0
        Storage[☁️ Vector/KV Storage]:::l0
        Runtime[⚙️ Docker/K8s Runtime]:::l0
    end

    %% =======================
    %% 核心循环连接 (The Loops)
    %% =======================
    
    %% 1. Cognitive Loop (认知循环)
    Critic -->|写 Trace| TraceDB
    Executor -->|写 Trace| TraceDB
    L1_Base -.->|读写| STS
    
    %% 2. Immune Loop (免疫循环)
    TraceDB -->|监控指标| Immune
    Immune -.->|❌ 熔断/降级| Router
    
    %% 3. Sleep Loop (睡眠循环)
    TraceDB -->|夜间整理| STS
    
    %% 4. Skill & Code Evolution (进化循环)
    SelfImp -->|🔍 挖掘 Skill| TraceDB
    SelfImp -->|💻 生成 Patch| Runtime
    Runtime -->|✅ 测试通过| Executor
    
    %% 安全拦截
    L3_Research -.->|所有变更必经| Safety
    L2_Meta -.->|所有动作必经| Safety