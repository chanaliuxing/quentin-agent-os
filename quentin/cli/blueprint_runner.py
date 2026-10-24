from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional
import json
import logging

from quentin.runtime.system import RuntimeFacade
from quentin.l3.research.layer import ResearchCycleRequest
from quentin.metrics.schema import RunMetrics
from quentin.metrics.collector import compute_run_metrics
from quentin.utils.time import now_iso

logger = logging.getLogger(__name__)


@dataclass
class BlueprintSelfIterateConfig:
    """
    一次“蓝皮书自迭代 run”的配置。

    这些都是通用参数，不依赖具体领域：
      - max_gaps_per_cycle: 每次改进周期最多处理多少个能力 gap
      - research_strategy: ResearchLayer 的策略名（例如 "simple"）
      - max_experiments: 本轮允许跑多少个 experiment（None=由预算控制器决定）
      - repo_root: 仓库根目录，用于写入 run 日志
      - run_tag: 可选标签，方便你日后过滤/分析
    """
    max_gaps_per_cycle: int = 10
    research_strategy: str = "simple"
    max_experiments: Optional[int] = None
    repo_root: str = "."
    run_tag: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BlueprintSelfIterateResult:
    """
    一次自迭代 run 的完整结果快照。
    """
    run_id: str
    started_at: str
    finished_at: str
    config: Dict[str, Any]
    capability_scan: Dict[str, Any]
    blueprint_cycle: Dict[str, Any]
    metrics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def run_blueprint_self_iteration(
    runtime: RuntimeFacade,
    config: BlueprintSelfIterateConfig,
) -> BlueprintSelfIterateResult:
    """
    高层 orchestrator：

      1. 使用 runtime.auto_update_capabilities_from_repo() 更新蓝皮书能力状态
      2. 使用 runtime.run_blueprint_improvement_cycle() 生成实验并跑研究周期
      3. 将此次 run 的结果写入 data/runs/blueprint_self_iterate/<timestamp>.json

    注意：
      - runtime 内部已经封装了 MultiModelCouncil / ResearchLayer / BlueprintImprover 等细节
      - 这里不关心具体 domain（桌面 / Legal / Trading），只关心“蓝皮书自迭代”这条流水线
    """
    repo_root = Path(config.repo_root).resolve()
    runs_dir = repo_root / "data" / "runs" / "blueprint_self_iterate"
    runs_dir.mkdir(parents=True, exist_ok=True)

    started_at = now_iso()

    # 1) 扫描 & 更新蓝皮书能力状态
    logger.info("BlueprintSelfIterate: starting capability scan ...")
    cap_scan = runtime.auto_update_capabilities_from_repo(repo_root=repo_root)

    # 2) 根据 gap 跑一轮蓝皮书改进周期
    logger.info("BlueprintSelfIterate: starting blueprint improvement cycle ...")
    rc_req = ResearchCycleRequest(
        strategy=config.research_strategy,
        max_experiments=config.max_experiments,
    )
    blueprint_cycle = runtime.run_blueprint_improvement_cycle(
        max_gaps=config.max_gaps_per_cycle,
        research_request=rc_req,
    )

    finished_at = now_iso()
    run_id = _make_run_id(started_at, config.run_tag)

    # 构造中间 dict 以计算 metrics
    raw_result_dict: Dict[str, Any] = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "config": config.to_dict(),
        "capability_scan": cap_scan,
        "blueprint_cycle": blueprint_cycle,
    }

    # 3) 计算指标（RunMetrics）
    run_metrics = compute_run_metrics(raw_result_dict)

    result = BlueprintSelfIterateResult(
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        config=config.to_dict(),
        capability_scan=cap_scan,
        blueprint_cycle=blueprint_cycle,
        metrics=run_metrics.to_dict(),
    )

    # 4) 写入本地 JSON 日志文件
    _save_run_result(runs_dir, result)
    
    # 5) 单独保存 metrics
    _save_run_metrics(runs_dir, run_metrics)

    logger.info("BlueprintSelfIterate: finished run_id=%s", run_id)

    return result


# --------------------------------------------------
# 辅助函数
# --------------------------------------------------

def _make_run_id(started_at_iso: str, run_tag: Optional[str]) -> str:
    ts = started_at_iso.replace(":", "").replace("-", "").replace(".", "")
    if run_tag:
        return f"blueprint_{run_tag}_{ts}"
    return f"blueprint_{ts}"


def _save_run_result(runs_dir: Path, result: BlueprintSelfIterateResult) -> None:
    data = result.to_dict()
    path = runs_dir / f"{result.run_id}.json"
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)

def _save_run_metrics(runs_dir: Path, metrics: RunMetrics) -> None:
    """
    单独保存一份 metrics JSON，便于后续做 dashboard / 统计。

    文件名格式： metrics_<run_id>.json
    """
    data = metrics.to_dict()
    path = runs_dir / f"metrics_{metrics.run_id}.json"
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)
