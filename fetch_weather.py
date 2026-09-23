"""
Taiwan Weather Forecast - Data Ingestion Pipeline (fetch_weather.py)
-------------------------------------------------------------------
AI 創新微課程 Phase 1 & Phase 2 實作腳本：
1. 從 .env 檔案安全載入 CWA_API_KEY
2. 使用 requests 呼叫中央氣象署 Open Data API (F-C0032-001)
3. 解析 JSON 氣象預報資料，提取 MinT (最低溫) 與 MaxT (最高溫)
4. 使用 pandas 進行數據轉換與整理
5. 建立與寫入 SQLite 資料庫 (data.db - TemperatureForecasts 表結構)
"""

import os
import sys
import sqlite3
import requests
import pandas as pd
from dotenv import load_dotenv

import urllib3

# 停用 SSL 警告 (針對特定政府 Open Data 憑證驗證問題)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 強制設定標準輸出編碼為 UTF-8 (解決 Windows Console CP950 多位元組字元與 Emoji 編碼錯誤)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# 1. 載入 .env 環境變數
load_dotenv()

CWA_API_KEY = os.getenv("CWA_API_KEY")
DB_PATH = "data.db"
CWA_API_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001"


def fetch_cwa_weather(api_key: str) -> dict:
    """呼叫中央氣象署 API 取得 JSON 氣象預報資料 (Phase 1: Steps 3-4)"""
    if not api_key or api_key == "CWA-YOUR-API-KEY-HERE":
        raise ValueError(
            "未檢測到有效的 CWA_API_KEY！請在 .env 檔案中設定您的中央氣象署授權碼。"
        )

    params = {
        "Authorization": api_key,
        "format": "JSON"
    }

    print(f"📡 正在從中央氣象署 API 擷取氣象預報資料...")
    try:
        response = requests.get(CWA_API_URL, params=params, timeout=15)
        response.raise_for_status()
    except requests.exceptions.SSLError:
        print("⚠️ 檢測到 SSL 憑證驗證問題，啟用相容模式存取 CWA API...")
        response = requests.get(CWA_API_URL, params=params, timeout=15, verify=False)
        response.raise_for_status()

    print("✅ 成功存取 CWA API 並取得 JSON 資料！")
    return response.json()


def parse_temperature_data(json_data: dict) -> pd.DataFrame:
    """解析 JSON 資料結構，萃取各區域 MinT 與 MaxT (Phase 2: Steps 5-7)"""
    records = []
    locations = json_data.get("records", {}).get("location", [])

    for loc in locations:
        location_name = loc.get("locationName")
        elements = loc.get("weatherElement", [])

        # 尋找 MinT 與 MaxT 氣溫元素
        mint_elem = next((e for e in elements if e.get("elementName") == "MinT"), {})
        maxt_elem = next((e for e in elements if e.get("elementName") == "MaxT"), {})

        mint_times = mint_elem.get("time", [])
        maxt_times = maxt_elem.get("time", [])

        # 配對並萃取每個時間區段之氣溫
        for t_min, t_max in zip(mint_times, maxt_times):
            # 取出預報開始日期 (YYYY-MM-DD)
            start_time = t_min.get("startTime", "")
            data_date = start_time.split(" ")[0] if start_time else "N/A"

            min_temp = float(t_min.get("parameter", {}).get("parameterName", 0))
            max_temp = float(t_max.get("parameter", {}).get("parameterName", 0))

            records.append({
                "regionName": location_name,
                "dataDate": data_date,
                "minT": min_temp,
                "maxT": max_temp
            })

    df = pd.DataFrame(records)
    print(f"📊 成功解析氣溫資料：共 {len(df)} 筆預報紀錄。")
    return df


def init_database(db_path: str = DB_PATH):
    """初始化 SQLite 資料庫與 TemperatureForecasts 資料表 (Phase 2: Steps 8-9)"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS TemperatureForecasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            regionName TEXT NOT NULL,
            dataDate TEXT NOT NULL,
            minT REAL NOT NULL,
            maxT REAL NOT NULL,
            UNIQUE(regionName, dataDate) ON CONFLICT REPLACE
        );
    """)

    conn.commit()
    conn.close()
    print(f"🗄️ SQLite 資料庫已初始化 ({db_path})。")


def save_to_database(df: pd.DataFrame, db_path: str = DB_PATH):
    """將 DataFrame 資料寫入 SQLite 資料庫 (Phase 2: Step 10)"""
    init_database(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    insert_sql = """
        INSERT INTO TemperatureForecasts (regionName, dataDate, minT, maxT)
        VALUES (?, ?, ?, ?);
    """

    for _, row in df.iterrows():
        cursor.execute(insert_sql, (
            row["regionName"],
            row["dataDate"],
            row["minT"],
            row["maxT"]
        ))

    conn.commit()
    conn.close()
    print(f"💾 成功將 {len(df)} 筆氣溫數據存入 SQLite 資料庫 (`TemperatureForecasts` 表)！")


def verify_database(db_path: str = DB_PATH):
    """驗證與查詢 SQLite 資料庫寫入結果 (Phase 2: Step 10)"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. 查詢涵蓋地區
    cursor.execute("SELECT DISTINCT regionName FROM TemperatureForecasts;")
    regions = [r[0] for r in cursor.fetchall()]
    print(f"🔍 [資料庫驗證] 收錄地區 ({len(regions)} 個): {', '.join(regions[:6])}...")

    # 2. 隨機預覽一筆地區的氣溫紀錄
    sample_region = regions[0] if regions else "臺北市"
    cursor.execute("SELECT regionName, dataDate, minT, maxT FROM TemperatureForecasts WHERE regionName = ?;", (sample_region,))
    sample_rows = cursor.fetchall()
    print(f"📋 [資料庫驗證] {sample_region} 預報資料:")
    for row in sample_rows:
        print(f"   📅 日期: {row[1]} | ❄️ 最低溫: {row[2]}°C | ☀️ 最高溫: {row[3]}°C")

    conn.close()


def main():
    print("=" * 60)
    print("🚀 啟動 Taiwan Weather Forecast - 資料擷取與 pipeline 流程")
    print("=" * 60)

    try:
        # 1. 呼叫 API
        json_data = fetch_cwa_weather(CWA_API_KEY)

        # 2. 解析 JSON 轉為 DataFrame
        df = parse_temperature_data(json_data)

        # 3. 儲存至 SQLite
        save_to_database(df, DB_PATH)

        # 4. 驗證資料
        verify_database(DB_PATH)

        print("=" * 60)
        print("🎉 氣象資料 Pipeline 執行完畢！(Phase 1 & Phase 2 完成)")
        print("=" * 60)

    except Exception as e:
        print(f"❌ 執行失敗：{e}")


if __name__ == "__main__":
    main()
