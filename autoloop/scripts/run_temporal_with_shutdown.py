#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from app.main import _write_shutdown_terminal_fallback, run_temporal
from app.observability.logger import setup_logging
from app.observability.tracer import setup_tracing
from app.control import ShutdownManager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--prd-path", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings.ensure_dirs()
    setup_logging()
    setup_tracing()
    manager = ShutdownManager()
    manager.install()
    try:
        asyncio.run(run_temporal(args.project_id, args.prd_path))
        return 0
    except KeyboardInterrupt:
        _write_shutdown_terminal_fallback(
            project_id=args.project_id,
            phase_id="phase_01",
            termination_reason=manager.state.termination_reason or "signal_interrupt",
        )
        return 130
    finally:
        manager.restore()


if __name__ == "__main__":
    raise SystemExit(main())
