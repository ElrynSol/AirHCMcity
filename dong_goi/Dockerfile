# Image máy chủ AirHCM — chạy trên mọi hệ điều hành có Docker (Windows, macOS, Linux) và mọi kiến trúc
# (x86-64 / amd64 và ARM64 — vd. Oracle Cloud Ampere A1 miễn phí, Apple Silicon, Raspberry Pi 4/5 64-bit).
# Xây từ THƯ MỤC GỐC dự án:  docker build -f dong_goi/Dockerfile -t airhcm .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Ho_Chi_Minh \
    MOI_TRUONG=production

# tzdata: giờ Việt Nam cho lịch đồng bộ/cảnh báo; không cần trình biên dịch (mọi thư viện đều có bản cài sẵn)
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Chạy bằng người dùng thường (không phải root). Pipeline đồng bộ ghi log_dong_bo.txt, tệp khóa trong data_pipeline/,
# mô hình huấn luyện lại vào models/, khóa VAPID vào bi_mat/ → mã nguồn thuộc quyền người dùng app.
RUN useradd --create-home --uid 10001 app && mkdir -p /app/bi_mat /app/du_lieu && chown app:app /app /app/bi_mat /app/du_lieu

# Mã nguồn (backend import ml/ và data_pipeline/, đọc models/ và phục vụ frontend/) — xem .dockerignore
COPY --chown=app:app backend ./backend
COPY --chown=app:app ml ./ml
COPY --chown=app:app data_pipeline ./data_pipeline
COPY --chown=app:app frontend ./frontend
COPY --chown=app:app models ./models
COPY --chown=app:app docs ./docs
COPY --chown=app:app README.md ./
# Ranh giới 168 phường/xã (máy chủ tự nạp vào PostGIS khi CSDL trống) + tệp cài app Android cho trang tai-app.html
COPY --chown=app:app du_lieu/ranh_gioi/phuong_xa_hcm.geojson ./du_lieu/ranh_gioi/
# Bộ dữ liệu mở (nạp bằng: python ../data_pipeline/du_lieu_mo.py --nhap)
COPY --chown=app:app du_lieu/mo ./du_lieu/mo
# APK không có trong kho GitHub: mẫu [k] + README giúp lệnh COPY không lỗi khi thiếu APK
COPY --chown=app:app mobile/README_MOBILE.md mobile/AirHCM.ap[k] ./mobile/
USER app

WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status==200 else 1)"

# 1 tiến trình (workers=1): bộ đếm chống dò mật khẩu, bus sự kiện, MQTT và lịch nền nằm trong bộ nhớ tiến trình.
# --proxy-headers: lấy IP thật của người dùng và https từ Caddy (reverse proxy) phía trước.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--timeout-keep-alive", "30"]
