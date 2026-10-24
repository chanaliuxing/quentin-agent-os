from typing import Dict, Any
from quentin.utils.time import now_utc
from quentin.infra.storage.kv_store import KVStore


class MetricsCollector:
    """
    统一写入 metrics：
    - 各域成功率 / 错误率 / 延迟 / 成本
    - Memory Fabric 命中率 / 升级 & 衰减速度
    - patch 数量 / 通过率 / 回滚率
    """

    def __init__(self, kv_store: KVStore, prefix: str = "metrics:"):
        self.kv = kv_store
        self.prefix = prefix

    async def log(self, name: str, value: float, tags: Dict[str, Any] | None = None):
        record = {
            "name": name,
            "value": value,
            "tags": tags or {},
            "timestamp": now_utc().isoformat(),
        }
        await self.kv.append_list(f"{self.prefix}{name}", record)
