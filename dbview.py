"""
ดูข้อมูลในฐานข้อมูลแบบอ่านง่าย — ใช้ได้ทั้ง PostgreSQL และ SQLite
(เลือก backend อัตโนมัติจาก DATABASE_URL ผ่าน db.py)

รันในเครื่อง:
    python3 dbview.py
    python3 dbview.py expenses          # ดูเฉพาะตาราง expenses
    python3 dbview.py users 20          # ดู 20 แถวล่าสุด
"""
import sys

import db

TABLES = ["users", "expenses", "payments", "categories", "budgets", "goals", "notify_log"]


def show(table, limit=50):
    with db.get_conn() as conn:
        try:
            rows = conn.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        except Exception as exc:
            print(f"  อ่านตาราง {table} ไม่ได้: {exc}")
            return
    rows = [dict(r) for r in rows]
    print(f"\n===== {table} ({len(rows)} แถวล่าสุด) =====")
    if not rows:
        print("  (ว่าง)")
        return
    cols = list(rows[0].keys())
    print(" | ".join(cols))
    print("-" * 60)
    for r in rows:
        print(" | ".join(str(r[c]) for c in cols))


def main():
    print(f"ฐานข้อมูล: {db.backend_name()}")
    args = sys.argv[1:]
    if args:
        show(args[0], int(args[1]) if len(args) > 1 else 50)
    else:
        for t in TABLES:
            show(t, 20)


if __name__ == "__main__":
    main()
