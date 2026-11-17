#!/usr/bin/env bash
# Cài AirHCM lên máy chủ Linux chạy 24/7 (đã nhắm tới Oracle Cloud Always Free – Ubuntu 22.04/24.04, ARM64 hoặc x86-64).
# Chạy TỪ THƯ MỤC GỐC dự án trên máy chủ:   bash dong_goi/trien_khai/cai_dat_may_chu.sh
# Chạy lại nhiều lần không sao (giữ nguyên .env và dữ liệu đã có).
set -euo pipefail

GOC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$GOC"
COMPOSE="docker compose -f dong_goi/docker-compose.prod.yml"
xanh() { printf '\033[1;32m%s\033[0m\n' "$*"; }
vang() { printf '\033[1;33m%s\033[0m\n' "$*"; }
[ -f backend/main.py ] || { echo "Hãy chạy script trong thư mục gốc dự án AirHCM"; exit 1; }
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"

# ---------------------------------------------------------------- 1. Docker
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  xanh "[1/6] Cài Docker..."
  $SUDO apt-get update -y
  $SUDO apt-get install -y ca-certificates curl
  if ! $SUDO apt-get install -y docker.io docker-compose-v2 2>/dev/null; then
    curl -fsSL https://get.docker.com | $SUDO sh          # kho chính thức của Docker (khi kho Ubuntu thiếu compose v2)
  fi
  $SUDO systemctl enable --now docker
  $SUDO usermod -aG docker "${SUDO_USER:-$USER}" || true
else
  xanh "[1/6] Docker đã có: $(docker --version)"
fi
DOCKER="docker"; docker info >/dev/null 2>&1 || DOCKER="$SUDO docker"
COMPOSE="$DOCKER compose -f dong_goi/docker-compose.prod.yml"

# ---------------------------------------------------------------- 2. Bộ nhớ swap (máy ít RAM)
RAM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if [ "$RAM_MB" -lt 4000 ] && ! swapon --show | grep -q .; then
  xanh "[2/6] RAM ${RAM_MB} MB: tạo 2 GB swap để build và chạy ổn định..."
  $SUDO fallocate -l 2G /swapfile && $SUDO chmod 600 /swapfile && $SUDO mkswap /swapfile && $SUDO swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | $SUDO tee -a /etc/fstab >/dev/null
else
  xanh "[2/6] RAM ${RAM_MB} MB: không cần thêm swap"
fi

# ---------------------------------------------------------------- 3. Tường lửa trong máy (ảnh Ubuntu của Oracle chặn sẵn mọi cổng trừ 22)
xanh "[3/6] Mở cổng 80, 443 (HTTP/HTTPS) trong iptables..."
for p in "tcp 80" "tcp 443" "udp 443"; do
  set -- $p
  $SUDO iptables -C INPUT -p "$1" --dport "$2" -m state --state NEW -j ACCEPT 2>/dev/null \
    || $SUDO iptables -I INPUT 5 -p "$1" --dport "$2" -m state --state NEW -j ACCEPT
done
if command -v netfilter-persistent >/dev/null 2>&1; then $SUDO netfilter-persistent save >/dev/null 2>&1 || true
else $SUDO apt-get install -y iptables-persistent >/dev/null 2>&1 && $SUDO netfilter-persistent save >/dev/null 2>&1 || true; fi
vang "    Nhớ mở thêm cổng 80, 443 ở Oracle Cloud: VCN → Security List → Add Ingress Rules (xem docs/TRIEN_KHAI_ORACLE.md)"

# ---------------------------------------------------------------- 4. Tệp cấu hình .env
khoa() { head -c 48 /dev/urandom | base64 | tr -d '/+=\n' | head -c "$1"; }
dat() {  # dat TEN GIA_TRI : ghi/ghi đè biến trong .env
  if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi
}
lay() { grep -E "^$1=" .env | head -1 | cut -d= -f2-; }
if [ ! -f .env ]; then
  xanh "[4/6] Tạo .env mới với khóa ngẫu nhiên..."
  cp .env.example .env
  dat DB_PASS "$(khoa 32)"
  dat JWT_SECRET_KEY "$(khoa 64)"
else
  xanh "[4/6] Giữ .env hiện có (bổ sung biến còn thiếu)"
  [ -n "$(lay DB_PASS)" ] || dat DB_PASS "$(khoa 32)"
  JWT="$(lay JWT_SECRET_KEY)"
  [ "${#JWT}" -ge 32 ] || dat JWT_SECRET_KEY "$(khoa 64)"
fi
dat MOI_TRUONG production
dat OTP_DEMO 0
[ -n "$(lay TEN_MIEN)" ]   || { read -rp "    Tên miền (vd. airhcm.duckdns.org): " v; dat TEN_MIEN "$v"; }
[ -n "$(lay EMAIL_ACME)" ] || { read -rp "    Email nhận thông báo chứng chỉ HTTPS: " v; dat EMAIL_ACME "$v"; }
[ -n "$(lay ADMIN_EMAILS)" ] || { read -rp "    Email tài khoản quản trị (admin): " v; dat ADMIN_EMAILS "$v"; }
chmod 600 .env
mkdir -p bi_mat_may_chu sao_luu
[ -f gee-key.json ] && [ ! -f bi_mat_may_chu/gee-key.json ] && mv gee-key.json bi_mat_may_chu/ && chmod 600 bi_mat_may_chu/gee-key.json || true
TEN_MIEN="$(lay TEN_MIEN)"

# ---------------------------------------------------------------- 5. Kiểm tra tên miền trỏ đúng máy này
IP_MAY=$(curl -fsS -4 https://ifconfig.me 2>/dev/null || true)
IP_TEN_MIEN=$(getent ahostsv4 "$TEN_MIEN" 2>/dev/null | awk 'NR==1{print $1}' || true)
if [ -n "$IP_MAY" ] && [ "$IP_MAY" != "$IP_TEN_MIEN" ]; then
  vang "[5/6] CHÚ Ý: $TEN_MIEN đang trỏ tới '${IP_TEN_MIEN:-không có}' nhưng IP máy này là $IP_MAY."
  vang "      Sửa bản ghi DNS (DuckDNS: điền IP $IP_MAY) rồi chạy lại; nếu không Caddy không xin được chứng chỉ HTTPS."
else
  xanh "[5/6] Tên miền $TEN_MIEN → $IP_MAY: đúng"
fi

# ---------------------------------------------------------------- 6. Build + chạy
xanh "[6/6] Build và khởi động (lần đầu mất 5–15 phút trên máy ARM miễn phí)..."
$COMPOSE up -d --build
printf "    Chờ máy chủ sẵn sàng"
for _ in $(seq 1 60); do
  if $COMPOSE exec -T backend python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health',timeout=4).status==200 else 1)" >/dev/null 2>&1; then
    echo; xanh "XONG! Mở https://$TEN_MIEN  (đăng ký bằng email admin đã khai báo để có quyền quản trị)"
    echo "  Xem nhật ký:      $COMPOSE logs -f backend"
    echo "  Khôi phục dữ liệu: bash dong_goi/trien_khai/khoi_phuc.sh backup.sql"
    echo "  Cập nhật mã mới:   bash dong_goi/trien_khai/cap_nhat.sh"
    exit 0
  fi
  printf "."; sleep 5
done
echo; vang "Máy chủ chưa phản hồi sau 5 phút. Xem lỗi: $COMPOSE logs --tail 100 backend"; exit 1
