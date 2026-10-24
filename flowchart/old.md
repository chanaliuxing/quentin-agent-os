graph TD
    %% 定义样式
    classDef input fill:#f9f,stroke:#333,stroke-width:2px;
    classDef l1 fill:#e1f5fe,stroke:#0277bd,stroke-width:2px;
    classDef l2 fill:#ffebee,stroke:#c62828,stroke-width:2px;
    classDef l3 fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef store fill:#fff9c4,stroke:#fbc02d,stroke-width:2px,stroke-dasharray: 5 5;

    %% 输入节点
    User((👤 用户任务)):::input --> Runtime[🚀 AgentRuntime<br/>任务接入 & ID生成]

    %% ==========================================
    %% L1: 认知循环
    %% ==========================================
    subgraph L1_Cognitive ["⚡️ L1: 认知循环 (Cognitive Loop) - 实时思考"]
        direction TB
        Runtime --> MemoryRetrieval[🧠 MemoryFabric<br/>检索上下文 STS/MTS]:::l1
        MemoryRetrieval --> Router{🚦 ModelRouter<br/>选择模型}:::l1
        
        Router -->|简单任务| SpeedModel[⚡️ Speed Agent]:::l1
        Router -->|复杂任务| ExpertModel[🧠 Expert Agent]:::l1
        
        SpeedModel --> Planner[📝 Planner<br/>任务拆解]:::l1
        ExpertModel --> Planner
        
        Planner --> Executor[🛠️ Executor<br/>调用工具执行]:::l1
        Executor --> Critic{🧐 Critic<br/>结果反思}:::l1
        
        Critic -->|❌ 结果不好/报错| Retry[🔄 重试/调整计划]:::l1
        Retry --> Planner
        
        Critic -->|✅ 结果满意| Result((📤 最终结果)):::input
    end

    %% ==========================================
    %% 存储层
    %% ==========================================
    Executor -.->|📝 记录 Trace| TraceStore[(💾 Trace / KV Store)]:::store
    Critic -.->|📝 记录 Lessons| TraceStore
    
    %% ==========================================
    %% L2: 免疫循环
    %% ==========================================
    subgraph L2_Immune ["🛡️ L2: 免疫循环 (Immune Loop) - 实时风控"]
        direction TB
        Monitor[📡 Metric Monitor<br/>监控 Error/Cost/Latency]:::l2
        TraceStore -.-> Monitor
        
        Monitor --> Detector{🔍 AnomalyDetector<br/>异常检测}:::l2
        
        Detector -->|🚨 发现异常| Intervention[✋ ImmuneAction<br/>降级 / 熔断 / 回滚]:::l2
        Intervention -.->|⚡️ 强制干预| L1_Cognitive
        
        Detector -->|📂 归档| CaseStore[(🚑 ImmuneCase Store)]:::store
    end

    %% ==========================================
    %% L3: 进化循环
    %% ==========================================
    subgraph L3_Evolution ["🧬 L3: 进化循环 (Evolution Loop) - 夜间进化"]
        direction TB
        
        %% 1. 睡眠循环
        Sleep[😴 SleepLoop<br/>记忆巩固 & 遗忘]:::l3
        TraceStore --> Sleep
        Sleep -->|📥 沉淀| LongTermMem[(🧠 LTS 长期记忆)]:::store
        
        %% 2. 技能挖掘
        Miner[⛏️ SkillMiner<br/>从成功案例挖技能]:::l3
        TraceStore -->|✅ 成功Trace| Miner
        Miner -->|📦 生成| SkillCand[📝 Skill Candidate]:::l3
        SkillCand -.->|注册| ToolManager[🧰 Tool Manager]:::l1
        
        %% 3. 自编程
        SelfProg[🤖 SelfProgramming<br/>修复 Bug]:::l3
        CaseStore -->|❌ 失败/异常Case| SelfProg
        SelfProg -->|💻 生成 Patch| Sandbox[🧪 沙盒测试]:::l3
        Sandbox -->|✅ 测试通过| Codebase[💾 Codebase / Mutable]:::store
    end

    %% 连接关系
    LongTermMem -.-> MemoryRetrieval
    Codebase -.-> Executor