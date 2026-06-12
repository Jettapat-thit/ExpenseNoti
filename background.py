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

    hour = int(os.environ.get("NOTIFY_HOUR", "8"))
    minute = int(os.environ.get("NOTIFY_MINUTE", "0"))
    summary_day = int(os.environ.get("SUMMARY_DAY", "1"))

    _scheduler = BackgroundScheduler(timezone=config.TIMEZONE)
    _scheduler.add_job(
        lambda: _run(summary_day),
        trigger="cron",
        hour=hour,
        minute=minute,
        id="daily_notify",
        replace_existing=True,
    )
    _scheduler.start()
    print(f"✅ Background scheduler เริ่มแล้ว — แจ้งเตือนทุกวันเวลา {hour:02d}:{minute:02d} ({config.TIMEZONE})")
    atexit.register(lambda: _scheduler.shutdown(wait=False))
    return _scheduler


def _run(summary_day):
    try:
        results = notifier.run_daily(send=True, summary_day=summary_day)
        if results:
            print(f"[scheduler] ส่งแจ้งเตือน {len(results)} รายการ")
    except Exception as exc:  # ไม่ให้ thread ตายเงียบ ๆ
        print(f"[scheduler] เกิดข้อผิดพลาด: {exc}")
