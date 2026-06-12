"""
ตัวรันแจ้งเตือนแบบ background thread ในตัวเว็บ
(ใช้ตอน deploy บน cloud ที่มี service เดียว + persistent disk เดียว)
เปิดใช้งานด้วย env var: RUN_SCHEDULER=1
"""
import os
import atexit

import config
import notifier

_scheduler = None


def start():
    """เริ่ม background scheduler ถ้าตั้ง RUN_SCHEDULER=1 (เรียกครั้งเดียว)"""
    global _scheduler
    if os.environ.get("RUN_SCHEDULER") != "1":
        return None
    if _scheduler is not None:
        return _scheduler

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        print("⚠️  ไม่พบ APScheduler — ข้ามการตั้งเวลาในแอป (pip install APScheduler)")
        return None

    minute = int(os.environ.get("NOTIFY_MINUTE", "0"))

    # รันทุกชั่วโมง แล้วส่งเฉพาะ user ที่ตั้งเวลาแจ้งเตือน (notify_hour) ตรงกับชั่วโมงนั้น
    _scheduler = BackgroundScheduler(timezone=config.TIMEZONE)
    _scheduler.add_job(
        _run,
        trigger="cron",
        minute=minute,
        id="daily_notify",
        replace_existing=True,
    )
    _scheduler.start()
    print(f"✅ Background scheduler เริ่มแล้ว — เช็คทุกชั่วโมง (นาที {minute:02d}) ส่งตามเวลาที่แต่ละ user ตั้งไว้ ({config.TIMEZONE})")
    atexit.register(lambda: _scheduler.shutdown(wait=False))
    return _scheduler


def _run():
    try:
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo(config.TIMEZONE))
        except Exception:
            now = datetime.now()
        results = notifier.run_daily_all(send=True, at_hour=now.hour)
        if results:
            print(f"[scheduler] ชั่วโมง {now.hour}: ส่งแจ้งเตือน {len(results)} รายการ")
    except Exception as exc:  # ไม่ให้ thread ตายเงียบ ๆ
        print(f"[scheduler] เกิดข้อผิดพลาด: {exc}")
