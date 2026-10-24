from fastapi import FastAPI
from pydantic import BaseModel
from quentin.runtime.agent_runtime import AgentRuntime
from quentin.kernel.schemas import ExperimentConfig, ExperimentResult


class ExperimentCreateBody(BaseModel):
    config: ExperimentConfig


def create_app(runtime: AgentRuntime) -> FastAPI:
    app = FastAPI(title="Project Quentin Research API")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/experiments", response_model=ExperimentResult)
    async def create_and_run_experiment(body: ExperimentCreateBody):
        """
        研究接口：
        - 创建一个实验配置
        - 立即触发 run_experiment（v0 简易版）
        """
        await runtime.experiment_orchestrator.create_experiment(body.config)
        res = await runtime.experiment_orchestrator.run_experiment(
            body.config.experiment_id
        )
        return res

    @app.get("/experiments/{experiment_id}", response_model=ExperimentResult)
    async def get_experiment_result(experiment_id: str):
        res = await runtime.experiment_orchestrator.compare_variants(experiment_id)
        return res

    return app
