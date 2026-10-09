"""SQLite 断网缓存。

⚠️ 补发逻辑务必用 peek + delete_by_id：
   先删后发会丢数据（发到一半失败，剩下的已经从库里没了）。
"""
import json
import sqlite3
import time


def init_cache(path="offline_cache.db"):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "plc_name TEXT NOT NULL,"
        "payload TEXT NOT NULL,"
        "created_at INTEGER NOT NULL)"
    )
    # 补索引：按 plc_name + id 查询
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cache_plc_id ON cache (plc_name, id)"
    )
    conn.commit()
    return conn


def cache_push(conn, plc_name, data):
    conn.execute(
        "INSERT INTO cache (plc_name, payload, created_at) VALUES (?, ?, ?)",
        (plc_name, json.dumps(data), int(time.time() * 1000)),
    )
    conn.commit()


def cache_count_for(conn, plc_name):
    return conn.execute(
        "SELECT COUNT(*) FROM cache WHERE plc_name=?", (plc_name,)
    ).fetchone()[0]


def cache_peek_batch(conn, plc_name, limit=20):
    """只读不删。返回 [(id, data), ...]，按 id 升序（先入先出）。"""
    rows = conn.execute(
        "SELECT id, payload FROM cache WHERE plc_name=? ORDER BY id LIMIT ?",
        (plc_name, limit),
    ).fetchall()
    return [(r[0], json.loads(r[1])) for r in rows]


def cache_delete_by_id(conn, ids):
    """按 id 列表删除。返回删除行数。"""
    if not ids:
        return 0
    placeholders = ",".join("?" * len(ids))
    cur = conn.execute(f"DELETE FROM cache WHERE id IN ({placeholders})", ids)
    conn.commit()
    return cur.rowcount


def cache_pop_batch(conn, plc_name, limit=20):
    """[已弃用] 先删后发会丢数据，请改用 peek_batch + delete_by_id。"""
    rows = cache_peek_batch(conn, plc_name, limit)
    if rows:
        cache_delete_by_id(conn, [r[0] for r in rows])
    return [r[1] for r in rows]


def cache_pop_for(conn, plc_name):
    """[已弃用] 同上。"""
    rows = conn.execute(
        "SELECT id, payload FROM cache WHERE plc_name=? ORDER BY id",
        (plc_name,),
    ).fetchall()
    if rows:
        cache_delete_by_id(conn, [r[0] for r in rows])
    return [json.loads(r[1]) for r in rows]
