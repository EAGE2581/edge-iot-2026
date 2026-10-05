"""测试报警翻译和去重。"""
import pytest
from app.alarm_codes import AlarmDeduper, translate


@pytest.fixture
def table():
    return {
        7900: {"text": "驱动：电机堵转", "severity": "critical", "category": "fault"},
        7910: {"text": "驱动：电机超温", "severity": "warning", "category": "warn"},
    }


class TestTranslate:
    def test_zero_returns_none(self, table):
        assert translate(0, table) is None

    def test_known_code(self, table):
        info = translate(7900, table)
        assert info["text"] == "驱动：电机堵转"
        assert info["severity"] == "critical"

    def test_unknown_code(self, table):
        info = translate(99999, table)
        assert "未知" in info["text"]
        assert info["category"] == "unknown"


class TestAlarmDeduper:
    def test_first_time_emit(self):
        d = AlarmDeduper(window=300)
        assert d.should_emit("p1", "drive_1", "fault", 7900, now=100) is True

    def test_duplicate_within_window(self):
        d = AlarmDeduper(window=300)
        d.should_emit("p1", "drive_1", "fault", 7900, now=100)
        assert d.should_emit("p1", "drive_1", "fault", 7900, now=105) is False

    def test_after_window(self):
        d = AlarmDeduper(window=300)
        d.should_emit("p1", "drive_1", "fault", 7900, now=100)
        assert d.should_emit("p1", "drive_1", "fault", 7900, now=500) is True

    def test_code_change(self):
        d = AlarmDeduper(window=300)
        d.should_emit("p1", "drive_1", "fault", 7900, now=100)
        assert d.should_emit("p1", "drive_1", "fault", 7910, now=101) is True

    def test_zero_clears(self):
        d = AlarmDeduper(window=300)
        d.should_emit("p1", "drive_1", "fault", 7900, now=100)
        assert d.should_emit("p1", "drive_1", "fault", 0, now=101) is False

    def test_reappear_after_zero(self):
        d = AlarmDeduper(window=300)
        d.should_emit("p1", "drive_1", "fault", 7900, now=100)
        d.should_emit("p1", "drive_1", "fault", 0, now=101)
        assert d.should_emit("p1", "drive_1", "fault", 7900, now=102) is True
