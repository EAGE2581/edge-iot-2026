"""降采样：每 5 分钟把原始数据聚合为 5 分钟均值。"""
import asyncio
import time

from influxdb_client import Point
from influxdb_client.client.write_api import SYNCHRONOUS

DOWNSAMPLE_FIELDS = ("iatst_glatt", "nist_a", "motor_temp", "mist_glatt")


def build_query(bucket, minutes=5):
    fields_filter = " or ".join(
        f'r._field == "{f}"' for f in DOWNSAMPLE_FIELDS
    )
    return f'''
from(bucket: "{bucket}")
  |> range(start: -{minutes}m)
  |> filter(fn: (r) => r._measurement == "drive_metrics")
  |> filter(fn: (r) => {fields_filter})
'''


def run_once(client, bucket, org, minutes=5):
    query_api = client.query_api()
    write_api = client.write_api(write_options=SYNCHRONOUS)
    flux = build_query(bucket, minutes)

    try:
        tables = query_api.query(flux, org=org)
    except Exception as e:
        print(f"[downsampler] 查询失败: {e}")
        return 0

    grouped = {}
    for table in tables:
        for record in table.records:
            plc = record.values.get("plc", "?")
            drive = record.values.get("drive", "?")
            field = record.get_field()
            value = record.get_value()
            if value is None:
                continue
            grouped.setdefault((plc, drive), {}).setdefault(field, []).append(value)

    if not grouped:
        return 0

    count = 0
    ts_ns = int(time.time() * 1_000_000_000)
    for (plc, drive), fields in grouped.items():
        point = (
            Point("drive_metrics_5m")
            .tag("plc", plc)
            .tag("drive", drive)
        )
        has_field = False
        for fname, values in fields.items():
            if not values:
                continue
            avg = sum(values) / len(values)
            point = point.field(f"{fname}_mean", round(avg, 2))
            has_field = True

        if has_field:
            point = point.time(ts_ns)
            try:
                write_api.write(bucket=bucket, record=point)
                count += 1
            except Exception as e:
                print(f"[downsampler] 写入失败 {plc}/{drive}: {e}")

    return count


async def downsample_loop(client, bucket, org, interval=300):
    print(f"[downsampler] 已启动，每 {interval} 秒聚合一次")
    while True:
        try:
            await asyncio.sleep(interval)
            n = run_once(client, bucket, org)
            if n > 0:
                print(f"[downsampler] 已聚合 {n} 组 5 分钟数据")
        except asyncio.CancelledError:
            print("[downsampler] 已停止")
            raise
        except Exception as e:
            print(f"[downsampler] 异常: {e}")
