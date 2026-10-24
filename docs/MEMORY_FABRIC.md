# Memory Fabric – Project Quentin

本篇解释系统中的可持续记忆系统 `Memory Fabric`。

## 1. 三层记忆（STS / MTS / LTS）

`Memory Fabric` 将记忆分为三个层级，以平衡记忆的容量、访问速度和持久性：

*   **STS (Short-Term Store)**：
    *   **特点**：会话级、任务级上下文。存储短期、瞬时信息。
    *   **生命周期**：分钟到小时级别。更新频率高，衰减速度快。
    *   **作用**：保持当前任务的上下文相关性，支持快速反应。

*   **MTS (Mid-Term Store)**：
    *   **特点**：项目级、版本级记忆。存储在多个任务中被重复使用或验证有效的信息。
    *   **生命周期**：天到周级别。更新频率中等，衰减速度慢于 STS。
    *   **作用**：支持跨任务的知识复用和经验积累。

*   **LTS (Long-Term Store)**：
    *   **特点**：跨项目、跨版本稳定知识。存储核心技能、通用原理和经过验证的长期经验。
    *   **生命周期**：周到年级别。更新频率低，基本不自动衰减或删除。
    *   **作用**：构成智能体“世界观”和“核心能力”的基石。

## 2. 记忆条目 `MemoryRecord`

每个记忆条目 `MemoryRecord` 包含以下关键信息：

*   `memory_id`：唯一标识符。
*   `tier`：当前所在记忆层（STS, MTS, LTS）。
*   `content`：记忆的实际内容，可以是文本、结构化数据等。
*   `metadata`：包含 `domain`、`tags`、`relations` 等额外信息。
*   `created_at`：记忆创建时间。
*   `last_access_at`：最后访问时间，用于评估活跃度。
*   `access_count`：访问次数，用于评估重要性。
*   `strength`：记忆的“强度”或“置信度”，在 0.0 到 1.0 之间。
*   `update_policy`：定义该记忆的升级 (`promotion_rule`) 和衰减 (`decay_rule`) 策略。

## 3. 记忆策略 `MemoryPolicyEngine`

`MemoryPolicyEngine` 是 Memory Fabric 的“大脑”，它根据 `MemoryRecord` 的 `update_policy` 和 `MemoryPolicyConfig` 来决定记忆的生命周期。

### 3.1 默认阈值配置 `MemoryPolicyConfig`

通过 `MemoryPolicyConfig` 可以灵活配置记忆升级和衰减的阈值：

*   `sts_to_mts_hits`：STS 记忆升级到 MTS 所需的最低访问次数。
*   `sts_to_mts_age_minutes`：STS 记忆升级到 MTS 所需的最低存活时间。
*   `mts_to_lts_hits`：MTS 记忆升级到 LTS 所需的最低访问次数。
*   `mts_to_lts_age_days`：MTS 记忆升级到 LTS 所需的最低存活天数。
*   `sts_ttl_minutes`：STS 记忆的存活时间，超过此时间可能被衰减。
*   `mts_ttl_days`：MTS 记忆的存活天数，超过此时间可能被衰减。

### 3.2 策略规则

内置的简单策略规则：

*   **`default_promotion_v1`**：
    *   STS → MTS：满足最低访问次数 (`sts_to_mts_hits`) 和存活时间 (`sts_to_mts_age_minutes`)。
    *   MTS → LTS：满足最低访问次数 (`mts_to_lts_hits`) 和存活天数 (`mts_to_lts_age_days`)，并且 `strength` 达到 0.5。
*   **`default_decay_v1`**：
    *   STS：如果 `last_access_at` 超过 `sts_ttl_minutes`，则标记为衰减。
    *   MTS：如果 `last_access_at` 超过 `mts_ttl_days`，则标记为衰减。
    *   LTS：默认不自动衰减（核心知识）。

## 4. 记忆巩固循环 `run_consolidation()`

`SleepLoop` 会定期（例如每晚 `nightly` 或每周 `weekly`）调用 `MemoryFabric.run_consolidation()`。这个过程会：

1.  遍历 Memory Fabric 中的记忆条目。
2.  根据每条记忆的 `update_policy` 和 `MemoryPolicyEngine` 的决策，进行：
    *   **Promotion (升级)**：将活跃且重要的记忆从低层级提升到高层级（例如 STS → MTS）。
    *   **Decay / Forgetting (衰减 / 遗忘)**：将长时间未访问或不重要的记忆从 STS / MTS 中删除。

## 5. CLI 观测与控制

你可以使用命令行工具 `qctl` 来观测 `Memory Fabric` 的状态和手动触发巩固过程：

*   **`qctl memory-stats`**：查看当前各层级记忆的数量分布。
*   **`qctl memory-consolidate --batch nightly`**：手动触发一次“夜间”记忆巩固任务。

## 6. 研究扩展点

`MemoryPolicyConfig` 和 `MemoryPolicyEngine` 的设计是高度可扩展的。研究者可以：

*   **创建新的 `promotion_rule` 或 `decay_rule`**：例如，基于记忆内容相似度、任务回报等更复杂的策略。
*   **将不同 `MemoryPolicyConfig` 作为 `VariantConfig` 注册**：通过 `ExperimentOrchestrator` 对不同的记忆策略进行 A/B 测试，对比它们对智能体长期性能的影响。
*   **利用 `quentin/research/memory_policy_runner.py` 作为 EvalHarness 的 runner**：评估不同记忆策略在模拟环境中的表现。
