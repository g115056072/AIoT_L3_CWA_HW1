"""
Taiwan Weather Forecast - Flask Web Application (app.py)
--------------------------------------------------------
Vercel Cloud Serverless Compatible Web App featuring Flask:
- Top-level `app = Flask(__name__)` instance required by Vercel.
- SQLite Database ingestion & fallbacks (`data.db` / `/tmp/data.db`).
- Interactive GIS Weather Map (Leaflet.js) with dynamic API Key input.
- Chart.js Dual-Line Trends, Metrics Cards, and Data Tables.
- Full compatibility with Vercel deployment.
"""

import os
import sys
import sqlite3
import requests
import json
import urllib3
from flask import Flask, render_template_string, jsonify, request
from dotenv import load_dotenv

# 載入 .env 環境變數
load_dotenv()

# 停用 SSL 警告 (針對特定政府 Open Data 憑證驗證問題)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 強制 UTF-8 輸出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Vercel 需要的頂層 Flask 實例
app = Flask(__name__)

# 地理座標資料庫 (全台 22 縣市中心座標)
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


def get_db_path():
    """取得資料庫路徑 (支援 Vercel Serverless 唯讀檔案系統與本地開發)"""
    # 在 Vercel 環境或根目錄無法寫入時，使用 /tmp/data.db
    if os.environ.get("VERCEL") or not os.access(".", os.W_OK):
        tmp_db = "/tmp/data.db"
        # 若根目錄有預置的 data.db 且 /tmp/data.db 尚未建立，複製一份過去
        if os.path.exists("data.db") and not os.path.exists(tmp_db):
            try:
                import shutil
                shutil.copyfile("data.db", tmp_db)
            except Exception:
                pass
        return tmp_db
    return "data.db"


def get_db_connection():
    """取得 SQLite 資料庫連線並確保資料表存在"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS TemperatureForecasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            regionName TEXT NOT NULL,
            dataDate TEXT NOT NULL,
            minT REAL NOT NULL,
            maxT REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(regionName, dataDate) ON CONFLICT REPLACE
        )
    """)
    conn.commit()
    conn.row_factory = sqlite3.Row
    return conn


def fetch_and_save_data():
    """
    擷取 CWA API 資料並寫入 SQLite
    支援 F-D0047-091 (1週縣市預報) 與 F-C0032-001 (36小時預報)
    支援大小寫相容解析 (Locations / Location / WeatherElement 等)
    API 金鑰僅從伺服器端環境變數 CWA_API_KEY 讀取。
    """
    api_key = os.getenv("CWA_API_KEY", "").strip()

    if not api_key or api_key == "CWA-YOUR-API-KEY-HERE":
        return False, "CWA_API_KEY 尚未在伺服器環境變數中設定，請於 Vercel 後台或 .env 檔案設定 CWA_API_KEY。", []

    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-091?Authorization={api_key}"
    try:
        resp = requests.get(url, timeout=20, verify=False)
        if resp.status_code in [401, 403]:
            return False, "授權碼無效 (401/403 Unauthorized)，請確認輸入的 CWA API Key 是否正確。", []
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return False, f"連線氣象署 API 失敗: {str(e)}", []

    rec_obj = data.get('records', {})
    locations = []
    # 支援 PascalCase (F-D0047-091) 與 camelCase/lowercase (F-C0032-001)
    if "Locations" in rec_obj and len(rec_obj["Locations"]) > 0:
        locations = rec_obj["Locations"][0].get("Location", [])
    elif "locations" in rec_obj and len(rec_obj["locations"]) > 0:
        locations = rec_obj["locations"][0].get("location", [])
    elif "Location" in rec_obj:
        locations = rec_obj["Location"]
    elif "location" in rec_obj:
        locations = rec_obj["location"]

    if not locations:
        return False, "未從氣象署 API 回應中解析到縣市位置清單，請確認 API 授權金鑰權限。", []

    daily_data = {}  # 結構: (regionName, dataDate) -> {'minT': [...], 'maxT': [...]}

    for loc in locations:
        r_name = loc.get('LocationName') or loc.get('locationName')
        if not r_name:
            continue

        elements = loc.get('WeatherElement') or loc.get('weatherElement') or []
        for elem in elements:
            e_name = elem.get('ElementName') or elem.get('elementName')
            times = elem.get('Time') or elem.get('time') or []

            if e_name in ['MinT', '最低溫度']:
                for t in times:
                    start_time = t.get('StartTime') or t.get('startTime', '')
                    d = start_time[:10]
                    ev = t.get('ElementValue') or t.get('elementValue') or [{}]
                    val = ev[0].get('MinTemperature') or ev[0].get('value')
                    if val is None and 'parameter' in t:
                        val = t['parameter'].get('parameterName')
                    if d and val is not None:
                        try:
                            daily_data.setdefault((r_name, d), {'minT': [], 'maxT': []})['minT'].append(float(val))
                        except (ValueError, TypeError):
                            pass

            elif e_name in ['MaxT', '最高溫度']:
                for t in times:
                    start_time = t.get('StartTime') or t.get('startTime', '')
                    d = start_time[:10]
                    ev = t.get('ElementValue') or t.get('elementValue') or [{}]
                    val = ev[0].get('MaxTemperature') or ev[0].get('value')
                    if val is None and 'parameter' in t:
                        val = t['parameter'].get('parameterName')
                    if d and val is not None:
                        try:
                            daily_data.setdefault((r_name, d), {'minT': [], 'maxT': []})['maxT'].append(float(val))
                        except (ValueError, TypeError):
                            pass

    records = []
    formatted_data = []
    for (r_name, d), vals in daily_data.items():
        if vals['minT'] and vals['maxT']:
            min_val = round(min(vals['minT']), 1)
            max_val = round(max(vals['maxT']), 1)
            records.append((r_name, d, min_val, max_val))
            formatted_data.append({
                "regionName": r_name,
                "dataDate": d,
                "minT": min_val,
                "maxT": max_val
            })

    if not records:
        return False, "氣象署 API 回應中未找到有效的最低/最高氣溫欄位。", []

    # 排序便於前端使用
    formatted_data.sort(key=lambda x: (x['dataDate'], x['regionName']))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.executemany("""
        INSERT INTO TemperatureForecasts (regionName, dataDate, minT, maxT)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(regionName, dataDate) DO UPDATE SET minT=excluded.minT, maxT=excluded.maxT
    """, records)
    conn.commit()
    conn.close()

    unique_regions = len(set(r[0] for r in records))
    return True, f"成功更新全台 {unique_regions} 縣市共 {len(records)} 筆預報數據！", formatted_data


@app.route('/api/weather', methods=['GET'])
def api_weather():
    """提供全台氣象 JSON API"""
    conn = get_db_connection()
    rows = conn.execute("SELECT regionName, dataDate, minT, maxT FROM TemperatureForecasts ORDER BY dataDate ASC, regionName ASC").fetchall()
    conn.close()

    data = [dict(r) for r in rows]

    # 如果資料庫為空，嘗試使用伺服器端環境變數自動擷取
    if not data:
        success, msg, new_data = fetch_and_save_data()
        if success:
            data = new_data

    return jsonify({"status": "success", "count": len(data), "data": data})


@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    """手動或前端觸發 CWA API 更新 (API 金鑰僅使用伺服器端環境變數)"""
    success, msg, data = fetch_and_save_data()
    return jsonify({
        "success": success,
        "message": msg,
        "count": len(data) if data else 0,
        "data": data
    }), (200 if success else 400)


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Taiwan Weather Forecast Dashboard | 台灣氣溫 GIS 互動看板</title>
    <!-- Google Fonts: Plus Jakarta Sans & Noto Sans TC -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Noto+Sans+TC:wght@400;500;700&display=swap" rel="stylesheet">
    <!-- Bootstrap 5 CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <!-- Leaflet CSS -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <!-- FontAwesome 6 -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <!-- Chart.js -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --primary: #2563eb;
            --primary-dark: #1d4ed8;
            --secondary: #0ea5e9;
            --surface: #ffffff;
            --background: #f1f5f9;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --border-color: #e2e8f0;
            --card-radius: 16px;
        }

        body {
            background-color: var(--background);
            font-family: 'Plus Jakarta Sans', 'Noto Sans TC', -apple-system, BlinkMacSystemFont, sans-serif;
            color: var(--text-main);
            margin: 0;
            padding-bottom: 2rem;
        }

        /* 導覽列 */
        .navbar-custom {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            box-shadow: 0 4px 20px -2px rgba(15, 23, 42, 0.25);
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }
        .navbar-brand {
            font-weight: 800;
            font-size: 1.35rem;
            letter-spacing: -0.02em;
            color: #ffffff !important;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .brand-badge {
            font-size: 0.72rem;
            background: rgba(37, 99, 235, 0.25);
            color: #60a5fa;
            border: 1px solid rgba(96, 165, 250, 0.3);
            border-radius: 20px;
            padding: 3px 10px;
            font-weight: 600;
        }

        /* 卡片設計 */
        .dashboard-card {
            background: var(--surface);
            border-radius: var(--card-radius);
            border: 1px solid var(--border-color);
            box-shadow: 0 4px 12px rgba(15, 23, 42, 0.04);
            transition: all 0.2s ease;
        }
        .dashboard-card:hover {
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.07);
        }

        /* 金鑰設定列 */
        .api-key-panel {
            background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
            border-left: 5px solid var(--primary);
        }

        /* 數據指標卡 */
        .metric-card {
            padding: 1.25rem;
            border-radius: var(--card-radius);
            background: #ffffff;
            border: 1px solid var(--border-color);
            position: relative;
            overflow: hidden;
            box-shadow: 0 4px 10px rgba(15, 23, 42, 0.03);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .metric-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06);
        }
        .metric-icon-bg {
            position: absolute;
            right: 15px;
            top: 15px;
            font-size: 2.2rem;
            opacity: 0.12;
        }
        .metric-label {
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.03em;
            margin-bottom: 0.35rem;
        }
        .metric-val {
            font-size: 1.95rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            line-height: 1.1;
        }

        /* 地圖樣式 */
        #map {
            height: 520px;
            width: 100%;
            border-radius: 12px;
            z-index: 1;
        }
        .leaflet-popup-content-wrapper {
            border-radius: 12px;
            padding: 4px;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.15);
        }
        .map-legend {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(8px);
            padding: 10px 14px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            font-size: 0.82rem;
            font-weight: 600;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
            line-height: 1.6;
        }
        .legend-dot {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 6px;
            vertical-align: middle;
        }

        /* 狀態標籤 */
        .badge-temp {
            font-size: 0.8rem;
            padding: 4px 8px;
            border-radius: 6px;
            font-weight: 600;
        }
        .badge-cold { background-color: #dbeafe; color: #1d4ed8; }
        .badge-mild { background-color: #d1fae5; color: #047857; }
        .badge-warm { background-color: #fef3c7; color: #b45309; }
        .badge-hot  { background-color: #fee2e2; color: #b91c1c; }

        /* 按鈕自訂 */
        .btn-primary-action {
            background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
            border: none;
            color: #ffffff;
            font-weight: 600;
            padding: 0.55rem 1.25rem;
            border-radius: 10px;
            transition: all 0.2s ease;
        }
        .btn-primary-action:hover {
            background: linear-gradient(135deg, #1d4ed8 0%, #1e40af 100%);
            color: #ffffff;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
        }

        /* 提示通知條 */
        #alertBox {
            display: none;
            border-radius: 12px;
            font-weight: 500;
        }

        /* 空資料引導容器 */
        .empty-placeholder {
            padding: 3rem 1rem;
            text-align: center;
            color: var(--text-muted);
        }
    </style>
</head>
<body>

    <!-- 頂部現代導覽列 -->
    <nav class="navbar navbar-expand-lg navbar-dark navbar-custom mb-4 py-3">
        <div class="container-fluid px-4">
            <a class="navbar-brand" href="#">
                <span>🌤️</span>
                <span>Taiwan Weather Dashboard</span>
                <span class="brand-badge d-none d-sm-inline">CWA OpenData × Leaflet GIS</span>
            </a>
            <div class="d-flex align-items-center gap-2">
                <span id="keyStatusBadge" class="badge bg-secondary-subtle text-light border border-secondary px-3 py-2">
                    <i class="fa-solid fa-circle-notch fa-spin"></i> 載入資料中...
                </span>
            </div>
        </div>
    </nav>

    <div class="container-fluid px-4">

        <!-- 警報/通知列 -->
        <div id="alertBox" class="alert alert-dismissible fade show mb-4" role="alert">
            <span id="alertMessage"></span>
            <button type="button" class="btn-close" onclick="closeAlert()"></button>
        </div>


        <!-- 互動控制篩選區塊 -->
        <div class="dashboard-card p-3 mb-4">
            <div class="row g-3 align-items-center">
                <div class="col-md-4">
                    <label class="form-label fw-bold"><i class="fa-solid fa-location-dot text-danger"></i> 選擇觀測縣市:</label>
                    <select id="regionSelect" class="form-select" onchange="updateDashboard(true)">
                        {% for reg in regions %}
                        <option value="{{ reg }}">{{ reg }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="col-md-4">
                    <label class="form-label fw-bold"><i class="fa-solid fa-calendar-days text-primary"></i> 選擇預報日期 (GIS 地圖動態切換):</label>
                    <select id="dateSelect" class="form-select" onchange="updateMap()">
                        {% for d in dates %}
                        <option value="{{ d }}">{{ d }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="col-md-4 text-md-end pt-md-4">
                    <button class="btn btn-outline-primary fw-semibold px-3 py-2 rounded-3" id="refreshBtn" onclick="refreshData()">
                        <i class="fa-solid fa-rotate me-1" id="refreshIcon"></i> 重新擷取最新數據
                    </button>
                </div>
            </div>
        </div>

        <!-- 數據指標列 (Metrics) -->
        <div class="row g-3 mb-4" id="metricsRow">
            <div class="col-sm-6 col-lg-3">
                <div class="metric-card">
                    <i class="fa-solid fa-snowflake metric-icon-bg text-primary"></i>
                    <div class="metric-label">❄️ 今日預測最低溫</div>
                    <div class="metric-val text-primary" id="mMinT">-- °C</div>
                    <div class="small text-muted mt-1" id="mMinTSub">載入中...</div>
                </div>
            </div>
            <div class="col-sm-6 col-lg-3">
                <div class="metric-card">
                    <i class="fa-solid fa-sun metric-icon-bg text-danger"></i>
                    <div class="metric-label">☀️ 今日預測最高溫</div>
                    <div class="metric-val text-danger" id="mMaxT">-- °C</div>
                    <div class="small text-muted mt-1" id="mMaxTSub">載入中...</div>
                </div>
            </div>
            <div class="col-sm-6 col-lg-3">
                <div class="metric-card">
                    <i class="fa-solid fa-temperature-arrow-down metric-icon-bg text-info"></i>
                    <div class="metric-label">📊 一週平均最低溫</div>
                    <div class="metric-val text-info" id="mAvgMin">-- °C</div>
                    <div class="small text-muted mt-1">7 日最低均溫</div>
                </div>
            </div>
            <div class="col-sm-6 col-lg-3">
                <div class="metric-card">
                    <i class="fa-solid fa-temperature-arrow-up metric-icon-bg text-warning"></i>
                    <div class="metric-label">🔥 一週平均最高溫</div>
                    <div class="metric-val text-warning" id="mAvgMax">-- °C</div>
                    <div class="small text-muted mt-1">7 日最高均溫</div>
                </div>
            </div>
        </div>

        <!-- 主要展示區域 (GIS 地圖 + 折線趨勢圖) -->
        <div class="row g-4 mb-4">
            <!-- GIS 地圖 -->
            <div class="col-lg-7">
                <div class="dashboard-card p-3 h-100">
                    <div class="d-flex justify-content-between align-items-center mb-3">
                        <h5 class="fw-bold mb-0">
                            <i class="fa-solid fa-map-location-dot text-success me-2"></i>台灣氣象 GIS 互動地圖
                        </h5>
                        <div class="d-flex gap-2">
                            <button class="btn btn-sm btn-light border rounded-pill px-3" onclick="resetMapView()">
                                <i class="fa-solid fa-crosshairs me-1"></i> 全台視野
                            </button>
                        </div>
                    </div>
                    <div id="map"></div>
                </div>
            </div>

            <!-- 折線圖 -->
            <div class="col-lg-5">
                <div class="dashboard-card p-3 h-100">
                    <div class="d-flex justify-content-between align-items-center mb-3">
                        <h5 class="fw-bold mb-0">
                            <i class="fa-solid fa-chart-line text-primary me-2"></i>一週氣溫預報雙趨勢圖
                        </h5>
                        <span class="badge bg-primary-subtle text-primary fw-semibold px-2 py-1" id="chartRegionBadge">
                            觀測縣市
                        </span>
                    </div>
                    <div style="position: relative; height: 460px;">
                        <canvas id="tempChart"></canvas>
                    </div>
                </div>
            </div>
        </div>

        <!-- 數據明細表格 -->
        <div class="dashboard-card p-4 mb-5">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h5 class="fw-bold mb-0"><i class="fa-solid fa-table-list text-secondary me-2"></i>氣溫預報數據明細與匯出</h5>
                <button class="btn btn-sm btn-outline-success fw-semibold px-3" onclick="exportCSV()">
                    <i class="fa-solid fa-file-csv me-1"></i> 下載 CSV
                </button>
            </div>
            <div class="table-responsive">
                <table class="table table-hover align-middle text-center" id="dataTable">
                    <thead class="table-light">
                        <tr>
                            <th>觀測縣市</th>
                            <th>預報日期 (Date)</th>
                            <th>最低氣溫 (°C)</th>
                            <th>最高氣溫 (°C)</th>
                            <th>日溫差 (°C)</th>
                            <th>體感舒適度等級</th>
                        </tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </div>
        </div>

    </div>

    <!-- Leaflet JS -->
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        // 後端初始資料
        let rawData = {{ raw_data | tojson }};
        const regionCoords = {{ coords | tojson }};
        let map, chart, mapMarkers = [];

        // 溫度級距顏色映射
        function getTempColor(temp) {
            if (temp < 20) return '#2563eb'; // 寒冷
            if (temp <= 25) return '#10b981'; // 舒適
            if (temp <= 30) return '#f59e0b'; // 溫暖
            return '#ef4444'; // 炎熱
        }

        function getTempBadge(temp) {
            if (temp < 20) return '<span class="badge badge-temp badge-cold">❄️ 偏涼/寒冷</span>';
            if (temp <= 25) return '<span class="badge badge-temp badge-mild">🍃 舒適宜人</span>';
            if (temp <= 30) return '<span class="badge badge-temp badge-warm">☀️ 溫暖偏熱</span>';
            return '<span class="badge badge-temp badge-hot">🔥 炎熱高溫</span>';
        }

        // 初始化 Leaflet GIS 地圖
        function initMap() {
            if (map) return;
            map = L.map('map', {
                center: [23.7, 120.95],
                zoom: 7,
                zoomControl: true
            });

            // 採用 CartoDB Positron 輕量高質感底圖，附 OpenStreetMap 容錯備份
            const positron = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19,
                attribution: '© OpenStreetMap'
            });
            positron.addTo(map);

            // 加入圖例
            const legend = L.control({ position: 'bottomright' });
            legend.onAdd = function() {
                const div = L.DomUtil.create('div', 'map-legend');
                div.innerHTML = `
                    <div class="fw-bold mb-1"><i class="fa-solid fa-temperature-three-quarters"></i> 氣溫分級</div>
                    <div><span class="legend-dot" style="background:#2563eb"></span> &lt; 20°C (寒冷)</div>
                    <div><span class="legend-dot" style="background:#10b981"></span> 20 - 25°C (舒適)</div>
                    <div><span class="legend-dot" style="background:#f59e0b"></span> 25 - 30°C (溫暖)</div>
                    <div><span class="legend-dot" style="background:#ef4444"></span> &gt; 30°C (炎熱)</div>
                `;
                return div;
            };
            legend.addTo(map);

            updateMap();
        }

        // 重置地圖視野
        function resetMapView() {
            if (map) {
                map.flyTo([23.7, 120.95], 7, { duration: 0.8 });
            }
        }

        // 動態繪製與更新地圖上的縣市氣溫標記
        function updateMap() {
            if (!map) return;
            // 清除現有標記
            mapMarkers.forEach(m => map.removeLayer(m));
            mapMarkers = [];

            const selectedDate = document.getElementById('dateSelect').value;
            const dateRecords = rawData.filter(r => r.dataDate === selectedDate);

            if (dateRecords.length === 0) return;

            dateRecords.forEach(r => {
                const coords = regionCoords[r.regionName];
                if (coords) {
                    const avgT = (r.minT + r.maxT) / 2;
                    const color = getTempColor(avgT);
                    const marker = L.circleMarker(coords, {
                        radius: 12,
                        fillColor: color,
                        color: '#ffffff',
                        weight: 2.5,
                        opacity: 1,
                        fillOpacity: 0.88
                    }).addTo(map);

                    // 點擊 Marker 同步切換該縣市之 Dashboard
                    marker.on('click', () => {
                        const regSelect = document.getElementById('regionSelect');
                        regSelect.value = r.regionName;
                        updateDashboard(false);
                    });

                    marker.bindTooltip(`<b>${r.regionName}</b>: ${avgT.toFixed(1)}°C`, {
                        permanent: false,
                        direction: 'top',
                        offset: [0, -10]
                    });

                    marker.bindPopup(`
                        <div style="min-width: 160px; font-family: inherit;">
                            <h6 class="fw-bold mb-1 text-primary">${r.regionName}</h6>
                            <div class="small text-muted mb-2">預報日期: ${r.dataDate}</div>
                            <div class="d-flex justify-content-between mb-1">
                                <span>平均氣溫:</span>
                                <b>${avgT.toFixed(1)} °C</b>
                            </div>
                            <div class="d-flex justify-content-between mb-1">
                                <span class="text-primary">最低溫:</span>
                                <b>${r.minT.toFixed(1)} °C</b>
                            </div>
                            <div class="d-flex justify-content-between mb-2">
                                <span class="text-danger">最高溫:</span>
                                <b>${r.maxT.toFixed(1)} °C</b>
                            </div>
                            <button class="btn btn-sm btn-primary w-100 mt-1" onclick="selectRegionFromPopup('${r.regionName}')">
                                查看一週趨勢圖
                            </button>
                        </div>
                    `);

                    mapMarkers.push(marker);
                }
            });
        }

        function selectRegionFromPopup(regionName) {
            const regSelect = document.getElementById('regionSelect');
            regSelect.value = regionName;
            updateDashboard(false);
        }

        // 更新 Dashboard 指標、Chart.js 折線圖與資料表
        function updateDashboard(panMap = true) {
            const selectedRegion = document.getElementById('regionSelect').value;
            const regionRecords = rawData.filter(r => r.regionName === selectedRegion);

            document.getElementById('chartRegionBadge').innerText = selectedRegion || '觀測縣市';

            if (regionRecords.length === 0) {
                document.getElementById('mMinT').innerText = '-- °C';
                document.getElementById('mMaxT').innerText = '-- °C';
                document.getElementById('mAvgMin').innerText = '-- °C';
                document.getElementById('mAvgMax').innerText = '-- °C';
                return;
            }

            // 更新 Metrics 卡片
            const firstRec = regionRecords[0];
            document.getElementById('mMinT').innerText = firstRec.minT.toFixed(1) + ' °C';
            document.getElementById('mMinTSub').innerText = firstRec.dataDate;
            document.getElementById('mMaxT').innerText = firstRec.maxT.toFixed(1) + ' °C';
            document.getElementById('mMaxTSub').innerText = firstRec.dataDate;

            const avgMin = regionRecords.reduce((acc, r) => acc + r.minT, 0) / regionRecords.length;
            const avgMax = regionRecords.reduce((acc, r) => acc + r.maxT, 0) / regionRecords.length;
            document.getElementById('mAvgMin').innerText = avgMin.toFixed(1) + ' °C';
            document.getElementById('mAvgMax').innerText = avgMax.toFixed(1) + ' °C';

            // 更新 Chart.js 趨勢圖
            const labels = regionRecords.map(r => r.dataDate);
            const minTs = regionRecords.map(r => r.minT);
            const maxTs = regionRecords.map(r => r.maxT);

            if (chart) chart.destroy();
            const ctx = document.getElementById('tempChart').getContext('2d');
            chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: '最高氣溫 MaxT (°C)',
                            data: maxTs,
                            borderColor: '#ef4444',
                            backgroundColor: 'rgba(239, 68, 68, 0.12)',
                            tension: 0.35,
                            fill: true,
                            pointRadius: 5,
                            pointHoverRadius: 7,
                            pointBackgroundColor: '#ef4444'
                        },
                        {
                            label: '最低氣溫 MinT (°C)',
                            data: minTs,
                            borderColor: '#2563eb',
                            backgroundColor: 'rgba(37, 99, 235, 0.12)',
                            tension: 0.35,
                            fill: true,
                            pointRadius: 5,
                            pointHoverRadius: 7,
                            pointBackgroundColor: '#2563eb'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'top', labels: { font: { family: 'Plus Jakarta Sans', weight: '600' } } },
                        tooltip: {
                            callbacks: {
                                label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y} °C`
                            }
                        }
                    },
                    scales: {
                        y: {
                            ticks: { callback: (val) => val + '°C' },
                            grid: { color: '#f1f5f9' }
                        },
                        x: {
                            grid: { display: false }
                        }
                    }
                }
            });

            // 更新明細表格
            const tbody = document.querySelector('#dataTable tbody');
            tbody.innerHTML = '';
            regionRecords.forEach(r => {
                const spread = (r.maxT - r.minT).toFixed(1);
                const avgT = (r.minT + r.maxT) / 2;
                tbody.innerHTML += `<tr>
                    <td class="fw-bold">${r.regionName}</td>
                    <td>${r.dataDate}</td>
                    <td class="text-primary fw-bold">${r.minT.toFixed(1)} °C</td>
                    <td class="text-danger fw-bold">${r.maxT.toFixed(1)} °C</td>
                    <td class="fw-semibold">${spread} °C</td>
                    <td>${getTempBadge(avgT)}</td>
                </tr>`;
            });

            // 平滑移動地圖至所選縣市
            if (panMap && map && regionCoords[selectedRegion]) {
                map.flyTo(regionCoords[selectedRegion], 9, { duration: 0.8 });
            }
        }

        // 下拉選單動態填入
        function populateDropdowns() {
            const regSelect = document.getElementById('regionSelect');
            const dateSelect = document.getElementById('dateSelect');

            const currentReg = regSelect.value;
            const currentDate = dateSelect.value;

            const regions = Array.from(new Set(rawData.map(r => r.regionName))).sort();
            const dates = Array.from(new Set(rawData.map(r => r.dataDate))).sort();

            regSelect.innerHTML = '';
            regions.forEach(reg => {
                const opt = document.createElement('option');
                opt.value = reg;
                opt.innerText = reg;
                if (reg === currentReg) opt.selected = true;
                regSelect.appendChild(opt);
            });

            dateSelect.innerHTML = '';
            dates.forEach(d => {
                const opt = document.createElement('option');
                opt.value = d;
                opt.innerText = d;
                if (d === currentDate) opt.selected = true;
                dateSelect.appendChild(opt);
            });
        }

        // 更新狀態徽章
        function updateKeyStatusBadge(configured) {
            const badge = document.getElementById('keyStatusBadge');
            if (configured) {
                badge.className = 'badge bg-success-subtle text-success border border-success px-3 py-2';
                badge.innerHTML = '<i class="fa-solid fa-circle-check"></i> CWA 資料已載入';
            } else {
                badge.className = 'badge bg-warning-subtle text-warning border border-warning px-3 py-2';
                badge.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> 資料載入失敗';
            }
        }

        // 顯示通知訊息
        function showAlert(msg, isSuccess = true) {
            const alertBox = document.getElementById('alertBox');
            const msgEl = document.getElementById('alertMessage');
            alertBox.className = `alert alert-${isSuccess ? 'success' : 'danger'} alert-dismissible fade show mb-4`;
            msgEl.innerHTML = (isSuccess ? '<i class="fa-solid fa-circle-check me-2"></i>' : '<i class="fa-solid fa-triangle-exclamation me-2"></i>') + msg;
            alertBox.style.display = 'block';
            alertBox.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }

        function closeAlert() {
            document.getElementById('alertBox').style.display = 'none';
        }

        // 重新擷取 API 資料 (使用伺服器端環境變數金鑰)
        function refreshData() {
            doRefresh();
        }

        function doRefresh() {
            const refreshBtn = document.getElementById('refreshBtn');
            const refreshIcon = document.getElementById('refreshIcon');

            refreshBtn.disabled = true;
            refreshIcon.classList.add('fa-spin');

            fetch('/api/refresh', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            })
            .then(res => res.json())
            .then(res => {
                refreshBtn.disabled = false;
                refreshIcon.classList.remove('fa-spin');

                if (res.success && res.data && res.data.length > 0) {
                    rawData = res.data;
                    populateDropdowns();
                    updateMap();
                    updateDashboard(false);
                    updateKeyStatusBadge(true);
                    showAlert(res.message, true);
                } else {
                    showAlert(res.message || '擷取失敗，請確認伺服器端 CWA_API_KEY 環境變數是否已正確設定。', false);
                    updateKeyStatusBadge(false);
                }
            })
            .catch(err => {
                refreshBtn.disabled = false;
                refreshIcon.classList.remove('fa-spin');
                showAlert('伺服器連線發生異常：' + err.message, false);
            });
        }

        // CSV 匯出功能
        function exportCSV() {
            const selectedRegion = document.getElementById('regionSelect').value;
            const regionRecords = rawData.filter(r => r.regionName === selectedRegion);
            if (regionRecords.length === 0) {
                showAlert('目前沒有可匯出的數據', false);
                return;
            }

            let csv = '\uFEFF觀測縣市,預報日期,最低氣溫(°C),最高氣溫(°C),溫差(°C)';
            regionRecords.forEach(r => {
                csv += `\n"${r.regionName}","${r.dataDate}",${r.minT},${r.maxT},${(r.maxT - r.minT).toFixed(1)}`;
            });

            const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `Taiwan_Weather_${selectedRegion}_${new Date().toISOString().slice(0, 10)}.csv`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        }

        // 頁面初始化
        window.onload = function() {
            // 初始化地圖與 Dashboard
            initMap();

            if (rawData && rawData.length > 0) {
                updateKeyStatusBadge(true);
                updateDashboard(false);
            } else {
                // 如果目前資料為空，自動觸發一次伺服器端擷取
                doRefresh();
            }
        };
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """主頁面渲染"""
    conn = get_db_connection()
    rows = conn.execute("SELECT regionName, dataDate, minT, maxT FROM TemperatureForecasts ORDER BY dataDate ASC, regionName ASC").fetchall()
    conn.close()

    raw_data = [dict(r) for r in rows]

    # 若資料庫為空，嘗試使用伺服器端環境變數自動載入
    if not raw_data:
        success, msg, new_data = fetch_and_save_data()
        if success:
            raw_data = new_data

    regions = sorted(list(set(r['regionName'] for r in raw_data))) if raw_data else []
    dates = sorted(list(set(r['dataDate'] for r in raw_data))) if raw_data else []

    return render_template_string(
        HTML_TEMPLATE,
        raw_data=raw_data,
        regions=regions,
        dates=dates,
        coords=REGION_COORDS
    )


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
