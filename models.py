"""
ชั้นจัดการฐานข้อมูล — แบบหลายผู้ใช้ (multi-user) รองรับทั้ง PostgreSQL และ SQLite
ทุกตารางผูกกับ user_id และทุกฟังก์ชันต้องส่ง user_id เพื่อแยกข้อมูลของแต่ละคน
ผู้ใช้ผูกกับบัญชี LINE ผ่าน line_user_id
การเชื่อมต่อ/ความต่างของ dialect อยู่ใน db.py
"""
from datetime import date

import config
import db
from db import get_conn

# หมวดหมู่เริ่มต้น (seed ให้ user ใหม่แต่ละคน) — (key, ชื่อ, ไอคอน, ชนิด, ลำดับ)
DEFAULT_CATEGORIES = [
    ("utility_water", "ค่าน้ำ", "💧", "expense", 10),
    ("utility_power", "ค่าไฟ", "⚡", "expense", 20),
    ("utility_other", "ค่าสาธารณูปโภคอื่น", "🏠", "expense", 30),
    ("loan_house", "ผ่อนบ้าน", "🏡", "expense", 40),
    ("loan_car", "ผ่อนรถ", "🚗", "expense", 50),
    ("installment", "ผ่อนสินค้า", "📱", "expense", 60),
    ("subscription", "ค่าบริการรายเดือน", "🔁", "expense", 70),
    ("credit_card", "บัตรเครดิต", "💳", "expense", 75),
    ("other", "อื่น ๆ", "📌", "expense", 999),
    ("salary", "เงินเดือน", "💰", "income", 10),
    ("bonus", "โบนัส/รายได้พิเศษ", "🎁", "income", 20),
    ("income_other", "รายได้อื่น", "💵", "income", 999),
]


def init_db():
    """สร้างตาราง + migration — ใช้ได้ทั้ง PostgreSQL และ SQLite"""
    pk = db.AUTOPK
    now = db.NOW
    with get_conn() as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS users (
                id            {pk},
                line_user_id  TEXT UNIQUE NOT NULL,
                display_name  TEXT,
                picture_url   TEXT,
                notify_hour   INTEGER NOT NULL DEFAULT 8,
                summary_day   INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT NOT NULL DEFAULT ({now}),
                last_login    TEXT
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS expenses (
                id                  {pk},
                user_id             INTEGER NOT NULL DEFAULT 0,
                name                TEXT    NOT NULL,
                category            TEXT    NOT NULL DEFAULT 'other',
                amount              REAL    NOT NULL DEFAULT 0,
                due_day             INTEGER NOT NULL DEFAULT 1,
                total_installments  INTEGER,
                paid_installments   INTEGER NOT NULL DEFAULT 0,
                start_date          TEXT,
                remind_days_before  INTEGER NOT NULL DEFAULT 3,
                active              INTEGER NOT NULL DEFAULT 1,
                note                TEXT,
                type                TEXT    NOT NULL DEFAULT 'expense',
                variable_amount     INTEGER NOT NULL DEFAULT 0,
                created_at          TEXT    NOT NULL DEFAULT ({now})
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS payments (
                id          {pk},
                user_id     INTEGER NOT NULL DEFAULT 0,
                expense_id  INTEGER NOT NULL,
                amount      REAL    NOT NULL DEFAULT 0,
                paid_date   TEXT    NOT NULL,
                installment_no INTEGER,
                note        TEXT,
                created_at  TEXT    NOT NULL DEFAULT ({now})
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS notify_log (
                id          {pk},
                user_id     INTEGER NOT NULL DEFAULT 0,
                kind        TEXT    NOT NULL,
                ref_key     TEXT    NOT NULL,
                message     TEXT,
                sent_at     TEXT    NOT NULL DEFAULT ({now})
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS categories (
                id          {pk},
                user_id     INTEGER NOT NULL DEFAULT 0,
                key         TEXT NOT NULL,
                label       TEXT NOT NULL,
                icon        TEXT NOT NULL DEFAULT '📌',
                type        TEXT NOT NULL DEFAULT 'expense',
                sort_order  INTEGER NOT NULL DEFAULT 100,
                UNIQUE(user_id, key)
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS budgets (
                id        {pk},
                user_id   INTEGER NOT NULL,
                category  TEXT    NOT NULL,
                amount    REAL    NOT NULL DEFAULT 0,
                UNIQUE(user_id, category)
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS goals (
                id                   {pk},
                user_id              INTEGER NOT NULL,
                name                 TEXT    NOT NULL,
                icon                 TEXT    NOT NULL DEFAULT '🎯',
                target_amount        REAL    NOT NULL DEFAULT 0,
                saved_amount         REAL    NOT NULL DEFAULT 0,
                monthly_contribution REAL    NOT NULL DEFAULT 0,
                created_at           TEXT    NOT NULL DEFAULT ({now})
            )
            """
        )

        # ---- migration จากสคีมาเดิม (single-user) ----
        conn.add_column("expenses", "user_id", "INTEGER NOT NULL DEFAULT 0")
        conn.add_column("expenses", "type", "TEXT NOT NULL DEFAULT 'expense'")
        conn.add_column("expenses", "variable_amount", "INTEGER NOT NULL DEFAULT 0")
        conn.add_column("payments", "user_id", "INTEGER NOT NULL DEFAULT 0")
        conn.add_column("notify_log", "user_id", "INTEGER NOT NULL DEFAULT 0")
        conn.add_column("categories", "user_id", "INTEGER NOT NULL DEFAULT 0")


# ---------- users ----------

def upsert_user(line_user_id, display_name=None, picture_url=None):
    """สร้าง user ถ้ายังไม่มี (พร้อม seed หมวด) หรืออัปเดตข้อมูลโปรไฟล์ — คืน dict ของ user"""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE line_user_id = ?", (line_user_id,)).fetchone()
        if row:
            conn.execute(
                f"UPDATE users SET display_name=?, picture_url=?, last_login={db.NOW} WHERE id=?",
                (display_name, picture_url, row["id"]),
            )
            user_id = row["id"]
            is_new = False
        else:
            user_id = conn.insert_returning_id(
                f"INSERT INTO users (line_user_id, display_name, picture_url, last_login) "
                f"VALUES (?,?,?,{db.NOW})",
                (line_user_id, display_name, picture_url),
            )
            is_new = True
        if is_new:
            conn.executemany(
                "INSERT INTO categories (user_id, key, label, icon, type, sort_order) VALUES (?,?,?,?,?,?)",
                [(user_id, *c) for c in DEFAULT_CATEGORIES],
            )
        return dict(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def get_user(user_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def list_users():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM users ORDER BY id").fetchall()]


def update_user_settings(user_id, notify_hour=None, summary_day=None):
    with get_conn() as conn:
        if notify_hour is not None:
            conn.execute("UPDATE users SET notify_hour=? WHERE id=?", (int(notify_hour), user_id))
        if summary_day is not None:
            conn.execute("UPDATE users SET summary_day=? WHERE id=?", (int(summary_day), user_id))


# ---------- categories (ต่อ user) ----------

def get_categories(user_id, kind=None):
    q = "SELECT * FROM categories WHERE user_id = ?"
    params = [user_id]
    if kind:
        q += " AND type = ?"
        params.append(kind)
    q += " ORDER BY type, sort_order, label"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def category_map(user_id, kind=None):
    return {c["key"]: c["label"] for c in get_categories(user_id, kind)}


def icon_map(user_id, kind=None):
    return {c["key"]: c["icon"] for c in get_categories(user_id, kind)}


def create_category(user_id, key, label, icon, kind="expense"):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO categories (user_id, key, label, icon, type, sort_order) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET label=excluded.label, icon=excluded.icon, type=excluded.type",
            (user_id, key, label, icon or "📌", kind if kind in ("expense", "income") else "expense", 500),
        )


def delete_category(user_id, key):
    with get_conn() as conn:
        used = conn.execute(
            "SELECT COUNT(*) AS n FROM expenses WHERE user_id=? AND category=?", (user_id, key)
        ).fetchone()["n"]
        if used:
            return False
        conn.execute("DELETE FROM categories WHERE user_id=? AND key=?", (user_id, key))
        return True


# ---------- expenses (ต่อ user) ----------

def list_expenses(user_id, active_only=False, kind=None):
    q = "SELECT * FROM expenses WHERE user_id = ?"
    params = [user_id]
    if active_only:
        q += " AND active = 1"
    if kind:
        q += " AND type = ?"
        params.append(kind)
    q += " ORDER BY due_day ASC, name ASC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def get_expense(user_id, expense_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id)
        ).fetchone()
        return dict(row) if row else None


def create_expense(user_id, data):
    with get_conn() as conn:
        return conn.insert_returning_id(
            """
            INSERT INTO expenses
                (user_id, name, category, amount, due_day, total_installments,
                 paid_installments, start_date, remind_days_before, active, note, type, variable_amount)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                user_id,
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
                data.get("type", "expense") if data.get("type") in ("expense", "income") else "expense",
                1 if data.get("variable_amount") else 0,
            ),
        )


def update_expense(user_id, expense_id, data):
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE expenses SET
                name=?, category=?, amount=?, due_day=?, total_installments=?,
                paid_installments=?, start_date=?, remind_days_before=?, active=?, note=?, type=?, variable_amount=?
            WHERE id=? AND user_id=?
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
                data.get("type", "expense") if data.get("type") in ("expense", "income") else "expense",
                1 if data.get("variable_amount") else 0,
                expense_id, user_id,
            ),
        )


def delete_expense(user_id, expense_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM expenses WHERE id=? AND user_id=?", (expense_id, user_id))
        conn.execute("DELETE FROM payments WHERE expense_id=? AND user_id=?", (expense_id, user_id))


def increment_paid(user_id, expense_id, by=1):
    with get_conn() as conn:
        conn.execute(
            f"UPDATE expenses SET paid_installments = {db.GREATEST}(0, paid_installments + ?) WHERE id=? AND user_id=?",
            (by, expense_id, user_id),
        )


# ---------- payments (ต่อ user) ----------

def record_payment(user_id, expense_id, amount, paid_date, installment_no=None, note=None):
    with get_conn() as conn:
        return conn.insert_returning_id(
            "INSERT INTO payments (user_id, expense_id, amount, paid_date, installment_no, note) "
            "VALUES (?,?,?,?,?,?)",
            (user_id, expense_id, float(amount or 0), paid_date, installment_no, note or None),
        )


def list_payments(user_id, expense_id=None, limit=None):
    q = (
        "SELECT p.*, e.name AS expense_name, e.category AS category "
        "FROM payments p LEFT JOIN expenses e ON e.id = p.expense_id "
        "WHERE p.user_id = ?"
    )
    params = [user_id]
    if expense_id is not None:
        q += " AND p.expense_id = ?"
        params.append(expense_id)
    q += " ORDER BY p.paid_date DESC, p.id DESC"
    if limit:
        q += " LIMIT ?"
        params.append(limit)
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def get_payment(user_id, payment_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM payments WHERE id=? AND user_id=?", (payment_id, user_id)
        ).fetchone()
        return dict(row) if row else None


def delete_payment(user_id, payment_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM payments WHERE id=? AND user_id=?", (payment_id, user_id))


def paid_expense_ids(user_id, ym=None):
    """คืน set ของ expense_id ที่มีการบันทึกจ่ายในเดือนนั้น (ใช้ทำ checklist จ่ายแล้ว/ยังไม่จ่าย)"""
    ym = ym or date.today().strftime("%Y-%m")
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT expense_id FROM payments WHERE user_id=? AND substr(paid_date,1,7)=?",
            (user_id, ym),
        ).fetchall()
    return {r["expense_id"] for r in rows}


def payment_total(user_id, expense_id=None):
    q = "SELECT COALESCE(SUM(amount),0) AS t FROM payments WHERE user_id = ?"
    params = [user_id]
    if expense_id is not None:
        q += " AND expense_id = ?"
        params.append(expense_id)
    with get_conn() as conn:
        return conn.execute(q, params).fetchone()["t"]


# ---------- สถิติ (ต่อ user) ----------

def monthly_payment_totals(user_id, months=6, end=None):
    end = end or date.today()
    months_list = []
    y, m = end.year, end.month
    for _ in range(months):
        months_list.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    months_list.reverse()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT substr(paid_date,1,7) AS ym, COALESCE(SUM(amount),0) AS total "
            "FROM payments WHERE user_id=? GROUP BY ym",
            (user_id,),
        ).fetchall()
    lookup = {r["ym"]: r["total"] for r in rows}
    return [{"ym": ym, "total": round(lookup.get(ym, 0), 2)} for ym in months_list]


def category_breakdown(user_id, ym=None):
    ym = ym or date.today().strftime("%Y-%m")
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT COALESCE(e.category,'other') AS category, COALESCE(SUM(p.amount),0) AS total
            FROM payments p LEFT JOIN expenses e ON e.id = p.expense_id
            WHERE p.user_id=? AND substr(p.paid_date,1,7) = ?
            GROUP BY e.category ORDER BY total DESC
            """,
            (user_id, ym),
        ).fetchall()
    cats = {c["key"]: c for c in get_categories(user_id)}
    out = []
    for r in rows:
        c = cats.get(r["category"], {})
        out.append({
            "category": r["category"],
            "label": c.get("label", r["category"] or "อื่น ๆ"),
            "icon": c.get("icon", "📌"),
            "total": round(r["total"], 2),
        })
    return out


def scheduled_totals(user_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT type, COALESCE(SUM(amount),0) AS t FROM expenses WHERE user_id=? AND active=1 GROUP BY type",
            (user_id,),
        ).fetchall()
    d = {r["type"]: r["t"] for r in rows}
    income = round(d.get("income", 0), 2)
    expense = round(d.get("expense", 0), 2)
    return {"income": income, "expense": expense, "net": round(income - expense, 2)}


# ---------- งบประมาณรายหมวด ----------

def set_budget(user_id, category, amount):
    """ตั้ง/แก้งบของหมวด (amount<=0 = ลบงบ)"""
    with get_conn() as conn:
        if float(amount or 0) <= 0:
            conn.execute("DELETE FROM budgets WHERE user_id=? AND category=?", (user_id, category))
        else:
            conn.execute(
                "INSERT INTO budgets (user_id, category, amount) VALUES (?,?,?) "
                "ON CONFLICT(user_id, category) DO UPDATE SET amount=excluded.amount",
                (user_id, category, float(amount)),
            )


def budget_status(user_id, ym=None):
    """
    สถานะงบแต่ละหมวดของเดือน (เทียบกับยอดจ่ายจริง)
    คืน list ของ {category, label, icon, limit, spent, pct, over, remaining}
    """
    ym = ym or date.today().strftime("%Y-%m")
    cats = {c["key"]: c for c in get_categories(user_id)}
    with get_conn() as conn:
        budgets = conn.execute(
            "SELECT category, amount FROM budgets WHERE user_id=?", (user_id,)
        ).fetchall()
        spent_rows = conn.execute(
            """
            SELECT COALESCE(e.category,'other') AS category, COALESCE(SUM(p.amount),0) AS spent
            FROM payments p LEFT JOIN expenses e ON e.id = p.expense_id
            WHERE p.user_id=? AND substr(p.paid_date,1,7)=?
            GROUP BY e.category
            """,
            (user_id, ym),
        ).fetchall()
    spent_map = {r["category"]: r["spent"] for r in spent_rows}
    out = []
    for b in budgets:
        cat = b["category"]
        limit = round(b["amount"], 2)
        spent = round(spent_map.get(cat, 0), 2)
        c = cats.get(cat, {})
        out.append({
            "category": cat,
            "label": c.get("label", cat),
            "icon": c.get("icon", "📌"),
            "limit": limit,
            "spent": spent,
            "pct": round(100 * spent / limit) if limit else 0,
            "over": spent > limit,
            "remaining": round(limit - spent, 2),
        })
    out.sort(key=lambda x: -x["pct"])
    return out


def total_budget(user_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT COALESCE(SUM(amount),0) AS t FROM budgets WHERE user_id=?", (user_id,)
        ).fetchone()["t"]


# ---------- เป้าหมายการออม ----------

def list_goals(user_id):
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM goals WHERE user_id=? ORDER BY id", (user_id,)
        ).fetchall()]


def get_goal(user_id, goal_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM goals WHERE id=? AND user_id=?", (goal_id, user_id)).fetchone()
        return dict(row) if row else None


def create_goal(user_id, name, target_amount, monthly_contribution=0, saved_amount=0, icon="🎯"):
    with get_conn() as conn:
        return conn.insert_returning_id(
            "INSERT INTO goals (user_id, name, icon, target_amount, saved_amount, monthly_contribution) "
            "VALUES (?,?,?,?,?,?)",
            (user_id, name, icon or "🎯", float(target_amount or 0),
             float(saved_amount or 0), float(monthly_contribution or 0)),
        )


def update_goal(user_id, goal_id, name, target_amount, monthly_contribution, icon="🎯"):
    with get_conn() as conn:
        conn.execute(
            "UPDATE goals SET name=?, icon=?, target_amount=?, monthly_contribution=? WHERE id=? AND user_id=?",
            (name, icon or "🎯", float(target_amount or 0), float(monthly_contribution or 0), goal_id, user_id),
        )


def add_goal_contribution(user_id, goal_id, amount):
    with get_conn() as conn:
        conn.execute(
            f"UPDATE goals SET saved_amount = {db.GREATEST}(0, saved_amount + ?) WHERE id=? AND user_id=?",
            (float(amount or 0), goal_id, user_id),
        )


def delete_goal(user_id, goal_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM goals WHERE id=? AND user_id=?", (goal_id, user_id))


def total_monthly_savings(user_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT COALESCE(SUM(monthly_contribution),0) AS t FROM goals WHERE user_id=?", (user_id,)
        ).fetchone()["t"]


# ---------- Safe to Spend (เหลือใช้ได้) ----------

def safe_to_spend(user_id):
    """
    เหลือใช้ได้ = รายรับรายเดือน − บิล/รายจ่ายตามแผน − เงินออมต่อเดือน
    (บิลใช้ยอดตามแผนของรายการ active ที่ไม่ใช่ยอดแปรผัน)
    """
    sched = scheduled_totals(user_id)
    savings = round(total_monthly_savings(user_id), 2)
    safe = round(sched["income"] - sched["expense"] - savings, 2)
    return {
        "income": sched["income"],
        "expense": sched["expense"],
        "savings": savings,
        "safe": safe,
    }


# ---------- notify log (ต่อ user) ----------

def already_sent(user_id, ref_key):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM notify_log WHERE user_id=? AND ref_key=? LIMIT 1", (user_id, ref_key)
        ).fetchone()
        return row is not None


def record_sent(user_id, kind, ref_key, message):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO notify_log (user_id, kind, ref_key, message) VALUES (?,?,?,?)",
            (user_id, kind, ref_key, message),
        )


def recent_logs(user_id, limit=30):
    with get_conn() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM notify_log WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit)
            ).fetchall()
        ]


def _int_or_none(v):
    if v is None or v == "" or str(v).lower() == "none":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
