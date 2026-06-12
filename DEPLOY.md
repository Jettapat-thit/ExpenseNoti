# 🚀 วิธี Deploy ขึ้น Cloud (Render)

แนะนำ **Render** เพราะถูก ตั้งง่าย และมี persistent disk ให้เก็บไฟล์ SQLite ไม่ให้หาย
ราคาประมาณ **$7/เดือน** (แพ็กเกจ Starter — จำเป็นเพราะแพ็กฟรีไม่รองรับ disk)

ระบบถูกปรับให้ตัวแจ้งเตือนรันอยู่**ในตัวเว็บเลย** (background scheduler) จึงใช้ service เดียว + disk เดียว
ไม่ต้องตั้ง cron แยก

---

## สิ่งที่ต้องเตรียมก่อน

1. **บัญชี GitHub** — ไว้เก็บโค้ด
2. **บัญชี Render** — สมัครฟรีที่ https://render.com (ผูกกับ GitHub ได้)
3. **ค่า LINE 2 ตัว** (จาก README หลัก):
   - `LINE_CHANNEL_ACCESS_TOKEN`
   - `LINE_TO_USER_ID`

---

## ขั้นตอน

### 1) อัปโหลดโค้ดขึ้น GitHub
ในโฟลเดอร์ ExpenseNoti:

```bash
git init
git add .
git commit -m "ExpenseNoti"
git branch -M main
git remote add origin https://github.com/<ชื่อคุณ>/ExpenseNoti.git
git push -u origin main
```

> ไฟล์ `.gitignore` กันไม่ให้ `.env` และ `*.db` หลุดขึ้น GitHub อยู่แล้ว — ค่าลับจะไปตั้งบน Render แทน

### 2) สร้าง service บน Render
1. เข้า Render Dashboard → **New** → **Blueprint**
2. เลือก repo `ExpenseNoti` ที่เพิ่ง push
3. Render จะอ่านไฟล์ **`render.yaml`** แล้วตั้งค่าให้อัตโนมัติ (service + disk + env)
4. กด **Apply**

### 3) ใส่ค่า LINE (ค่าลับ)
ในหน้า service → แท็บ **Environment** → กรอก 2 ตัวที่ยังว่าง:
- `LINE_CHANNEL_ACCESS_TOKEN` = token จาก LINE
- `LINE_TO_USER_ID` = User ID ของคุณ (ขึ้นต้นด้วย U)

กด **Save** แล้ว Render จะ deploy ใหม่ให้เอง

### 4) เสร็จ — เปิดใช้งาน
- เปิด URL ที่ Render ให้ (เช่น `https://expensenoti.onrender.com`) → เพิ่มรายการได้เลย
- กด **"ส่งสรุปทดสอบเข้า LINE"** เพื่อเช็คว่าตั้งค่าถูก
- ระบบจะส่งแจ้งเตือนอัตโนมัติทุกวันเวลา 08:00 (ปรับได้ด้วย env `NOTIFY_HOUR`)

---

## ตารางตัวแปร (env vars) ที่ปรับได้

| ตัวแปร | ความหมาย | ค่าเริ่มต้น |
|---|---|---|
| `NOTIFY_HOUR` | เวลาส่งแจ้งเตือนรายวัน (0–23) | 8 |
| `NOTIFY_MINUTE` | นาที | 0 |
| `SUMMARY_DAY` | วันของเดือนที่ส่งสรุปรวม | 1 |
| `TIMEZONE` | โซนเวลา | Asia/Bangkok |
| `DATABASE_PATH` | ที่เก็บไฟล์ SQLite | /data/expenses.db |
| `RUN_SCHEDULER` | เปิดตัวแจ้งเตือนในแอป (1=เปิด) | 1 |

---

## ทางเลือกอื่น

- **Railway** ($5/เดือน) — ใช้ `Dockerfile` ที่ให้มา + ผูก Volume ที่ `/data` แล้วตั้ง env เหมือนข้างบน
- **Fly.io** — ใช้ `Dockerfile` ได้เช่นกัน แต่ตอนนี้ไม่มีแพ็กฟรีแล้ว
- **รันที่บ้านฟรี** — เครื่องเก่า/Raspberry Pi เปิดทิ้งไว้ ใช้ crontab เรียก `scheduler.py` ตามใน README หลัก (ไม่ต้องเสียค่า cloud เลย เพราะแอปกินทรัพยากรน้อยมาก)

---

## หมายเหตุเรื่องค่าใช้จ่าย
- LINE Messaging API: ส่ง push ฟรีได้จำนวนหนึ่งต่อเดือน — แอปนี้ส่งวันละไม่กี่ข้อความ ปกติไม่เกินโควต้าฟรี
- Render Starter: คิดรายเดือนแบบคงที่ ($7) + disk 1GB (รวมอยู่/เพิ่มเล็กน้อย)
