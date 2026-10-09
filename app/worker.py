"""单个 PLC 的采集主循环（订阅 + 轮询混合）。

关键点：
1. 缓存补发用 peek_batch + delete_by_id，失败不丢数据
2. 钉钉推送是 async，不阻塞采集循环
3. 订阅值带新鲜度判定，过期值不发送并打日志
"""
import asyncio
import time

from asyncua import Client

from .node_builder import build_node_ids, split_by_mode
from .cache import (
    cache_push, cache_peek_batch, cache_delete_by_id, cache_count_for,
)
from .transports import publish_mqtt, write_influx, write_alarm_influx
from .alarm_codes import translate
from .converter import is_valid
from .subscriber import OpcUaSubscriber


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
            try:
                code = int(data["values"][key])
            except (TypeError, ValueError):
                continue
            if not deduper.should_emit(plc, drive, kind, code, now):
                continue
            info = translate(code, alarm_table)
            if info is None:
                continue
            out.append({
                "timestamp": ts, "plc": plc, "drive": drive, "kind": kind,
                "code": code, "text": info["text"], "severity": info["severity"],
                "category": info["category"], "topic": topic,
            })
    return out


async def _emit_alarms(mqtt_client, write_api, bucket, alarms, notifier=None):
    for a in alarms:
        publish_mqtt(mqtt_client, a["topic"], a)
        write_alarm_influx(write_api, bucket, a)
        if notifier is not None and a["severity"] == "critical":
            ok = await notifier.send_alarm(a)
            if ok:
                print(f"[ding] 已推送: {a['plc']} {a['drive']} {a['code']} {a['text']}")


async def _read_poll_nodes(client, poll_nodes, rated, name):
    values = {}
    for key, meta in poll_nodes.items():
        try:
            node = client.get_node(meta["node_id"])
            value = await node.read_value()
        except Exception as e:
            print(f"[{name}] 轮询读值失败 {key}: {e}")
            continue
        if is_valid(value, meta["type"], rated):
            values[key] = value
        else:
            print(f"[{name}] 丢弃异常值 {key}={value}")
    return values


async def _flush_cache_batch(plc_cfg, mqtt_client, write_api, bucket,
                              tag_map, cache_conn, name, limit=20):
    """从缓存补发一批。失败就停，剩下的留在库里。
    返回成功补发条数。"""
    batch = cache_peek_batch(cache_conn, name, limit)
    if not batch:
        return 0

    ok_ids = []
    for cache_id, cached in batch:
        m = publish_mqtt(mqtt_client, plc_cfg["topic"], cached)
        i = write_influx(write_api, bucket, plc_cfg, tag_map, cached)
        if not m or not i:
            break   # 失败：剩下的不删
        ok_ids.append(cache_id)

    if ok_ids:
        cache_delete_by_id(cache_conn, ok_ids)
    return len(ok_ids)


async def collect_plc(
    plc_cfg, mqtt_client, write_api, bucket, cache_conn, alarm_table, deduper,
    notifier=None,
):
    name = plc_cfg["name"]
    rated = plc_cfg.get("rated_current", 16.0)
    interval = plc_cfg.get("interval", 5)

    tag_map = build_node_ids(plc_cfg)
    subscribe_nodes, poll_nodes = split_by_mode(tag_map)
    print(f"[{name}] 节点分类：订阅 {len(subscribe_nodes)} 个 / 轮询 {len(poll_nodes)} 个")

    retry_delay = 5
    max_delay = 60
    stale_warned = False   # 过期只警告一次，避免刷屏

    while True:
        try:
            async with Client(plc_cfg["url"]) as client:
                print(f"[{name}] 已连接")
                retry_delay = 5

                subscriber = OpcUaSubscriber(period_ms=100, interval_s=interval)
                try:
                    await subscriber.start(client, subscribe_nodes)
                    print(f"[{name}] 订阅已建立（{len(subscribe_nodes)} 个节点）")
                except Exception as e:
                    print(f"[{name}] 订阅建立失败: {e}，仅用轮询模式")
                    subscriber = None

                # 启动时补发
                cnt = cache_count_for(cache_conn, name)
                if cnt > 0:
                    print(f"[{name}] 启动时补发缓存 {cnt} 条")
                    total = 0
                    while True:
                        n = await _flush_cache_batch(
                            plc_cfg, mqtt_client, write_api, bucket,
                            tag_map, cache_conn, name, limit=100,
                        )
                        total += n
                        if n == 0:
                            break
                    print(f"[{name}] 启动补发 {total} 条，剩余 {cache_count_for(cache_conn, name)} 条")

                while True:
                    data = {"timestamp": int(time.time() * 1000), "plc": name, "values": {}}

                    if subscriber is not None:
                        snap = subscriber.snapshot()
                        for key, val in snap.items():
                            meta = tag_map.get(key)
                            if meta is None:
                                continue
                            if is_valid(val, meta["type"], rated):
                                data["values"][key] = val

                        # 新鲜度检查
                        stale = subscriber.stale_keys()
                        if stale and not stale_warned:
                            print(f"[{name}] ⚠ 订阅值过期 {len(stale)} 个：{stale[:5]}...")
                            stale_warned = True
                        elif not stale:
                            stale_warned = False

                    poll_values = await _read_poll_nodes(client, poll_nodes, rated, name)
                    data["values"].update(poll_values)

                    ok_m = publish_mqtt(mqtt_client, plc_cfg["topic"], data)
                    ok_i = write_influx(write_api, bucket, plc_cfg, tag_map, data)

                    if not ok_m or not ok_i:
                        cache_push(cache_conn, name, data)
                        cnt = cache_count_for(cache_conn, name)
                        print(f"[{name}] 已缓存 (累计 {cnt} 条)")
                    else:
                        sub_n = len(data["values"]) if subscriber else 0
                        print(f"[{name}] OK 订阅 {sub_n}/{len(subscribe_nodes)} 轮询 {len(poll_values)}/{len(poll_nodes)}")

                        # 在线时小批量补发
                        cnt = cache_count_for(cache_conn, name)
                        if cnt > 0:
                            n = await _flush_cache_batch(
                                plc_cfg, mqtt_client, write_api, bucket,
                                tag_map, cache_conn, name, limit=20,
                            )
                            print(f"[{name}] 补发 {n} 条，剩余 {cache_count_for(cache_conn, name)} 条")

                    alarms = _process_alarms(plc_cfg, data, alarm_table, deduper)
                    if alarms:
                        await _emit_alarms(mqtt_client, write_api, bucket, alarms, notifier)
                        for a in alarms:
                            print(f"[{name}] 告警 {a['drive']} {a['kind']} {a['code']} {a['text']}")

                    await asyncio.sleep(interval)

        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"[{name}] 断开: {e}，{retry_delay}s 后重试")
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)
