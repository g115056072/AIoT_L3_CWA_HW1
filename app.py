"""
Taiwan Weather Forecast - Flask Web Application (app.py)
--------------------------------------------------------
Vercel Cloud Serverless Compatible Web App featuring Flask:
- Top-level `app = Flask(__name__)` instance required by Vercel.
- SQLite Database ingestion & fallbacks (`data.db` / `/tmp/data.db`).
- Interactive GIS Weather Map (Leaflet.js), Chart.js Dual-Line Trends, Metrics Cards, and Data Tables.
- Full compatibility with Vercel deployment.
"""

import os
import sys
import sqlite3
import requests
import json
import pandas as pd
from flask import Flask, render_template_string, jsonify, request, Response
from dotenv import load_dotenv

load_dotenv()

# 強制 UTF-8 輸出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Vercel 需要的頂層 Flask 實例
app = Flask(__name__)

# 地理座標資料庫
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


def get_db_connection():
    """取得資料庫連線 (優先選本地 data.db，次選 /tmp/data.db)"""
    db_paths = ["data.db", "/tmp/data.db"]
    for path in db_paths:
        if os.path.exists(path):
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            return conn
    # 若資料庫不存在，在可寫入路徑建立表
    write_path = "data.db" if os.access(".", os.W_OK) else "/tmp/data.db"
    conn = sqlite3.connect(write_path)
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
    """擷取 CWA API 資料並寫入 SQLite"""
    api_key = os.getenv("CWA_API_KEY", "")
    if not api_key:
        return False, "CWA_API_KEY 未設定"

    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-091?Authorization={api_key}"
    try:
        resp = requests.get(url, timeout=15, verify=False)
        data = resp.json()
        locations = data['records']['locations'][0]['location']
    except Exception as e:
        return False, str(e)

    records = []
    for loc in locations:
        r_name = loc.get('locationName')
        min_t_dict, max_t_dict = {}, {}
        for elem in loc.get('weatherElement', []):
            e_name = elem.get('elementName')
            if e_name in ['MinT', '最低溫度']:
                for t in elem.get('time', []):
                    d = t.get('startTime', '')[:10]
                    val = t.get('elementValue', [{}])[0].get('value') or t.get('elementValue', [{}])[0].get('MinTemperature')
                    if d and val: min_t_dict[d] = float(val)
            elif e_name in ['MaxT', '最高溫度']:
                for t in elem.get('time', []):
                    d = t.get('startTime', '')[:10]
                    val = t.get('elementValue', [{}])[0].get('value') or t.get('elementValue', [{}])[0].get('MaxTemperature')
                    if d and val: max_t_dict[d] = float(val)
        
        all_dates = set(min_t_dict.keys()).union(set(max_t_dict.keys()))
        for d in sorted(all_dates):
            if d in min_t_dict and d in max_t_dict:
                records.append((r_name, d, min_t_dict[d], max_t_dict[d]))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.executemany("""
        INSERT INTO TemperatureForecasts (regionName, dataDate, minT, maxT)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(regionName, dataDate) DO UPDATE SET minT=excluded.minT, maxT=excluded.maxT
    """, records)
    conn.commit()
    conn.close()
    return True, f"成功更新 {len(records)} 筆預報數據"


@app.route('/api/weather', methods=['GET'])
def api_weather():
    """提供全台氣象 JSON API"""
    conn = get_db_connection()
    rows = conn.execute("SELECT regionName, dataDate, minT, maxT FROM TemperatureForecasts ORDER BY dataDate ASC").fetchall()
    conn.close()
    
    data = [dict(r) for r in rows]
    return jsonify({"status": "success", "count": len(data), "data": data})


@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    """手動觸發 CWA API 更新"""
    success, msg = fetch_and_save_data()
    return jsonify({"success": success, "message": msg})


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Taiwan Weather Forecast Dashboard</title>
    <!-- Bootstrap 5 CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <!-- Leaflet CSS -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <!-- FontAwesome -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <!-- Chart.js -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background-color: #f8fafc; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        .navbar-brand { font-weight: 700; font-size: 1.5rem; }
        .card { border-radius: 12px; border: none; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); margin-bottom: 1.5rem; }
        .metric-card { text-align: center; padding: 1.2rem; background: white; border-radius: 12px; }
        .metric-val { font-size: 1.8rem; font-weight: 700; }
        .metric-label { font-size: 0.9rem; color: #64748b; }
        #map { height: 480px; width: 100%; border-radius: 12px; }
        .badge-cold { background-color: #1e88e5; }
        .badge-mild { background-color: #4caf50; }
        .badge-warm { background-color: #ff9800; }
        .badge-hot { background-color: #f44336; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark mb-4">
        <div class="container-fluid px-4">
            <a class="navbar-brand" href="#">🌤️ Taiwan Weather Dashboard</a>
            <span class="navbar-text text-light">AI 創新微課程 | CWA API × Flask × SQLite × Leaflet</span>
        </div>
    </nav>

    <div class="container-fluid px-4">
        <!-- 控制選單區塊 -->
        <div class="card p-3">
            <div class="row g-3 align-items-center">
                <div class="col-md-4">
                    <label class="form-label font-weight-bold"><i class="fa-solid fa-location-dot"></i> 選擇觀測縣市:</label>
                    <select id="regionSelect" class="form-select" onchange="updateDashboard()">
                        {% for reg in regions %}
                        <option value="{{ reg }}">{{ reg }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="col-md-4">
                    <label class="form-label font-weight-bold"><i class="fa-solid fa-calendar-days"></i> 選擇預報日期 (GIS 地圖):</label>
                    <select id="dateSelect" class="form-select" onchange="updateMap()">
                        {% for d in dates %}
                        <option value="{{ d }}">{{ d }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="col-md-4 text-end pt-4">
                    <button class="btn btn-primary" onclick="refreshData()"><i class="fa-solid fa-rotate"></i> 重新擷取 API 資料</button>
                </div>
            </div>
        </div>

        <!-- 數據指標列 -->
        <div class="row g-3 mb-4" id="metricsRow">
            <div class="col-md-3">
                <div class="metric-card">
                    <div class="metric-label">❄️ 今日預測最低溫</div>
                    <div class="metric-val text-primary" id="mMinT">-- °C</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="metric-card">
                    <div class="metric-label">☀️ 今日預測最高溫</div>
                    <div class="metric-val text-danger" id="mMaxT">-- °C</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="metric-card">
                    <div class="metric-label">📊 一週平均最低溫</div>
                    <div class="metric-val text-info" id="mAvgMin">-- °C</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="metric-card">
                    <div class="metric-label">🔥 一週平均最高溫</div>
                    <div class="metric-val text-warning" id="mAvgMax">-- °C</div>
                </div>
            </div>
        </div>

        <!-- 主要展示區域 (GIS 地圖 + 折線圖) -->
        <div class="row g-4 mb-4">
            <div class="col-lg-7">
                <div class="card p-3">
                    <h5 class="card-title mb-3"><i class="fa-solid fa-map-location-dot"></i> 台灣氣溫 GIS 互動地圖</h5>
                    <div id="map"></div>
                </div>
            </div>
            <div class="col-lg-5">
                <div class="card p-3">
                    <h5 class="card-title mb-3"><i class="fa-solid fa-chart-line"></i> 一週最高與最低溫趨勢圖</h5>
                    <canvas id="tempChart" height="280"></canvas>
                </div>
            </div>
        </div>

        <!-- 數據明細表格 -->
        <div class="card p-3 mb-5">
            <h5 class="card-title mb-3"><i class="fa-solid fa-table"></i> 數據明細與下載</h5>
            <div class="table-responsive">
                <table class="table table-hover align-middle" id="dataTable">
                    <thead class="table-light">
                        <tr>
                            <th>預報日期 (Date)</th>
                            <th>最低氣溫 (°C)</th>
                            <th>最高氣溫 (°C)</th>
                            <th>日溫差 (°C)</th>
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
        const rawData = {{ raw_data | tojson }};
        const regionCoords = {{ coords | tojson }};
        let map, chart;

        function getTempColor(temp) {
            if (temp < 20) return '#1e88e5';
            if (temp <= 25) return '#4caf50';
            if (temp <= 30) return '#ff9800';
            return '#f44336';
        }

        function initMap() {
            map = L.map('map').setView([23.7, 120.95], 7);
            L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
                maxZoom: 19,
                attribution: '© OpenStreetMap © CARTO'
            }).addTo(map);
            updateMap();
        }

        function updateMap() {
            const selectedDate = document.getElementById('dateSelect').value;
            map.eachLayer((layer) => {
                if (layer instanceof L.CircleMarker) map.removeLayer(layer);
            });

            const dateRecords = rawData.filter(r => r.dataDate === selectedDate);
            dateRecords.forEach(r => {
                const coords = regionCoords[r.regionName];
                if (coords) {
                    const avgT = (r.minT + r.maxT) / 2;
                    const color = getTempColor(avgT);
                    const marker = L.circleMarker(coords, {
                        radius: 10,
                        fillColor: color,
                        color: color,
                        weight: 2,
                        opacity: 1,
                        fillOpacity: 0.8
                    }).addTo(map);
                    marker.bindPopup(`<b>${r.regionName}</b><br>日期: ${r.dataDate}<br>平均氣溫: ${avgT.toFixed(1)}°C<br>範圍: ${r.minT}°C ~ ${r.maxT}°C`);
                }
            });
        }

        function updateDashboard() {
            const selectedRegion = document.getElementById('regionSelect').value;
            const regionRecords = rawData.filter(r => r.regionName === selectedRegion);

            if (regionRecords.length === 0) return;

            // 更新 Metrics
            document.getElementById('mMinT').innerText = regionRecords[0].minT.toFixed(1) + ' °C';
            document.getElementById('mMaxT').innerText = regionRecords[0].maxT.toFixed(1) + ' °C';
            
            const avgMin = regionRecords.reduce((acc, r) => acc + r.minT, 0) / regionRecords.length;
            const avgMax = regionRecords.reduce((acc, r) => acc + r.maxT, 0) / regionRecords.length;
            document.getElementById('mAvgMin').innerText = avgMin.toFixed(1) + ' °C';
            document.getElementById('mAvgMax').innerText = avgMax.toFixed(1) + ' °C';

            // 更新 Chart
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
                        { label: '最高氣溫 (°C)', data: maxTs, borderColor: '#e53935', backgroundColor: 'rgba(229,57,53,0.1)', tension: 0.3, fill: true },
                        { label: '最低氣溫 (°C)', data: minTs, borderColor: '#1e88e5', backgroundColor: 'rgba(30,136,229,0.1)', tension: 0.3, fill: true }
                    ]
                },
                options: { responsive: true, plugins: { legend: { position: 'top' } } }
            });

            // 更新表格
            const tbody = document.querySelector('#dataTable tbody');
            tbody.innerHTML = '';
            regionRecords.forEach(r => {
                const spread = (r.maxT - r.minT).toFixed(1);
                tbody.innerHTML += `<tr>
                    <td>${r.dataDate}</td>
                    <td class="text-primary font-weight-bold">${r.minT.toFixed(1)}</td>
                    <td class="text-danger font-weight-bold">${r.maxT.toFixed(1)}</td>
                    <td>${spread}</td>
                </tr>`;
            });
        }

        function refreshData() {
            fetch('/api/refresh', { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    alert(data.message);
                    location.reload();
                });
        }

        window.onload = function() {
            initMap();
            updateDashboard();
        };
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """主頁面渲染」"""
    conn = get_db_connection()
    rows = conn.execute("SELECT regionName, dataDate, minT, maxT FROM TemperatureForecasts ORDER BY dataDate ASC").fetchall()
    conn.close()

    raw_data = [dict(r) for r in rows]
    if not raw_data:
        # 自動嘗試觸發抓取
        fetch_and_save_data()
        conn = get_db_connection()
        rows = conn.execute("SELECT regionName, dataDate, minT, maxT FROM TemperatureForecasts ORDER BY dataDate ASC").fetchall()
        conn.close()
        raw_data = [dict(r) for r in rows]

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
