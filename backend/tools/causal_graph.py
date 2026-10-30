# backend/tools/causal_graph_tool.py
from pydantic import Field
from mira.types import LLMTool
from typing import Any
from pyvis.network import Network
import tempfile
import json

class CausalGraphTool(LLMTool):
    """
    接受 nodes_json（字符串或 json 可解析的结构），和 relations_json。
    返回 pyvis 生成的 html 字符串（可直接在前端嵌入）。
    """
    nodes_json: str = Field(..., description="节点的 JSON 字符串，格式: [{id:..., title:...}, ...]")
    edges_json: str = Field(..., description="边的 JSON 字符串, 格式: [{source:..., target:..., relation:...}, ...]")

    def __call__(self) -> dict:
        nodes = json.loads(self.nodes_json)
        edges = json.loads(self.edges_json)
        net = Network(height="600px", width="100%", directed=True, notebook=False)
        net.barnes_hut()
        for n in nodes:
            net.add_node(n["id"], label=(n.get("title") or "")[:80], title=n.get("title",""))
        for e in edges:
            net.add_edge(e["source"], e["target"], title=e.get("relation",""))
        net.set_options("""
        var options = {
          "physics": {"enabled": true, "stabilization": {"iterations": 100}},
          "interaction": {"hover": true, "navigationButtons": true}
        }
        """)
        # 使用 write_html 方法生成 HTML，避免 template 为 None 的问题
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode='w', encoding='utf-8')
        tmp.close()
        try:
            net.write_html(tmp.name, open_browser=False, notebook=False)
            with open(tmp.name, "r", encoding="utf-8") as f:
                html = f.read()
        finally:
            import os
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)
        return {"html": html}