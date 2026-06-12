# ใช้สำหรับ deploy บน Railway / Fly.io / หรือที่ไหนก็ได้ที่รองรับ Docker
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# เก็บ SQLite ไว้บน volume ที่ /data (ผูก volume ตอน deploy)
ENV DATABASE_PATH=/data/expenses.db
ENV RUN_SCHEDULER=1
ENV NOTIFY_HOUR=8
ENV SUMMARY_DAY=1
ENV TIMEZONE=Asia/Bangkok
ENV PORT=8080

VOLUME ["/data"]
EXPOSE 8080

# worker เดียวเพื่อไม่ให้ scheduler รันซ้ำ
CMD gunicorn app:app --workers 1 --bind 0.0.0.0:${PORT} --timeout 120
