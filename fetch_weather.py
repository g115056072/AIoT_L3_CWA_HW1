"""
Taiwan Weather Forecast - Data Ingestion Pipeline (fetch_weather.py)
-------------------------------------------------------------------
AI 創新微課程 Phase 1 & Phase 2 實作腳本：
1. 從 .env 檔案安全載入 CWA_API_KEY
2. 使用 requests 呼叫中央氣象署 Open Data API (預設 F-D0047-091 1週天氣預報 / 相容 F-C0032-001)
3. 解析 JSON 氣象預報資料，動態提取 MinT (最低溫) 與 MaxT (最高溫)
4. 使用 pandas 進行數據轉換與整理
5. 清除舊資料庫 (data.db)，建立與寫入最新 SQLite 資料庫
"""

import os
import sys
import sqlite3
import requests
import urllib3
import pandas as pd
from dotenv import load_dotenv

# 停用 SSL 警告 (針對特定政府 Open Data 憑證驗證問題)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 強制設定標準輸出編碼為 UTF-8 (解決 Windows Console CP950 多位元組字元與 Emoji 編碼錯誤)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# 1. 載入 .env 環境變數
load_dotenv()

CWA_API_KEY = os.getenv("CWA_API_KEY")
DB_PATH = "data.db"
# 預設採用全台灣1週縣市天氣預報 (F-D0047-091)，相容 F-C0032-001
CWA_API_URL = os.getenv("CWA_API_URL", "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-091")


def fetch_cwa_weather(api_key: str, api_url: str = CWA_API_URL) -> dict:
    """呼叫中央氣象署 API 取得 JSON 氣象預報資料 (Phase 1: Steps 3-4)"""
    if not api_key or api_key == "CWA-YOUR-API-KEY-HERE":
        raise ValueError(
            "未檢測到有效的 CWA_API_KEY！請在 .env 檔案中設定您的中央氣象署授權碼。"
        )

    params = {
        "Authorization": api_key,
        "format": "JSON"
    }

    print(f"📡 正在從中央氣象署 API ({api_url.split('/')[-1]}) 擷取氣象預報資料...")
    try:
        response = requests.get(api_url, params=params, timeout=15)
        response.raise_for_status()
    except requests.exceptions.SSLError:
        print("⚠️ 檢測到 SSL 憑證驗證問題，啟用相容模式存取 CWA API...")
        response = requests.get(api_url, params=params, timeout=15, verify=False)
        response.raise_for_status()

    print("✅ 成功存取 CWA API 並取得 JSON 資料！")
    return response.json()


def parse_temperature_data(json_data: dict) -> pd.DataFrame:
    """解析 JSON 資料結構，適用於 F-D0047-091 以及 F-C0032-001 (Phase 2: Steps 5-7)"""
    rec_obj = json_data.get("records", {})

    # 定義 location 清單位址 (相容 F-D0047-091 的 Locations[0].Location 與 F-C0032-001 的 location)
    locations = []
    if "Locations" in rec_obj and len(rec_obj["Locations"]) > 0:
        locations = rec_obj["Locations"][0].get("Location", [])
    elif "locations" in rec_obj and len(rec_obj["locations"]) > 0:
        locations = rec_obj["locations"][0].get("location", [])
    elif "Location" in rec_obj:
        locations = rec_obj["Location"]
    elif "location" in rec_obj:
        locations = rec_obj["location"]

    daily_data = {}

    for loc in locations:
        location_name = loc.get("LocationName") or loc.get("locationName")
        if not location_name:
            continue
        elements = loc.get("WeatherElement") or loc.get("weatherElement") or []

        for elem in elements:
            e_name = elem.get("ElementName") or elem.get("elementName")
            times = elem.get("Time") or elem.get("time") or []

            if e_name in ["最低溫度", "MinT"]:
                for t in times:
                    start_time = t.get("StartTime") or t.get("startTime", "")
                    data_date = start_time[:10]
                    ev = t.get("ElementValue") or t.get("elementValue") or [{}]
                    min_val = ev[0].get("MinTemperature") or ev[0].get("value")
                    if min_val is None and "parameter" in t:
                        min_val = t["parameter"].get("parameterName")
                    if data_date and min_val is not None:
                        try:
                            daily_data.setdefault((location_name, data_date), {"minT": [], "maxT": []})["minT"].append(float(min_val))
                        except (ValueError, TypeError):
                            pass

            elif e_name in ["最高溫度", "MaxT"]:
                for t in times:
                    start_time = t.get("StartTime") or t.get("startTime", "")
                    data_date = start_time[:10]
                    ev = t.get("ElementValue") or t.get("elementValue") or [{}]
                    max_val = ev[0].get("MaxTemperature") or ev[0].get("value")
                    if max_val is None and "parameter" in t:
                        max_val = t["parameter"].get("parameterName")
                    if data_date and max_val is not None:
                        try:
                            daily_data.setdefault((location_name, data_date), {"minT": [], "maxT": []})["maxT"].append(float(max_val))
                        except (ValueError, TypeError):
                            pass

    records = []
    for (r_name, d), vals in daily_data.items():
        if vals["minT"] and vals["maxT"]:
            records.append({
                "regionName": r_name,
                "dataDate": d,
                "minT": round(min(vals["minT"]), 1),
                "maxT": round(max(vals["maxT"]), 1)
            })

    records.sort(key=lambda x: (x["dataDate"], x["regionName"]))
    df = pd.DataFrame(records)
    print(f"📊 成功解析氣溫資料：共 {len(df)} 筆預報紀錄 (涵蓋 {len(set(r['regionName'] for r in records))} 個縣市)。")
    return df


def wipe_database(db_path: str = DB_PATH):
    """徹底清除 SQLite 資料庫檔案或重新建表"""
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"🗑️ 已成功重置與清空資料庫 ({db_path})！")


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
    print(f"🗄️ SQLite 資料庫結構已初始化 ({db_path})。")


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

    cursor.execute("SELECT COUNT(*) FROM TemperatureForecasts;")
    total_count = cursor.fetchone()[0]
    print(f"🔢 [資料庫驗證] 總紀錄筆數: {total_count} 筆")

    cursor.execute("SELECT DISTINCT regionName FROM TemperatureForecasts;")
    regions = [r[0] for r in cursor.fetchall()]
    print(f"🔍 [資料庫驗證] 收錄地區 ({len(regions)} 個): {', '.join(regions[:6])}...")

    sample_region = regions[0] if regions else "臺北市"
    cursor.execute("SELECT regionName, dataDate, minT, maxT FROM TemperatureForecasts WHERE regionName = ? LIMIT 5;", (sample_region,))
    sample_rows = cursor.fetchall()
    print(f"📋 [資料庫驗證] {sample_region} 前 5 筆預報紀錄:")
    for row in sample_rows:
        print(f"   📅 日期: {row[1]} | ❄️ 最低溫: {row[2]}°C | ☀️ 最高溫: {row[3]}°C")

    conn.close()


def main():
    print("=" * 60)
    print("🚀 啟動 Taiwan Weather Forecast - 資料擷取與 pipeline 流程 (F-D0047-091)")
    print("=" * 60)

    try:
        # 0. 清除舊資料庫 (依使用者要求 wipe database)
        wipe_database(DB_PATH)

        # 1. 呼叫 API
        json_data = fetch_cwa_weather(CWA_API_KEY, CWA_API_URL)

        # 2. 解析 JSON 轉為 DataFrame
        df = parse_temperature_data(json_data)

        # 3. 儲存至 SQLite
        save_to_database(df, DB_PATH)

        # 4. 驗證資料
        verify_database(DB_PATH)

        print("=" * 60)
        print("🎉 氣象資料 Pipeline 重新建置完畢！(Phase 1 & Phase 2 完成)")
        print("=" * 60)

    except Exception as e:
        print(f"❌ 執行失敗：{e}")


if __name__ == "__main__":
    main()
