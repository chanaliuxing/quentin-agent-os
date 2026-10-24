#!/usr/bin/env python
"""
Connect to an already-open real browser (Chrome/Edge) via CDP and dump Playwright storage_state.

Usage (after launching Chrome with remote debugging):
  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222
  venv/bin/python scripts/save_storage_state.py --output chatgpt_state.json

This avoids Cloudflare bot detection by reusing a real session you logged in manually.
"""
from __future__ import annotations
import argparse
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright


async def main(cdp_url: str, output: Path) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(cdp_url)
        contexts = browser.contexts
        if not contexts:
            raise RuntimeError("No contexts found in connected browser; open a tab and log in first.")

        context = contexts[0]
        # Ensure at least one page exists to keep context alive
        if not context.pages:
            await context.new_page()

        await context.storage_state(path=str(output))
        print(f"Saved storage state to {output}")

        await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Save Playwright storage state from a real browser via CDP")
    parser.add_argument("--cdp-url", default="http://localhost:9222", help="CDP endpoint, e.g. http://localhost:9222")
    parser.add_argument("--output", required=True, help="Path to write storage_state.json")
    args = parser.parse_args()

    asyncio.run(main(args.cdp_url, Path(args.output)))
