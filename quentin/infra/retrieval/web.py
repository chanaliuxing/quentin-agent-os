from __future__ import annotations

import logging
import re
import httpx
from typing import Dict, Any, Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class WebUnfurler:
    """
    Link Understanding & Scraper module.
    Ported from OpenClaw's link-understanding.
    """
    
    @staticmethod
    async def unfurl_url(url: str) -> Dict[str, str]:
        """
        Scrapes a URL to extract metadata (Title, Desc, Main Content).
        """
        if not url.startswith("http"):
            return {}

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                headers = {"User-Agent": "Mozilla/5.0 (Quentin Agent)"}
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                title = soup.title.string if soup.title else ""
                
                # Meta description
                meta_desc = soup.find("meta", attrs={"name": "description"})
                description = meta_desc["content"] if meta_desc else ""
                
                # Simple text extraction (remove scripts/styles)
                for script in soup(["script", "style"]):
                    script.decompose()
                
                content = soup.get_text()
                # Clean up whitespace
                lines = (line.strip() for line in content.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                clean_text = "\n".join(chunk for chunk in chunks if chunk)

                return {
                    "url": url,
                    "title": title.strip(),
                    "description": description.strip(),
                    "snippet": clean_text[:2000] # First 2k chars
                }
        except Exception as e:
            logger.error(f"Failed to unfurl {url}: {e}")
            return {"url": url, "error": str(e)}

    @staticmethod
    def extract_urls(text: str) -> list[str]:
        """Helper to find URLs in a text block."""
        return re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)

# Global instance
web_retriever = WebUnfurler()
