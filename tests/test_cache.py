"""测试 SQLite 断网缓存。"""
import pytest
from app.cache import init_cache, cache_push, cache_count_for, cache_pop_batch


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "test_cache.db"
    return init_cache(str(db))


class TestCache:
    def test_empty_initially(self, conn):
        assert cache_count_for(conn, "plc1") == 0

    def test_push_and_count(self, conn):
        cache_push(conn, "plc1", {"a": 1})
        cache_push(conn, "plc1", {"a": 2})
        assert cache_count_for(conn, "plc1") == 2

    def test_separate_by_plc(self, conn):
        cache_push(conn, "plc1", {"a": 1})
        cache_push(conn, "plc2", {"a": 2})
        assert cache_count_for(conn, "plc1") == 1
        assert cache_count_for(conn, "plc2") == 1

    def test_pop_batch(self, conn):
        for i in range(5):
            cache_push(conn, "plc1", {"i": i})
        batch = cache_pop_batch(conn, "plc1", 3)
        assert len(batch) == 3
        assert batch[0]["i"] == 0
        assert cache_count_for(conn, "plc1") == 2

    def test_pop_removes(self, conn):
        cache_push(conn, "plc1", {"a": 1})
        cache_pop_batch(conn, "plc1", 10)
        assert cache_count_for(conn, "plc1") == 0
