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

def build_monthly_summary(today=None):
    """สร้างข้อความสรุปรวมค่าใช้จ่ายทั้งหมดของเดือน"""
    today = today or date.today()
    expenses = [e for e in models.list_expenses(active_only=True) if not is_finished(e)]
    expenses.sort(key=lambda e: e["due_day"])

    if not expenses:
        return None

    lines = [f"📊 สรุปค่าใช้จ่ายเดือน {today.month}/{today.year}", ""]
    total = 0.0
    for e in expenses:
        total += float(e["amount"])
        cat = models.CATEGORIES.get(e["category"], e["category"])
        line = f"• {e['name']} ({cat})  {_fmt_baht(e['amount'])} บาท — ครบกำหนดวันที่ {e['due_day']}"
        rem = remaining_installments(e)
        if rem is not None:
            paid = int(e.get("paid_installments", 0))
            total_inst = int(e["total_installments"])
            line += f"\n   └ งวด {paid + 1}/{total_inst} (เหลืออีก {rem} งวด)"
        lines.append(line)

    lines.append("")
    lines.append(f"💰 รวมทั้งสิ้น {_fmt_baht(total)} บาท/เดือน")
    return "\n".join(lines)


def build_due_reminders(today=None):
    """
    สร้างรายการเตือน — แยกเป็น
      - due_today: ครบกำหนดวันนี้
      - upcoming: ใกล้ครบกำหนด (ภายใน remind_days_before)
    คืน list ของ dict: {kind, exp, due, days_left, message}
    """
    today = today or date.today()
    out = []
    for e in models.list_expenses(active_only=True):
        if is_finished(e):
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

        cat = models.CATEGORIES.get(e["category"], e["category"])
        rem = remaining_installments(e)
        inst_txt = ""
        if rem is not None:
            paid = int(e.get("paid_installments", 0))
            inst_txt = f" (งวด {paid + 1}/{int(e['total_installments'])}, เหลือ {rem} งวด)"

        if kind == "due_today":
            head = "⏰ ครบกำหนดวันนี้!"
        else:
            head = f"🔔 อีก {days_left} วันครบกำหนด"

        msg = (
            f"{head}\n"
            f"{e['name']} ({cat}){inst_txt}\n"
            f"ยอด {_fmt_baht(e['amount'])} บาท — กำหนด {due.day}/{due.month}/{due.year}"
        )
        out.append({
            "kind": kind, "exp": e, "due": due,
            "days_left": days_left, "message": msg,
        })
    # เรียงตามวันที่ครบกำหนด
    out.sort(key=lambda x: x["days_left"])
    return out


# ---------- ตัวสั่งงาน (เรียกโดย scheduler) ----------

def run_daily(today=None, send=True, summary_day=1, dry_run=False):
    """
    ฟังก์ชันหลักที่รันทุกวัน:
      - วันที่ = summary_day  -> ส่งสรุปรวมรายเดือน (เดือนละครั้ง)
      - ทุกวัน               -> ส่งเตือนใกล้ครบกำหนด / ครบกำหนดวันนี้
    มีการกันส่งซ้ำด้วย notify_log
    คืน list ข้อความที่ส่ง (หรือจะส่ง)
    """
    today = today or date.today()
    sent_messages = []

    def _maybe_send(kind, ref_key, message):
        if models.already_sent(ref_key):
            return
        if dry_run:
            sent_messages.append({"kind": kind, "ref_key": ref_key, "message": message, "status": "dry_run"})
            return
        if send:
            line_client.send_push(message)
            models.record_sent(kind, ref_key, message)
        sent_messages.append({"kind": kind, "ref_key": ref_key, "message": message, "status": "sent"})

    # 1) สรุปรวมรายเดือน
    if today.day == summary_day:
        summary = build_monthly_summary(today)
        if summary:
            ref = f"{today.year}-{today.month:02d}|summary"
            _maybe_send("monthly_summary", ref, summary)

    # 2) เตือนรายรายการ
    for item in build_due_reminders(today):
        e = item["exp"]
        ref = f"{item['due'].isoformat()}|{e['id']}|{item['kind']}"
        _maybe_send(item["kind"], ref, item["message"])

    return sent_messages
