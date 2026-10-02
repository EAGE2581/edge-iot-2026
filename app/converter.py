"""原始值 → 真实物理量的换算 + 数据清洗。"""
import math


def convert(value, field_type, rated_current=16.0):
    raw = int(value)
    if field_type == "current":
        return round((raw / 16384) * rated_current, 2)
    if field_type == "speed":
        return round((raw / 16384) * 1500, 1)
    if field_type == "temp":
        return round(raw / 100, 1)
    return raw


def is_valid(value, field_type, rated_current=16.0):
    if value is None:
        return False
    try:
        raw = int(value)
    except (TypeError, ValueError):
        return False
    if raw == -32768:
        return False

    if field_type == "current":
        amps = (raw / 16384) * rated_current
        return 0 <= amps <= 2 * rated_current
    if field_type == "speed":
        rpm = (raw / 16384) * 1500
        return -1600 <= rpm <= 1600
    if field_type == "temp":
        c = raw / 100
        return -50 <= c <= 200
    return 0 <= raw <= 65535
