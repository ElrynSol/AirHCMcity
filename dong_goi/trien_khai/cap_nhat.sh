#!/usr/bin/env bash
# Cập nhật máy chủ sau khi chép mã nguồn mới lên (git pull hoặc giải nén bản mới đè lên thư mục dự án).
# Sao lưu CSDL trước, build lại image, khởi động lại — dữ liệu, .env, chứng chỉ HTTPS được giữ nguyên.
#   bash dong_goi/trien_khai/cap_nhat.sh
set -euo pipefail
GOC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$GOC"
DOCKER="docker"; docker info >/dev/null 2>&1 || DOCKER="sudo docker"
C="$DOCKER compose -f dong_goi/docker-compose.prod.yml"
mkdir -p sao_luu
f="sao_luu/truoc_cap_nhat_$(date +%Y%m%d_%H%M).sql.gz"
echo "Sao lưu CSDL → $f"
$C exec -T db pg_dump -U postgres -d air_quality_db --no-owner | gzip > "$f"
[ -d .git ] && git pull --ff-only || true
$C up -d --build
$DOCKER image prune -f >/dev/null
echo "Đã cập nhật. Theo dõi: $C logs -f --tail 50 backend"
