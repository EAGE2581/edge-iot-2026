"""原始值 → 真实物理量的换算。"""


def convert(value, field_type, rated_current=16.0):
    raw = int(value)
    if field_type == "current":
        return round((raw / 16384) * rated_current, 2)
    if field_type == "speed":
        return round((raw / 16384) * 1500, 1)
    if field_type == "temp":
        return round(raw / 100, 1)
    return raw
