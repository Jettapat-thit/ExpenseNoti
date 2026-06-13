#!/usr/bin/env bash
# รันย้ายข้อมูล SQLite -> PostgreSQL แบบคำสั่งเดียว
#
# วิธีใช้:
#   ./run_migrate.sh                 # ใช้ไฟล์ expenses.db + DATABASE_URL จาก .env/env
#   ./run_migrate.sh path/to.db      # ระบุไฟล์ SQLite เอง
#   DATABASE_URL="postgresql://..." ./run_migrate.sh
#
# ต้องมี Python 3 และต่อ Postgres ปลายทางได้

set -e
cd "$(dirname "$0")"

SQLITE_FILE="${1:-expenses.db}"

# 1) โหลด DATABASE_URL จาก .env ถ้ายังไม่ได้ตั้งใน environment
if [ -z "$DATABASE_URL" ] && [ -f .env ]; then
  export "$(grep -E '^DATABASE_URL=' .env | head -1 | sed 's/^ *//')" 2>/dev/null || true
fi

# 2) ตรวจความพร้อม
if [ -z "$DATABASE_URL" ]; then
  echo "❌ ยังไม่ได้ตั้ง DATABASE_URL"
  echo '   ลอง:  export DATABASE_URL="postgresql://user:pass@host:5432/dbname"'
  echo "   (ใช้ External Database URL ของ Postgres บน Render)"
  exit 1
fi
if [ ! -f "$SQLITE_FILE" ]; then
  echo "❌ ไม่พบไฟล์ SQLite: $SQLITE_FILE"
  echo "   ระบุ path เอง:  ./run_migrate.sh /path/to/expenses.db"
  exit 1
fi

# 3) ติดตั้ง psycopg ถ้ายังไม่มี
python3 -c "import psycopg" 2>/dev/null || {
  echo "📦 กำลังติดตั้ง psycopg ..."
  pip install "psycopg[binary]>=3.1" >/dev/null
}

# 4) รันสคริปต์ย้ายข้อมูล
echo "🚀 เริ่มย้ายข้อมูลจาก $SQLITE_FILE ..."
DATABASE_URL="$DATABASE_URL" python3 migrate_sqlite_to_pg.py "$SQLITE_FILE"
