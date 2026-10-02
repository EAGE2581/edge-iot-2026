"""EDGE-IOT-2026 采集入口（v2.0 模块化）。"""
import argparse
import asyncio
import os

from app.config_loader import load_plcs
from app.cache import init_cache
from app.transports import make_mqtt, make_influx
from app.alarm_codes import load_alarm_codes, AlarmDeduper
from app.notifier import load_notifier
from app.downsampler import downsample_loop
from app.worker import collect_plc


async def main(config_path, plc_names=None, alarm_path="alarm_codes.yaml"):
    cfg, selected = load_plcs(config_path, plc_names)

    if not selected:
        print("[!] 没有要跑的 PLC")
        return

    print(f"[*] 启动 {len(selected)} 个 PLC")
    for p in selected:
        print(f"    {p['name']} | {p['drive_count']} 台 | {len(p['fields'])} 字段")

    alarm_table = {}
    if os.path.exists(alarm_path):
        alarm_table = load_alarm_codes(alarm_path)
        print(f"[*] 加载报警映射表 {len(alarm_table)} 条 ({alarm_path})")
    else:
        print(f"[!] 未找到 {alarm_path}，报警将显示未知代码")

    notifier = load_notifier(cfg)
    if notifier is not None:
        print(f"[*] 钉钉推送已启用（min_severity={notifier.min_level}）")
    else:
        print("[*] 钉钉推送未启用")

    mqtt_client = make_mqtt(cfg["mqtt"]["host"], cfg["mqtt"]["port"])
    influx_client, write_api = make_influx(
        cfg["influx"]["url"], cfg["influx"]["token"], cfg["influx"]["org"]
    )
    cache_conn = init_cache()
    deduper = AlarmDeduper(window=300)

    tasks = [
        asyncio.create_task(
            collect_plc(
                p, mqtt_client, write_api,
                cfg["influx"]["bucket"], cache_conn,
                alarm_table, deduper,
                notifier,
            )
        )
        for p in selected
    ]

    tasks.append(asyncio.create_task(
        downsample_loop(influx_client, cfg["influx"]["bucket"], cfg["influx"]["org"])
    ))

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    parser.add_argument("--plc", nargs="+")
    parser.add_argument("--alarms", default="alarm_codes.yaml")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.config, args.plc, args.alarms))
    except KeyboardInterrupt:
        print("\n[*] 已停止")
