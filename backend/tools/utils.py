import os
import asyncio
from typing import Callable, Any
import httpx
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv(r"C:\Users\89635\Desktop\Study\PYTHON\python clawer\FINHUB\.env")

SERPER_API_KEY = os.getenv("SERPER_API_KEY")

def serper_search_sync(query: str, top_k: int = 5):
    """同步 serper search 调用，返回简化列表"""
    if not SERPER_API_KEY:
        raise RuntimeError("SERPER_API_KEY not set")
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    payload = {"q": query, "num": top_k}
    r = httpx.post("https://google.serper.dev/search", headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    items = []
    for it in (data.get("organic", []) or [])[:top_k]:
        items.append({
            "title": it.get("title"),
            "url": it.get("link"),
            "snippet": it.get("snippet"),
            "date": it.get("date"),
            "site": it.get("source"),
        })
    return items

async def serper_search(query: str, top_k: int = 5):
    # 调用阻塞函数在线程池中运行以便与 async 兼容
    return await asyncio.to_thread(serper_search_sync, query, top_k)

# def fetch_page_sync(url: str, wait_selector: str | None = None, timeout: int = 15000, full_text: bool = False):
#     """使用 playwright 同步抓取 HTML 并尽量抽取正文（一个简单版本）"""
#     with sync_playwright() as p:
#         browser = p.chromium.launch(headless=True)
#         page = browser.new_page()
#         page.goto(url, timeout=timeout)
#         if wait_selector:
#             try:
#                 page.wait_for_selector(wait_selector, timeout=timeout)
#             except:
#                 pass
#         title = page.title()
#         html = page.content()
#         # 尝试提取日期和正文的简单 heuristics
#         date = None
#         try:
#             # 常见 meta tags
#             el = page.query_selector('meta[property="article:published_time"]')
#             if el:
#                 date = el.get_attribute("content")
#             if not date:
#                 el = page.query_selector('time')
#                 if el:
#                     date = el.inner_text()
#         except Exception:
#             date = None

#         text = None
#         if full_text:
#             try:
#                 # 一个简单的正文抽取：取文章主体可能的 selector
#                 for sel in ["article", "main", ".article", ".post", "#article", ".content", ".entry-content"]:
#                     el = page.query_selector(sel)
#                     if el:
#                         text = el.inner_text()
#                         break
#                 if not text:
#                     text = page.inner_text("body")
#             except Exception:
#                 text = None

#         browser.close()
#         return {"title": title, "html": html, "date": date, "text": text}
    
# async def fetch_page(url: str, wait_selector: str | None = None, timeout: int = 15000, full_text: bool = False):
#     return await asyncio.to_thread(fetch_page_sync, url, wait_selector, timeout, full_text)