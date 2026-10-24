import asyncio
from temporalio.client import Client
from temporalio.worker import Worker

from app.config import settings
from app.temporal.workflow import RunProjectWorkflow
from app.temporal.activities import (
    read_prd_activity,
    decompose_modules_activity,
    generate_phase_tasks_activity,
    run_agent_activity,
    collect_results_activity,
    git_overlap_report_activity,
    integration_test_activity,
    write_phase_report_activity,
)


async def start_worker():
    client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)

    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[RunProjectWorkflow],
        activities=[
            read_prd_activity,
            decompose_modules_activity,
            generate_phase_tasks_activity,
            run_agent_activity,
            collect_results_activity,
            git_overlap_report_activity,
            integration_test_activity,
            write_phase_report_activity,
        ],
    )

    print(f"Starting Temporal worker on task queue: {settings.temporal_task_queue}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(start_worker())
