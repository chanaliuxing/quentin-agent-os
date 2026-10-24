from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from quentin.infra.storage.kv_store import KVStore
from quentin.traces.schemas import TraceSpan, TraceEpisode
from quentin.traces.episode_builder import TraceEpisodeBuilder


@dataclass
class KVTraceEpisodeProvider:
    """
    一个基于 KVStore 的 episodes_provider 实现。

    假设：
    - 所有 TraceSpan 以 JSON 形式存储在：
        key = "trace:span:{span_id}"
    - 有一个 index key 记录所有 span_id 顺序：
        key = "trace:index:spans"  ->  [span_id1, span_id2, ...]

    如果你现有的 Tracer 存储格式不一样：
    - 要么调整 Tracer 的写入逻辑
    - 要么自己实现一个自定义 Provider 满足 get_recent_episodes 接口
    """

    kv: KVStore
    span_prefix: str = "trace:span:"
    span_index_key: str = "trace:index:spans"

    builder: TraceEpisodeBuilder = field(default_factory=TraceEpisodeBuilder)

    async def _load_recent_spans(self, span_limit: int) -> List[TraceSpan]:
        """
        从 KV 中读取最近 span_limit 条 spans（倒序）。
        """
        ids = await self.kv.get(self.span_index_key) or []
        if not ids:
            return []

        # 去重并保留最新 span_limit 个
        # index 里假定是 append 顺序（旧→新），所以取末尾
        ids = list(dict.fromkeys(ids))[-span_limit:]

        spans: List[TraceSpan] = []
        for sid in ids:
            raw = await self.kv.get(f"{self.span_prefix}{sid}")
            if not raw:
                continue
            try:
                span = TraceSpan(**raw)
                spans.append(span)
            except Exception:
                # 某些旧格式 / 脏数据可以忽略
                continue

        return spans

    async def get_recent_episodes(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        提供给 SleepLoop.SkillMiningJob 使用的接口。

        返回值是「字典列表」，兼容 SkillMiner 预期：
        [
          {
            "episode_id": "...",
            "domain": "...",
            "steps": [...],
            "meta": {...}
          },
          ...
        ]
        """
        # 为了凑够 limit 个 episode，大致抓 limit * 10 个 spans（可以以后调参）
        spans = await self._load_recent_spans(span_limit=limit * 10)

        if not spans:
            return []

        episodes: List[TraceEpisode] = self.builder.build_episodes_from_spans(
            spans,
            limit_episodes=limit,
        )
        # SkillMiner 期望的是 dict
        return [ep.model_dump() for ep in episodes]
