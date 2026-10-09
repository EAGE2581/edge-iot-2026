"""MQTT 与 InfluxDB 客户端封装。"""
import json

import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from .converter import convert


def make_mqtt(host, port=1883, keepalive=60, tls_cfg=None):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    if tls_cfg and tls_cfg.get("enabled"):
        import ssl
        ctx = ssl.create_default_context(cafile=tls_cfg["ca"])
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_cert_chain(certfile=tls_cfg["cert"], keyfile=tls_cfg["key"])
        client.tls_set_context(ctx)

    client.connect(host, port, keepalive)
    client.loop_start()
    return client


def make_influx(url, token, org):
    client = InfluxDBClient(url=url, token=token, org=org)
    write_api = client.write_api(write_options=SYNCHRONOUS)
    return client, write_api


def publish_mqtt(mqtt_client, topic, data):
    if mqtt_client is None or not mqtt_client.is_connected():
        return False
    try:
        result = mqtt_client.publish(topic, json.dumps(data, ensure_ascii=False))
        return result.rc == mqtt.MQTT_ERR_SUCCESS
    except Exception:
        return False


def write_influx(write_api, bucket, plc_cfg, tag_map, data):
    """把一次采集的所有变频器构造成 list[Point]，一次性写入。"""
    try:
        rated = plc_cfg.get("rated_current", 16.0)
        drive_count = len(plc_cfg["udt_starts"])
        ts_ns = data["timestamp"] * 1000000

        points = []
        for i in range(drive_count):
            drive = f"drive_{i+1}"
            point = (
                Point("drive_metrics")
                .tag("plc", plc_cfg["name"])
                .tag("drive", drive)
            )
            has_field = False
            for key, meta in tag_map.items():
                if not key.startswith(f"{drive}_"):
                    continue
                if key not in data["values"]:
                    continue
                field_name = key[len(drive) + 1:]
                val = convert(data["values"][key], meta["type"], rated)
                point = point.field(field_name, val)
                has_field = True

            if has_field:
                points.append(point.time(ts_ns))

        if points:
            # 一次 HTTP POST 写整批，网络开销降到 1/N
            write_api.write(bucket=bucket, record=points)
        return True
    except Exception as e:
        print(f"[!] InfluxDB 写入失败: {e}")
        return False


def write_alarm_influx(write_api, bucket, alarm):
    try:
        point = (
            Point("alarms")
            .tag("plc", alarm["plc"])
            .tag("drive", alarm["drive"])
            .tag("kind", alarm["kind"])
            .tag("code", str(alarm["code"]))
            .tag("severity", alarm["severity"])
            .field("value", alarm["code"])
            .time(alarm["timestamp"] * 1000000)
        )
        write_api.write(bucket=bucket, record=point)
        return True
    except Exception as e:
        print(f"[!] 告警写入失败: {e}")
        return False
