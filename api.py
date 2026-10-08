"""EDGE-IOT-2026 REST API 服务。

用法：
    uvicorn api:app --reload --host 0.0.0.0 --port 8000
"""
import time

from fastapi import FastAPI, HTTPException

from app.config_loader import load_config, load_plcs
from app.transports import make_influx


app = FastAPI(
    title="EDGE-IOT-2026 API",
    description="工业物联网数据采集系统 · REST API",
    version="2.0.0",
)

# ── 全局缓存：只建一次 InfluxDB 连接，后续复用 ──
_cfg = None
_influx_client = None


def get_influx():
    """获取 InfluxDB 客户端（首次调用时建立，之后复用）。"""
    global _cfg, _influx_client
    if _influx_client is None:
        _cfg = load_config("config.yaml")
        _influx_client, _ = make_influx(
            _cfg["influx"]["url"],
            _cfg["influx"]["token"],
            _cfg["influx"]["org"],
        )
    return _influx_client, _cfg


@app.get("/")
def root():
    return {"service": "edge-iot-2026", "status": "ok"}


@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "timestamp": int(time.time()),
        "version": "2.0.0",
        "service": "edge-iot-2026-api",
    }


@app.get("/api/devices")
def list_devices():
    cfg, plcs = load_plcs("config.yaml")
    result = []
    for p in plcs:
        parts = p["name"].split("_")
        result.append({
            "name": p["name"],
            "site": parts[0],
            "line": parts[1],
            "plc": parts[2],
            "drive_count": p["drive_count"],
            "url": p["url"],
            "topic": p["topic"],
        })
    return {"count": len(result), "devices": result}


@app.get("/api/devices/{plc_name}/latest")
def get_latest(plc_name: str):
    """查指定 PLC 的所有变频器最新值（最近 5 分钟）。"""
    client, cfg = get_influx()
    query_api = client.query_api()
    bucket = cfg["influx"]["bucket"]
    org = cfg["influx"]["org"]

    flux = f'''
from(bucket: "{bucket}")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "drive_metrics")
  |> filter(fn: (r) => r.plc == "{plc_name}")
'''

    try:
        tables = query_api.query(flux, org=org)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")

    # 组织数据：{drive_name: {field: value}}
    drives = {}
    latest_time = None
    for table in tables:
        for record in table.records:
            drive = record.values.get("drive")
            field = record.get_field()
            value = record.get_value()
            t = record.get_time()
            if not drive:
                continue
            drives.setdefault(drive, {})[field] = value
            if latest_time is None or t > latest_time:
                latest_time = t

    if not drives:
        raise HTTPException(status_code=404, detail=f"未找到 PLC {plc_name} 的数据")

    return {
        "plc": plc_name,
        "timestamp": latest_time.isoformat() if latest_time else None,
        "drive_count": len(drives),
        "drives": drives,
    }
