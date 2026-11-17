#!/usr/bin/env bash
# Khôi phục dữ liệu (trạm, số liệu, tài khoản...) từ bản sao lưu vào CSDL của Docker.
#   bash dong_goi/trien_khai/khoi_phuc.sh backup.sql                  # CSDL còn trống (lần đầu triển khai)
#   bash dong_goi/trien_khai/khoi_phuc.sh sao_luu/airhcm_xxx.sql.gz --ghi-de   # XÓA dữ liệu hiện có rồi khôi phục
# Dùng được cho cả docker-compose.yml (máy cá nhân) và docker-compose.prod.yml (máy chủ): đặt FILE_COMPOSE nếu cần.
set -euo pipefail
GOC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$GOC"
TEP="${1:?Cách dùng: khoi_phuc.sh <tệp .sql hoặc .sql.gz> [--ghi-de]}"
[ -f "$TEP" ] || { echo "Không thấy tệp $TEP"; exit 1; }
FILE_COMPOSE="${FILE_COMPOSE:-dong_goi/docker-compose.prod.yml}"
DOCKER="docker"; docker info >/dev/null 2>&1 || DOCKER="sudo docker"
C="$DOCKER compose -f $FILE_COMPOSE"
PSQL="$C exec -T db psql -v ON_ERROR_STOP=0 -q -U postgres -d air_quality_db"

$C up -d db
until $C exec -T db pg_isready -U postgres -d air_quality_db >/dev/null 2>&1; do sleep 2; done

SO_BANG=$($C exec -T db psql -tA -U postgres -d air_quality_db -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' AND table_name <> 'spatial_ref_sys'")
if [ "$SO_BANG" -gt 0 ]; then
  if [ "${2:-}" != "--ghi-de" ]; then
    echo "CSDL đã có $SO_BANG bảng. Chạy lại với --ghi-de để XÓA dữ liệu hiện có rồi khôi phục."; exit 1
  fi
  echo "Dừng máy chủ và xóa dữ liệu cũ..."
  $C stop backend >/dev/null 2>&1 || true
  $PSQL -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; CREATE EXTENSION IF NOT EXISTS postgis;"
fi

echo "Đang khôi phục $TEP ..."
case "$TEP" in
  *.gz) gunzip -c "$TEP" | $PSQL ;;
  *)    $PSQL < "$TEP" ;;
esac
echo "Đã khôi phục. Khởi động lại máy chủ (tự nâng cấp bảng bảo mật khi khởi động)..."
$C up -d
echo "Xong. Số tài khoản: $($C exec -T db psql -tA -U postgres -d air_quality_db -c 'SELECT count(*) FROM nguoi_dung' 2>/dev/null || echo '?')"
