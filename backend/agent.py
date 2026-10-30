import os
import asyncio
import json
import traceback
from typing import List, Dict, Any, Optional, Union
from uuid import uuid4

from loguru import logger
from dotenv import load_dotenv

from mira.args import OpenAIArgs
from mira.openrouter import OpenRouterLLM
from mira.types import SystemMessage, HumanMessage, AIMessage, ToolMessage
from backend.tools.toolspackage import GoogleSearchTool
from backend.tools.playwright_scraper import PlaywrightScraperTool
from backend.tools.causal_graph import CausalGraphTool
from backend.tools.models import (
    TraceResult, TraceNode, TraceEdge, 
    TraceRequest, SearchResult
)

# 加载环境变量
load_dotenv()

class NewsTracer:
    def __init__(self, max_concurrency: int = 5):
        # 初始化LLM（用于AI决策是否继续递归溯源）
        api_key = os.getenv("DB_API_KEY")
        base_url = os.getenv("DB_BASE_URL")
        model = os.getenv("MODEL")
        
        if not api_key:
            raise ValueError("DB_API_KEY environment variable is required. Please set it in .env file.")
        if not model:
            raise ValueError("MODEL environment variable is required. Please set it in .env file.")
        
        llm_args = OpenAIArgs(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.7,
            max_completion_tokens=2000,
            verbose=True
        )
        self.llm = OpenRouterLLM(args=llm_args)
        self.semaphore = asyncio.Semaphore(max_concurrency)  # 限制并发任务数
        self.nodes: Dict[str, TraceNode] = {}  # 存储所有节点（id: TraceNode）
        self.edges: List[TraceEdge] = []  # 存储因果关系边

    async def _call_llm(self, messages: List[Union[SystemMessage, HumanMessage]]) -> str:
        """封装LLM调用，用于判断是否继续递归溯源"""
        try:
            dm = await self.llm.forward(messages=messages)
            if dm and len(dm) > 0 and len(dm[0]) > 0:
                return dm[0][-1].content.strip()  # 返回AI决策结果
            return "NO"  # 默认不继续
        except Exception as e:
            logger.error(f"LLM调用失败: {traceback.format_exc()}")
            return "NO"

    async def _should_recurse(self, node: TraceNode) -> (bool, str):
        """
        调用AI判断是否需要对当前节点继续溯源：
        - 输入：节点的标题和摘要
        - 输出：(是否继续, 新的搜索关键词)
        """
        system_prompt = SystemMessage(content="""
        你是一个新闻溯源决策助手。给定一条新闻的标题和摘要，请判断是否需要进一步搜索其原始来源/引用以验证真实性。
        输出格式：
        - 需要继续：返回 "YES::关键词"（关键词为建议的搜索词，如事件核心主体+时间+来源类型）
        - 无需继续：返回 "NO"
        """)
        human_prompt = HumanMessage(content=f"""
        新闻标题：{node.title or '无标题'}
        新闻摘要：{node.snippet or '无摘要'}
        请判断是否需要继续搜索原始来源？
        """)
        decision = await self._call_llm([system_prompt, human_prompt])
        
        if decision.startswith("YES"):
            keywords = decision.split("::")[-1].strip() if "::" in decision else node.title
            return True, keywords
        return False, ""

    async def _fetch_news_metadata(self, search_result: Any) -> TraceNode:
    # 辅助取值函数：优先 dict.get，再尝试 getattr，再尝试 pydantic model 的 dict()
        def _val(obj, *keys, default=""):
            # keys 用来尝试多个可能的字段名
            if obj is None:
                return default
            if isinstance(obj, dict):
                for k in keys:
                    if k in obj and obj[k] not in (None, ""):
                        return obj[k]
                return default
            # pydantic model 或任意对象：先尝试 getattr
            for k in keys:
                if hasattr(obj, k):
                    v = getattr(obj, k)
                    if v not in (None, ""):
                        return v
            # 最后尝试 obj.dict() if available
            try:
                d = obj.dict()
                for k in keys:
                    if k in d and d[k] not in (None, ""):
                        return d[k]
            except Exception:
                pass
            return default

        title = _val(search_result, "title", "headline", default="无标题")
        url = _val(search_result, "link", "url", default="")
        date = _val(search_result, "date", "published", default=None)
        snippet = _val(search_result, "snippet", "summary", default="无摘要")
        text = _val(search_result, "text", "content", default="")

        node_id = str(uuid4())

        # 如果 TraceNode 的 url 字段是 HttpUrl 严格类型，确保它是合法字符串或传 None
        if url == "":
            url_value = None
        else:
            url_value = str(url)

        # 构造 TraceNode，尽量用显式参数，若失败再用 kwargs 回退
        try:
            node = TraceNode(id=node_id, title=title, url=url_value, date=date, snippet=snippet, text=text)
        except Exception:
            # 兼容不同 TraceNode 签名
            node = TraceNode(**{"id": node_id, "title": title, "url": url_value, "date": date, "snippet": snippet, "text": text})

        # 记录调试信息，便于排查
        logger.debug(f"Created TraceNode from search result: id={node_id}, title={title[:100]}, url={url_value}")

        return node



    async def _recursive_trace(
        self, 
        query: str, 
        depth: int, 
        top_k: int, 
        parent_node_id: Optional[str] = None
    ) -> None:
        """
        递归溯源核心逻辑：
        1. 当前深度为0时停止递归
        2. 调用GoogleSearchTool搜索query
        3. 提取结果元数据生成节点，加入因果图
        4. 调用AI判断是否需要对每个节点继续溯源（递归）
        """
        if depth <= 0:
            logger.info(f"递归深度耗尽（当前depth={depth}），停止溯源")
            return

        logger.info(f"开始递归溯源（query={query}, depth={depth}, parent_node_id={parent_node_id}）")

        # 1. 调用谷歌搜索工具（仅用搜索获取元数据，不调用Playwright）
        try:
            search_tool = GoogleSearchTool(query=query, top_k=top_k)  # 假设工具接收query和top_k参数
            search_results: List[Dict[str, Any]] = await search_tool.run()  # 参考test_tool.py的工具返回格式
            logger.info(f"搜索完成，获取{len(search_results)}条结果")
        except Exception as e:
            logger.error(f"搜索工具调用失败: {traceback.format_exc()}")
            return

        # 2. 遍历搜索结果，生成节点并加入因果图
        for result in search_results:
            # 2.1 生成节点（仅用搜索结果元数据，不调用Playwright）
            node = await self._fetch_news_metadata(result)
            self.nodes[node.id] = node  # 存入节点字典

            # 2.2 添加因果边（若有父节点，建立parent -> current的关系）
            if parent_node_id:
                edge = TraceEdge(
                    source=parent_node_id,
                    target=node.id,
                    relation="supports",  # 关系类型：支持/引用/反驳（可后续用LLM优化）
                    weight=1.0
                )
                self.edges.append(edge)

            # 3. 调用AI判断是否需要继续递归溯源当前节点
            need_recurse, new_query = await self._should_recurse(node)
            if need_recurse and new_query:
                logger.info(f"AI决策：需要对节点{node.id}继续溯源，新关键词={new_query}")
                await self._recursive_trace(
                    query=new_query,
                    depth=depth - 1,  # 深度减1
                    top_k=top_k,
                    parent_node_id=node.id  # 当前节点作为下一层的父节点
                )
            else:
                logger.info(f"AI决策：节点{node.id}无需继续溯源")

    async def _ask_llm_to_build_graph(self, nodes: List[TraceNode]):
        # 准备 nodes/edges 简化列表，让 LLM 分析并调用 CausalGraphTool
        nodes_short = [{"id": n.id, "title": n.title, "snippet": n.snippet or ""} for n in nodes]
        nodes_json = json.dumps(nodes_short, ensure_ascii=False)
        # 提示 LLM：只返回需要调用工具的指令（调用 CausalGraphTool）
        system = SystemMessage(content="你是一个因果判定助手。请判断这些条目间的高置信度因果/引用关系，然后调用工具生成交互式图。")
        human = HumanMessage(content=f"条目列表（最多 20 条）：\n{nodes_json}\n\n请调用 CausalGraphTool，并把 nodes_json 以及 relations_json（仅包含判定为关系的三元组）作为参数。")

        # 将工具类传给 llm.forward，mira 会自动执行工具并返回 ToolMessage
        dm = await self.llm.forward(messages=[system, human], tools=[CausalGraphTool])
        # mira 返回的消息列表，每个元素是一个消息列表
        if dm and len(dm) > 0:
            messages = dm[0] if isinstance(dm[0], list) else dm
            # 查找 ToolMessage（mira 自动执行工具后的返回结果）
            for msg in messages:
                if isinstance(msg, ToolMessage) and msg.name == "CausalGraphTool":
                    # ToolMessage.content 是工具返回结果的字符串表示
                    # mira 使用 str(result) 转换，所以是 Python dict 的字符串表示
                    try:
                        if isinstance(msg.content, str):
                            # 尝试使用 ast.literal_eval 解析 Python 字面量（安全）
                            import ast
                            result = ast.literal_eval(msg.content)
                            html = result.get("html", "")
                            if html:
                                return html
                        elif isinstance(msg.content, dict):
                            html = msg.content.get("html", "")
                            if html:
                                return html
                    except Exception as e:
                        logger.debug(f"解析 ToolMessage content 失败: {e}, content: {str(msg.content)[:200]}")
                        continue
        return None

    async def _summarize_nodes(self, nodes: List[TraceNode]) -> str:
        system = SystemMessage(content="你是新闻摘要助手，请基于下面的条目给出：1) 50-120 字中立总结 2) 关键证据点 3) 可信度建议（高/中/低）")
        enumerated = "\n".join([f"{i}. 标题: {n.title}\n摘要: {n.snippet or ''}\nURL: {n.url}" for i,n in enumerate(nodes)])
        human = HumanMessage(content=enumerated + "\n\n请输出 JSON：{\"summary\":\"...\",\"evidence\":[...],\"confidence\":\"high|mid|low\"}")
        reply = await self.llm.forward(messages=[system, human])
        # reply 解析略，通常在 dm[0][-1].content 中
        if reply and len(reply)>0 and len(reply[0])>0:
            return reply[0][-1].content
        return ""

    async def run_trace(self, req: TraceRequest) -> TraceResult:
        """主入口：接收TraceRequest，返回带因果图的TraceResult"""

        self.nodes = {}  # 重置节点和边
        self.edges = []
        query = (req.query or "").strip()
        depth = req.depth or 2
        top_k = req.top_k or 5

        if not query:
            return TraceResult(query="", nodes=[], edges=[])

        try:
            # 1) 递归溯源，填充 self.nodes/self.edges（如果 _recursive_trace 会追加边）
            await self._recursive_trace(
                query=query,
                depth=depth,
                top_k=top_k,
                parent_node_id=None
            )

            # 将节点转换为列表，方便后续处理
            nodes_list = list(self.nodes.values())

            # 2) 用 LLM 对节点生成摘要（溯源完成后再做）
            try:
                summary = await self._summarize_nodes(nodes_list)
            except Exception:
                logger.exception("生成摘要失败")
                summary = ""

            # 3) 用 LLM 推断节点间高置信度关系，追加到 self.edges
            # 注意：_infer_relations 方法尚未实现，暂时跳过
            # try:
            #     await self._infer_relations(self.nodes, self.edges)
            # except Exception:
            #     logger.exception("LLM 推断关系失败，继续后续流程")

            # 4) 让 LLM 调用工具生成交互式因果图（优先），若 LLM 未调用工具则回退到本地生成
            graph_html = None
            try:
                # 对于图/LLM 输入，限制节点数量以防超长 prompt
                limited_nodes = nodes_list[:20]
                graph_html = await self._ask_llm_to_build_graph(limited_nodes)

                # 如果 LLM 没有返回 html，则用本地工具生成（回退）
                if not graph_html:
                    logger.info("LLM 未返回 graph_html，使用本地 CausalGraphTool 回退生成")
                    nodes_short = [{"id": n.id, "title": n.title} for n in limited_nodes]
                    # 只保留 limited_nodes 范围内的边
                    allowed_ids = {n["id"] for n in nodes_short}
                    edges_short = []
                    for e in self.edges:
                        try:
                            sid = e.source
                            tid = e.target
                            if sid in allowed_ids and tid in allowed_ids:
                                edges_short.append({
                                    "source": sid,
                                    "target": tid,
                                    "relation": getattr(e, "relation", "") or ""
                                })
                        except Exception:
                            continue

                    tool = CausalGraphTool(
                        nodes_json=json.dumps(nodes_short, ensure_ascii=False),
                        edges_json=json.dumps(edges_short, ensure_ascii=False)
                    )
                    res = await asyncio.to_thread(tool.__call__)
                    graph_html = res.get("html")
            except Exception:
                logger.exception("生成交互式因果图失败，跳过 graph_html")

            # 5) 返回 TraceResult（确保 TraceResult 支持 summary 与 graph_html 字段）
            return TraceResult(
                query=query,
                nodes=nodes_list,
                edges=self.edges,
                summary=summary,
                graph_html=graph_html
            )

        except Exception:
            logger.error(f"溯源主流程失败: {traceback.format_exc()}")
            return TraceResult(query=query, nodes=[], edges=[])

    async def trace(self, req: TraceRequest) -> TraceResult:
        """兼容FastAPI路由调用的别名方法"""
        return await self.run_trace(req)

# 测试代码
if __name__ == "__main__":
    async def test():
        tracer = NewsTracer()
        req = TraceRequest(
            query="特斯拉 2024 销量",
            depth=2,
            top_k=3,
            fetch_text=True  # 测试抓取全文
        )
        result = await tracer.run_trace(req)
        print(f"溯源结果：{json.dumps(result.dict(), ensure_ascii=False, indent=2)}")

    asyncio.run(test())