from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from quentin.utils.time import now_utc


class SkillKind(str, Enum):
    """
    Skill 类型：
    - procedural: 由一串步骤组成的流程（宏命令）
    - tool_wrapper: 对某个工具的包装
    - code: 纯代码实现的函数技能
    """
    procedural = "procedural"
    tool_wrapper = "tool_wrapper"
    code = "code"


class SkillDefinition(BaseModel):
    """
    一个 Skill 的结构化定义。

    v1 设计：
    - 对于 code 型技能：只需要 code_ref（module + attr）
    - 对于 procedural 型：使用 plan_steps 存储步骤列表
    """

    skill_id: str
    name: str
    version: str = "1.0.0"

    kind: SkillKind = SkillKind.procedural

    description: str = ""
    domain: Optional[str] = None        # "desktop" / "legal" / "trading" / "demo" / ...

    tags: List[str] = Field(default_factory=list)

    # 对于 code 型技能：指定模块路径和函数名
    code_ref: Optional[Dict[str, str]] = None
    # 对于 procedural 型技能：一个步骤列表（具体格式由业务决定）
    plan_steps: Optional[List[Dict[str, Any]]] = None

    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)

    active: bool = True
    supersedes: Optional[str] = None     # 被替代的 skill_id

    meta: Dict[str, Any] = Field(default_factory=dict)


class SkillStats(BaseModel):
    """
    每个 Skill 的性能统计信息。
    """
    skill_id: str

    calls: int = 0
    success: int = 0
    failure: int = 0

    avg_latency_sec: float = 0.0
    last_called_at: Optional[datetime] = None

    meta: Dict[str, Any] = Field(default_factory=dict)
