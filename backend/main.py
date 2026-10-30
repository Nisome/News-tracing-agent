import os
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from backend.agent import NewsTracer
from backend.tools.models import TraceRequest
from dotenv import load_dotenv
import asyncio
import json
from backend.tools.playwright_scraper import PlaywrightScraperTool
from mira.types import SystemMessage, HumanMessage, ToolMessage, AIMessage

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class FetchReq(BaseModel):
    id: str
    url: str

class AnalyzeRequest(BaseModel):
    query: str
    mode: str = "news"  # "news" 或 "finance"

tracer = NewsTracer()  # 根据你的可用模型调整

@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    try:
        if req.mode == "finance":
            # 金融模式：让 AI 自由调用工具
            from backend.tools.financial_analyze_akshare import FinancialDataToolAkshare
            messages = [
                SystemMessage(content="你是一个专业的金融分析师。用户询问股票时，请使用 FinancialDataToolAkshare 获取真实数据并进行分析。直接输出分析结果和图表说明。"),
                HumanMessage(content=req.query)
            ]
            response = await tracer.llm.forward(messages=messages, tools=[FinancialDataToolAkshare])
            
            # 获取最终文本 + 工具调用结果
            # mira 返回的是消息列表的列表，每个元素是一个消息列表
            content = ""
            tool_results = []
            if response and len(response) > 0:
                messages_list = response[0] if isinstance(response[0], list) else response
                logger.info(f"收到 {len(messages_list)} 条消息")
                
                # 先提取工具结果
                for msg in messages_list:
                    logger.debug(f"消息类型: {type(msg).__name__}, name: {getattr(msg, 'name', None)}")
                    if isinstance(msg, ToolMessage) and msg.name == "FinancialDataToolAkshare":
                        try:
                            # 解析工具返回结果
                            logger.info(f"找到工具消息，content 类型: {type(msg.content)}")
                            if isinstance(msg.content, str):
                                import ast
                                try:
                                    result = ast.literal_eval(msg.content)
                                    logger.info(f"成功解析工具结果: {type(result)}")
                                    # 检查是否有错误
                                    if isinstance(result, dict) and "error" in result:
                                        logger.warning(f"工具返回错误: {result['error']}")
                                    tool_results.append(result)
                                except (ValueError, SyntaxError) as e:
                                    # 如果 literal_eval 失败，尝试 json.loads
                                    try:
                                        result = json.loads(msg.content)
                                        tool_results.append(result)
                                    except:
                                        logger.error(f"解析工具结果失败: {e}, content: {msg.content[:200]}")
                                        # 即使解析失败，也将原始内容作为错误返回
                                        tool_results.append({"error": f"解析工具结果失败: {msg.content[:200]}"})
                            elif isinstance(msg.content, dict):
                                tool_results.append(msg.content)
                        except Exception as e:
                            import traceback
                            logger.error(f"处理工具消息失败: {traceback.format_exc()}")
                            tool_results.append({"error": f"处理工具消息失败: {str(e)}"})
                
                # 如果有工具结果，再次调用 LLM 获取分析结果
                if tool_results:
                    logger.info(f"找到 {len(tool_results)} 个工具结果，获取 LLM 分析")
                    # 将工具结果添加到消息中，再次调用 LLM 获取最终分析
                    analysis_messages = messages + messages_list
                    final_response = await tracer.llm.forward(messages=analysis_messages, tools=[])
                    if final_response and len(final_response) > 0:
                        final_messages = final_response[0] if isinstance(final_response[0], list) else final_response
                        # 获取最后一条 AIMessage 的内容
                        for msg in reversed(final_messages):
                            if isinstance(msg, AIMessage) and msg.content:
                                content = msg.content
                                logger.info(f"获取到 LLM 分析内容: {len(content)} 字符")
                                break
                else:
                    # 没有工具调用，直接提取文本内容
                    for msg in messages_list:
                        if isinstance(msg, AIMessage) and msg.content:
                            content += str(msg.content) + "\n"
            
            logger.info(f"返回结果: content长度={len(content)}, tool_results数量={len(tool_results)}")
            return {
                "content": content.strip() if content.strip() else "分析完成，请查看图表数据。",
                "tool_results": tool_results
            }

        else:
            # 新闻溯源模式（保持你原来的逻辑）
            trace_req = TraceRequest(query=req.query, depth=2, top_k=5, fetch_text=False)
            result = await tracer.run_trace(trace_req)
            # 使用 model_dump() 而不是 dict()（兼容 Pydantic v2）
            if hasattr(result, 'model_dump'):
                return result.model_dump()
            elif hasattr(result, 'dict'):
                return result.dict()
            else:
                # 如果已经是字典，直接返回
                return result if isinstance(result, dict) else {"error": "Unexpected result type"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/fetch_page")
async def fetch_page(req: FetchReq):
    try:
        tool = PlaywrightScraperTool(url=str(req.url))
        res = await asyncio.to_thread(tool.__call__)
        return {"id": req.id, "text": res.get("text",""), "title": res.get("title","")}
    except Exception as e:
        return {"id": req.id, "text": "", "error": str(e)}

@app.get("/api/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)