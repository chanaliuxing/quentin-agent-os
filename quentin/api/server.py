from __future__ import annotations

"""
Gateway-style API server entrypoint (OpenClaw parity).

This is a thin wrapper around the existing FastAPI app in `meta_agent.api.server`.
Keeping it here provides a stable import path for future UI/gateway integrations.
"""

from fastapi import FastAPI

from meta_agent.api.server import app as meta_agent_app

app = FastAPI(title="Quentin Gateway", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


# Mount the current control API.
app.mount("/", meta_agent_app)

