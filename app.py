"""
Taiwan Weather Forecast - Streamlit Web Application (app.py)
------------------------------------------------------------
AI 創新微課程 Phase 3 實作網頁應用程式：
Step 11: Streamlit 入門與視覺化主題風格設定
Step 12: 從 SQLite 資料庫 (data.db) 讀取與快取氣溫預報資料
Step 13: 互動式下拉選單 (地區 / 縣市選擇)
Step 14: 一週最高溫 (MaxT) 與最低溫 (MinT) 雙趨勢折線圖
Step 15: 數據指標 (Metrics) 與結構化資料表格
Step 16: 整合互動式 Web 介面與版面設計 (Layout)
"""

import os
import sqlite3
import subprocess
import pandas as pd
import streamlit as st

# ==============================================================================
# Step 11: Streamlit 基本配置與網頁風格定調
# ==============================================================================
st.set_page_config(
    page_title="Taiwan Weather Forecast | 互動式天氣預報應用",
    page_icon="🌤️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自訂 UI 樣式美化
st.markdown("""
    <style>
    .main-header {
        font-size: 2.3rem;
        font-weight: 700;
        color: #1e293b;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #64748b;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }
    .stApp {
        background-color: #f8fafc;
    }
    </style>
""", unsafe_allow_html=True)


# ==============================================================================
# Step 12: 從 SQLite 資料庫 (data.db) 讀取與快取資料
# ==============================================================================
DB_PATH = "data.db"


@st.cache_data(ttl=3600)
def load_weather_data(db_path: str = DB_PATH) -> pd.DataFrame:
    """從 SQLite 資料庫中讀取 TemperatureForecasts 氣溫數據"""
    if not os.path.exists(db_path):
        return pd.DataFrame()

    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(
            "SELECT regionName, dataDate, minT, maxT FROM TemperatureForecasts ORDER BY dataDate ASC",
            conn
        )
    except Exception as e:
        st.error(f"讀取資料庫失敗: {e}")
        df = pd.DataFrame()
    finally:
        conn.close()

    return df


def trigger_data_fetch():
    """執行 fetch_weather.py 重新抓取資料」"""
    with st.spinner("📡 正在從中央氣象署 API 擷取最新天氣預報資料..."):
        result = subprocess.run([sys.executable, "fetch_weather.py"], capture_output=True, text=True)
        if result.returncode == 0:
            st.success("✅ 氣象資料更新成功！")
            st.cache_data.clear()
            st.rerun()
        else:
            st.error(f"❌ 擷取資料失敗：\n{result.stderr}")


# 頁面標頭渲染
st.markdown("<div class='main-header'>🌤️ Taiwan Weather Forecast 互動式天氣預報</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='sub-header'>AI 創新微課程 | CWA API × JSON × Python × SQLite × Streamlit | <i>Code Smarter, Build a Better Tomorrow! — 煥哥</i></div>",
    unsafe_allow_html=True
)

# 載入資料
import sys
df = load_weather_data(DB_PATH)

# 資料庫防護檢查：若無資料則提示執行 Pipeline
if df.empty:
    st.warning("⚠️ 目前資料庫 (`data.db`) 無資料或尚未建立！")
    if st.button("🚀 立即從中央氣象署 (CWA) 擷取資料", type="primary"):
        trigger_data_fetch()
    st.stop()


# ==============================================================================
# Step 13: 側邊欄與互動式下拉選單 (Select Region)
# ==============================================================================
st.sidebar.image("https://img.icons8.com/color/96/000000/weather.png", width=80)
st.sidebar.title("⚙️ 控制面板 (Control Panel)")

# 取得所有縣市列表
all_regions = sorted(df["regionName"].unique().tolist())

# 下拉選單選擇地區
selected_region = st.sidebar.selectbox(
    "📍 請選擇觀測縣市 (Select Region):",
    options=all_regions,
    index=0
)

# 重新整理按鈕
if st.sidebar.button("🔄 重新抓取 API 資料"):
    trigger_data_fetch()

st.sidebar.markdown("---")
st.sidebar.info(
    "💡 **提示**：選擇縣市後，系統將自動過濾並更新一週最高與最低氣溫趨勢圖與明細數據。"
)


# 依選擇過濾資料
region_df = df[df["regionName"] == selected_region].copy()
region_df["temp_spread"] = region_df["maxT"] - region_df["minT"]


# ==============================================================================
# Step 14 & Step 15 & Step 16: 整合核心網頁介面、數據指標與圖表
# ==============================================================================

# 1. 頂部數據指標面板 (Metrics Panel)
col1, col2, col3, col4 = st.columns(4)

latest_min = region_df["minT"].iloc[0] if not region_df.empty else 0
latest_max = region_df["maxT"].iloc[0] if not region_df.empty else 0
avg_min = region_df["minT"].mean() if not region_df.empty else 0
avg_max = region_df["maxT"].mean() if not region_df.empty else 0

with col1:
    st.metric(label="❄️ 今日預測最低溫", value=f"{latest_min:.1f} °C")
with col2:
    st.metric(label="☀️ 今日預測最高溫", value=f"{latest_max:.1f} °C")
with col3:
    st.metric(label="📊 一週平均最低溫", value=f"{avg_min:.1f} °C")
with col4:
    st.metric(label="🔥 一週平均最高溫", value=f"{avg_max:.1f} °C")

st.markdown("---")

# 主頁籤設計
tab1, tab2, tab3 = st.tabs(["📊 氣溫趨勢圖表", "📋 氣象數據明細表", "📖 課程與專案介紹"])

# Tab 1: 氣溫雙趨勢折線圖 (Step 14)
with tab1:
    st.subheader(f"📈 【{selected_region}】一週最高溫 (MaxT) 與 最低溫 (MinT) 趨勢分析")
    
    # 建立圖表專用 DataFrame 結構
    chart_df = region_df.pivot_table(
        index="dataDate",
        values=["minT", "maxT"],
        aggfunc="mean"
    ).rename(columns={"minT": "最低氣溫 (°C)", "maxT": "最高氣溫 (°C)"})

    # 使用 Streamlit 折線圖展示
    st.line_chart(chart_df, color=["#1e88e5", "#e53935"])

    st.caption("註：藍線代表最低氣溫 (MinT)，紅線代表最高氣溫 (MaxT)。")

# Tab 2: 資料表格呈現 (Step 15)
with tab2:
    st.subheader(f"📋 【{selected_region}】詳細氣溫數據表")
    
    display_df = region_df[["dataDate", "minT", "maxT", "temp_spread"]].rename(columns={
        "dataDate": "預報日期 (Date)",
        "minT": "最低氣溫 (°C)",
        "maxT": "最高氣溫 (°C)",
        "temp_spread": "日溫差 (°C)"
    })

    st.dataframe(
        display_df.style.highlight_max(subset=["最高氣溫 (°C)"], color="#ffebee")
                         .highlight_min(subset=["最低氣溫 (°C)"], color="#e3f2fd")
                         .format({"最低氣溫 (°C)": "{:.1f}", "最高氣溫 (°C)": "{:.1f}", "日溫差 (°C)": "{:.1f}"}),
        width="stretch"
    )

    # 提供 CSV 檔案下載
    csv_data = display_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label=f"📥 下載 {selected_region} 氣溫數據 CSV",
        data=csv_data,
        file_name=f"{selected_region}_weather_forecast.csv",
        mime="text/csv"
    )

# Tab 3: 專案介紹與 24 步驟學習地圖 (Step 16 整合說明)
with tab3:
    st.subheader("💡 關於 AI 創新微課程 Taiwan Weather Forecast")
    st.markdown("""
    本專案引導學習者從 **中央氣象署 (CWA) Open Data API** 取得即時預報數據，透過 **Python & Pandas** 處理，
    儲存於 **SQLite 資料庫**，並使用 **Streamlit** 打造視覺化氣象儀表板。

    #### 📍 24 步驟學習路線圖概覽：
    - **Phase 1 (Steps 1-4)**: CWA API 註冊、`requests` 呼叫 JSON 氣象資料。
    - **Phase 2 (Steps 5-10)**: JSON 資料結構剖析、Pandas 資料整理、SQLite `data.db` 表建置與 SQL 驗證。
    - **Phase 3 (Steps 11-16)**: Streamlit 互動開發、下拉選單過濾、折線趨勢圖與明細數據表整合。 *(當前完成區塊)*
    - **Phase 4 (Steps 17-19)**: Folium 台灣地圖 GIS 氣溫分級視覺化與動態日期切換。
    - **Phase 5 (Steps 20-24)**: 程式碼重構優化、GitHub 版本管理與延伸應用 (Line Bot / AI 分析)。

    > *"技術可以解決問題，但更重要的是用技術創造更好的未來！"* — 煥哥
    """)

# 頁尾
st.markdown("---")
st.markdown("<div style='text-align: center; color: #94a3b8;'>Taiwan Weather Forecast App © 2026 | Powered by Streamlit & CWA Open Data</div>", unsafe_allow_html=True)
