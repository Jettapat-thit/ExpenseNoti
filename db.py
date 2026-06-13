"""
ชั้นเชื่อมต่อฐานข้อมูล — รองรับทั้ง PostgreSQL และ SQLite
- ถ้าตั้ง DATABASE_URL (postgres://...) จะใช้ Postgres  (เหมาะกับ production / ต่อ DBeaver)
- ถ้าไม่ตั้ง จะใช้ SQLite ที่ DATABASE_PATH  (เหมาะกับรันในเครื่อง)

โค้ดส่วนอื่น (models.py) เรียกผ่าน get_conn() แล้วใช้ conn.execute(sql, params)
โดยใช้ placeholder '?' เหมือนเดิม — ตัว wrapper จะแปลงเป็น '%s' ให้อัตโนมัติเมื่อเป็น Postgres
"""
import os
from contextlib import contextmanager

import config

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
IS_PG = DATABASE_URL.startswith("postgres")

# คำที่ต่างกันระหว่าง dialect
AUTOPK = "BIGSERIAL PRIMARY KEY" if IS_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"
NOW = "now()::text" if IS_PG else "datetime('now','localtime')"   # คืนค่าเป็น text เวลาปัจจุบัน
GREATEST = "GREATEST" if IS_PG else "MAX"                          # ค่ามากสุดแบบ scalar

if IS_PG:
    import psycopg
    from psycopg.rows import dict_row


class _Conn:
    """ห่อ connection ให้ใช้งานเหมือน sqlite (conn.execute) ได้ทั้งสอง backend"""

    def __init__(self, raw):
        self.raw = raw

    def _q(self, sql):
        return sql.replace("?", "%s") if IS_PG else sql

    def execute(self, sql, params=()):
        if IS_PG:
            cur = self.raw.cursor()
            cur.execute(self._q(sql), params)
            return cur
        return self.raw.execute(sql, params)

    def executemany(self, sql, seq):
        if IS_PG:
            cur = self.raw.cursor()
            cur.executemany(self._q(sql), list(seq))
            return cur
        return self.raw.executemany(sql, seq)

    def insert_returning_id(self, sql, params=()):
        """INSERT แล้วคืนค่า id ของแถวที่เพิ่ง insert (ใช้ได้ทั้งสอง backend)"""
        if IS_PG:
            cur = self.raw.cursor()
            cur.execute(self._q(sql) + " RETURNING id", params)
            return cur.fetchone()["id"]
        cur = self.raw.execute(sql, params)
        return cur.lastrowid

    def column_exists(self, table, column):
        if IS_PG:
            cur = self.raw.cursor()
            cur.execute(
                "SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s",
                (table, column),
            )
            return cur.fetchone() is not None
        rows = self.raw.execute(f"PRAGMA table_info({table})").fetchall()
        return any(r["name"] == column for r in rows)

    def add_column(self, table, column, decl):
        """เพิ่มคอลัมน์ถ้ายังไม่มี"""
        if IS_PG:
            self.raw.cursor().execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {decl}"
            )
        elif not self.column_exists(table, column):
            self.raw.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")

    def commit(self):
        self.raw.commit()

    def close(self):
        self.raw.close()


@contextmanager
def get_conn():
    if IS_PG:
        raw = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    else:
        import sqlite3
        raw = sqlite3.connect(config.DATABASE_PATH)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA foreign_keys = ON")
    conn = _Conn(raw)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def backend_name():
    return "PostgreSQL" if IS_PG else "SQLite"
