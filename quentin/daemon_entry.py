from __future__ import annotations

import asyncio
import os
import warnings

import uvicorn

from quentin.api.server import app
from quentin.infra.acp.server import gateway
from quentin.runtime.brain_daemon import brain_daemon_from_env


async def run_brain_loops() -> None:
    """Run background loops (Cognitive, Sleep, Immune) from TaskQueue."""
    daemon = brain_daemon_from_env()
    print("Starting Quentin background loops...")
    await asyncio.to_thread(daemon.run_queue_forever, worker_id="daemon_01")


async def main() -> None:
    warnings.warn(
        "quentin.daemon_entry is a compatibility entrypoint; prefer scripts/run_brain_daemon.py "
        "and quentin.api.server for canonical startup paths.",
        DeprecationWarning,
        stacklevel=2,
    )

    acp_port = int(os.getenv("QUENTIN_ACP_PORT", "8888") or "8888")
    acp_task = asyncio.create_task(gateway.start())

    loop_task = asyncio.create_task(run_brain_loops())

    api_port = int(os.getenv("QUENTIN_API_PORT", "8000") or "8000")
    config = uvicorn.Config(app, host="0.0.0.0", port=api_port, log_level="info")
    api_task = asyncio.create_task(uvicorn.Server(config).serve())

    print(f"Quentin services online: REST=http://localhost:{api_port} ACP=ws://localhost:{acp_port}")
    await asyncio.gather(acp_task, loop_task, api_task)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Quentin shutting down.")
