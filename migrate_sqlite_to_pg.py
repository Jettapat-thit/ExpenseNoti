"""
ย้ายข้อมูลจาก SQLite เดิม → PostgreSQL (รักษา id เดิมทุกตาราง)

วิธีใช้ (รันในเครื่องที่มีไฟล์ SQLite และต่อ Postgres ได้):
    pip install -r requirements.txt
    export DATABASE_URL="postgresql://user:pass@host:5432/dbname"   # Postgres ปลายทาง
    python3 migrate_sqlite_to_pg.py expenses.db                     # ระบุไฟล์ SQLite ต้นทาง

ขั้นตอนที่ทำ:
  1) สร้างตารางบน Postgres (ถ้ายังไม่มี)
  2) คัดลอกข้อมูลทุกตาราง รักษา id เดิม (ข้ามแถวที่ซ้ำด้วย ON CONFLICT DO NOTHING)
  3) รีเซ็ต sequence ของ id ให้ต่อจากค่าสูงสุด เพื่อให้ insert ใหม่ไม่ชน

ปลอดภัย: รันซ้ำได้ (idempotent) — แถวที่มีอยู่แล้วจะถูกข้าม
"""
import os
import sys
import sqlite3

# ลำดับการย้าย (users/categories ก่อน แต่ไม่มี FK บังคับ จึงสลับได้)
TABLES = ["users", "categories", "expenses", "payments", "budgets", "goals", "notify_log"]


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SQLITE_PATH", "expenses.db")
    pg_url = os.environ.get("DATABASE_URL", "").strip()

    if not pg_url.startswith("postgres"):
        print("❌ กรุณาตั้ง DATABASE_URL ให้เป็น PostgreSQL ก่อน")
        print('   เช่น  export DATABASE_URL="postgresql://user:pass@host:5432/db"')
        sys.exit(1)
    if not os.path.exists(src):
        print(f"❌ ไม่พบไฟล์ SQLite ต้นทาง: {src}")
        sys.exit(1)

    # 1) สร้าง schema บน Postgres (models อ่าน DATABASE_URL จาก env ผ่าน db.py)
    import models
    models.init_db()
    print(f"✅ เตรียมตารางบน Postgres เรียบร้อย (ต้นทาง: {src})")

    import psycopg

    sconn = sqlite3.connect(src)
    sconn.row_factory = sqlite3.Row
    pconn = psycopg.connect(pg_url)

    total = 0
    for table in TABLES:
        exists = sconn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not exists:
            print(f"  • {table}: ข้าม (ไม่มีใน SQLite)")
            continue

        rows = sconn.execute(f"SELECT * FROM {table}").fetchall()
        if not rows:
            print(f"  • {table}: 0 แถว")
            continue

        cols = list(rows[0].keys())
        collist = ", ".join(cols)
        placeholders = ", ".join(["%s"] * len(cols))
        data = [tuple(r[c] for c in cols) for r in rows]

        with pconn.cursor() as cur:
            cur.executemany(
                f"INSERT INTO {table} ({collist}) VALUES ({placeholders}) ON CONFLICT DO NOTHING",
                data,
            )
            # รีเซ็ต sequence ของ id ให้ต่อจากค่าสูงสุด
            if "id" in cols:
                cur.execute(
                    f"SELECT setval(pg_get_serial_sequence('{table}','id'), "
                    f"GREATEST((SELECT COALESCE(MAX(id),1) FROM {table}), 1))"
                )
        pconn.commit()
        total += len(rows)
        print(f"  • {table}: ย้าย {len(rows)} แถว ✓")

    sconn.close()
    pconn.close()
    print(f"\n🎉 เสร็จสิ้น — ย้ายทั้งหมด {total} แถว")
    print("   ลองเปิดเว็บ/DBeaver เช็คข้อมูลได้เลย")


if __name__ == "__main__":
    main()
