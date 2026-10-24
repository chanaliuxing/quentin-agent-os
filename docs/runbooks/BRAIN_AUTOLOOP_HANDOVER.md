# Project Taylor (Quentin) 自我进化系统工程交接文档

## 1. 系统核心目标
建立一个**基于 LLM 的全自动工程进化循环 (AutoLoop)**，使 Quentin 认知内核（"大脑"）能够通过自我诊断、自我修复、自我验证，从每一次任务失败中提升其工程实现质量和认知能力（"智商"）。

**核心哲学**：
*   **不修考卷，只修大脑**：任务产物（如 `extensions/tools/web_search/`）是临时的，必须每轮清空。我们只修改内核代码 (`quentin/`)，通过内核的进化来让它下次写出更好的产物。
*   **物理驱动**：所有诊断和修复都基于真实的文件读写和 Shell 命令，拒绝 JSON 解析带来的脆弱性。
*   **严防退化**：引入“Git 审计”和“TDD 闭环”，确保每次修改都是增量进化，严禁暴力删减代码（脑缩水）。

---

## 2. 关键基础设施架构

### 2.1 控制中枢：`scripts/brain_autoloop.py`
这是整个循环的编排器（Orchestrator），负责串联各个环节。

*   **运行模式**：
    ```bash
    python3 scripts/brain_autoloop.py --config config/brain_autoloop.local.json --session [UUID] --iterations N
    ```
*   **核心流程 (The Loop)**：
    1.  **Phase 0 (Clean)**: 物理删除 `extensions/tools/web_search/`，强制大脑从零开始。
    2.  **Step 1 (Run)**: 运行 `verify_system.py`（大脑大考）。无论成功失败，都进入下一步。
    3.  **Step 2 (Analyze)**: 调用 Gemini CLI，加载 `prompts/autoloop/analyzer.md`。
        *   Gemini 自主调查日志 (`logs/`, `data/`)。
        *   Gemini 将诊断报告写入 `mutable/last_brain_diagnosis.md`。
    4.  **Step 3 (Fix)**: 调用 Gemini CLI，加载 `prompts/autoloop/fixer.md`。
        *   Gemini 读取报告。
        *   Gemini 编写复现测试 (`reproduce_issue.py`)。
        *   Gemini 修改内核代码 (`quentin/`)。
        *   Gemini 运行测试并通过后，执行 `git commit`。
    5.  **Step 4 (Verify)**: 脚本检查 Git 状态，确认物理变更。
    6.  **Step 5 (Test)**: 运行系统级集成测试 `pytest`。

### 2.2 智库指令：Prompt 体系
位于 `prompts/autoloop/` 目录下，是 Gemini 的“操作手册”。

*   **`analyzer.md` (首席诊断官)**
    *   **核心职责**：基于 `audit_events.jsonl` (物理行为) 和 `traces/events.jsonl` (认知思维) 进行多维审计。
    *   **分析矩阵**：[感知、推理、规划、工具、环境] x [Coding、运维]。
    *   **输出产物**：Markdown 格式的诊断报告，包含代码病灶定位和验证挑战。

*   **`fixer.md` (主刀医生)**
    *   **核心职责**：执行代码手术。
    *   **绝对红线**：严禁修改 `web_search/`，严禁脑缩水（功能密度守恒）。
    *   **操作闭环**：Read Report -> Write Reproduction Test (Red) -> Fix Code (Refactor) -> Verify Test (Green) -> Git Commit。

### 2.3 记忆载体
*   **Session UUID**：通过 `--session` 参数复用云端 Context，保持对话连贯性。
*   **物理文件**：`mutable/last_brain_diagnosis.md` 是诊断与修复之间的“交接棒”。

---

## 3. 日常运维 SOP

### 3.1 启动进化循环
推荐使用后台运行并重定向日志，以避免 CLI 缓冲区阻塞。

```bash
# 示例：启动 1 轮测试
PYTHONUNBUFFERED=1 python3 scripts/brain_autoloop.py 
  --config config/brain_autoloop.local.json 
  --session a0332e2e-8e0e-4e04-b992-858659123b34 
  --iterations 1 
  > logs/autoloop_live.log 2>&1 &

# 实时监控进度
tail -f logs/autoloop_live.log
```

### 3.2 监控指标
*   **成功标志**：日志末尾出现 `✅ MISSION ACCOMPLISHED`。
*   **进化标志**：执行 `git log`，看到由 AutoLoop 提交的 `Evolve: ...` 记录。
*   **失败排查**：
    *   **日志为空**：检查 Python 环境或 `scripts/brain_autoloop.py` 头部。
    *   **Gemini 不动**：检查网络连接或 API Quota (429 错误)。
    *   **大脑死循环**：检查 `analyzer` 的报告是否指出了重复操作。

### 3.3 故障恢复
如果进程卡死或需要重置环境：

```bash
# 1. 杀掉所有相关进程
pkill -f brain_autoloop.py
pkill -f verify_system.py

# 2. 清理临时状态
rm -rf extensions/tools/web_search/
rm logs/autoloop_live.log
```

---

## 4. 当前系统状态 (截至交接点)
*   **脚本状态**：`scripts/brain_autoloop.py` 已修复 `shell=True` 启动问题，支持 `--session` 参数，逻辑已验证。
*   **Prompt 状态**：`analyzer.md` 和 `fixer.md` 已更新至 vFinal 版本，包含严格的 TDD 和 Git 约束。
*   **环境状态**：已设置 `PYTHONUNBUFFERED=1` 绕过输出缓冲，确保日志实时可见。
*   **下一步动作**：执行第一轮正式的“文件驱动”进化测试。
