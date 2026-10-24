from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
from quentin.infra.storage.kv_store import KVStore
from quentin.infra.logging import Tracer
from quentin.experiments.schemas import VariantConfig


@dataclass
class VariantRegistry:
    """
    变体注册表：
    - 注册不同的策略 / 模型路由 / Planner 版本
    - 实验时只用 variant_id 拿配置，不直接依赖具体模块
    """
    kv: KVStore
    tracer: Tracer

    prefix: str = "variant:config:"
    index_key: str = "variant:index:all"

    async def register(self, cfg: VariantConfig) -> VariantConfig:
        key = f"{self.prefix}{cfg.variant_id}"
        await self.kv.save(key, cfg.model_dump())
        await self.kv.append_list(self.index_key, cfg.variant_id)

        self.tracer.span(
            "L3",
            "variant_registered",
            module="variant_registry",
            input={"variant_id": cfg.variant_id, "kind": cfg.kind},
        )
        return cfg

    async def get(self, variant_id: str) -> Optional[VariantConfig]:
        data = await self.kv.get(f"{self.prefix}{variant_id}")
        if not data:
            return None
        return VariantConfig(**data)

    async def list(self, limit: int = 100) -> List[VariantConfig]:
        ids = await self.kv.get(self.index_key) or []
        ids = list(dict.fromkeys(ids))[-limit:]
        res: List[VariantConfig] = []
        for vid in ids:
            data = await self.kv.get(f"{self.prefix}{vid}")
            if data:
                res.append(VariantConfig(**data))
        return res
