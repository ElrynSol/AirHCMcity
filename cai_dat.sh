#!/usr/bin/env bash
# Cài AirHCM trên Linux / macOS (chạy được nhiều lần):   bash cai_dat.sh [--dev]
# Việc làm: tìm Python 3.11+ → tạo/sửa venv → cài thư viện → tạo .env với khóa ngẫu nhiên → tạo CSDL + PostGIS → kiểm tra.
# Cần cài trước PostgreSQL + PostGIS:
#   Ubuntu/Debian: sudo apt install python3-venv postgresql postgresql-contrib postgis
#   macOS (Homebrew): brew install python@3.12 postgresql@17 postgis
# Không muốn cài gì ngoài Docker: docker compose -f dong_goi/docker-compose.yml up -d --build
set -euo pipefail
GOC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; cd "$GOC"
buoc() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }

buoc "Tìm Python 3.11+"
PY=""
for ung in python3.12 python3.13 python3.11 python3 python; do
  if command -v "$ung" >/dev/null 2>&1 && "$ung" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then PY="$ung"; break; fi
done
[ -n "$PY" ] || { echo "Không thấy Python 3.11+. Ubuntu: sudo apt install python3 python3-venv · macOS: brew install python@3.12"; exit 1; }
echo "Dùng: $PY ($($PY --version))"

buoc "Môi trường ảo venv"
if [ -x venv/bin/python ] && ! venv/bin/python -c 'import sys' 2>/dev/null; then echo "venv hỏng → tạo lại"; rm -rf venv; fi
if [ -f venv/pyvenv.cfg ] && ! grep -q "$GOC/venv" venv/pyvenv.cfg 2>/dev/null && grep -q '^command' venv/pyvenv.cfg; then
  echo "venv được tạo ở thư mục khác (đã chuyển dự án) → tạo lại"; rm -rf venv
fi
[ -x venv/bin/python ] || { "$PY" -m venv venv; echo "Đã tạo venv"; }

buoc "Cài thư viện (lần đầu vài phút)"
venv/bin/python -m pip install --upgrade pip --quiet
REQ=requirements.txt; [ "${1:-}" = "--dev" ] && REQ=requirements-dev.txt
venv/bin/python -m pip install -r "$REQ" --quiet

buoc "Tệp cấu hình .env"
if [ ! -f .env ]; then
  cp .env.example .env
  JWT="$(venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
  read -rsp "Mật khẩu tài khoản postgres của PostgreSQL trên máy này: " MK; echo
  venv/bin/python - "$JWT" "$MK" <<'PY'
import re, sys
from pathlib import Path
p = Path(".env"); s = p.read_text(encoding="utf-8")
s = re.sub(r"(?m)^JWT_SECRET_KEY=.*$", "JWT_SECRET_KEY=" + sys.argv[1], s)
s = re.sub(r"(?m)^DB_PASS=.*$", lambda m: "DB_PASS=" + sys.argv[2], s)
p.write_text(s, encoding="utf-8")
PY
  chmod 600 .env
  echo "Đã tạo .env (khóa JWT ngẫu nhiên). Mở .env để điền SMTP, GEMINI_API_KEY nếu cần."
else
  echo "Giữ .env hiện có"
fi

buoc "Kiểm tra môi trường, tạo CSDL + PostGIS nếu thiếu"
set +e; venv/bin/python dong_goi/kiem_tra_moi_truong.py --tao-csdl; KQ=$?; set -e
printf '\n\033[1;32mChạy máy chủ:  bash chay_server.sh   (rồi mở http://localhost:8000)\033[0m\n'
exit $KQ
