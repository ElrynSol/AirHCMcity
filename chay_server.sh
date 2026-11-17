#!/usr/bin/env bash
# Chạy máy chủ AirHCM trên Linux / macOS:   bash chay_server.sh [--lan] [--reload]
#   --lan     nghe mọi địa chỉ mạng (điện thoại cùng Wi-Fi truy cập được) thay vì chỉ máy này
#   --reload  tự nạp lại khi sửa mã (khi phát triển)
set -euo pipefail
GOC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -x "$GOC/venv/bin/python" ] || { echo "Chưa cài: chạy bash cai_dat.sh trước"; exit 1; }
HOST=127.0.0.1; THEM=()
for a in "$@"; do
  case "$a" in
    --lan) HOST=0.0.0.0 ;;
    --reload) THEM+=(--reload) ;;
  esac
done
if [ "$HOST" = 0.0.0.0 ]; then
  echo "Điện thoại cùng Wi-Fi mở:"; (hostname -I 2>/dev/null || ipconfig getifaddr en0 2>/dev/null) | tr ' ' '\n' | grep -E '^[0-9.]+$' | sed 's/.*/    http:\/\/&:8000/'
fi
cd "$GOC/backend"
exec "$GOC/venv/bin/python" -m uvicorn main:app --host "$HOST" --port "${CONG:-8000}" --workers 1 "${THEM[@]}"
