# Blueprint v3：剩余差距与下一步行动（代码对照）

Date: 2026-02-07

目的：
- 将“蓝皮书（`blueprint.md`）/工程目标”与“代码库现实”之间仍然存在的差距，整理成**可执行 TODO**。
- 避免把“工具能跑/脚本能跑”误认为“研究闭环真正可依赖”。

参考：
- Checklist：`docs/TODO_BLUEPRINT_V3_CHECKLIST.md`
- Placeholder report：`docs/BLUEPRINT_V3_CODEBASE_GAP_AND_PLACEHOLDER_REPORT.md`
- Machine spec（追踪用）：`blueprint/spec_v3.json`、`blueprint/meta_agent_v3_spec.json`

---

## 已在本轮修复（重要的工程/工具稳定性）

- `meta_agent/self_programming/tools/cli_wrapper.py`
  - 修复：`ExternalCLITool.generate_tests()` 不再抛 `NotImplementedError`，默认生成 deterministic smoke tests。
- `quentin/cli/qctl.py` + `quentin/blueprint/auto_patcher.py`
  - 修复：`blueprint-scan`/`blueprint-item` 使用 `quentin/blueprint/tracker.py`（而非 legacy gap tracker）。
  - 升级：`blueprint-autopatch` 支持 `--run-selfprog`（默认 dry-run，不自动改代码）。
- `meta_agent/self_programming/auditing/ast_index.py` + `scripts/save_storage_state.py`
  - 修复：evidence audit 的 `SyntaxWarning: invalid escape sequence '\\ '`（AST parse 传 filename；修正文档字符串里的反斜杠空格）。
- `blueprint/spec_v3.json`
  - 修复：模块 hints 更新到 canonical 路径（消除“删除文件导致一直 missing”的噪声）。
- `quentin/l3/research/experiments.py`
  - 修复：`ResearchManager.get_task_level_stats()` 从空实现升级为 file-backed 统计（给 L2/L3 做决策提供最小信号）。

---

## 仍建议继续落地的差距（按影响优先级排序）

### 1) Blueprint v3 “可观测证据”更强：trace / experiment 信号需标准化

现状：
- `blueprint/spec_v3.json` 的 `trace_capability_id`/`experiment_capability` 是“工程雷达图”用的 hints，但不同 trace/experiment 系统的 schema 不完全一致。
- `quentin/blueprint/tracker.py` 当前对 trace/exps 做的是 best-effort heuristics（能用，但不够 load-bearing）。

建议 TODO：
- [x] 为关键组件（L0/L1/L2/L3）定义 `TraceEventType + payload.schema` 的稳定约定（每个 capability 至少 1 条可判定信号）。
- [x] 为 ResearchInterfaceV3/ExperimentOrchestrator 增加“capability 标签”字段，确保 `tracker` 可以严谨判定 `has_experiments=True`。
- [x] 为 `blueprint/spec_v3.json` 补充 `hints.trace_signals`（允许多个 signal，替代纯 substring 匹配）。
  - 现状：`qctl blueprint-scan --emit-evidence` 可在离线模式下将 spec_v3 10/10 变为全绿（score=1.00）。

### 2) Blueprint->Patch 自动化：自编程跑通与安全边界更强

现状：
- `blueprint-autopatch` 默认 dry-run，`--run-selfprog` 会触发 `SelfProgrammingEngineV2`（可能依赖外部 coder backend/LLM）。
- “生成 patch -> 评估 -> 决策 ->（可选）应用”的链路已具备，但还需要更强的离线验证与回归基线。

建议 TODO：
- [x] 为 `SelfProgrammingEngineV2` 增加“离线/无 LLM”模式的 deterministic coder backend（用于 CI/本地 smoke）。
- [x] 为 patch report 增加最小 benchmark：`pytest` 通过率 +（可选）关键脚本退出码 + 关键指标回归阈值。
  - 现状：集成测试覆盖 `tests/integration/test_evolution_feedback_loop_runs.py` + `tests/integration/test_blueprint_scan_can_be_made_green.py`。

### 3) L3->L2->L1 闭环“常态化”

现状：
- `scripts/run_evolution_feedback_loop.py` 能跑通闭环（offline），但仍是“脚本级验证”。

建议 TODO：
- [x] 将闭环脚本上升为 `tests/integration/` 中的可重复集成测试（允许跳过外部 provider）。
- [x] 将“promotion 生效”的可观测证据写入 trace（schema 稳定），便于回放与审计。

---

## 建议的下一步落地顺序（避免返工）

1. 先标准化 trace/experiment 的“证据协议”（让 tracker/审计更可信）。
2. 再把自编程的离线验证与 benchmark 做实（减少自动化引入的回归风险）。
3. 最后把闭环从脚本提升到集成测试与 dashboard 指标常态化。
