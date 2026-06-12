"""
ชั้นจัดการฐานข้อมูล SQLite สำหรับรายการค่าใช้จ่าย
"""
import sqlite3
from datetime import date, datetime
from contextlib import contextmanager

import config

# ประเภทค่าใช้จ่ายที่รองรับ (key -> ชื่อแสดงผล)
CATEGORIES = {
    "utility_water": "ค่าน้ำ",
    "utility_power": "ค่าไฟ",
    "utility_other": "ค่าสาธารณูปโภคอื่น",
    "loan_house": "ผ่อนบ้าน",
    "loan_car": "ผ่อนรถ",
    "installment": "ผ่อนสินค้า",
    "subscription": "ค่าบริการรายเดือน",
    "other": "อื่น ๆ",
}


@contextmanager
def get_conn():
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """สร้างตารางถ้ายังไม่มี"""
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                name                TEXT    NOT NULL,
                category            TEXT    NOT NULL DEFAULT 'other',
                amount              REAL    NOT NULL DEFAULT 0,
                due_day             INTEGER NOT NULL DEFAULT 1,   -- วันครบกำหนดของเดือน (1-31)
                total_installments  INTEGER,                     -- จำนวนงวดทั้งหมด (NULL = รายเดือนไม่จำกัด)
                paid_installments   INTEGER NOT NULL DEFAULT 0,   -- จำนวนงวดที่จ่ายแล้ว
                start_date          TEXT,                        -- วันเริ่ม (YYYY-MM-DD)
                remind_days_before  INTEGER NOT NULL DEFAULT 3,
                active              INTEGER NOT NULL DEFAULT 1,
                note                TEXT,
                created_at          TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
            )
            """
        )
        # ตารางบันทึกประวัติการแจ้งเตือน (กันส่งซ้ำ + ไว้ดูย้อนหลัง)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notify_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                kind        TEXT    NOT NULL,   -- monthly_summary / due_reminder / due_today
                ref_key     TEXT    NOT NULL,   -- คีย์กันส่งซ้ำ เช่น 2026-06|summary
                message     TEXT,
                sent_at     TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
            )
            """
        )


# ---------- CRUD ----------

def list_expenses(active_only=False):
    q = "SELECT * FROM expenses"
    if active_only:
        q += " WHERE active = 1"
    q += " ORDER BY due_day ASC, name ASC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(q).fetchall()]


def get_expense(expense_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        return dict(row) if row else None


def create_expense(data):
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO expenses
                (name, category, amount, due_day, total_installments,
                 paid_installments, start_date, remind_days_before, active, note)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                data["name"],
                data.get("category", "other"),
                float(data.get("amount", 0) or 0),
                int(data.get("due_day", 1) or 1),
                _int_or_none(data.get("total_installments")),
                int(data.get("paid_installments", 0) or 0),
                data.get("start_date") or None,
                int(data.get("remind_days_before", config.DEFAULT_REMIND_DAYS_BEFORE) or 3),
                1 if data.get("active", 1) else 0,
                data.get("note") or None,
            ),
        )
        return cur.lastrowid


def update_expense(expense_id, data):
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE expenses SET
                name=?, category=?, amount=?, due_day=?, total_installments=?,
                paid_installments=?, start_date=?, remind_days_before=?, active=?, note=?
            WHERE id=?
            """,
            (
                data["name"],
                data.get("category", "other"),
                float(data.get("amount", 0) or 0),
                int(data.get("due_day", 1) or 1),
                _int_or_none(data.get("total_installments")),
                int(data.get("paid_installments", 0) or 0),
                data.get("start_date") or None,
                int(data.get("remind_days_before", config.DEFAULT_REMIND_DAYS_BEFORE) or 3),
                1 if data.get("active", 1) else 0,
                data.get("note") or None,
                expense_id,
            ),
        )


def delete_expense(expense_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))


def increment_paid(expense_id, by=1):
    """เพิ่มจำนวนงวดที่จ่ายแล้ว (กดเมื่อจ่ายเงินจริง)"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE expenses SET paid_installments = paid_installments + ? WHERE id = ?",
            (by, expense_id),
        )


# ---------- notify log ----------

def already_sent(ref_key):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM notify_log WHERE ref_key = ? LIMIT 1", (ref_key,)
        ).fetchone()
        return row is not None


def record_sent(kind, ref_key, message):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO notify_log (kind, ref_key, message) VALUES (?,?,?)",
            (kind, ref_key, message),
        )


def recent_logs(limit=30):
    with get_conn() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM notify_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        ]


def _int_or_none(v):
    if v is None or v == "" or str(v).lower() == "none":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
