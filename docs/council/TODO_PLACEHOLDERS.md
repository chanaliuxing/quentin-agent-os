下面是我把 **Gemini 的评价 + 你当前代码现状** 融合后的「最终版 Placeholder Removal Plan（vFinal）」：目标是把 **Memory 从被动容器→主动认知系统**，并把 **Skill Mining 从开环→复用 Self-Programming Engine 闭环**，同时把 **Relation Inference 前移到 Consolidation 阶段**。

> 先说明一个事实：在这次对话里我能检索到的上传文件只有 `quentin/council/manager.py / reflection.py / done.py`。从代码看，CouncilManager 目前确实仍是单轮线性：问成员→聚合，且 decision_mode 只有 `first / arbiter_llm` 、聚合逻辑也只覆盖这两种模式 ；ReflectionCouncil 也确实依赖 `decision.final["answer"]` 结构化字段（action/new_plan/skill_ideas 等）。
> 所以下面计划会把 Council 当作“治理闸门”，但 Memory/Skill 那些文件如果你要我生成 **可直接应用的 Patch**，需要你把相关文件也发进当前对话（否则我只能给到接口+改动点清单）。所以下面只是改动点清单

---

## Placeholder Removal Plan vFinal（取长补短后的最终版）

### Guiding Principles（这版计划的硬约束）

1. **闭环优先**：任何“候选/日志/输出文件”都必须有后续自动处理链路（否则就是占位符）。
2. **可控收敛**：任何 LLM 参与的循环都必须有 `max_rounds / stall_detect / fallback`。
3. **Token 预算稳定**：历史上下文不堆砌，采用 Working Memory（摘要）+ 溯源 relations。
4. **复用现有强骨架**：Skill 闭环复用 Self-Programming Engine，不再维护两套“代码生成器”。

---

# Phase 0（治理层打底）：Council 升级为可多轮的 Moderator（可选但强烈建议）

你现在的 CouncilManager 还是一次性聚合 ，但后面 Phase 2/3 都需要“多轮澄清”的能力（否则总结、去重、技能生成会经常卡在半真半假）。

**交付物**

* `decision_mode: moderator_v2`（四态：approve/reject/revise/debate + working_memory + next_round_plan + stall）
* 让 ReflectionCouncil / DoneCouncil 继续沿用 `final.answer` 结构，不破坏现有调用方 、

**验收**

* debate 时能点名提问；stall / max_rounds 必定收敛为 revise（不死循环）。

---

# Phase 1（解决 A）：Embedding Injection（写入即向量化 + 查询即向量化）

**目标**：MemoryFabric 不再“甩锅”给调用方传 vector；`remember(content)` 就能被语义 recall 命中。

**实现要点**

* 新增 `EmbeddingService`（统一接口 + provider）

  * 本地 Ollama embedding + 云端 OpenAI embedding（可配）
* `MemoryFabric.remember_atomic`：

  * `if vector is None: vector = embed(content)`（失败可降级但要标记）
* `recall(query_text)`：

  * `embed(query_text)` 后再走向量检索（可选：混合检索 + RRF）

**验收（硬指标）**

* `remember_atomic(content="测试")` 后 DB vector 非空（或 vector_status=ok）
* `recall("测试")` 能在 topK 命中这条记忆

---

# Phase 2（解决 B + 前移 D）：Intelligent SleepLoop = Memory Editor（聚类→提炼→去重→关系）

> 这里我采纳 Gemini 的优化：**Relation Inference 不等 Phase 4，在 Consolidation 时就做**，尤其是 `crystallized_from` 这种关系，天然发生在 STS→MTS 的压缩过程。

**新流程（每次 sleep_run_once）**

1. **聚类（Clustering）**：从 STS 拉取候选（时间窗/usage/importance），按向量相似度分组
2. **提炼（Distillation）**：对每组调用 LLM Summarizer，生成一条 MTS “Insight”
3. **去重（Semantic Dedup）**：写 MTS 前先在 MTS 搜 top-k，相似度>阈值 → 走 merge（更新旧 MTS，而不是新增）
4. **关系推断（Relations）**：

   * 新 MTS 记录 relations：`crystallized_from: [sts_ids...]`
   * dedup merge 时追加 `refines/updates` 关系
   * 可选：为相似 MTS 建 `similar_to`

**治理闸门（强推荐复用 Council）**

* 引入 `consolidation` council：检查 summary 是否“压缩有效、无幻觉、可执行”
* debate 时可以定向问某个“严格成员”（比如 safety/accuracy）

**验收**

* 10 条重复 STS → ≤2 条 MTS
* 新 MTS 可追溯到来源 STS（relations 可查）
* MTS 规模随时间增长变慢（dedup merge 生效）

---

# Phase 3（解决 C）：Skill Mining 闭环（复用 Self-Programming Engine）

> 采纳 Gemini 的关键建议：别再写一套 SkillIngestor 的“代码生成器”，把 skill candidates **翻译成 ProgrammingTask**，直接丢给 `SelfProgrammingEngineV2` 做：生成→测试→治理→落地。

**闭环链路**

1. `SleepLoop / SkillsMiner` 产出 `skill_candidates`（可以继续 jsonl）
2. 新增 `SkillTaskBuilder`：

   * candidate → `ProgrammingTask`（包含：技能描述、I/O 示例、约束、允许依赖、禁区）
3. `SelfProgrammingEngineV2.run(task)`：

   * 生成代码 + 生成单测 + sandbox 测试 + patch proposal
4. **上线闸门**：

   * DoneCouncil 用来“是否可注册为正式技能”（is_done 映射逻辑你已有）
5. 成功后：

   * 写入 `mutable/skills/*.py`
   * 更新 registry
   * 生成一条 MTS 记忆并 relations 指向来源 trace（形成“技能来源可解释”）

**验收**

* 一条 candidate 能自动产出技能文件 + 单测通过 + registry 可调用
* 失败不会卡死：进入 ReflectionCouncil 让其给出“下一步/缺失技能”（你已有结构化解析）

---

# Phase 4（补齐 D 的剩余部分）：Graph API + 查询能力

Phase 2 已经把“最关键的 relations”前移做了；Phase 4 做“图谱可用性”。

**交付物**

* `get_neighbors(memory_id, depth)`
* `explain_link(a,b)`（可选，LLM 解释路径）
* 最小可视化/导出（json/graphml）

**验收**

* 能从某个 MTS 追溯到对应 STS/Trace；能从 Skill 追溯到来源候选与测试记录。

---

## 实施顺序（最小阻力路径）

1. Phase 1 Embedding（立刻让 recall 可用）
2. Phase 2 Consolidation（立刻让 MTS 不变垃圾堆 + 同时补 relations）
3. Phase 3 Skill（复用 engine，闭环价值最大）
4. Phase 4 Graph API（把 relations 变成可用能力）
   （Phase 0 Council 多轮：如果你已经在做，直接并行推进；否则建议先上）

---

## 你现在能立刻开始做的两件事

* **把 Memory 相关文件也上传到当前对话**（fabric.py / sleep_loop.py / store_postgres.py / skills/miner.py / self_programming/engine_v2.py），我就能按 Phase 1 给你出“可直接应用的 Patch（逐文件 diff）”。
* 或者你先不上传，我也可以先把 **Phase 1 的接口文件（embeddings.py）+ 调用点伪代码**按你项目风格写出来，但那会是“半自动落地”（你还得手动对接到现有实现）。

你想我先从 **Phase 1（Embedding Injection）** 开刀生成 patch，还是先把 **Phase 0（Council Moderator 多轮）** 做成你项目里的最终实现（因为它会给 Phase 2/3 提供治理能力）？
Phase0 我给你直接落地到 `quentin/council/manager.py`：把现在 **“一次问完→仲裁/first”** 的线性流程（`run_council` 只跑一轮）升级成 **Moderator 多轮讨论（带 working memory）**，但保持对现有 `arbiter_llm / first` 的完全兼容（默认不改你现有行为）。

## Phase0 目标

* 新增 `decision_mode = "moderator_v2"`：Moderator 负责 **多轮** 讨论、收敛、或发起下一轮“定向追问”
* working memory：用 `current_summary` 控制上下文，不把所有原文塞回 prompt（防 token 爆炸）
* 定向追问：Moderator 输出 `next_round_plan=[{target, question}]`，下一轮只问指定成员或 all
* 保护机制：`max_rounds` 上限 + `stall_patience` 卡住检测（open issues 不变就强制结束为 revise）

## 你现有代码为什么需要 Phase0

* 当前 `run_council` 会把同一个问题问所有成员，然后立刻 `_aggregate_decision` 出最终结论 —— **没有“讨论-追问-收敛”的回路**。
* 你的 `reflection.py` 明确假设 `decision.final["answer"]` 有结构化动作/新计划等字段，所以最终输出结构必须稳定。
* 成员输出目前要求严格 JSON（否则 parse_error），Moderator 也必须同样严格，否则会影响可控性。

## 我已经给你的改动产物（可直接替换/打补丁）

* [下载替换版 manager.py（含 Phase0）](sandbox:/mnt/data/manager_phase0.py)
* [下载 unified diff 补丁](sandbox:/mnt/data/manager_phase0_patch.diff)
* （可选）[下载 pytest 测试样例（模拟两轮 moderator 收敛 + 回归 arbiter_llm）](sandbox:/mnt/data/test_phase0_council_moderator.py)

## 你需要怎么接入（最短路径）

1. 用我给的 `manager_phase0.py` 覆盖你仓库里的 `quentin/council/manager.py`（或用 diff 打补丁）
2. 在你的 councils 配置里，把你想启用 Phase0 的 council 改成：

### YAML 示例

```yaml
- name: reflection
  decision_mode: moderator_v2
  max_rounds: 3
  stall_patience: 2
  summary_max_chars: 1800
  moderator:
    router_mode: balanced
    router_task_type: moderation
```

### JSON 示例

```json
{
  "name": "reflection",
  "decision_mode": "moderator_v2",
  "max_rounds": 3,
  "stall_patience": 2,
  "summary_max_chars": 1800,
  "moderator": { "router_mode": "balanced", "router_task_type": "moderation" }
}
```

> 不改 `decision_mode` 的 council 继续走你现在的逻辑（`arbiter_llm` 或 `first`），不会被影响。

## 测试计划（建议你按顺序跑）

1. **单元测试（无真实 LLM）**：用我给的 `test_phase0_council_moderator.py`，monkeypatch `call_llm`，验证：

   * round1 返回 debate + next_round_plan → round2 返回 approve
   * final 结构仍然有 `verdict / reasoning / answer`（保证 reflection 不炸）
2. **集成测试（真实 LLM）**：只对一个 council（建议 `reflection`）开启 `moderator_v2`，观察日志里 round 递增与 open_issues 收敛
3. **异常测试**：刻意让模型输出非 JSON，确认会自动重试/降级为 debate，然后不会卡死
