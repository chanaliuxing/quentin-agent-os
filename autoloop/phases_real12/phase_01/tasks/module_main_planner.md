# Planner Task - phase_01

## Module
module_main

## Context
Meta-Agent 工程落地蓝皮书 v3.1代号：Project Quentin副标题：Dual-Track & MCP Edition（双轨进化 + MCP 工具生态版）

0. 定位 & 边界：v3.1 比 v3 多了什么？
   0.1 系统是什么（更新版）
   一个运行在本地（或云端）的 “自进化 AI 操作系统”，具备：

* 能接不同领域的任务（Desktop 自动化 / LegalBot / Trading / 以后更多）
* 能拆解、执行、记录、反思任务
* 能在受控范围内：

  * 更新自己的记忆（知识和技能）
  * 生成并测试新工具 / 新代码
  * 持续引入外部工具能力（MCP）
  * 决定下一步在哪里投入“自我改进的资源”
    与 v3 的关键差异：
    v3.1 正式引入三件大事：

1. 双轨能力获取（Dual-Track Acquisition）

   * 不再“所有 Gap 都去写代码”；
   * 而是：能用 MCP 工具，就用工具；工具没有 / 不合适，再启动自编程引擎。
2. MCP 工具学习层（Tool Learning & MCP Integration Layer）

   * 新增一个“工具学习层”，负责：

     * 在 MCP 生态里发现工具
     * 学习工具的使用方法
     * 把工具封装成内部...

## Your Tasks
1. Produce module implementation plan
2. Break down concrete tasks
3. Define acceptance criteria

## Typed Contracts
- TaskSpec: ./autoloop/phases_real12/phase_01/tasks/contracts/module_main_task_spec.json
- ChangeSpec: ./autoloop/phases_real12/phase_01/tasks/contracts/module_main_change_spec.json
- AcceptanceSpec: ./autoloop/phases_real12/phase_01/tasks/contracts/module_main_acceptance_spec.json

## Deliverables
Return strict JSON contract only.

