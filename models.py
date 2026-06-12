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

# ไอคอน emoji ของแต่ละหมวด (ใช้แสดงผลในหน้าเว็บ)
CATEGORY_ICONS = {
    "utility_water": "💧",
    "utility_power": "⚡",
    "utility_other": "🏠",
    "loan_house": "🏡",
    "loan_car": "🚗",
    "installment": "📱",
    "subscription": "🔁",
    "other": "📌",
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
        # ตารางประวัติการจ่ายเงิน
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                expense_id  INTEGER NOT NULL,
                amount      REAL    NOT NULL DEFAULT 0,
                paid_date   TEXT    NOT NULL,   -- YYYY-MM-DD
                installment_no INTEGER,         -- งวดที่เท่าไหร่ (ถ้าเป็นการผ่อน)
                note        TEXT,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (expense_id) REFERENCES expenses(id) ON DELETE CASCADE
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
            "UPDATE expenses SET paid_installments = MAX(0, paid_installments + ?) WHERE id = ?",
            (by, expense_id),
        )


# ---------- payments (ประวัติการจ่าย) ----------

def record_payment(expense_id, amount, paid_date, installment_no=None, note=None):
    """บันทึกการจ่าย 1 ครั้ง คืน id ของรายการที่บันทึก"""
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO payments (expense_id, amount, paid_date, installment_no, note)
            VALUES (?,?,?,?,?)
            """,
            (expense_id, float(amount or 0), paid_date, installment_no, note or None),
        )
        return cur.lastrowid


def list_payments(expense_id=None, limit=None):
    """ดูประวัติการจ่าย (ทั้งหมด หรือเฉพาะรายการเดียว) พร้อมชื่อรายการ"""
    q = (
        "SELECT p.*, e.name AS expense_name, e.category AS category "
        "FROM payments p LEFT JOIN expenses e ON e.id = p.expense_id"
    )
    params = []
    if expense_id is not None:
        q += " WHERE p.expense_id = ?"
        params.append(expense_id)
    q += " ORDER BY p.paid_date DESC, p.id DESC"
    if limit:
        q += " LIMIT ?"
        params.append(limit)
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def get_payment(payment_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
        return dict(row) if row else None


def delete_payment(payment_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM payments WHERE id = ?", (payment_id,))


def payment_total(expense_id=None):
    """ยอดรวมที่จ่ายไปแล้วทั้งหมด (หรือเฉพาะรายการเดียว)"""
    q = "SELECT COALESCE(SUM(amount),0) AS t FROM payments"
    params = []
    if expense_id is not None:
        q += " WHERE expense_id = ?"
        params.append(expense_id)
    with get_conn() as conn:
        return conn.execute(q, params).fetchone()["t"]


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
