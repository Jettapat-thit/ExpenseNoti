"""
สคริปต์สำหรับรันแบบตั้งเวลา (cron / Task Scheduler / scheduled task)
ตัวอย่าง crontab (รันทุกวัน 8 โมงเช้า):
    0 8 * * *  cd /path/to/ExpenseNoti && python3 scheduler.py >> cron.log 2>&1

ตัวเลือก:
    --dry-run        แสดงข้อความที่จะส่ง โดยไม่ส่งจริงและไม่บันทึก log
    --summary-day N  วันของเดือนที่ส่งสรุปรวม (ค่าเริ่มต้น 1)
"""
import argparse
import sys

import models
import notifier
import line_client


def main():
    parser = argparse.ArgumentParser(description="แจ้งเตือนค่าใช้จ่ายผ่าน LINE")
    parser.add_argument("--dry-run", action="store_true", help="ไม่ส่งจริง แค่แสดงผล")
    parser.add_argument("--summary-day", type=int, default=1, help="วันที่ส่งสรุปรวมรายเดือน")
    args = parser.parse_args()

    models.init_db()

    if not args.dry_run and not line_client.is_configured():
        print("⚠️  ยังไม่ได้ตั้งค่า LINE (LINE_CHANNEL_ACCESS_TOKEN / LINE_TO_USER_ID) ในไฟล์ .env")
        print("   ลองรันด้วย --dry-run เพื่อดูข้อความก่อนได้")
        sys.exit(1)

    results = notifier.run_daily(
        send=not args.dry_run,
        summary_day=args.summary_day,
        dry_run=args.dry_run,
    )

    if not results:
        print("วันนี้ไม่มีรายการที่ต้องแจ้งเตือน")
        return

    for r in results:
        print(f"[{r['status']}] {r['kind']}")
        print(r["message"])
        print("-" * 40)


if __name__ == "__main__":
    main()
