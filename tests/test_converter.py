"""测试 converter 的换算和清洗。"""
import pytest
from app.converter import convert, is_valid


class TestConvert:
    def test_current_half(self):
        assert convert(8192, "current", 16.0) == 8.0

    def test_current_full(self):
        assert convert(16384, "current", 16.0) == 16.0

    def test_current_zero(self):
        assert convert(0, "current", 16.0) == 0.0

    def test_speed(self):
        assert convert(8192, "speed") == 750.0

    def test_temp(self):
        assert convert(4250, "temp") == 42.5

    def test_raw_passthrough(self):
        assert convert(12345, "raw") == 12345


class TestIsValid:
    def test_none_invalid(self):
        assert is_valid(None, "current") is False

    def test_overflow_invalid(self):
        assert is_valid(-32768, "raw") is False

    def test_current_normal(self):
        assert is_valid(8192, "current") is True

    def test_current_overflow(self):
        # 33000 → 32.2A，超 2 倍额定
        assert is_valid(33000, "current", 16.0) is False

    def test_speed_normal(self):
        assert is_valid(8192, "speed") is True

    def test_speed_overflow(self):
        assert is_valid(30000, "speed") is False

    def test_temp_normal(self):
        assert is_valid(4000, "temp") is True

    def test_temp_overflow(self):
        assert is_valid(30000, "temp") is False

    def test_raw_valid(self):
        assert is_valid(12345, "raw") is True

    def test_raw_too_big(self):
        assert is_valid(99999, "raw") is False

    def test_string_invalid(self):
        assert is_valid("abc", "raw") is False
