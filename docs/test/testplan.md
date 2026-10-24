这是一份**全系统集成测试计划（Master Test Plan）**，用于验证 Phase 1（Embedding）、Phase 2（SleepLoop）、Phase 3（SkillLoop）和 Phase 4（Knowledge Graph）是否已全部打通并能协同工作。

这份计划按**依赖顺序**排列，请一步步执行。

### 🧪 1. 验证 Phase 1 & 2：记忆与睡眠循环 (Memory & Sleep)

**目标**：验证“写入即向量化”和“睡眠聚类提炼”。

**测试步骤：**

1.  **运行验证脚本**
    使用之前创建的 `scripts/verify_phase2.py`。

    ```bash
    python scripts/verify_phase2.py
    ```

2.  **观察控制台输出**

      * ✅ **Embedding 成功**：不应报错 `Embedding failed`。
      * ✅ **聚类成功**：`generated_clusters` 应大于 0（例如 `1` 或 `2`）。
      * ✅ **MTS 生成**：`mts_created` 应大于 0。

3.  **检查数据库 (Postgres)**
    进入数据库验证数据落地：

    ```sql
    -- 1. 检查是否生成了 MTS 记录
    SELECT id, content, tier, vector_status FROM memories WHERE tier='mid_term' ORDER BY created_at DESC LIMIT 1;
    -- 预期: vector_status='generated' (Phase 1), content 是总结性文字 (Phase 2)

    -- 2. 检查 Phase 4 图谱同步是否触发 (自动写边)
    SELECT * FROM kg_edges WHERE edge_type='crystallized_from' ORDER BY created_at DESC LIMIT 1;
    -- 预期: 应该有一条边连接 MTS 和 原始 STS
    ```

-----

### 🧪 2. 验证 Phase 3：技能闭环 (Skill Loop)

**目标**：验证从“候选发现”到“代码落地”的全流程。

**测试步骤：**

1.  **准备测试数据**
    手动注入一条技能候选到 `data/skill_candidates.jsonl`：

    ```json
    {"candidate_id": "test_skill_001", "skill_name": "calc_fibonacci", "description": "Calculate the Nth Fibonacci number recursively.", "priority": 1, "metadata": {"domain": "math"}}
    ```

2.  **运行技能循环**

    ```bash
    python -m quentin.skills.skill_loop
    ```

3.  **观察执行过程**

      * 日志应显示：`Processing candidate: test_skill_001`
      * 日志应显示：`Delegating to EngineV2`
      * 日志最后应显示：`✅ Skill 'calc_fibonacci' registered successfully.`

4.  **检查产物**

      * **文件**：检查 `quentin/mutable/skills/calc_fibonacci.py` 是否存在，且内容包含斐波那契函数。
      * **注册表**：检查 `quentin/mutable/skills/registry.json` 是否包含 `calc_fibonacci` 条目。
      * **记忆**：检查数据库，确认是否有一条“Learned new skill”的 MTS 记忆。

-----

### 🧪 3. 验证 Phase 4：知识图谱 (Knowledge Graph)

**目标**：验证上述操作是否自动在图谱中留下了痕迹（Provenance）。

**测试步骤：**

1.  **查询技能来源**
    我们刚刚注册了 `calc_fibonacci`，现在去图谱里查它的来源。

    ```sql
    -- 查找 'calc_fibonacci' 节点
    SELECT node_id, title FROM kg_nodes WHERE node_type='skill' AND ref_id='calc_fibonacci';

    -- 查找连接到该技能的边 (应该是 produces_skill 类型)
    SELECT * FROM kg_edges 
    WHERE dst_node_id IN (SELECT node_id FROM kg_nodes WHERE ref_id='calc_fibonacci')
    AND edge_type='produces_skill';
    ```

      * ✅ **预期**：能找到一条从 `candidate` (test\_skill\_001) 指向 `skill` (calc\_fibonacci) 的边。

2.  **查询记忆溯源**
    回顾 Phase 2 生成的 MTS 记忆。

    ```sql
    -- 查找最近的 MTS 节点
    SELECT node_id, title FROM kg_nodes WHERE node_type='memory' ORDER BY created_at DESC LIMIT 1;

    -- 查找它的来源 (crystallized_from)
    SELECT * FROM kg_edges 
    WHERE src_node_id = (SELECT node_id FROM kg_nodes WHERE node_type='memory' ORDER BY created_at DESC LIMIT 1)
    AND edge_type='crystallized_from';
    ```

      * ✅ **预期**：能找到边指向原始的 STS 记录。

-----

### 🚨 故障排查指南 (Troubleshooting)

如果在上述测试中遇到问题，请按以下清单检查：

  * **问题 A：Phase 2 报错 "generated\_clusters: 0"**

      * **原因**：Embedding 没生效，导致向量为空，聚类器忽略了数据。
      * **修复**：检查 `Ollama` 是否运行；检查 `quentin/memory/fabric.py` 中 `remember_atomic` 是否真的调用了 `embedding_client`。

  * **问题 B：Phase 3 报错 "stdout is not a terminal"**

      * **原因**：`gemini_cli_backend.py` 没修好。
      * **修复**：手动修改 `meta_agent/tools/coder/gemini_cli_backend.py`，加入 `env={"NON_INTERACTIVE": "1", ...}`（参考上一轮对话的修复代码）。

  * **问题 C：Phase 3 卡在 "Engine execution failed"**

      * **原因**：LLM 生成代码失败或沙箱测试不通过。
      * **临时修复**：确认 `SkillLoop` 里是否有 Fallback 逻辑（生成 Stub 代码），或者多试几次简单的技能描述。

  * **问题 D：Phase 4 数据库无数据**

      * **原因**：`MemoryFabric` 或 `SkillRegistrar` 初始化时 `GraphService` 连接失败（静默失败）。
      * **修复**：检查启动日志中的 `WARNING: Graph schema init failed`，确认 Postgres 连接配置正确。

### ✅ 最终验收标准

当你能连续跑通：
`verify_phase2.py` (产出 MTS) **-\>** `skill_loop` (产出 Skill) **-\>** `SQL 查询` (查到图谱关系)

**恭喜你！你的 Meta-Agent 系统已经成功完成了从“感知”到“思考”再到“行动”和“记忆”的完整闭环。**