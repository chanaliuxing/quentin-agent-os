#!/usr/bin/env python
# scripts/headless_web_research.py
from __future__ import annotations
import argparse
import asyncio
from playwright.async_api import async_playwright, Page
import json
import os
import sys

async def run(query: str, max_pages: int, max_chars_per_page: int) -> str:
    """
    Performs a web search and extracts text from the specified number of pages.
    Returns a JSON string of collected data.
    """
    results_data = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            # 1. Perform search (e.g., using DuckDuckGo)
            await page.goto("https://duckduckgo.com/")
            await page.fill("input[name=q]", query)
            await page.keyboard.press("Enter")
            await page.wait_for_load_state('networkidle')

            search_results = await page.locator("a.result__a").all()
            
            urls_to_visit = []
            for i, result_link in enumerate(search_results):
                if i >= max_pages: break
                url = await result_link.get_attribute('href')
                if url and url.startswith("http"):
                    urls_to_visit.append(url)
            
            # 2. Visit each page and extract content
            for url in urls_to_visit:
                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                    # Extract visible text content, clean up
                    content_element = await page.locator('body').all_text_contents()
                    full_text = " ".join(content_element).strip()
                    full_text = ' '.join(full_text.split()) # Normalize whitespace

                    if len(full_text) > max_chars_per_page:
                        full_text = full_text[:max_chars_per_page] + " ... (truncated)"
                    
                    results_data.append({
                        "url": url,
                        "content": full_text,
                    })
                except Exception as e:
                    print(f"Error fetching {url}: {e}", file=sys.stderr)
        finally:
            await browser.close()
            
    return json.dumps(results_data)

def main():
    parser = argparse.ArgumentParser(description="Headless Web Research Script")
    parser.add_argument("--query", required=True, help="Search query for web research")
    parser.add_argument("--max-pages", type=int, default=3, help="Max number of search results pages to visit")
    parser.add_argument("--max-chars-per-page", type=int, default=4000, help="Max characters to extract per page")
    args = parser.parse_args()

    result_json = asyncio.run(run(args.query, args.max_pages, args.max_chars_per_page))
    print(result_json)

if __name__ == "__main__":
    main()
