"""报警代码加载 + 翻译 + 去重。"""
import time

import yaml


def load_alarm_codes(path="alarm_codes.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}

    raw = doc.get("alarms", {})
    table = {}
    for code, meta in raw.items():
        table[int(code)] = {
            "text": meta.get("text", ""),
            "severity": meta.get("severity", "warning"),
            "category": meta.get("category", "warn"),
        }
    return table


def translate(code, table):
    if not code:
        return None

    hit = table.get(int(code))
    if hit:
        return hit

    return {
        "text": f"未知代码 {int(code)}",
        "severity": "warning",
        "category": "unknown",
    }


class AlarmDeduper:
    def __init__(self, window=300):
        self.window = window
        self._last_code = {}
        self._last_emit = {}

    def should_emit(self, plc, drive, kind, code, now=None):
        now = now if now is not None else time.time()
        key = (plc, drive, kind)
        prev = self._last_code.get(key, 0)
        self._last_code[key] = code

        if code == 0:
            self._last_emit.pop(key, None)
            return False

        if code != prev:
            self._last_emit[key] = now
            return True

        if now - self._last_emit.get(key, 0) > self.window:
            self._last_emit[key] = now
            return True

        return False
