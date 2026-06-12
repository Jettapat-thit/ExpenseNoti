"""
การตั้งค่าระบบ — อ่านค่าจาก environment variables (ไฟล์ .env)
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# โหลดไฟล์ .env ถ้ามี (ไม่บังคับติดตั้ง python-dotenv)
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip())

# ฐานข้อมูล
DATABASE_PATH = os.environ.get("DATABASE_PATH", str(BASE_DIR / "expenses.db"))

# LINE Messaging API
# 1) สร้าง Provider + Messaging API channel ที่ https://developers.line.biz/console/
# 2) คัดลอก Channel access token (long-lived) มาใส่ที่นี่
# 3) หา User ID ของผู้รับ (เพิ่มบอทเป็นเพื่อน แล้วดูจาก webhook หรือใช้ /me)
# .strip() กันกรณี paste แล้วมีช่องว่าง/ขึ้นบรรทัดติดมา (สาเหตุ 401 ที่พบบ่อย)
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
LINE_TO_USER_ID = os.environ.get("LINE_TO_USER_ID", "").strip()

# จำนวนวันก่อนถึงกำหนดที่จะเริ่มเตือน (ค่าเริ่มต้น)
DEFAULT_REMIND_DAYS_BEFORE = int(os.environ.get("DEFAULT_REMIND_DAYS_BEFORE", "3"))

# โซนเวลา (สำหรับการคำนวณวันที่)
TIMEZONE = os.environ.get("TIMEZONE", "Asia/Bangkok")

# พอร์ตของเว็บ
WEB_PORT = int(os.environ.get("WEB_PORT", "5000"))
