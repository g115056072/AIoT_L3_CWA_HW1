"""
Taiwan Weather Forecast - Streamlit & Folium Interactive Dashboard (streamlit_app.py)
----------------------------------------------------------------------------------
AI 創新微課程 Phase 3 & Phase 4 完整 Web 應用程式：
Step 11: Streamlit 基本配置與網頁風格定調
Step 12: 從 SQLite 資料庫 (data.db) 讀取與快取氣溫預報資料
Step 13: 互動式下拉選單 (地區 / 縣市選擇)
Step 14: 一週最高溫 (MaxT) 與最低溫 (MinT) 雙趨勢折線圖
Step 15: 數據指標 (Metrics) 與結構化資料表格
Step 16: 整合 Web App 介面與版面設計 (Layout)
Step 17: 進階：Folium 台灣氣象地圖與氣溫顏色分級視覺化
Step 18: 互動式日期選擇器動態更新 GIS 天氣地圖
Step 19: 完整 Taiwan Weather Dashboard (地圖 + 圖表 + 表格 + 指標)
"""

import os
import sys
import sqlite3
import subprocess
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

# 強制設定標準輸出編碼為 UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# ==============================================================================
# Step 11: Streamlit 基本配置與網頁風格定調
# ==============================================================================
st.set_page_config(
    page_title="Taiwan Weather Forecast Dashboard",
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
        font-size: 1.05rem;
        color: #64748b;
        margin-bottom: 1.5rem;
    }
    .metric-container {
        background-color: #ffffff;
        border-radius: 12px;
        padding: 1.2rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    }
    .stApp {
        background-color: #f8fafc;
    }
    </style>
""", unsafe_allow_html=True)


# ==============================================================================
# 台灣縣市地理座標對照表 (用於 Folium GIS 地圖標註)
# ==============================================================================
REGION_COORDS = {
    "臺北市": [25.0330, 121.5654],
    "新北市": [24.9157, 121.6739],
    "基隆市": [25.1283, 121.7419],
    "宜蘭縣": [24.7570, 121.7530],
    "桃園市": [24.9936, 121.3010],
    "新竹縣": [24.7033, 121.1252],
    "新竹市": [24.8138, 120.9675],
    "苗栗縣": [24.5602, 120.8214],
    "臺中市": [24.1477, 120.6736],
    "彰化縣": [24.0518, 120.5161],
    "南投縣": [23.9610, 120.9719],
    "雲林縣": [23.7093, 120.4313],
    "嘉義縣": [23.4588, 120.5740],
    "嘉義市": [23.4800, 120.4491],
    "臺南市": [22.9997, 120.2270],
    "高雄市": [22.6273, 120.3014],
    "屏東縣": [22.5519, 120.5487],
    "花蓮縣": [23.9872, 121.6016],
    "臺東縣": [22.7613, 121.1444],
    "澎湖縣": [23.5711, 119.5793],
    "金門縣": [24.4493, 118.3766],
    "連江縣": [26.1505, 119.9499]
}


def get_temp_color(temp: float) -> tuple[str, str]:
    """Step 17: 依據平均氣溫等級回傳 (folium_color_name, hex_color)"""
    if temp < 20:
        return "blue", "#1e88e5"      # 寒冷 (< 20°C)
    elif temp <= 25:
        return "green", "#4caf50"     # 宜人 (20 - 25°C)
    elif temp <= 30:
        return "orange", "#ff9800"    # 偏熱 (25 - 30°C)
    else:
        return "red", "#f44336"       # 炎熱 (> 30°C)


# ==============================================================================
# Step 12: 從 SQLite 資料庫 (data.db) 讀取與快取數據
# ==============================================================================
DB_PATH = "data.db"


@st.cache_data(ttl=1800)
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
    with st.spinner("📡 正在從中央氣象署 API (F-D0047-091) 擷取最新預報資料..."):
        result = subprocess.run([sys.executable, "fetch_weather.py"], capture_output=True, text=True)
        if result.returncode == 0:
            st.success("✅ 氣象資料更新成功！")
            st.cache_data.clear()
            st.rerun()
        else:
            st.error(f"❌ 擷取資料失敗：\n{result.stderr}")


# 頁面標題渲染
st.markdown("<div class='main-header'>🌤️ Taiwan Weather Dashboard (台灣互動氣象儀表板)</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='sub-header'>AI 創新微課程 | CWA API × SQLite × Streamlit × Folium 地圖 | <i>Code Smarter, Build a Better Tomorrow! — 煥哥</i></div>",
    unsafe_allow_html=True
)

# 載入數據
df = load_weather_data(DB_PATH)

# 資料庫檢查與防護提示
if df.empty:
    st.warning("⚠️ 目前資料庫 (`data.db`) 無資料或尚未初始化！")
    if st.button("🚀 立即從中央氣象署 (CWA) 擷取最新氣象資料", type="primary"):
        trigger_data_fetch()
    st.stop()


# ==============================================================================
# 控制面板 (Sidebar)
# ==============================================================================
st.sidebar.image("https://img.icons8.com/color/96/000000/weather.png", width=80)
st.sidebar.title("⚙️ 控制面板 (Control Panel)")

all_regions = sorted(df["regionName"].unique().tolist())
all_dates = sorted(df["dataDate"].unique().tolist())

selected_region = st.sidebar.selectbox(
    "📍 選擇觀測縣市 (Select Region):",
    options=all_regions,
    index=0
)

selected_date = st.sidebar.selectbox(
    "📅 選擇預報日期 (Select Date):",
    options=all_dates,
    index=0
)

if st.sidebar.button("🔄 重新抓取 CWA API 資料"):
    trigger_data_fetch()

st.sidebar.markdown("---")
st.sidebar.markdown("""
### 🌡️ 氣溫顏色分級指南 (Legend)
- 🔵 **寒冷 (< 20°C)**: 氣溫較低，注意保暖
- 🟢 **宜人 (20 - 25°C)**: 氣候舒適，極適合出遊
- 🟡 **偏熱 (25 - 30°C)**: 體感微熱，留意補充水分
- 🔴 **炎熱 (> 30°C)**: 氣溫偏高，防範高溫中暑
""")

# 資料篩選
region_df = df[df["regionName"] == selected_region].copy()
region_df["temp_spread"] = region_df["maxT"] - region_df["minT"]


# ==============================================================================
# Step 19: 完整 Taiwan Weather Dashboard (Multi-Tab Layout)
# ==============================================================================
tab_map, tab_chart, tab_table, tab_about = st.tabs([
    "🗺️ 台灣氣溫互動地圖 (GIS Map)",
    "📊 縣市氣溫趨勢分析 (Trends)",
    "📋 詳細數據明細 (Data Table)",
    "📖 課程與專案介紹 (About & Roadmap)"
])


# ------------------------------------------------------------------------------
# Tab 1: Folium 台灣氣象地圖與動態日期切換 (Step 17 & Step 18)
# ------------------------------------------------------------------------------
with tab_map:
    st.subheader(f"🗺️ 台灣地區氣溫 GIS 地圖視覺化 (預報日期：{selected_date})")

    # 篩選指定日期的全台氣象資料
    date_df = df[df["dataDate"] == selected_date].groupby("regionName").agg({
        "minT": "mean",
        "maxT": "mean"
    }).reset_index()

    date_df["avgT"] = (date_df["minT"] + date_df["maxT"]) / 2

    col_map, col_info = st.columns([7, 3])

    with col_map:
        # Step 17: 初始化 Folium 地圖 (中心點設定於台灣中部)
        m = folium.Map(
            location=[23.7, 120.95],
            zoom_start=7,
            tiles="CartoDB positron"
        )

        # 遍歷地區繪製氣溫 Marker
        for _, row in date_df.iterrows():
            r_name = row["regionName"]
            if r_name in REGION_COORDS:
                coords = REGION_COORDS[r_name]
                avg_t = row["avgT"]
                min_t = row["minT"]
                max_t = row["maxT"]
                color_name, hex_code = get_temp_color(avg_t)

                popup_text = f"""
                <div style="font-family: sans-serif; min-width: 140px;">
                    <h4 style="margin: 0 0 5px 0; color: #1e293b;">{r_name}</h4>
                    <b>預報日期:</b> {selected_date}<br>
                    <b>平均氣溫:</b> <span style="color:{hex_code}; font-weight:bold;">{avg_t:.1f}°C</span><br>
                    <b>最低溫 (MinT):</b> {min_t:.1f}°C<br>
                    <b>最高溫 (MaxT):</b> {max_t:.1f}°C
                </div>
                """

                # 標註圖示
                folium.CircleMarker(
                    location=coords,
                    radius=12,
                    popup=folium.Popup(popup_text, max_width=250),
                    tooltip=f"{r_name}: {avg_t:.1f}°C ({min_t:.1f}°C ~ {max_t:.1f}°C)",
                    color=hex_code,
                    fill=True,
                    fill_color=hex_code,
                    fill_opacity=0.75,
                    weight=2
                ).add_to(m)

        # 在 Streamlit 中渲染 Folium 地圖
        st_folium(m, width="stretch", height=520)

    with col_info:
        st.markdown(f"### 📍 {selected_date} 全台摘要")
        if not date_df.empty:
            max_row = date_df.loc[date_df["maxT"].idxmax()]
            min_row = date_df.loc[date_df["minT"].idxmin()]

            st.metric("🔥 全台最高溫地點", f"{max_row['regionName']}", f"{max_row['maxT']:.1f} °C")
            st.metric("❄️ 全台最低溫地點", f"{min_row['regionName']}", f"{min_row['minT']:.1f} °C")
            st.metric("🌡️ 全台平均溫", f"{date_df['avgT'].mean():.1f} °C")
        
        st.caption("提示：點擊地圖上的圓圈標籤可檢視該縣市精確之預報數據。")


# ------------------------------------------------------------------------------
# Tab 2: 縣市氣溫雙趨勢折線圖 (Step 14 & Step 15)
# ------------------------------------------------------------------------------
with tab_chart:
    st.subheader(f"📈 【{selected_region}】一週最高溫 (MaxT) 與 最低溫 (MinT) 雙趨勢分析")

    c1, c2, c3, c4 = st.columns(4)
    latest_min = region_df["minT"].iloc[0] if not region_df.empty else 0
    latest_max = region_df["maxT"].iloc[0] if not region_df.empty else 0
    avg_min = region_df["minT"].mean() if not region_df.empty else 0
    avg_max = region_df["maxT"].mean() if not region_df.empty else 0

    c1.metric(label="❄️ 今日最低溫", value=f"{latest_min:.1f} °C")
    c2.metric(label="☀️ 今日最高溫", value=f"{latest_max:.1f} °C")
    c3.metric(label="📊 平均最低溫", value=f"{avg_min:.1f} °C")
    c4.metric(label="🔥 平均最高溫", value=f"{avg_max:.1f} °C")

    st.markdown("---")

    chart_df = region_df.pivot_table(
        index="dataDate",
        values=["minT", "maxT"],
        aggfunc="mean"
    ).rename(columns={"minT": "最低氣溫 (°C)", "maxT": "最高氣溫 (°C)"})

    st.line_chart(chart_df, color=["#1e88e5", "#e53935"])


# ------------------------------------------------------------------------------
# Tab 3: 詳細數據表格與 CSV 下載 (Step 15)
# ------------------------------------------------------------------------------
with tab_table:
    st.subheader(f"📋 【{selected_region}】氣溫預報數據明細")

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

    csv_data = display_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label=f"📥 下載 {selected_region} 氣溫數據 CSV",
        data=csv_data,
        file_name=f"{selected_region}_weather_forecast.csv",
        mime="text/csv"
    )


# ------------------------------------------------------------------------------
# Tab 4: 課程與專案介紹 (Roadmap & Philosophy)
# ------------------------------------------------------------------------------
with tab_about:
    st.subheader("💡 關於 AI 創新微課程 Taiwan Weather Forecast")
    st.markdown("""
    本專案引導學習者從 **中央氣象署 (CWA) Open Data API** 取得即時氣象預報數據，透過 **Python & Pandas** 處理，
    儲存於 **SQLite 資料庫**，並使用 **Streamlit** 與 **Folium** 打造結合 GIS 地圖視覺化與圖表分析之氣象儀表板。

    #### 📍 24 步驟學習路線圖概覽：
    - **Phase 1 (Steps 1-4)**: CWA API 註冊、`requests` 呼叫 JSON 氣象資料。
    - **Phase 2 (Steps 5-10)**: JSON 資料結構剖析、Pandas 資料整理、SQLite `data.db` 表建置與 SQL 驗證。
    - **Phase 3 (Steps 11-16)**: Streamlit 互動開發、下拉選單過濾、折線趨勢圖與明細數據表整合。
    - **Phase 4 (Steps 17-19)**: Folium 台灣地圖 GIS 氣溫分級視覺化與動態日期切換。
    - **Phase 5 (Steps 20-24)**: 程式碼重構優化、GitHub 版本管理與延伸應用 (Line Bot / AI 分析)。

    > *"技術可以解決問題，但更重要的是用技術創造更好的未來！"* — 煥哥
    """)

# 頁尾
st.markdown("---")
st.markdown("<div style='text-align: center; color: #94a3b8;'>Taiwan Weather Forecast Dashboard © 2026 | Powered by Streamlit, Folium & CWA Open Data</div>", unsafe_allow_html=True)
