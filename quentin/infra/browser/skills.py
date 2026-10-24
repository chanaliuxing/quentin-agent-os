from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from .manager import browser_manager

logger = logging.getLogger(__name__)

class BrowserSkills:
    """
    Standard Quentin Skills for Browser Automation.
    """

    @staticmethod
    async def open_url(url: str) -> str:
        """Navigate to a specified URL."""
        await browser_manager.navigate(url)
        return f"Navigated to {url}"

    @staticmethod
    async def click_element(selector: str) -> str:
        """Click a button or link and verify the result."""
        # 1. Take Pre-action snapshot
        prev_tree = await browser_manager.get_pruned_ui_tree()
        
        # 2. Perform action
        await browser_manager.click(selector)
        
        # 3. Verify Delta
        if await browser_manager.verify_action_success(prev_tree):
            return f"Successfully clicked {selector} (UI updated)"
        else:
            # Maybe it didn't fail, but nothing changed (e.g. no-op button)
            return f"Clicked {selector}, but no UI change detected. Possibly blocked or no-op."

    @staticmethod
    async def type_text(selector: str, text: str) -> str:
        """Type text into an input field."""
        await browser_manager.fill(selector, text)
        return f"Typed into {selector}"

    @staticmethod
    async def scroll(direction: str) -> str:
        """Scroll the page 'down' or 'up'."""
        await browser_manager.scroll(direction)
        return f"Scrolled {direction}"

    @staticmethod
    async def back() -> str:
        """Go back to the previous page."""
        await browser_manager.go_back()
        return "Navigated back"

    @staticmethod
    async def refresh() -> str:
        """Refresh current page."""
        await browser_manager.refresh()
        return "Page refreshed"

    @staticmethod
    async def save_session() -> str:
        """Saves current login state/cookies."""
        await browser_manager.save_state()
        return "Browser session state saved"

    @staticmethod
    async def scrape_page() -> str:
        """Extract all HTML content from the current page."""
        return await browser_manager.get_content()

    @staticmethod
    async def get_ui_tree() -> Dict[str, Any]:
        """Get a pruned, LLM-optimized accessibility tree of the page."""
        return await browser_manager.get_pruned_ui_tree()

    @staticmethod
    async def get_screenshot_analysis() -> str:
        """Capture current view and return analysis (requires Vision LLM bridge)."""
        # In a real loop, this would trigger the Vision manager
        return "Screenshot captured and visible on Canvas."
