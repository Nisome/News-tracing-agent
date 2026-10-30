# backend/tools/financial_data_tool_akshare.py
import akshare as ak
import json
from pydantic import Field
from mira.types import LLMTool
from typing import Dict
import datetime
from datetime import timedelta
import time
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

class FinancialDataToolAkshare(LLMTool):
    """
    使用 akshare 获取股票历史数据，进行分析，并生成 Chart.js 图表配置。
    支持A股和港股（如 000001、600519、01810）
    """
    symbol: str = Field("000001", description="股票代码，例如：000001（平安银行）、600519（贵州茅台）、01810（小米）")
    period: str = Field(
        "2y",
        description="时间范围，可选：1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max（默认2年）"
    )

    def _convert_period_to_dates(self, period: str) -> tuple:
        """将period字符串转换为开始和结束日期"""
        end_date = datetime.datetime.now()
        
        if period == "1mo":
            start_date = end_date - timedelta(days=30)
        elif period == "3mo":
            start_date = end_date - timedelta(days=90)
        elif period == "6mo":
            start_date = end_date - timedelta(days=180)
        elif period == "1y":
            start_date = end_date - timedelta(days=365)
        elif period == "2y":
            start_date = end_date - timedelta(days=730)
        elif period == "5y":
            start_date = end_date - timedelta(days=1825)
        elif period == "10y":
            start_date = end_date - timedelta(days=3650)
        elif period == "ytd":
            start_date = datetime.datetime(end_date.year, 1, 1)
        elif period == "max":
            start_date = datetime.datetime(2000, 1, 1)  # 设置一个较早的日期
        else:
            # 默认2年
            start_date = end_date - timedelta(days=730)
        
        return start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")

    def _get_stock_data_akshare(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """使用akshare获取股票数据"""
        try:
            # 判断是A股还是港股
            if '.' in symbol:
                # 可能是港股格式，如 01810.HK
                if '.HK' in symbol.upper():
                    # 港股
                    hk_symbol = symbol.replace('.HK', '').replace('.hk', '').strip()
                    # 港股代码需要补齐5位
                    if len(hk_symbol) == 4:
                        hk_symbol = '0' + hk_symbol
                    df = ak.stock_hk_hist(symbol=hk_symbol, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
                    if df is None or df.empty:
                        # 尝试不指定日期范围
                        df = ak.stock_hk_hist(symbol=hk_symbol, period="daily", adjust="qfq")
                else:
                    # A股，去掉后缀
                    a_symbol = symbol.split('.')[0]
                    df = ak.stock_zh_a_hist(symbol=a_symbol, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
            elif symbol.startswith('0') or symbol.startswith('3') or symbol.startswith('6'):
                # A股：0/3开头是深市，6开头是沪市
                df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
            else:
                # 假设是港股（5位数字）
                if len(symbol) == 4:
                    symbol = '0' + symbol
                df = ak.stock_hk_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
                if df is None or df.empty:
                    df = ak.stock_hk_hist(symbol=symbol, period="daily", adjust="qfq")
            
            if df is None or df.empty:
                return pd.DataFrame()
            
            # 标准化列名
            if '日期' in df.columns:
                df = df[['日期', '开盘', '收盘', '最高', '最低', '成交量']].copy()
                df.columns = ['date', 'open', 'close', 'high', 'low', 'volume']
            elif 'date' in df.columns:
                # 已经是标准格式
                df = df[['date', 'open', 'close', 'high', 'low', 'volume']].copy()
            else:
                return pd.DataFrame()
            
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)
            
            return df
            
        except Exception as e:
            return pd.DataFrame()

    def __call__(self) -> Dict:
        max_retries = 3
        retry_delay = 2  # 秒
        
        for attempt in range(max_retries):
            try:
                # 如果不是第一次尝试，先等待
                if attempt > 0:
                    wait_time = retry_delay * attempt
                    time.sleep(wait_time)
                
                # 转换period为日期范围
                start_date, end_date = self._convert_period_to_dates(self.period)
                
                # 获取股票数据
                df = self._get_stock_data_akshare(self.symbol, start_date, end_date)
                
                if df.empty:
                    return {"error": f"未找到股票代码 '{self.symbol}' 的数据，请检查代码是否正确"}
                
                # 提取数据
                dates = df['date'].dt.strftime("%Y-%m-%d").tolist()
                closes = df['close'].round(2).tolist()
                opens = df['open'].round(2).tolist()
                highs = df['high'].round(2).tolist()
                lows = df['low'].round(2).tolist()
                volumes = df['volume'].tolist()

                # 基础分析
                latest_price = closes[-1]
                avg_price = sum(closes) / len(closes)
                max_price = max(closes)
                min_price = min(closes)
                price_change = closes[-1] - closes[0]
                pct_change = (price_change / closes[0]) * 100 if closes[0] != 0 else 0

                # 尝试获取公司名称
                company_name = self.symbol
                try:
                    # 对于A股，尝试获取股票基本信息
                    clean_symbol = self.symbol.replace('.SH', '').replace('.SZ', '').replace('.HK', '').replace('.hk', '').strip()
                    if clean_symbol.startswith(('0', '3', '6')):
                        # A股：0/3开头是深市，6开头是沪市
                        stock_info = ak.stock_individual_info_em(symbol=clean_symbol)
                        if stock_info is not None and not stock_info.empty:
                            # 尝试获取股票简称
                            if 'item' in stock_info.columns and 'value' in stock_info.columns:
                                name_rows = stock_info[stock_info['item'] == '股票简称']
                                if not name_rows.empty:
                                    company_name = name_rows['value'].iloc[0]
                except Exception:
                    pass

                analysis = (
                    f"**{company_name} ({self.symbol}) 股价分析**\n\n"
                    f"时间范围：{self.period}（共 {len(dates)} 个交易日）\n"
                    f"最新收盘价：**¥{latest_price:.2f}**\n"
                    f"平均价格：¥{avg_price:.2f}\n"
                    f"最高价：¥{max_price:.2f}\n"
                    f"最低价：¥{min_price:.2f}\n"
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
                error_str = str(e)
                # 检查是否是速率限制或连接错误
                if any(keyword in error_str.lower() for keyword in ["rate limited", "too many requests", "429", "timeout", "connection"]):
                    if attempt < max_retries - 1:
                        # 还有重试机会，继续循环（延迟在循环开始处处理）
                        continue
                    else:
                        # 最后一次重试失败
                        return {"error": f"获取股票数据失败：{error_str}。已重试{max_retries}次，请稍后再试。"}
                else:
                    # 其他错误直接返回，不重试
                    return {"error": f"获取股票数据失败：{error_str}"}
        
        # 如果所有重试都失败（不应该到达这里，因为上面都有return）
        return {"error": "获取股票数据失败：未知错误，已重试多次"}

