"""
ดูข้อมูลในฐานข้อมูลแบบอ่านง่าย (ใช้ Python ล้วน ไม่ต้องมี sqlite3 CLI)

รันในเครื่อง:
    python3 dbview.py
    python3 dbview.py expenses          # ดูเฉพาะตาราง expenses
    python3 dbview.py users 20          # ดู 20 แถวล่าสุด

บน Render (แท็บ Shell ของ service):
    python3 dbview.py
"""
import sys
import sqlite3

import config


def show(table, limit=50):
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
    except sqlite3.OperationalError as exc:
        print(f"  อ่านตาราง {table} ไม่ได้: {exc}")
        return
    finally:
        conn.close()
    print(f"\n===== {table} ({len(rows)} แถวล่าสุด) =====")
    if not rows:
        print("  (ว่าง)")
        return
    cols = rows[0].keys()
    print(" | ".join(cols))
    print("-" * 60)
    for r in rows:
        print(" | ".join(str(r[c]) for c in cols))


def main():
    print(f"ฐานข้อมูล: {config.DATABASE_PATH}")
    conn = sqlite3.connect(config.DATABASE_PATH)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()]
    conn.close()

    args = sys.argv[1:]
    if args:
        table = args[0]
        limit = int(args[1]) if len(args) > 1 else 50
        show(table, limit)
    else:
        print("ตารางทั้งหมด:", ", ".join(tables))
        for t in tables:
            show(t, 20)


if __name__ == "__main__":
    main()
