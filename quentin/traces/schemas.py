from __future__ import annotations

from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TraceSpan(BaseModel):
    """
    系统内部统一的 span 结构。

    设计目标：
    - 覆盖 Tracer 写入的所有字段
    - 不限制具体存储格式（KV / DB / 文件都行）
    - 方便后续 EpisodeBuilder 做聚合

    约定：
    - task_id / episode_id 等“归属于哪条任务”的信息，放在 meta 或 input 里
    """

    span_id: str
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))

    layer: str               # "L0" / "L1" / "L2" / "L3"
    event: str               # "task_start" / "task_end" / "sleep_loop" / ...
    module: str              # "cognitive" / "sleep" / "skills" / ...

    input: Dict[str, Any] = Field(default_factory=dict)
    output: Dict[str, Any] = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)


class TraceEpisode(BaseModel):
    """
    由多条 TraceSpan 聚合而成的一条 Episode（一次完整尝试 / 一次任务运行）。

    注意：这和 SkillMiner 里的 TraceEpisode 结构保持一致：
    {
      "episode_id": "...",
      "domain": "demo",
      "steps": [ {...}, {...} ],
      "meta": {...}
    }
    """

    episode_id: str
    domain: Optional[str] = None

    # 一个 episode 下的“步骤序列”
    # 每一步都可以是任意结构，但推荐：
    # {
    #   "event": "...",
    #   "module": "...",
    #   "layer": "L1",
    #   "tool": "add" / "planner" / "...",
    #   "input": {...},
    #   "output": {...},
    #   "span_id": "...",
    #   "ts": "..."
    # }
    steps: List[Dict[str, Any]] = Field(default_factory=list)

    # 其他元信息：task_id / trace_ids / 成功与否等
    meta: Dict[str, Any] = Field(default_factory=dict)
