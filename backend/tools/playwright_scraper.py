# backend/tools/playwright_tool.py
from pydantic import Field
from mira.types import LLMTool
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

class PlaywrightScraperTool(LLMTool):
    """mira 工具：抓取页面并抽取正文，返回 dict"""
    url: str = Field(..., description="要抓取的页面 URL，必须是纯字符串")
    timeout: int = Field(15000, description="超时时间 ms")

    def __call__(self):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(self.url, timeout=self.timeout)
                html = page.content()
                title = page.title()
                browser.close()
        except Exception as e:
            return {"error": str(e), "url": self.url}

        soup = BeautifulSoup(html, "html.parser")
        article = soup.find("article")
        if article:
            text = article.get_text(separator="\n").strip()
        else:
            ps = soup.find_all("p")
            if ps:
                text = "\n\n".join([p.get_text().strip() for p in ps[:200]])
            else:
                text = soup.get_text(separator="\n").strip()

        return {"url": self.url, "title": title, "text": text, "html": html}