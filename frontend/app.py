import streamlit as st
import streamlit.components.v1 as components
import requests
import networkx as nx
import matplotlib.pyplot as plt
import os
import json

plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000")

# ====================== 夸克AI 风格 CSS ======================
st.markdown("""
<style>
    /* 全局背景 */
    .main {
        background: linear-gradient(135deg, #0f1620, #1a2330);
        color: #e0e0e0;
        min-height: 100vh;
    }

    /* 大标题 */
    .big-title {
        text-align: center;
        font-size: 4.8rem !important;
        font-weight: 300;
        color: #ffffff;
        margin: 4rem 0 1rem 0;
        letter-spacing: 5px;
    }

    /* 模式切换按钮 */
    .mode-buttons {
        display: flex;
        justify-content: center;
        gap: 2rem;
        margin: 2rem 0 5rem 0;
        flex-wrap: wrap;
    }
    .mode-btn {
        padding: 0.9rem 2.5rem;
        border-radius: 30px;
        font-size: 1.2rem;
        font-weight: 500;
        min-width: 180px;
        transition: all 0.3s;
        cursor: pointer;
    }

    /* 搜索框容器 */
    .search-container {
        max-width: 960px;
        margin: 0 auto 4rem auto;
        position: relative;
    }
    .stTextInput > div > div > input {
        background: rgba(30, 35, 45, 0.8) !important;
        backdrop-filter: blur(20px);
        border: 1px solid rgba(80, 120, 180, 0.5);
        border-radius: 40px !important;
        padding: 28px 120px 28px 40px !important;
        font-size: 1.6rem !important;
        color: #ffffff !important;
        height: 90px !important;
        box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
        box-sizing: border-box;
        line-height: 1.4;
    }
    .stTextInput > div > div > input::placeholder {
        color: #999999;
        font-size: 1.5rem;
    }
    .stTextInput > div > div > input:focus {
        border-color: #0066ff;
        box-shadow: 0 0 35px rgba(0, 102, 255, 0.6);
    }

    /* 搜索图标 */
    .search-icon::before {
        content: "🔍";
        position: absolute;
        right: 40px;
        top: 50%;
        transform: translateY(-50%);
        font-size: 2.2rem;
        color: #888888;
        pointer-events: none;
        z-index: 10;
    }

    /* 参数滑块 */
    .params-row {
        max-width: 900px;
        margin: 0 auto 4rem auto;
        display: flex;
        justify-content: center;
        gap: 3rem;
        flex-wrap: wrap;
    }

    /* 主按钮 */
    .stButton > button {
        background: linear-gradient(90deg, #0066ff, #00ccff);
        color: white;
        border: none;
        border-radius: 40px;
        padding: 1.2rem 4rem;
        font-size: 1.5rem;
        font-weight: 600;
        width: 320px;
        height: 70px;
        margin: 0 auto;
        display: block;
        box-shadow: 0 12px 40px rgba(0, 102, 255, 0.6);
    }
    .stButton > button:hover {
        box-shadow: 0 16px 50px rgba(0, 102, 255, 0.8);
        transform: translateY(-4px);
    }

    /* 结果卡片 */
    .result-card {
        background: rgba(25, 30, 45, 0.7);
        backdrop-filter: blur(15px);
        border: 1px solid rgba(70, 100, 150, 0.4);
        border-radius: 24px;
        padding: 2.2rem;
        margin: 2rem 0;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4);
    }

    .graph-section {
        background: rgba(20, 25, 40, 0.7);
        backdrop-filter: blur(15px);
        border: 1px solid rgba(70, 100, 150, 0.4);
        border-radius: 24px;
        padding: 2.5rem;
        margin: 3rem 0;
    }

    a { color: #00eeff; text-decoration: none; }
    a:hover { text-decoration: underline; }
</style>
""", unsafe_allow_html=True)

# ====================== 页面设置 ======================
st.set_page_config(page_title="溯源与分析智能体", layout="wide")

# 初始化模式
if "mode" not in st.session_state:
    st.session_state.mode = "news"

# 大标题
st.markdown('<div class="big-title">溯源与分析智能体</div>', unsafe_allow_html=True)

# 模式切换按钮
st.markdown('<div class="mode-buttons">', unsafe_allow_html=True)
col1, col2 = st.columns(2)
with col1:
    if st.button("📰 新闻溯源", use_container_width=True, 
                 type="primary" if st.session_state.mode == "news" else "secondary"):
        st.session_state.mode = "news"
        st.rerun()
with col2:
    if st.button("📈 金融数据分析", use_container_width=True, 
                 type="primary" if st.session_state.mode == "finance" else "secondary"):
        st.session_state.mode = "finance"
        st.rerun()
st.markdown('</div>', unsafe_allow_html=True)

# 搜索框
st.markdown('<div class="search-container">', unsafe_allow_html=True)
with st.form("main_form", clear_on_submit=False):
    query = st.text_input(
        "搜索查询",  # 提供一个非空的 label
        placeholder="搜索新闻、事件、公司、股票、热点话题…",
        label_visibility="collapsed",  # 这个设置会隐藏 label，但 label 本身不能为空
        key="query_input"
    )

    if st.session_state.mode == "news":
        st.markdown('<div class="params-row">', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            depth = st.slider("递归深度", 1, 4, 2)
        with col2:
            top_k = st.slider("每层搜索数量", 1, 8, 5)
        st.markdown('</div>', unsafe_allow_html=True)

    submitted = st.form_submit_button("开始分析" if st.session_state.mode == "finance" else "开始溯源")

st.markdown('<div class="search-icon"></div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# ====================== 提交处理 ======================
if submitted and query.strip():
    payload = {
        "query": query,
        "mode": st.session_state.mode
    }

    spinner_text = "正在深度溯源..." if st.session_state.mode == "news" else "正在分析金融数据..."
    with st.spinner(spinner_text):
        try:
            r = requests.post(BACKEND + "/api/analyze", json=payload, timeout=600)
            if r.status_code != 200:
                st.error(f"后端错误: {r.text}")
            else:
                data = r.json()

                if st.session_state.mode == "news":
                    # ================ 新闻溯源显示 ================
                    raw_summary = data.get("summary")
                    if raw_summary:
                        st.markdown("<div class='result-card'>", unsafe_allow_html=True)
                        st.subheader("🧠 AI 事件总结")
                        try:
                            parsed = json.loads(raw_summary) if isinstance(raw_summary, str) else raw_summary
                            if isinstance(parsed, dict):
                                st.info(parsed.get("summary", parsed))
                                if parsed.get("evidence"):
                                    st.markdown("**关键证据**")
                                    for ev in parsed["evidence"]:
                                        st.write("• " + ev)
                                if parsed.get("confidence"):
                                    st.markdown("**可信度**")
                                    st.warning(parsed["confidence"])
                            else:
                                st.write(parsed)
                        except:
                            st.write(raw_summary)
                        st.markdown("</div>", unsafe_allow_html=True)

                    st.subheader("📰 相关新闻条目")
                    nodes = {n["id"]: n for n in data.get("nodes", [])}
                    for n in data.get("nodes", []):
                        st.markdown("<div class='result-card'>", unsafe_allow_html=True)
                        st.markdown(f"**{n.get('title') or '无标题'}**")
                        st.caption(f"📅 {n.get('date') or '未知'} | 🔗 [{n.get('url')}]({n.get('url')})")
                        st.write(n.get("snippet", "无摘要"))
                        st.markdown("</div>", unsafe_allow_html=True)

                    graph_html = data.get("graph_html")
                    if graph_html or data.get("nodes"):
                        st.markdown("<div class='graph-section'>", unsafe_allow_html=True)
                        st.subheader("🔗 事件因果关系图")
                        if graph_html:
                            components.html(graph_html, height=750)
                        else:
                            G = nx.DiGraph()
                            for nid, nd in nodes.items():
                                G.add_node(nid, label=nd.get("title", "")[:50])
                            for e in data.get("edges", []):
                                G.add_edge(e["source"], e["target"])
                            plt.figure(figsize=(14, 9), facecolor='#0f1620')
                            ax = plt.gca()
                            ax.set_facecolor('#0f1620')
                            pos = nx.spring_layout(G, seed=42, k=1.5)
                            nx.draw(G, pos, with_labels=True, node_size=3500,
                                    node_color="#1e2a40", edge_color="#00ccff",
                                    arrowsize=30, font_size=11, font_color="#ffffff")
                            st.pyplot(plt)
                        st.markdown("</div>", unsafe_allow_html=True)

                else:
                    # ================ 金融数据分析显示 ================
                    content = data.get("content", "")
                    tool_results = data.get("tool_results", [])

                    if content:
                        st.markdown("<div class='result-card'>", unsafe_allow_html=True)
                        st.markdown(content)
                        st.markdown("</div>", unsafe_allow_html=True)

                    for res in tool_results:
                        st.markdown("<div class='result-card'>", unsafe_allow_html=True)
                        # 如果有错误，显示错误信息
                        if "error" in res:
                            st.error(f"❌ 错误: {res['error']}")
                            if "Rate limited" in str(res.get("error", "")) or "Too Many Requests" in str(res.get("error", "")):
                                st.info("💡 提示: yfinance API 请求过于频繁，请稍后再试。")
                        # 如果有分析结果或图表配置，正常显示
                        elif "analysis" in res or "chart_config" in res:
                            if res.get("analysis"):
                                st.markdown(res["analysis"])
                            if res.get("chart_config"):
                                chart_html = f"""
                                <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
                                <canvas id="stockChart{hash(res.get('symbol',''))}" style="width:100%; height:500px;"></canvas>
                                <script>
                                new Chart(document.getElementById('stockChart{hash(res.get('symbol',''))}'), {res['chart_config']});
                                </script>
                                """
                                components.html(chart_html, height=550)
                        st.markdown("</div>", unsafe_allow_html=True)

        except Exception as e:
            st.error(f"请求失败：{str(e)}")