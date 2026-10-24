from __future__ import annotations

from enum import Enum
from typing import Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime


class ToolKind(str, Enum):
    """
    工具类型：
    - builtin: 内置纯 Python 工具
    - llm: 通过 LLM 进行“函数调用式”工具（例如 ReAct 工具）
    - external: 需要调用外部系统 / API 的工具
    """
    builtin = "builtin"
    llm = "llm"
    external = "external"

ToolLifecycle = Literal["active", "draft", "candidate", "deprecated", "disabled"]
ToolRiskLevel = Literal["low", "medium", "high", "critical"]


class ToolSpec(BaseModel):
    """
    工具的声明性定义：
    - name: 全局唯一（建议用 domain 前缀，如 "generic.echo"）
    - description: 给 Planner / LLM 使用的自然语言描述
    - kind: ToolKind
    - input_schema / output_schema: OPTIONAL -> 给 LLM / UI 做校验和提示
    """
    name: str
    description: str
    kind: ToolKind = ToolKind.builtin
    domain: str = "core"

    version: str = "v1"
    owner: str = "system"
    risk_level: ToolRiskLevel = "medium"
    lifecycle: ToolLifecycle = "active"

    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)

    meta: Dict[str, Any] = Field(default_factory=dict)
    policy_profile: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ToolCallRequest(BaseModel):
    """
    调用工具时的标准请求结构：
    - tool_name: ToolSpec.name
    - payload: 输入参数（可以是 dict / str / list，尽量统一成 dict）
    """
    tool_name: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    trace_id: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class ToolCallResult(BaseModel):
    """
    调用工具后的标准返回：
    - success: 是否成功
    - output: 结果（可以任意结构，但尽量是 dict/json friendly）
    - error: 如果失败，这里存错误信息
    """
    tool_name: str
    success: bool
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    meta: Dict[str, Any] = Field(default_factory=dict)
