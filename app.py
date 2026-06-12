"""
เว็บแอปจัดการค่าใช้จ่าย + แจ้งเตือน LINE — รองรับหลายผู้ใช้ (login ด้วย LINE)
รัน:  python3 app.py   แล้วเปิด http://localhost:5000
"""
import os
import csv
import io
import re
from functools import wraps
from datetime import date

from flask import (
    Flask, render_template, request, redirect, url_for, flash, session, Response, abort
)

import config
import models
import notifier
import line_client
import auth
import background

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "expense-noti-local-secret")

models.init_db()
background.start()


# ---------- auth helpers ----------

def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    return models.get_user(uid)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("uid"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_user():
    return {"user": current_user()}


# ---------- auth routes ----------

@app.route("/login")
def login():
    if session.get("uid"):
        return redirect(url_for("index"))
    return render_template("login.html", login_ready=auth.is_configured())


@app.route("/login/start")
def login_start():
    if not auth.is_configured():
        flash("ยังไม่ได้ตั้งค่า LINE Login บนเซิร์ฟเวอร์", "error")
        return redirect(url_for("login"))
    state = auth.new_state()
    session["oauth_state"] = state
    return redirect(auth.build_authorize_url(state))


@app.route("/callback")
def callback():
    if request.args.get("error"):
        flash(f"เข้าสู่ระบบไม่สำเร็จ: {request.args.get('error_description', '')}", "error")
        return redirect(url_for("login"))
    code = request.args.get("code")
    state = request.args.get("state")
    if not code or state != session.get("oauth_state"):
        flash("เซสชันไม่ถูกต้อง ลองเข้าสู่ระบบใหม่อีกครั้ง", "error")
        return redirect(url_for("login"))
    try:
        profile = auth.exchange_code(code)
    except auth.AuthError as exc:
        flash(f"เข้าสู่ระบบไม่สำเร็จ: {exc}", "error")
        return redirect(url_for("login"))
    if not profile.get("user_id"):
        flash("ไม่ได้รับข้อมูลผู้ใช้จาก LINE", "error")
        return redirect(url_for("login"))
    user = models.upsert_user(profile["user_id"], profile.get("display_name"), profile.get("picture_url"))
    session["uid"] = user["id"]
    session.pop("oauth_state", None)
    flash(f"ยินดีต้อนรับ {user.get('display_name') or ''}", "success")
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- main ----------

@app.route("/")
@login_required
def index():
    uid = session["uid"]
    expenses = models.list_expenses(uid)
    today = date.today()
    cat_map = models.category_map(uid)
    ico_map = models.icon_map(uid)
    paid_ids = models.paid_expense_ids(uid)   # รายการที่จ่ายแล้วเดือนนี้

    unpaid_view, paid_view, income_view = [], [], []
    expense_total = income_total = 0.0
    active_count = upcoming_count = 0
    for e in expenses:
        due = notifier.next_due_date(e["due_day"], today)
        rem = notifier.remaining_installments(e)
        finished = notifier.is_finished(e)
        days_left = (due - today).days
        is_income = e.get("type") == "income"
        is_paid = e["id"] in paid_ids
        if bool(e["active"]) and not finished:
            active_count += 1
            if is_income:
                income_total += float(e["amount"])
            else:
                if not e.get("variable_amount"):
                    expense_total += float(e["amount"])
                if not is_paid and days_left <= int(e.get("remind_days_before", 3)):
                    upcoming_count += 1
        progress = None
        if e.get("total_installments"):
            progress = round(100 * int(e.get("paid_installments", 0)) / int(e["total_installments"]))
        row = {
            **e,
            "category_name": cat_map.get(e["category"], e["category"]),
            "icon": ico_map.get(e["category"], "💰" if is_income else "📌"),
            "next_due": due, "days_left": days_left, "remaining": rem,
            "finished": finished, "progress": progress, "paid": is_paid,
        }
        if is_income:
            income_view.append(row)
        elif is_paid:
            paid_view.append(row)
        else:
            unpaid_view.append(row)

    # นับเฉพาะรายจ่ายที่ใช้งานอยู่ (ไม่รวมรายการปิด/ผ่อนครบ) สำหรับ checklist
    active_expenses = [r for r in (unpaid_view + paid_view) if r["active"] and not r["finished"]]
    paid_count = sum(1 for r in active_expenses if r["paid"])
    expense_count = len(active_expenses)

    return render_template(
        "index.html",
        unpaid=unpaid_view, paid=paid_view, incomes=income_view,
        monthly_total=expense_total, income_total=income_total,
        net_total=income_total - expense_total, has_income=bool(income_view),
        active_count=active_count, upcoming_count=upcoming_count,
        paid_count=paid_count, expense_count=expense_count,
        sts=models.safe_to_spend(uid),
        line_ready=line_client.is_configured(),
        logs=models.recent_logs(uid, 10), today=today,
    )


@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    uid = session["uid"]
    if request.method == "POST":
        models.create_expense(uid, _form_to_data(request.form))
        flash("เพิ่มรายการเรียบร้อยแล้ว", "success")
        return redirect(url_for("index"))
    return render_template("form.html", expense=None, categories=models.get_categories(uid),
                           default_remind=config.DEFAULT_REMIND_DAYS_BEFORE, today=date.today())


@app.route("/edit/<int:expense_id>", methods=["GET", "POST"])
@login_required
def edit(expense_id):
    uid = session["uid"]
    expense = models.get_expense(uid, expense_id)
    if not expense:
        abort(404)
    if request.method == "POST":
        models.update_expense(uid, expense_id, _form_to_data(request.form))
        flash("บันทึกการแก้ไขแล้ว", "success")
        return redirect(url_for("index"))
    return render_template("form.html", expense=expense, categories=models.get_categories(uid),
                           default_remind=config.DEFAULT_REMIND_DAYS_BEFORE, today=date.today())


@app.route("/delete/<int:expense_id>", methods=["POST"])
@login_required
def delete(expense_id):
    models.delete_expense(session["uid"], expense_id)
    flash("ลบรายการแล้ว", "success")
    return redirect(url_for("index"))


@app.route("/pay/<int:expense_id>", methods=["GET", "POST"])
@login_required
def pay(expense_id):
    uid = session["uid"]
    expense = models.get_expense(uid, expense_id)
    if not expense:
        abort(404)
    if request.method == "POST":
        amount = request.form.get("amount") or expense["amount"]
        paid_date = request.form.get("paid_date") or date.today().isoformat()
        note = request.form.get("note", "").strip()
        installment_no = None
        if expense.get("total_installments"):
            installment_no = int(expense.get("paid_installments", 0)) + 1
            models.increment_paid(uid, expense_id, 1)
        models.record_payment(uid, expense_id, amount, paid_date, installment_no, note)
        flash(f"บันทึกการจ่าย {expense['name']} แล้ว", "success")
        return redirect(url_for("index"))
    return render_template("pay.html", expense=expense, today=date.today())


@app.route("/quickpay/<int:expense_id>", methods=["POST"])
@login_required
def quickpay(expense_id):
    """จ่ายเร็วแตะเดียว — บันทึกจ่ายยอดปกติ + วันนี้ทันที (ไม่เปิดฟอร์ม)"""
    uid = session["uid"]
    expense = models.get_expense(uid, expense_id)
    if not expense:
        abort(404)
    installment_no = None
    if expense.get("total_installments"):
        installment_no = int(expense.get("paid_installments", 0)) + 1
        models.increment_paid(uid, expense_id, 1)
    models.record_payment(uid, expense_id, expense["amount"], date.today().isoformat(),
                          installment_no, "จ่ายเร็ว")
    flash(f"บันทึกจ่าย {expense['name']} {expense['amount']:,.0f} บาทแล้ว", "success")
    return redirect(request.referrer or url_for("index"))


@app.route("/history")
@app.route("/history/<int:expense_id>")
@login_required
def history(expense_id=None):
    uid = session["uid"]
    expense = models.get_expense(uid, expense_id) if expense_id else None
    payments = models.list_payments(uid, expense_id=expense_id)
    total = models.payment_total(uid, expense_id=expense_id)
    cat_map = models.category_map(uid)
    ico_map = models.icon_map(uid)
    for p in payments:
        p["category_name"] = cat_map.get(p.get("category"), p.get("category") or "-")
        p["icon"] = ico_map.get(p.get("category"), "📌")
    return render_template("history.html", payments=payments, total=total, expense=expense)


@app.route("/payment/delete/<int:payment_id>", methods=["POST"])
@login_required
def payment_delete(payment_id):
    uid = session["uid"]
    p = models.get_payment(uid, payment_id)
    if p:
        if p.get("installment_no"):
            models.increment_paid(uid, p["expense_id"], -1)
        models.delete_payment(uid, payment_id)
        flash("ลบรายการจ่ายแล้ว", "success")
    return redirect(request.referrer or url_for("history"))


# ---------- categories ----------

@app.route("/categories", methods=["GET", "POST"])
@login_required
def categories():
    uid = session["uid"]
    if request.method == "POST":
        label = request.form.get("label", "").strip()
        icon = request.form.get("icon", "").strip() or "📌"
        kind = request.form.get("type", "expense")
        if label:
            base = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "cat"
            existing = {c["key"] for c in models.get_categories(uid)}
            key, i = base, 2
            while key in existing:
                key = f"{base}_{i}"; i += 1
            models.create_category(uid, key, label, icon, kind)
            flash(f"เพิ่มหมวด {icon} {label} แล้ว", "success")
        return redirect(url_for("categories"))
    return render_template("categories.html", categories=models.get_categories(uid))


@app.route("/categories/delete/<key>", methods=["POST"])
@login_required
def category_delete(key):
    if models.delete_category(session["uid"], key):
        flash("ลบหมวดแล้ว", "success")
    else:
        flash("ลบไม่ได้ — ยังมีรายการใช้หมวดนี้อยู่", "error")
    return redirect(url_for("categories"))


# ---------- stats / export ----------

@app.route("/stats")
@login_required
def stats():
    uid = session["uid"]
    today = date.today()
    monthly = models.monthly_payment_totals(uid, months=6, end=today)
    breakdown = models.category_breakdown(uid, today.strftime("%Y-%m"))
    sched = models.scheduled_totals(uid)
    this_m = monthly[-1]["total"] if monthly else 0
    prev_m = monthly[-2]["total"] if len(monthly) >= 2 else 0
    diff = this_m - prev_m
    pct = round(100 * diff / prev_m) if prev_m else None
    return render_template("stats.html", monthly=monthly, breakdown=breakdown, sched=sched,
                           this_m=this_m, prev_m=prev_m, diff=diff, pct=pct, today=today)


@app.route("/export.csv")
@login_required
def export_csv():
    uid = session["uid"]
    cat_map = models.category_map(uid)
    payments = models.list_payments(uid)
    buf = io.StringIO()
    buf.write("﻿")
    writer = csv.writer(buf)
    writer.writerow(["วันที่จ่าย", "รายการ", "หมวดหมู่", "งวด", "ยอด (บาท)", "หมายเหตุ"])
    for p in payments:
        writer.writerow([
            p.get("paid_date", ""), p.get("expense_name", ""),
            cat_map.get(p.get("category"), p.get("category") or ""),
            p.get("installment_no") or "", f"{p.get('amount', 0):.2f}", p.get("note") or "",
        ])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=expense_payments.csv"})


# ---------- settings ----------

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    uid = session["uid"]
    if request.method == "POST":
        models.update_user_settings(
            uid,
            notify_hour=request.form.get("notify_hour", 8),
            summary_day=request.form.get("summary_day", 1),
        )
        flash("บันทึกการตั้งค่าแล้ว", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html", me=models.get_user(uid))


# ---------- preview / test ----------

@app.route("/preview")
@login_required
def preview():
    uid = session["uid"]
    summary = notifier.build_monthly_summary(uid)
    reminders = notifier.build_due_reminders(uid)
    return render_template("preview.html", summary=summary, reminders=reminders)


@app.route("/send-test", methods=["POST"])
@login_required
def send_test():
    user = current_user()
    if not line_client.is_configured():
        flash("ยังไม่ได้ตั้งค่า LINE Messaging API บนเซิร์ฟเวอร์", "error")
        return redirect(url_for("index"))
    summary = notifier.build_monthly_summary(user["id"])
    if not summary:
        flash("ยังไม่มีรายการให้สรุป", "error")
        return redirect(url_for("index"))
    try:
        line_client.send_push(summary, to_user_id=user["line_user_id"])
        flash("ส่งข้อความทดสอบไปยัง LINE ของคุณแล้ว", "success")
    except line_client.LineError as exc:
        flash(f"ส่งไม่สำเร็จ: {exc} (อย่าลืมแอดบอทเป็นเพื่อนใน LINE)", "error")
    return redirect(url_for("index"))


# ---------- งบประมาณ ----------

@app.route("/budgets", methods=["GET", "POST"])
@login_required
def budgets():
    uid = session["uid"]
    if request.method == "POST":
        category = request.form.get("category")
        amount = request.form.get("amount", 0)
        if category:
            models.set_budget(uid, category, amount)
            flash("บันทึกงบแล้ว", "success")
        return redirect(url_for("budgets"))
    status = models.budget_status(uid)
    budgeted = {s["category"] for s in status}
    # หมวดรายจ่ายที่ยังไม่ได้ตั้งงบ (ไว้ให้เลือกเพิ่ม)
    avail = [c for c in models.get_categories(uid, kind="expense") if c["key"] not in budgeted]
    return render_template("budgets.html", status=status, avail=avail,
                           total_limit=models.total_budget(uid), today=date.today())


@app.route("/budgets/delete/<category>", methods=["POST"])
@login_required
def budget_delete(category):
    models.set_budget(session["uid"], category, 0)
    flash("ลบงบหมวดนี้แล้ว", "success")
    return redirect(url_for("budgets"))


# ---------- เป้าหมายการออม ----------

@app.route("/goals", methods=["GET", "POST"])
@login_required
def goals():
    uid = session["uid"]
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name:
            models.create_goal(
                uid, name,
                request.form.get("target_amount", 0),
                request.form.get("monthly_contribution", 0),
                request.form.get("saved_amount", 0),
                request.form.get("icon", "🎯").strip() or "🎯",
            )
            flash(f"เพิ่มเป้าหมาย {name} แล้ว", "success")
        return redirect(url_for("goals"))
    goal_list = models.list_goals(uid)
    for g in goal_list:
        tgt = g["target_amount"] or 0
        g["pct"] = round(100 * g["saved_amount"] / tgt) if tgt else 0
        g["remaining"] = round(max(0, tgt - g["saved_amount"]), 2)
        g["done"] = g["saved_amount"] >= tgt and tgt > 0
        if g["monthly_contribution"] and g["remaining"] > 0:
            import math
            g["months_left"] = math.ceil(g["remaining"] / g["monthly_contribution"])
        else:
            g["months_left"] = None
    return render_template("goals.html", goals=goal_list,
                           monthly_total=models.total_monthly_savings(uid))


@app.route("/goals/contribute/<int:goal_id>", methods=["POST"])
@login_required
def goal_contribute(goal_id):
    amount = request.form.get("amount", 0)
    models.add_goal_contribution(session["uid"], goal_id, amount)
    flash("บันทึกเงินออมแล้ว", "success")
    return redirect(url_for("goals"))


@app.route("/goals/delete/<int:goal_id>", methods=["POST"])
@login_required
def goal_delete(goal_id):
    models.delete_goal(session["uid"], goal_id)
    flash("ลบเป้าหมายแล้ว", "success")
    return redirect(url_for("goals"))


# ---------- ปฏิทินครบกำหนด ----------

@app.route("/calendar")
@login_required
def calendar_view():
    import calendar as _cal
    uid = session["uid"]
    today = date.today()
    try:
        year = int(request.args.get("y", today.year))
        month = int(request.args.get("m", today.month))
    except (TypeError, ValueError):
        year, month = today.year, today.month

    cat_icons = models.icon_map(uid)
    # รวมรายการรายจ่าย active ที่ครบกำหนดในเดือนนี้ ตามวัน
    items_by_day = {}
    last = _cal.monthrange(year, month)[1]
    for e in models.list_expenses(uid, active_only=True):
        if e.get("type") == "income" or notifier.is_finished(e):
            continue
        d = min(int(e["due_day"]), last)
        items_by_day.setdefault(d, []).append({
            "name": e["name"],
            "icon": cat_icons.get(e["category"], "📌"),
            "amount": e["amount"],
            "variable": bool(e.get("variable_amount")),
        })

    cal = _cal.Calendar(firstweekday=6)  # เริ่มวันอาทิตย์
    weeks = []
    for week in cal.monthdatescalendar(year, month):
        cells = []
        for d in week:
            in_month = (d.month == month)
            day_items = items_by_day.get(d.day, []) if in_month else []
            if in_month and day_items:
                if d < today:
                    status = "overdue"
                elif d == today:
                    status = "due"
                elif (d - today).days <= 3:
                    status = "soon"
                else:
                    status = "later"
            else:
                status = ""
            cells.append({"date": d, "in_month": in_month, "items": day_items,
                          "is_today": d == today, "status": status})
        weeks.append(cells)

    prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
    next_m = (year + 1, 1) if month == 12 else (year, month + 1)
    th_months = ["", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
                 "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
    return render_template("calendar.html", weeks=weeks, year=year, month=month,
                           month_name=th_months[month], prev_m=prev_m, next_m=next_m, today=today)


def _form_to_data(form):
    total_inst = form.get("total_installments", "").strip()
    return {
        "name": form.get("name", "").strip(),
        "type": form.get("type", "expense"),
        "variable_amount": 1 if form.get("variable_amount") == "on" else 0,
        "category": form.get("category", "other"),
        "amount": form.get("amount", 0),
        "due_day": form.get("due_day", 1),
        "total_installments": total_inst if total_inst else None,
        "paid_installments": form.get("paid_installments", 0) or 0,
        "start_date": form.get("start_date", "").strip(),
        "remind_days_before": form.get("remind_days_before", config.DEFAULT_REMIND_DAYS_BEFORE),
        "active": 1 if form.get("active") == "on" else 0,
        "note": form.get("note", "").strip(),
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.WEB_PORT, debug=True)
