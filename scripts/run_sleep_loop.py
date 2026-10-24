#!/usr/bin/env python
# scripts/run_sleep_loop.py
from __future__ import annotations

from meta_agent.evolution.sleep_loop import SleepLoop


def main() -> None:
    loop = SleepLoop()
    summary = loop.run_once()
    print("SleepLoop finished:", summary)


if __name__ == "__main__":
    main()
