"""Gửi email qua SMTP (Gmail App Password đặt trong .env)."""

from core import config  # noqa: F401  (nạp .env và đường dẫn dự án trước)
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
import os
import smtplib
import socket
import ssl


def _gui_qua_smtp(msg: MIMEText) -> bool:
    """Gửi MIMEText qua SMTP với cơ chế tự thử cổng dự phòng (465 SSL <-> 587 STARTTLS) và ưu tiên IPv4."""
    smtp_user = (os.getenv("SMTP_USER") or "").strip().strip('"').strip("'")
    smtp_pass = (os.getenv("SMTP_PASS") or "").replace(" ", "").strip().strip('"').strip("'")
    if not smtp_user or not smtp_pass:
        return False
    host = (os.getenv("SMTP_HOST") or "smtp.gmail.com").strip()
    try:
        port_chinh = int((os.getenv("SMTP_PORT") or "587").strip())
    except ValueError:
        port_chinh = 587

    msg["From"] = formataddr(("AirHCM", smtp_user))
    ds_cong = [port_chinh, 587 if port_chinh == 465 else 465]
    loi_cuoi = None

    for port in ds_cong:
        for _lan in range(2):   # thử lại 1 lần nếu máy chủ ngắt kết nối giữa chừng
            try:
                target_host = host   # luôn kết nối theo tên miền để kiểm tra chứng chỉ TLS đầy đủ
                ctx = ssl.create_default_context()
                if port == 465:
                    with smtplib.SMTP_SSL(target_host, port, local_hostname="airhcmcity.asia", timeout=20, context=ctx) as server:
                        server.ehlo()
                        server.login(smtp_user, smtp_pass)
                        server.send_message(msg)
                else:
                    with smtplib.SMTP(target_host, port, local_hostname="airhcmcity.asia", timeout=20) as server:
                        server.ehlo()
                        server.starttls(context=ctx)
                        server.ehlo()
                        server.login(smtp_user, smtp_pass)
                        server.send_message(msg)
                return True
            except Exception as exc:
                loi_cuoi = exc
                continue
    if loi_cuoi:
        raise loi_cuoi
    return False


def gui_email_otp(den_email: str, ma_otp: str) -> bool:
    """Gửi OTP qua SMTP (Gmail). Trả False nếu chưa cấu hình SMTP trong .env."""
    noi_dung = (
        f"Mã OTP đặt lại mật khẩu của bạn là: {ma_otp}\n\n"
        "Mã có hiệu lực trong 10 phút và chỉ dùng được 1 lần. Không chia sẻ mã này cho bất kỳ ai, "
        "kể cả người tự xưng là quản trị viên. Nếu bạn không yêu cầu, hãy bỏ qua email này.\n\n"
        "— AirHCM · Hệ thống Giám sát & Dự báo Chất lượng Không khí TP.HCM"
    )
    msg = MIMEText(noi_dung, "plain", "utf-8")
    msg["Subject"] = Header(f"[{ma_otp}] Mã OTP đặt lại mật khẩu — AirHCM", "utf-8")
    msg["To"] = den_email
    return _gui_qua_smtp(msg)


def gui_mail_chung(den_email: str, tieu_de: str, noi_dung: str) -> bool:
    """Gửi email văn bản thường qua SMTP đã cấu hình. Trả False nếu chưa cấu hình."""
    msg = MIMEText(noi_dung, "plain", "utf-8")
    msg["Subject"] = Header(tieu_de, "utf-8")
    msg["To"] = den_email
    return _gui_qua_smtp(msg)
