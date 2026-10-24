# meta_agent/tools/browser/playwright_tool.py
from __future__ import annotations
import os
try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None

from meta_agent.tools.browser.base import BrowserTool, WebSearchResult
from quentin.security.external_content import wrap_web_content


class PlaywrightBrowserTool(BrowserTool):
    def __init__(self, headless: bool = True):
        self.headless = headless

    @staticmethod
    def _shield_enabled() -> bool:
        raw = (os.getenv("QUENTIN_EXTERNAL_CONTENT_SHIELD", "true") or "").strip().lower()
        return raw in ("1", "true", "yes", "on")

    async def search(self, query: str) -> List[WebSearchResult]:
        if async_playwright is None:
            return [WebSearchResult(url="http://mock.url", title="Mock Result (Playwright not installed)", snippet="Please install playwright.")]

        """
        简单示例：打开搜索引擎（比如 DuckDuckGo/Google），输入 query，爬前几条结果。
        你需要自己根据 ToS 决定用哪个搜索引擎以及请求频率。
        """
        results: List[WebSearchResult] = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            page = await browser.new_page()
            await page.goto("https://duckduckgo.com/")
            await page.fill("input[name=q]", query)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(3000)

            items = await page.query_selector_all("a.result__a")
            for item in items[:5]:
                title = (await item.inner_text()).strip()
                url = await item.get_attribute("href")
                snippet = ""
                results.append(WebSearchResult(url=url or "", title=title, snippet=snippet))
            await browser.close()
        return results

    async def fetch_page_text(self, url: str) -> str:
        if async_playwright is None:
            return "Mock page text (Playwright not installed)."

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            page = await browser.new_page()
            await page.goto(url)
            # 这里可以根据网站结构定制抽取方式
            content = await page.content()
            await browser.close()
        if self._shield_enabled():
            return wrap_web_content(content, source="web_fetch")
        return content
