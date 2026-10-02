"""SQLite 断网缓存。"""
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
    conn.commit()
    return conn


def cache_push(conn, plc_name, data):
    conn.execute(
        "INSERT INTO cache (plc_name, payload, created_at) VALUES (?, ?, ?)",
        (plc_name, json.dumps(data), int(time.time() * 1000)),
    )
    conn.commit()


def cache_pop_for(conn, plc_name):
    rows = conn.execute(
        "SELECT id, payload FROM cache WHERE plc_name=? ORDER BY id",
        (plc_name,),
    ).fetchall()
    if rows:
        ids = [r[0] for r in rows]
        placeholders = ",".join("?" * len(ids))
        conn.execute(f"DELETE FROM cache WHERE id IN ({placeholders})", ids)
        conn.commit()
    return [json.loads(r[1]) for r in rows]


def cache_pop_batch(conn, plc_name, limit=20):
    rows = conn.execute(
        "SELECT id, payload FROM cache WHERE plc_name=? ORDER BY id LIMIT ?",
        (plc_name, limit),
    ).fetchall()
    if rows:
        ids = [r[0] for r in rows]
        placeholders = ",".join("?" * len(ids))
        conn.execute(f"DELETE FROM cache WHERE id IN ({placeholders})", ids)
        conn.commit()
    return [json.loads(r[1]) for r in rows]


def cache_count_for(conn, plc_name):
    return conn.execute(
        "SELECT COUNT(*) FROM cache WHERE plc_name=?", (plc_name,)
    ).fetchone()[0]
