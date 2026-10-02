"""系统健康上报。"""
import asyncio
import platform
import socket
import time

import psutil

from .transports import publish_mqtt
from .cache import cache_count_for


def collect_metrics(cache_conn, mqtt_client, plc_names):
    mem = psutil.virtual_memory()

    cache_per_plc = {}
    for name in plc_names:
        try:
            cache_per_plc[name] = cache_count_for(cache_conn, name)
        except Exception:
            cache_per_plc[name] = -1

    total_cache = sum(v for v in cache_per_plc.values() if v > 0)

    try:
        mqtt_ok = bool(mqtt_client.is_connected())
    except Exception:
        mqtt_ok = False

    return {
        "timestamp": int(time.time() * 1000),
        "host": socket.gethostname(),
        "platform": platform.system() + " " + platform.release(),
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "mem_percent": mem.percent,
        "mem_used_mb": round(mem.used / 1024 / 1024, 1),
        "mem_total_mb": round(mem.total / 1024 / 1024, 1),
        "cache_total": total_cache,
        "cache_per_plc": cache_per_plc,
        "mqtt_connected": mqtt_ok,
    }


async def health_loop(mqtt_client, cache_conn, plc_names,
                      topic="factory/system/health", interval=60):
    print(f"[health] 已启动，每 {interval} 秒上报一次到 {topic}")

    while True:
        try:
            metrics = collect_metrics(cache_conn, mqtt_client, plc_names)
            ok = publish_mqtt(mqtt_client, topic, metrics)
            if not ok:
                print(f"[health] 上报失败（MQTT 未连接？）")
        except asyncio.CancelledError:
            print("[health] 已停止")
            raise
        except Exception as e:
            print(f"[health] 异常: {e}")

        await asyncio.sleep(interval)
