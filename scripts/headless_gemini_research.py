#!/usr/bin/env python
# scripts/headless_gemini_research.py
from __future__ import annotations
import argparse
import asyncio
from playwright.async_api import async_playwright, Page
import os
import sys
from pathlib import Path


GEMINI_URL = "https://gemini.google.com/app"


async def _ensure_input(page: Page) -> Page:
    editor = page.locator("div[contenteditable='true'], textarea").first
    await editor.wait_for(state="visible", timeout=30000)
    return editor


async def _wait_for_answer(page: Page) -> str:
    await page.wait_for_timeout(500)  # Let UI settle
    await page.wait_for_selector("[data-message-author-role='assistant'], message-content", timeout=120000)
    answers = page.locator("[data-message-author-role='assistant'], message-content").last
    await page.wait_for_timeout(1500)
    return await answers.inner_text()


def _headless_default() -> bool:
    return os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() in {"1", "true", "yes"}


def _channel_default() -> str | None:
    return os.getenv("PLAYWRIGHT_CHANNEL", "chrome")


def _user_agent_default() -> str:
    return os.getenv(
        "PLAYWRIGHT_USER_AGENT",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    )


async def _open_context(p, storage_state: Path | None, user_data_dir: str | None):
    headless = _headless_default()
    channel = _channel_default()
    common_args = ["--disable-blink-features=AutomationControlled"]
    context_kwargs = {
        "viewport": {"width": 1280, "height": 800},
        "user_agent": _user_agent_default(),
    }

    if user_data_dir:
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=headless,
            channel=channel,
            args=common_args,
            **context_kwargs,
        )
        page = context.pages[0] if context.pages else await context.new_page()
        return context, page, None

    browser = await p.chromium.launch(headless=headless, channel=channel, args=common_args)
    context = await browser.new_context(storage_state=storage_state, **context_kwargs)
    page = await context.new_page()
    return context, page, browser


async def run(query: str, max_tokens: int, storage_state: str | None = None, user_data_dir: str | None = None) -> str:
    async with async_playwright() as p:
        storage_path = Path(storage_state) if storage_state else None
        if storage_state and storage_path and not storage_path.exists():
            raise RuntimeError(f"storage_state not found: {storage_state}")
        use_storage = storage_path if storage_path and storage_path.exists() else None

        context, page, browser = await _open_context(p, use_storage, user_data_dir)

        await page.goto(GEMINI_URL, wait_until="domcontentloaded")

        try:
            editor = await _ensure_input(page)
        except Exception as e:
            raise RuntimeError(
                "Gemini page did not expose an input box. Ensure you are logged in. "
                "Provide a Playwright storage_state.json via --storage-state or GEMINI_STORAGE_STATE."
            ) from e

        await editor.fill(query)
        await editor.press("Enter")

        answer = await _wait_for_answer(page)

        if storage_path:
            try:
                await context.storage_state(path=str(storage_path))
            except Exception:
                pass

        await context.close()
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        return answer

def main():
    parser = argparse.ArgumentParser(description="Headless Gemini Research Script")
    parser.add_argument("--query", required=True, help="Query to send to Gemini")
    parser.add_argument("--max-tokens", type=int, default=2000, help="Max tokens for the response")
    parser.add_argument(
        "--storage-state",
        default=os.getenv("GEMINI_STORAGE_STATE"),
        help="Path to Playwright storage_state.json with a logged-in Gemini session",
    )
    parser.add_argument(
        "--user-data-dir",
        default=os.getenv("GEMINI_USER_DATA_DIR"),
        help="Persistent user data dir for Playwright (can carry cookies/fingerprint)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Force headless mode (default is non-headless to reduce bot detection)",
    )
    args = parser.parse_args()

    if not args.storage_state:
        print("[WARN] No GEMINI_STORAGE_STATE provided; you must already be logged in in this browser context.", file=sys.stderr)

    if args.headless:
        os.environ["PLAYWRIGHT_HEADLESS"] = "true"

    result = asyncio.run(run(args.query, args.max_tokens, args.storage_state, args.user_data_dir))
    print(result)

if __name__ == "__main__":
    main()
