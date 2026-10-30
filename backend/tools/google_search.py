# backend/tools/toolspackage.py 或新建 google_search_tool.py

from mira.types import LLMTool
from pydantic import Field
import requests  # 或你原来的搜索库
import json
from dotenv import load_dotenv

load_dotenv(r"C:\Users\89635\Desktop\Study\PYTHON\python clawer\FINHUB\.env")

class GoogleSearchTool(LLMTool):
    """
    使用 Google 搜索（或 Serper、SerpAPI 等）进行网页搜索
    """
    query: str = Field(..., description="搜索关键词")
    num_results: int = Field(10, ge=1, le=30, description="返回结果数量，1-30")

    def __call__(self) -> dict:
        # 这里放你原来的搜索逻辑
        # 示例（如果你用的是 serper.dev）：
        api_key = os.getenv("SERPER_API_KEY")  # 或你的搜索 API key
        if not api_key:
            return {"error": "搜索 API Key 未配置"}

        url = "https://google.serper.dev/search"
        payload = json.dumps({"q": self.query, "num": self.num_results})
        headers = {
            'X-API-KEY': api_key,
            'Content-Type': 'application/json'
        }

        try:
            response = requests.post(url, headers=headers, data=payload)
            if response.status_code == 200:
                results = response.json()
                organic = results.get("organic", [])[:self.num_results]
                formatted = []
                for r in organic:
                    formatted.append({
                        "title": r.get("title"),
                        "url": r.get("link"),
                        "snippet": r.get("snippet")
                    })
                return {"results": formatted}
            else:
                return {"error": f"搜索失败: {response.status_code} {response.text}"}
        except Exception as e:
            return {"error": str(e)}