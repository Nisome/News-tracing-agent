from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict, Any

class TraceRequest(BaseModel):
    query: str
    depth: int = 2
    top_k: int = 5
    fetch_text: bool = False

class SearchResult(BaseModel):
    title: Optional[str] = None
    url: Optional[HttpUrl] = None
    snippet: Optional[str] = None
    date: Optional[str] = None
    site: Optional[str] = None
    text: Optional[str] = None

class TraceNode(BaseModel):
    id: str
    title: Optional[str] = None
    url: Optional[HttpUrl] = None
    date: Optional[str] = None
    site: Optional[str] = None
    snippet: Optional[str] = None
    text: Optional[str] = None
    score: Optional[float] = None
    meta: Optional[Dict[str, Any]] = None

class TraceEdge(BaseModel):
    source: str
    target: str
    relation: Optional[str] = None
    weight: Optional[float] = None

# class TraceResult(BaseModel):
#     query: str
#     nodes: List[TraceNode]
#     edges: List[TraceEdge]
#     raw_search: Optional[List[SearchResult]] = None

class TraceResult(BaseModel):
    query: str
    nodes: List[TraceNode]
    edges: List[TraceEdge]
    summary: Optional[str] = None      # AI 总结
    graph_html: Optional[str] = None  # 交互式因果图 HTML