"""
เว็บแอปจัดการรายการค่าใช้จ่าย + แจ้งเตือนผ่าน LINE
รัน:  python3 app.py   แล้วเปิด http://localhost:5000
"""
from datetime import date

from flask import Flask, render_template, request, redirect, url_for, flash

import os

import config
import models
import notifier
import line_client
import background

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "expense-noti-local-secret")

models.init_db()

# เริ่ม background scheduler (ทำงานเฉพาะเมื่อ RUN_SCHEDULER=1 เช่นตอน deploy)
background.start()


@app.route("/")
def index():
    expenses = models.list_expenses()
    today = date.today()

    # คำนวณข้อมูลเพิ่มเติมสำหรับแสดงผล
    view = []
    monthly_total = 0.0
    active_count = 0
    upcoming_count = 0
    for e in expenses:
        due = notifier.next_due_date(e["due_day"], today)
        rem = notifier.remaining_installments(e)
        finished = notifier.is_finished(e)
        days_left = (due - today).days
        is_live = bool(e["active"]) and not finished
        if is_live:
            monthly_total += float(e["amount"])
            active_count += 1
            if days_left <= int(e.get("remind_days_before", 3)):
                upcoming_count += 1
        # เปอร์เซ็นต์ความคืบหน้าการผ่อน
        progress = None
        if e.get("total_installments"):
            progress = round(100 * int(e.get("paid_installments", 0)) / int(e["total_installments"]))
        view.append({
            **e,
            "category_name": models.CATEGORIES.get(e["category"], e["category"]),
            "icon": models.CATEGORY_ICONS.get(e["category"], "📌"),
            "next_due": due,
            "days_left": days_left,
            "remaining": rem,
            "finished": finished,
            "progress": progress,
        })

    return render_template(
        "index.html",
        expenses=view,
        monthly_total=monthly_total,
        active_count=active_count,
        upcoming_count=upcoming_count,
        categories=models.CATEGORIES,
        line_ready=line_client.is_configured(),
        logs=models.recent_logs(10),
        today=today,
    )


@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        models.create_expense(_form_to_data(request.form))
        flash("เพิ่มรายการเรียบร้อยแล้ว", "success")
        return redirect(url_for("index"))
    return render_template(
        "form.html", expense=None, categories=models.CATEGORIES,
        default_remind=config.DEFAULT_REMIND_DAYS_BEFORE, today=date.today(),
    )


@app.route("/edit/<int:expense_id>", methods=["GET", "POST"])
def edit(expense_id):
    expense = models.get_expense(expense_id)
    if not expense:
        flash("ไม่พบรายการ", "error")
        return redirect(url_for("index"))
    if request.method == "POST":
        models.update_expense(expense_id, _form_to_data(request.form))
        flash("บันทึกการแก้ไขแล้ว", "success")
        return redirect(url_for("index"))
    return render_template(
        "form.html", expense=expense, categories=models.CATEGORIES,
        default_remind=config.DEFAULT_REMIND_DAYS_BEFORE, today=date.today(),
    )


@app.route("/delete/<int:expense_id>", methods=["POST"])
def delete(expense_id):
    models.delete_expense(expense_id)
    flash("ลบรายการแล้ว", "success")
    return redirect(url_for("index"))


@app.route("/pay/<int:expense_id>", methods=["GET", "POST"])
def pay(expense_id):
    """บันทึกการจ่าย — กรอกยอดจริง + วันที่ แล้วเก็บลงประวัติ"""
    expense = models.get_expense(expense_id)
    if not expense:
        flash("ไม่พบรายการ", "error")
        return redirect(url_for("index"))

    if request.method == "POST":
        amount = request.form.get("amount") or expense["amount"]
        paid_date = request.form.get("paid_date") or date.today().isoformat()
        note = request.form.get("note", "").strip()

        installment_no = None
        # ถ้าเป็นการผ่อน ให้เพิ่มงวดที่จ่าย + บันทึกเลขงวด
        if expense.get("total_installments"):
            installment_no = int(expense.get("paid_installments", 0)) + 1
            models.increment_paid(expense_id, 1)

        models.record_payment(expense_id, amount, paid_date, installment_no, note)
        flash(f"บันทึกการจ่าย {expense['name']} แล้ว", "success")
        return redirect(url_for("index"))

    return render_template("pay.html", expense=expense, today=date.today())


@app.route("/history")
@app.route("/history/<int:expense_id>")
def history(expense_id=None):
    """ดูประวัติการจ่าย — ทั้งหมด หรือเฉพาะรายการเดียว"""
    expense = models.get_expense(expense_id) if expense_id else None
    payments = models.list_payments(expense_id=expense_id)
    total = models.payment_total(expense_id=expense_id)
    for p in payments:
        p["category_name"] = models.CATEGORIES.get(p.get("category"), p.get("category") or "-")
        p["icon"] = models.CATEGORY_ICONS.get(p.get("category"), "📌")
    return render_template("history.html", payments=payments, total=total, expense=expense)


@app.route("/payment/delete/<int:payment_id>", methods=["POST"])
def payment_delete(payment_id):
    """ลบรายการจ่าย (ถ้าเป็นงวดผ่อนจะลดจำนวนงวดที่จ่ายคืนด้วย)"""
    p = models.get_payment(payment_id)
    if p:
        if p.get("installment_no"):
            models.increment_paid(p["expense_id"], -1)
        models.delete_payment(payment_id)
        flash("ลบรายการจ่ายแล้ว", "success")
    return redirect(request.referrer or url_for("history"))


@app.route("/preview")
def preview():
    """ดูตัวอย่างข้อความที่จะส่งวันนี้ (ไม่ส่งจริง)"""
    summary = notifier.build_monthly_summary()
    reminders = notifier.build_due_reminders()
    return render_template("preview.html", summary=summary, reminders=reminders)


@app.route("/send-test", methods=["POST"])
def send_test():
    """ส่งสรุปรายเดือนทดสอบทันที"""
    if not line_client.is_configured():
        flash("ยังไม่ได้ตั้งค่า LINE ในไฟล์ .env", "error")
        return redirect(url_for("index"))
    summary = notifier.build_monthly_summary()
    if not summary:
        flash("ยังไม่มีรายการให้สรุป", "error")
        return redirect(url_for("index"))
    try:
        line_client.send_push(summary)
        flash("ส่งข้อความทดสอบไปยัง LINE แล้ว", "success")
    except line_client.LineError as exc:
        flash(f"ส่งไม่สำเร็จ: {exc}", "error")
    return redirect(url_for("index"))


def _form_to_data(form):
    total_inst = form.get("total_installments", "").strip()
    return {
        "name": form.get("name", "").strip(),
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
