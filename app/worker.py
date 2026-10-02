"""单个 PLC 的采集主循环。"""
import asyncio
import time

from asyncua import Client

from .node_builder import build_node_ids
from .cache import cache_push, cache_pop_for, cache_pop_batch, cache_count_for
from .transports import publish_mqtt, write_influx, write_alarm_influx
from .alarm_codes import translate


def alarm_topic(data_topic):
    return data_topic.replace("/data", "/alarms")


def _process_alarms(plc_cfg, data, alarm_table, deduper):
    plc = plc_cfg["name"]
    ts = data["timestamp"]
    now = ts / 1000.0
    topic = alarm_topic(plc_cfg["topic"])
    out = []

    for i in range(len(plc_cfg["udt_starts"])):
        drive = f"drive_{i+1}"
        for kind, field in (("warn", "warn_code"), ("fault", "fault_code")):
            key = f"{drive}_{field}"
            if key not in data["values"]:
                continue
            code = int(data["values"][key])
            if not deduper.should_emit(plc, drive, kind, code, now):
                continue
            info = translate(code, alarm_table)
            if info is None:
                continue
            out.append({
                "timestamp": ts,
                "plc": plc,
                "drive": drive,
                "kind": kind,
                "code": code,
                "text": info["text"],
                "severity": info["severity"],
                "category": info["category"],
                "topic": topic,
            })
    return out


def _emit_alarms(mqtt_client, write_api, bucket, alarms, notifier=None):
    for a in alarms:
        publish_mqtt(mqtt_client, a["topic"], a)
        write_alarm_influx(write_api, bucket, a)
        if notifier is not None and a["severity"] == "critical":
            ok = notifier.send_alarm(a)
            if ok:
                print(f"[ding] 已推送: {a['plc']} {a['drive']} {a['code']} {a['text']}")


async def collect_plc(
    plc_cfg, mqtt_client, write_api, bucket, cache_conn, alarm_table, deduper,
    notifier=None,
):
    name = plc_cfg["name"]
    tag_map = build_node_ids(plc_cfg)
    retry_delay = 5
    max_delay = 60

    while True:
        try:
            async with Client(plc_cfg["url"]) as client:
                print(f"[{name}] 已连接，{len(tag_map)} 点位")
                retry_delay = 5

                cnt = cache_count_for(cache_conn, name)
                if cnt > 0:
                    print(f"[{name}] 启动时补发缓存 {cnt} 条")
                    for cached in cache_pop_for(cache_conn, name):
                        ok_m = publish_mqtt(mqtt_client, plc_cfg["topic"], cached)
                        ok_i = write_influx(write_api, bucket, plc_cfg, tag_map, cached)
                        if not ok_m or not ok_i:
                            cache_push(cache_conn, name, cached)

                while True:
                    data = {
                        "timestamp": int(time.time() * 1000),
                        "plc": name,
                        "values": {},
                    }

                    for tag_name, meta in tag_map.items():
                        node = client.get_node(meta["node_id"])
                        value = await node.read_value()
                        data["values"][tag_name] = value

                    ok_m = publish_mqtt(mqtt_client, plc_cfg["topic"], data)
                    ok_i = write_influx(write_api, bucket, plc_cfg, tag_map, data)

                    if not ok_m or not ok_i:
                        cache_push(cache_conn, name, data)
                        cnt = cache_count_for(cache_conn, name)
                        print(f"[{name}] 已缓存 (累计 {cnt} 条)")
                    else:
                        print(f"[{name}] OK ({len(tag_map)} 点位)")
                        cnt = cache_count_for(cache_conn, name)
                        if cnt > 0:
                            print(f"[{name}] 缓存积压 {cnt} 条，开始补发")
                            batch = cache_pop_batch(cache_conn, name, 20)
                            ok_n = 0
                            for cached in batch:
                                m = publish_mqtt(mqtt_client, plc_cfg["topic"], cached)
                                i = write_influx(write_api, bucket, plc_cfg, tag_map, cached)
                                if not m or not i:
                                    cache_push(cache_conn, name, cached)
                                    break
                                ok_n += 1
                            print(f"[{name}] 补发 {ok_n} 条，剩余 {cache_count_for(cache_conn, name)} 条")

                    alarms = _process_alarms(plc_cfg, data, alarm_table, deduper)
                    if alarms:
                        _emit_alarms(mqtt_client, write_api, bucket, alarms, notifier)
                        for a in alarms:
                            print(f"[{name}] 告警 {a['drive']} {a['kind']} "
                                  f"{a['code']} {a['text']}")

                    await asyncio.sleep(plc_cfg.get("interval", 5))

        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"[{name}] 断开: {e}，{retry_delay}s 后重试")
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)
