"""
สคริปต์สำหรับรันแบบตั้งเวลา (cron / Task Scheduler) — แบบหลายผู้ใช้
ส่งแจ้งเตือนให้ทุก user เข้า LINE ของแต่ละคน
ปกติถ้า deploy แล้วใช้ background scheduler ในตัวเว็บอยู่แล้ว สคริปต์นี้ไว้รันมือ/ทดสอบ

ตัวอย่าง crontab (เช็คทุกชั่วโมง):
    0 * * * *  cd /path/to/ExpenseNoti && python3 scheduler.py >> cron.log 2>&1

ตัวเลือก:
    --dry-run        แสดงข้อความที่จะส่ง โดยไม่ส่งจริงและไม่บันทึก log
    --all-hours      ไม่กรองตามเวลา notify_hour (ส่งให้ทุก user เลย)
"""
import argparse
import sys
from datetime import datetime

import models
import notifier
import line_client


def main():
    parser = argparse.ArgumentParser(description="แจ้งเตือนค่าใช้จ่ายผ่าน LINE (multi-user)")
    parser.add_argument("--dry-run", action="store_true", help="ไม่ส่งจริง แค่แสดงผล")
    parser.add_argument("--all-hours", action="store_true", help="ส่งทุก user ไม่กรองตาม notify_hour")
    args = parser.parse_args()

    models.init_db()

    if not args.dry_run and not line_client.is_configured():
        print("⚠️  ยังไม่ได้ตั้งค่า LINE_CHANNEL_ACCESS_TOKEN")
        print("   ลองรันด้วย --dry-run เพื่อดูข้อความก่อนได้")
        sys.exit(1)

    at_hour = None if (args.all_hours or args.dry_run) else datetime.now().hour
    results = notifier.run_daily_all(send=not args.dry_run, dry_run=args.dry_run, at_hour=at_hour)

    if not results:
        print("ตอนนี้ไม่มีรายการที่ต้องแจ้งเตือน")
        return

    for r in results:
        print(f"[{r['status']}] user={r.get('user')} {r['kind']}")
        print(r["message"])
        print("-" * 40)


if __name__ == "__main__":
    main()
