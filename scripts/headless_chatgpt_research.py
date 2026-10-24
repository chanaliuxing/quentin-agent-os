#!/usr/bin/env python
# scripts/headless_chatgpt_research.py
from __future__ import annotations
import argparse
import asyncio
from playwright.async_api import async_playwright, Page
import os
import sys
from pathlib import Path


CHATGPT_URL = "https://chatgpt.com/?temporary-chat=true"


async def _ensure_input(page: Page) -> Page:
    # ChatGPT UI changes often; prefer a broad textarea locator.
    textarea = page.locator("textarea")
    await textarea.wait_for(state="visible", timeout=30000)
    return textarea


async def _wait_for_answer(page: Page) -> str:
    # Wait for the newest assistant message and read its text content.
    await page.wait_for_selector("[data-message-author-role='assistant']", timeout=120000)
    messages = page.locator("[data-message-author-role='assistant']")
    # Wait a short grace period to let streaming finish.
    await page.wait_for_timeout(2000)
    return await messages.last.inner_text()


def _headless_default() -> bool:
    # Default to non-headless to reduce bot signals; allow override.
    return os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() in {"1", "true", "yes"}


def _channel_default() -> str | None:
    # Prefer real Chrome if available to look less like automation.
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

    cdp_url = os.getenv("PLAYWRIGHT_CDP_URL")
    if cdp_url:
        # Reuse a real, manually-logged-in browser via CDP.
        browser = await p.chromium.connect_over_cdp(cdp_url)
        contexts = browser.contexts
        context = contexts[0] if contexts else await browser.new_context(**context_kwargs)
        page = context.pages[0] if context.pages else await context.new_page()
        return context, page, browser

    if user_data_dir:
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=headless,
            channel=channel,
            args=common_args,
            **context_kwargs,
        )
        page = context.pages[0] if context.pages else await context.new_page()
        return context, page, None  # persistent context closes browser

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

        await page.goto(CHATGPT_URL, wait_until="domcontentloaded")

        try:
            textarea = await _ensure_input(page)
        except Exception as e:
            raise RuntimeError(
                "ChatGPT page did not expose a prompt textarea. Ensure you are logged in. "
                "Use a Playwright storage state file via --storage-state or set CHATGPT_STORAGE_STATE."
            ) from e

        await textarea.fill(query)
        await textarea.press("Enter")

        answer = await _wait_for_answer(page)

        # Persist updated auth/session if a storage path was provided
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
    parser = argparse.ArgumentParser(description="Headless ChatGPT Research Script")
    parser.add_argument("--query", required=True, help="Query to send to ChatGPT")
    parser.add_argument("--max-tokens", type=int, default=2000, help="Max tokens for the response")
    parser.add_argument(
        "--storage-state",
        default=os.getenv("CHATGPT_STORAGE_STATE"),
        help="Path to Playwright storage_state.json with a logged-in ChatGPT session",
    )
    parser.add_argument(
        "--user-data-dir",
        default=os.getenv("CHATGPT_USER_DATA_DIR"),
        help="Persistent user data dir for Playwright (can carry cookies/fingerprint)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Force headless mode (default is non-headless to reduce bot detection)",
    )
    args = parser.parse_args()

    if not args.storage_state:
        print("[WARN] No CHATGPT_STORAGE_STATE provided; you must already be logged in in this browser context.", file=sys.stderr)

    if args.headless:
        os.environ["PLAYWRIGHT_HEADLESS"] = "true"

    # Playwright's async methods need to be run in an event loop
    result = asyncio.run(run(args.query, args.max_tokens, args.storage_state, args.user_data_dir))
    print(result)

if __name__ == "__main__":
    main()
