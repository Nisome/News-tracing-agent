from pydantic import BaseModel
from typing import List, Any
from backend.tools import models
from backend.tools.utils import serper_search
import uuid
import asyncio

class GoogleSearchTool(BaseModel):
    """Google/serper 搜索工具包装"""
    query: str
    top_k: int = 5

    async def run(self) -> List[models.SearchResult]:
        items = await serper_search(self.query, self.top_k)
        results = []
        for it in items:
            results.append(models.SearchResult(
                title=it.get("title") or "",
                url=it.get("url"),
                snippet=it.get("snippet"),
                date=it.get("date"),
                site=it.get("site"),
            ))
        return results

# class PlaywrightScraperTool(BaseModel):
#     url: str
#     fetch_text: bool = False

#     async def run(self):
#         res = await fetch_page(self.url, full_text=self.fetch_text)
#         return {
#             "id": str(uuid.uuid4()),
#             "title": res.get("title"),
#             "date": res.get("date"),
#             "text": res.get("text"),
#             "html": res.get("html"),
#         }