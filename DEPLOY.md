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

### 3) สร้าง LINE Login channel (สำหรับให้ผู้ใช้ล็อกอิน)
ระบบนี้รองรับหลายผู้ใช้ — แต่ละคนล็อกอินด้วย LINE แล้วข้อมูลแยกเป็นส่วนตัว

1. เข้า https://developers.line.biz/console/ → provider เดิม (อันเดียวกับ Messaging API)
2. **Create a new channel → LINE Login**
3. ในแท็บ **LINE Login** → ตั้ง **Callback URL** เป็น:
   `https://<your-app>.onrender.com/callback`  (และ `http://localhost:5000/callback` ถ้าจะรันในเครื่องด้วย)
4. ในแท็บ **Basic settings** จดค่า **Channel ID** และ **Channel secret** ของ Login channel นี้
5. (แนะนำ) แท็บ LINE Login → เปิด **Linked LINE Official Account** ให้เชื่อมกับบอท Messaging API
   เพื่อให้ตอนล็อกอินผู้ใช้ถูกชวนแอดบอท จะได้ส่งแจ้งเตือนได้

### 4) ใส่ค่า env (ค่าลับ)
ในหน้า service → แท็บ **Environment** → กรอกที่ยังว่าง:
- `LINE_CHANNEL_ACCESS_TOKEN` = token จาก **Messaging API** channel
- `LINE_LOGIN_CHANNEL_ID` = Channel ID จาก **LINE Login** channel
- `LINE_LOGIN_CHANNEL_SECRET` = Channel secret จาก **LINE Login** channel
- `BASE_URL` = URL จริงของแอป เช่น `https://expensenoti.onrender.com` (ต้องตรงกับ Callback URL)

กด **Save** แล้ว Render จะ deploy ใหม่ให้เอง

### 5) เสร็จ — เปิดใช้งาน
- เปิด URL ที่ Render ให้ → กด **"เข้าสู่ระบบด้วย LINE"** → อนุญาต → เริ่มเพิ่มรายการได้เลย
- กด **"ส่งสรุปเข้า LINE"** เพื่อเช็คว่าส่งแจ้งเตือนได้ (ต้องแอดบอทเป็นเพื่อนก่อน)
- ตั้งเวลาแจ้งเตือนของแต่ละคนได้ที่หน้า **ตั้งค่า**

---

## ตารางตัวแปร (env vars)

| ตัวแปร | ความหมาย | ค่าเริ่มต้น |
|---|---|---|
| `LINE_CHANNEL_ACCESS_TOKEN` | token บอทส่งแจ้งเตือน (ลับ) | — |
| `LINE_LOGIN_CHANNEL_ID` | Channel ID ของ LINE Login | — |
| `LINE_LOGIN_CHANNEL_SECRET` | Channel secret ของ LINE Login (ลับ) | — |
| `BASE_URL` | URL จริงของแอป (ทำ redirect URI) | http://localhost:5000 |
| `SECRET_KEY` | กุญแจเข้ารหัส session | (สุ่มให้) |
| `NOTIFY_MINUTE` | นาทีที่เช็คทุกชั่วโมง | 0 |
| `TIMEZONE` | โซนเวลา | Asia/Bangkok |
| `DATABASE_PATH` | ที่เก็บไฟล์ SQLite | /data/expenses.db |
| `RUN_SCHEDULER` | เปิดตัวแจ้งเตือนในแอป (1=เปิด) | 1 |

> เวลาส่งแจ้งเตือนและวันสรุปรายเดือน ตั้งแยกรายคนได้ในหน้า **ตั้งค่า** ของแต่ละ user
> (scheduler เช็คทุกชั่วโมงแล้วส่งให้คนที่ตั้งเวลาตรงกับชั่วโมงนั้น)

---

## ทางเลือกอื่น

- **Railway** ($5/เดือน) — ใช้ `Dockerfile` ที่ให้มา + ผูก Volume ที่ `/data` แล้วตั้ง env เหมือนข้างบน
- **Fly.io** — ใช้ `Dockerfile` ได้เช่นกัน แต่ตอนนี้ไม่มีแพ็กฟรีแล้ว
- **รันที่บ้านฟรี** — เครื่องเก่า/Raspberry Pi เปิดทิ้งไว้ ใช้ crontab เรียก `scheduler.py` ตามใน README หลัก (ไม่ต้องเสียค่า cloud เลย เพราะแอปกินทรัพยากรน้อยมาก)

---

## หมายเหตุเรื่องค่าใช้จ่าย
- LINE Messaging API: ส่ง push ฟรีได้จำนวนหนึ่งต่อเดือน — แอปนี้ส่งวันละไม่กี่ข้อความ ปกติไม่เกินโควต้าฟรี
- Render Starter: คิดรายเดือนแบบคงที่ ($7) + disk 1GB (รวมอยู่/เพิ่มเล็กน้อย)
