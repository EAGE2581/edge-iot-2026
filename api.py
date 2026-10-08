"""EDGE-IOT-2026 REST API 服务（含 RAG 问答）。"""
import asyncio
import json
import ssl
import time

import paho.mqtt.client as mqtt
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config_loader import load_config, load_plcs
from app.transports import make_influx
from app.rag import RagEngine


app = FastAPI(
    title="EDGE-IOT-2026 API",
    description="工业物联网数据采集系统 · REST API + RAG",
    version="2.1.0",
)

_cfg = None
_influx_client = None
ws_clients = set()
main_loop = None
mqtt_client = None
rag_engine = None


class AskRequest(BaseModel):
    question: str


def get_influx():
    global _cfg, _influx_client
    if _influx_client is None:
        _cfg = load_config("config.yaml")
        _influx_client, _ = make_influx(
            _cfg["influx"]["url"], _cfg["influx"]["token"], _cfg["influx"]["org"],
        )
    return _influx_client, _cfg


def on_mqtt_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode("utf-8"))
    except Exception:
        return
    if main_loop is None:
        return
    asyncio.run_coroutine_threadsafe(broadcast(data), main_loop)


async def broadcast(data):
    if not ws_clients:
        return
    payload = json.dumps(data, ensure_ascii=False)
    dead = set()
    for ws in list(ws_clients):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    ws_clients.difference_update(dead)


@app.on_event("startup")
async def on_startup():
    global main_loop, mqtt_client, rag_engine
    main_loop = asyncio.get_running_loop()

    # ── RAG 引擎（会加载 BGE 模型，约 5~10 秒）
    print("[api] 初始化 RAG 引擎...")
    rag_engine = RagEngine()

    # ── MQTT 客户端
    cfg = load_config("config.yaml")
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    tls_cfg = cfg["mqtt"].get("tls")
    if tls_cfg and tls_cfg.get("enabled"):
        ctx = ssl.create_default_context(cafile=tls_cfg["ca"])
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_cert_chain(tls_cfg["cert"], tls_cfg["key"])
        mqtt_client.tls_set_context(ctx)

    mqtt_client.on_message = on_mqtt_message
    try:
        mqtt_client.connect(cfg["mqtt"]["host"], cfg["mqtt"]["port"], 60)
        mqtt_client.subscribe("factory/+/+/+/data", qos=1)
        mqtt_client.loop_start()
        print("[api] MQTT 已连接，订阅 factory/+/+/+/data")
    except Exception as e:
        print(f"[api] MQTT 连接失败（RAG 仍可用）：{e}")
        mqtt_client = None


@app.on_event("shutdown")
async def on_shutdown():
    global mqtt_client
    if mqtt_client:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()


@app.get("/")
def root():
    return {"service": "edge-iot-2026", "status": "ok"}


@app.get("/chat")
def chat_page():
    """返回聊天网页。"""
    return FileResponse("chat.html", media_type="text/html")


@app.get("/api/health")
def health():
    return {
        "status": "healthy", "timestamp": int(time.time()),
        "version": "2.1.0", "service": "edge-iot-2026-api",
    }


@app.get("/api/devices")
def list_devices():
    cfg, plcs = load_plcs("config.yaml")
    result = []
    for p in plcs:
        parts = p["name"].split("_")
        result.append({
            "name": p["name"], "site": parts[0], "line": parts[1], "plc": parts[2],
            "drive_count": p["drive_count"], "url": p["url"], "topic": p["topic"],
        })
    return {"count": len(result), "devices": result}


@app.get("/api/devices/{plc_name}/latest")
def get_latest(plc_name: str):
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


@app.post("/api/ask")
def ask(req: AskRequest):
    """RAG 问答：检索报警字典 + DeepSeek 生成分析。"""
    if rag_engine is None:
        raise HTTPException(status_code=503, detail="RAG 引擎尚未就绪")
    q = (req.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="问题不能为空")
    try:
        result = rag_engine.ask(q)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG 失败: {e}")
    return result


@app.websocket("/ws/realtime")
async def ws_realtime(websocket: WebSocket):
    await websocket.accept()
    ws_clients.add(websocket)
    print(f"[ws] 客户端连接，当前 {len(ws_clients)} 个")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_clients.discard(websocket)
        print(f"[ws] 客户端断开，剩余 {len(ws_clients)} 个")
