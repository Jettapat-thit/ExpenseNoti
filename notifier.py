"""
ตรรกะการสรุปและสร้างข้อความแจ้งเตือนค่าใช้จ่าย
- สรุปรวมรายเดือน
- เตือนก่อนถึงกำหนด
- เตือนวันครบกำหนด
- นับงวดผ่อนที่เหลือ
"""
import calendar
from datetime import date, datetime, timedelta

import models
import line_client


# ---------- ตัวช่วยเรื่องวันที่ ----------

def _clamp_due_date(year, month, due_day):
    """คืนวันที่ครบกำหนดของเดือนนั้น โดยไม่เกินจำนวนวันจริงของเดือน"""
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(due_day, last))


def next_due_date(due_day, today=None):
    """หาวันครบกำหนดถัดไป (เดือนนี้ถ้ายังไม่เลย ไม่งั้นเดือนหน้า)"""
    today = today or date.today()
    this_month = _clamp_due_date(today.year, today.month, due_day)
    if this_month >= today:
        return this_month
    # เดือนถัดไป
    y, m = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return _clamp_due_date(y, m, due_day)


def remaining_installments(exp):
    """จำนวนงวดที่เหลือ (คืน None ถ้าเป็นรายเดือนไม่จำกัด เช่น ค่าน้ำค่าไฟ)"""
    total = exp.get("total_installments")
    if not total:
        return None
    return max(0, int(total) - int(exp.get("paid_installments", 0)))


def is_finished(exp):
    """ผ่อนครบแล้วหรือยัง"""
    rem = remaining_installments(exp)
    return rem is not None and rem <= 0


def _fmt_baht(amount):
    return f"{amount:,.0f}" if float(amount).is_integer() else f"{amount:,.2f}"


# ---------- สร้างข้อความ ----------

def build_monthly_summary(user_id, today=None):
    """สร้างข้อความสรุปรวมรายรับ-รายจ่ายของเดือน (ต่อ user)"""
    today = today or date.today()
    cat_map = models.category_map(user_id)
    items = [e for e in models.list_expenses(user_id, active_only=True) if not is_finished(e)]
    expenses = sorted([e for e in items if e.get("type", "expense") != "income"], key=lambda e: e["due_day"])
    incomes = sorted([e for e in items if e.get("type") == "income"], key=lambda e: e["due_day"])

    if not expenses and not incomes:
        return None

    lines = [f"📊 สรุปรายรับ-รายจ่ายเดือน {today.month}/{today.year}", ""]

    expense_total = 0.0
    if expenses:
        for e in expenses:
            cat = cat_map.get(e["category"], e["category"])
            if e.get("variable_amount"):
                line = f"• {e['name']} ({cat})  ยอดแล้วแต่บิล — ครบกำหนดวันที่ {e['due_day']}"
            else:
                expense_total += float(e["amount"])
                line = f"• {e['name']} ({cat})  {_fmt_baht(e['amount'])} บาท — ครบกำหนดวันที่ {e['due_day']}"
            rem = remaining_installments(e)
            if rem is not None:
                paid = int(e.get("paid_installments", 0))
                total_inst = int(e["total_installments"])
                line += f"\n   └ งวด {paid + 1}/{total_inst} (เหลืออีก {rem} งวด)"
            lines.append(line)
        lines.append("")
        lines.append(f"💸 รายจ่ายรวม {_fmt_baht(expense_total)} บาท")

    income_total = 0.0
    if incomes:
        lines.append("")
        for e in incomes:
            income_total += float(e["amount"])
            cat = cat_map.get(e["category"], e["category"])
            lines.append(f"• {e['name']} ({cat})  +{_fmt_baht(e['amount'])} บาท")
        lines.append(f"💰 รายรับรวม {_fmt_baht(income_total)} บาท")

    if incomes:
        net = income_total - expense_total
        sign = "เหลือ" if net >= 0 else "ขาด"
        lines.append("")
        lines.append(f"🧮 คงเหลือสุทธิ {sign} {_fmt_baht(abs(net))} บาท/เดือน")
    return "\n".join(lines)


def build_due_reminders(user_id, today=None):
    """สร้างรายการเตือนของ user — due_today / upcoming"""
    today = today or date.today()
    cat_map = models.category_map(user_id)
    out = []
    for e in models.list_expenses(user_id, active_only=True):
        if is_finished(e) or e.get("type") == "income":
            continue
        due = next_due_date(e["due_day"], today)
        days_left = (due - today).days
        remind_before = int(e.get("remind_days_before", 3))

        if days_left == 0:
            kind = "due_today"
        elif 0 < days_left <= remind_before:
            kind = "upcoming"
        else:
            continue

        cat = cat_map.get(e["category"], e["category"])
        rem = remaining_installments(e)
        inst_txt = ""
        if rem is not None:
            paid = int(e.get("paid_installments", 0))
            inst_txt = f" (งวด {paid + 1}/{int(e['total_installments'])}, เหลือ {rem} งวด)"

        if kind == "due_today":
            head = "⏰ ครบกำหนดวันนี้!"
        else:
            head = f"🔔 อีก {days_left} วันครบกำหนด"

        if e.get("variable_amount"):
            amount_txt = "💳 เช็คยอดบิลแล้วกรอกตอนจ่าย"
        else:
            amount_txt = f"ยอด {_fmt_baht(e['amount'])} บาท"
        msg = (
            f"{head}\n"
            f"{e['name']} ({cat}){inst_txt}\n"
            f"{amount_txt} — กำหนด {due.day}/{due.month}/{due.year}"
        )
        out.append({
            "kind": kind, "exp": e, "due": due,
            "days_left": days_left, "message": msg,
        })
    # เรียงตามวันที่ครบกำหนด
    out.sort(key=lambda x: x["days_left"])
    return out


# ---------- ตัวสั่งงาน (เรียกโดย scheduler) ----------

def run_daily_for_user(user, today=None, send=True, dry_run=False):
    """
    รันแจ้งเตือนของ user คนเดียว ส่ง push ไปยัง line_user_id ของเขา
    - วันที่ == summary_day ของ user -> ส่งสรุปรวมรายเดือน
    - ทุกวัน -> เตือนใกล้/ถึงกำหนด
    กันส่งซ้ำด้วย notify_log (แยกตาม user)
    """
    today = today or date.today()
    uid = user["id"]
    to = user.get("line_user_id")
    summary_day = int(user.get("summary_day", 1) or 1)
    sent_messages = []

    def _maybe_send(kind, ref_key, message):
        if models.already_sent(uid, ref_key):
            return
        if dry_run:
            sent_messages.append({"user": uid, "kind": kind, "message": message, "status": "dry_run"})
            return
        if send:
            line_client.send_push(message, to_user_id=to)
            models.record_sent(uid, kind, ref_key, message)
        sent_messages.append({"user": uid, "kind": kind, "message": message, "status": "sent"})

    if today.day == summary_day:
        summary = build_monthly_summary(uid, today)
        if summary:
            ref = f"{today.year}-{today.month:02d}|summary"
            _maybe_send("monthly_summary", ref, summary)

    for item in build_due_reminders(uid, today):
        e = item["exp"]
        ref = f"{item['due'].isoformat()}|{e['id']}|{item['kind']}"
        _maybe_send(item["kind"], ref, item["message"])

    return sent_messages


def run_daily_all(today=None, send=True, dry_run=False, at_hour=None):
    """
    วนทุก user แล้วส่งแจ้งเตือนให้แต่ละคน (ใช้โดย scheduler)
    ถ้าระบุ at_hour จะส่งเฉพาะ user ที่ตั้งเวลาแจ้งเตือน (notify_hour) ตรงกับชั่วโมงนั้น
    """
    results = []
    for user in models.list_users():
        if not user.get("line_user_id"):
            continue
        if at_hour is not None and int(user.get("notify_hour", 8) or 8) != int(at_hour):
            continue
        try:
            results += run_daily_for_user(user, today=today, send=send, dry_run=dry_run)
        except Exception as exc:  # ไม่ให้ user คนเดียวล้มทั้งระบบ
            results.append({"user": user["id"], "kind": "error", "message": str(exc), "status": "error"})
    return results
