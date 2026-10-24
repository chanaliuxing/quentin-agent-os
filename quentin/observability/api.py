from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Depends

from quentin.config.settings import Settings # Updated import
from quentin.runtime.agent_runtime import AgentRuntime
from quentin.observability.service import ObservabilityService


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """
    创建一个 FastAPI 应用，用于暴露 Observability HTTP 接口。

    用法（命令行）：
        uvicorn quentin.observability.api:create_app --factory --reload
    或在 qctl 里提供 serve-observability 命令。
    """
    app = FastAPI(
        title="Project Quentin Observability API",
        version="0.1.0",
        description="Observability endpoints for the meta-agent system.",
    )

    settings = settings or Settings()
    runtime = AgentRuntime.create_from_settings(settings)
    obs_service = ObservabilityService(runtime=runtime)

    def get_obs() -> ObservabilityService:
        return obs_service

    # --------- 基本健康检查 ---------

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    # --------- 各子系统指标 ---------

    @app.get("/overview")
    async def overview(service: ObservabilityService = Depends(get_obs)):
        return await service.get_overview()

    @app.get("/models")
    async def model_stats(service: ObservabilityService = Depends(get_obs)):
        return await service.get_model_stats()

    @app.get("/memory")
    async def memory_stats(service: ObservabilityService = Depends(get_obs)):
        return await service.get_memory_stats()

    @app.get("/immune")
    async def immune_stats(service: ObservabilityService = Depends(get_obs)):
        return await service.get_immune_stats()

    @app.get("/patches")
    async def patch_stats(service: ObservabilityService = Depends(get_obs)):
        return await service.get_patch_stats()

    @app.get("/experiments")
    async def experiment_stats(service: ObservabilityService = Depends(get_obs)):
        return await service.get_experiment_stats()

    @app.get("/skills")
    async def skill_stats(service: ObservabilityService = Depends(get_obs)):
        return await service.get_skill_stats()

        @app.get("/sleep")

        async def sleep_stats(service: ObservabilityService = Depends(get_obs)):

            return await service.get_sleep_stats()

    

        @app.get("/blueprint")

        async def blueprint_stats(service: ObservabilityService = Depends(get_obs)):

            return await service.get_blueprint_stats()

    

        return app

    