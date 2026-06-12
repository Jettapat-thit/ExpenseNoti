"""
ตัวห่อ LINE Messaging API — ส่ง push message
(LINE Notify ปิดบริการแล้วตั้งแต่ 1 เม.ย. 2025 จึงใช้ Messaging API แทน)
"""
import requests
import config

PUSH_URL = "https://api.line.me/v2/bot/message/push"


class LineError(Exception):
    pass


def send_push(text, to_user_id=None, access_token=None):
    """
    ส่งข้อความ push ไปยังผู้ใช้คนเดียว
    คืนค่า True เมื่อสำเร็จ มิฉะนั้น raise LineError
    """
    token = access_token or config.LINE_CHANNEL_ACCESS_TOKEN
    to = to_user_id or config.LINE_TO_USER_ID

    if not token:
        raise LineError("ยังไม่ได้ตั้งค่า LINE_CHANNEL_ACCESS_TOKEN")
    if not to:
        raise LineError("ยังไม่ได้ตั้งค่า LINE_TO_USER_ID")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    # LINE จำกัด 1 ข้อความ 5000 ตัวอักษร
    payload = {
        "to": to,
        "messages": [{"type": "text", "text": text[:5000]}],
    }
    resp = requests.post(PUSH_URL, headers=headers, json=payload, timeout=15)
    if resp.status_code != 200:
        raise LineError(f"LINE API ตอบกลับ {resp.status_code}: {resp.text}")
    return True


def is_configured():
    return bool(config.LINE_CHANNEL_ACCESS_TOKEN and config.LINE_TO_USER_ID)
