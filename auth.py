"""
LINE Login (OAuth 2.0 / OpenID Connect)
ดูเอกสาร: https://developers.line.biz/en/docs/line-login/integrate-line-login/
ขั้นตอน: /login -> redirect ไป LINE -> ผู้ใช้อนุญาต -> /callback?code=... -> แลก token -> ได้โปรไฟล์
"""
import secrets
import urllib.parse

import requests

import config

AUTHORIZE_URL = "https://access.line.me/oauth2/v2.1/authorize"
TOKEN_URL = "https://api.line.me/oauth2/v2.1/token"
PROFILE_URL = "https://api.line.me/v2/profile"


class AuthError(Exception):
    pass


def is_configured():
    return bool(config.LINE_LOGIN_CHANNEL_ID and config.LINE_LOGIN_CHANNEL_SECRET)


def redirect_uri():
    return config.BASE_URL + "/callback"


def new_state():
    return secrets.token_urlsafe(16)


def build_authorize_url(state):
    """สร้าง URL ให้ผู้ใช้กดเข้า LINE Login (ขอ scope โปรไฟล์)
    bot_prompt=aggressive จะชวนผู้ใช้แอดบอทเป็นเพื่อนตอนล็อกอิน เพื่อให้ส่งแจ้งเตือนได้"""
    params = {
        "response_type": "code",
        "client_id": config.LINE_LOGIN_CHANNEL_ID,
        "redirect_uri": redirect_uri(),
        "state": state,
        "scope": "profile openid",
        "bot_prompt": "aggressive",
    }
    return AUTHORIZE_URL + "?" + urllib.parse.urlencode(params)


def exchange_code(code):
    """แลก authorization code เป็น access token แล้วดึงโปรไฟล์ผู้ใช้
    คืน dict: {user_id, display_name, picture_url}"""
    if not is_configured():
        raise AuthError("ยังไม่ได้ตั้งค่า LINE Login (LINE_LOGIN_CHANNEL_ID / SECRET)")

    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(),
            "client_id": config.LINE_LOGIN_CHANNEL_ID,
            "client_secret": config.LINE_LOGIN_CHANNEL_SECRET,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    if resp.status_code != 200:
        raise AuthError(f"แลก token ไม่สำเร็จ ({resp.status_code}): {resp.text}")
    access_token = resp.json().get("access_token")
    if not access_token:
        raise AuthError("ไม่ได้รับ access token")

    prof = requests.get(
        PROFILE_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=15
    )
    if prof.status_code != 200:
        raise AuthError(f"ดึงโปรไฟล์ไม่สำเร็จ ({prof.status_code}): {prof.text}")
    p = prof.json()
    return {
        "user_id": p.get("userId"),
        "display_name": p.get("displayName"),
        "picture_url": p.get("pictureUrl"),
    }
