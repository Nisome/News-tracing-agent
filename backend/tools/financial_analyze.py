# backend/tools/financial_data_tool.py
import yfinance as yf
import json
from pydantic import Field
from mira.types import LLMTool
from typing import Dict
import datetime

class FinancialDataTool(LLMTool):
    """
    使用 yfinance 获取股票历史数据，进行分析，并生成 Chart.js 图表配置。
    支持全球股票（如 AAPL、TSLA、00700.HK、600519.SH）
    """
    symbol: str = Field("AAPL", description="股票代码，例如：AAPL（苹果）、TSLA、600519.SH（茅台）、BTC-USD（比特币）")
    period: str = Field(
        "2y",
        description="时间范围，可选：1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max（默认2年）"
    )

    def __call__(self) -> Dict:
        try:
            # 下载数据
            ticker = yf.Ticker(self.symbol)
            hist = ticker.history(period=self.period)

            if hist.empty:
                return {"error": f"未找到股票代码 '{self.symbol}' 的数据，请检查代码是否正确（如加 .HK 或 .SH）"}

            # 重置索引，获取日期
            hist = hist.reset_index()
            dates = hist['Date'].dt.strftime("%Y-%m-%d").tolist()
            closes = hist['Close'].round(2).tolist()
            opens = hist['Open'].round(2).tolist()
            highs = hist['High'].round(2).tolist()
            lows = hist['Low'].round(2).tolist()
            volumes = hist['Volume'].tolist()

            # 基础分析
            latest_price = closes[-1]
            avg_price = sum(closes) / len(closes)
            max_price = max(closes)
            min_price = min(closes)
            price_change = closes[-1] - closes[0]
            pct_change = (price_change / closes[0]) * 100 if closes[0] != 0 else 0

            # 公司名称（如果有）
            info = ticker.info
            company_name = info.get("longName") or info.get("shortName") or self.symbol

            analysis = (
                f"**{company_name} ({self.symbol}) 股价分析**\n\n"
                f"时间范围：{self.period}（共 {len(dates)} 个交易日）\n"
                f"最新收盘价：**${latest_price:.2f}**\n"
                f"平均价格：${avg_price:.2f}\n"
                f"最高价：${max_price:.2f}\n"
                f"最低价：${min_price:.2f}\n"
                f"涨跌额：{'+' if price_change >= 0 else ''}{price_change:.2f}\n"
                f"涨幅：{'+' if pct_change >= 0 else ''}{pct_change:.2f}%\n"
            )

            # 采样数据点（最多100个，避免前端卡顿）
            max_points = 100
            if len(dates) > max_points:
                step = len(dates) // max_points
                sampled_dates = dates[::step][:max_points]
                sampled_closes = closes[::step][:max_points]
            else:
                sampled_dates = dates
                sampled_closes = closes

            # Chart.js 配置（深色主题友好）
            chart_config = {
                "type": "line",
                "data": {
                    "labels": sampled_dates,
                    "datasets": [{
                        "label": "收盘价",
                        "data": sampled_closes,
                        "borderColor": "#00ffff",
                        "backgroundColor": "rgba(0, 255, 255, 0.1)",
                        "fill": True,
                        "tension": 0.4,
                        "pointRadius": 1,
                        "borderWidth": 2
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": f"{company_name} 股价走势",
                            "color": "#ffffff",
                            "font": {"size": 20}
                        },
                        "legend": {"display": False}
                    },
                    "scales": {
                        "x": {
                            "ticks": {"color": "#aaaaaa", "maxTicksLimit": 10},
                            "grid": {"color": "rgba(100,100,100,0.2)"}
                        },
                        "y": {
                            "ticks": {"color": "#aaaaaa"},
                            "grid": {"color": "rgba(100,100,100,0.2)"}
                        }
                    }
                }
            }

            return {
                "analysis": analysis,
                "chart_config": json.dumps(chart_config),
                "symbol": self.symbol,
                "company_name": company_name,
                "period": self.period
            }

        except Exception as e:
            return {"error": f"获取股票数据失败：{str(e)}"}