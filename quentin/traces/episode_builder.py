from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Iterable
from collections import defaultdict

from quentin.traces.schemas import TraceSpan, TraceEpisode


@dataclass
class TraceEpisodeBuilder:
    """
    把 TraceSpan 列表聚合成 TraceEpisode 列表的工具类。

    v1 策略（非常简单版）：
    - 用 task_id 作为 episode_id（如果有的话）
    - 如果没有 task_id，则用 span.meta["episode_id"]，还没有就丢弃
    - 一个 episode 内的 steps 按时间排序

    你以后可以在这里玩更复杂的 episode 划分逻辑：
    - 按 trace window（时间窗口）
    - 按 domain / module 分类
    """

    # 从 span 中提取 episode_id 的逻辑
    def _extract_episode_id(self, span: TraceSpan) -> Optional[str]:
        # 优先 meta.episode_id
        ep = span.meta.get("episode_id")
        if ep:
            return str(ep)

        # 其次 meta.task_id
        ep = span.meta.get("task_id")
        if ep:
            return str(ep)

        # 再其次 input.task_id
        inp = span.input or {}
        ep = inp.get("task_id")
        if ep:
            return str(ep)

        # 最后 output.task_id（一般用不到）
        out = span.output or {}
        ep = out.get("task_id")
        if ep:
            return str(ep)

        return None

    def _extract_domain(self, span: TraceSpan) -> Optional[str]:
        # 优先 meta.domain
        dom = span.meta.get("domain")
        if dom:
            return str(dom)

        # 其次 input.domain
        dom = (span.input or {}).get("domain")
        if dom:
            return str(dom)

        return None

    def build_episodes_from_spans(
        self,
        spans: Iterable[TraceSpan],
        limit_episodes: Optional[int] = None,
    ) -> List[TraceEpisode]:
        """
        给定一堆 spans，按 episode_id 聚合成 episodes。
        """

        # 1) 分组：episode_id -> spans[]
        groups: Dict[str, List[TraceSpan]] = defaultdict(list)

        for span in spans:
            ep_id = self._extract_episode_id(span)
            if not ep_id:
                # 没有 episode_id 的 span 暂时丢弃
                continue
            groups[ep_id].append(span)

        # 2) 每组内部按 ts 排序
        episodes: List[TraceEpisode] = []

        for ep_id, sp_list in groups.items():
            sp_list_sorted = sorted(sp_list, key=lambda s: s.ts)

            # 选一个 domain（目前简单用第一条 span 提取）
            domain = self._extract_domain(sp_list_sorted[0])

            # 构造 steps
            steps: List[Dict[str, Any]] = []
            span_ids: List[str] = []

            for s in sp_list_sorted:
                step = {
                    "event": s.event,
                    "module": s.module,
                    "layer": s.layer,
                    "tool": s.meta.get("tool") or s.input.get("tool"),
                    "input": s.input,
                    "output": s.output,
                    "span_id": s.span_id,
                    "ts": s.ts.isoformat(),
                }
                steps.append(step)
                span_ids.append(s.span_id)

            ep = TraceEpisode(
                episode_id=ep_id,
                domain=domain,
                steps=steps,
                meta={
                    "span_ids": span_ids,
                    # 可加更多统计，比如 steps 数、开始/结束时间等
                    "num_steps": len(steps),
                    "started_at": sp_list_sorted[0].ts.isoformat(),
                    "finished_at": sp_list_sorted[-1].ts.isoformat(),
                },
            )
            episodes.append(ep)

        # 3) 只保留最新若干个 episode（按 finished_at 排序）
        episodes_sorted = sorted(
            episodes,
            key=lambda e: e.meta.get("finished_at", ""),
        )
        if limit_episodes is not None and limit_episodes > 0:
            episodes_sorted = episodes_sorted[-limit_episodes:]

        return episodes_sorted
