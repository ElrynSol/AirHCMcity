"""Gửi email qua SMTP (Gmail App Password đặt trong .env)."""

from core import config  # noqa: F401  (nạp .env và đường dẫn dự án trước)
from email.mime.text import MIMEText
import os
import smtplib


def gui_email_otp(den_email: str, ma_otp: str) -> bool:
    """Gửi OTP qua SMTP (Gmail). Trả False nếu chưa cấu hình SMTP trong .env."""
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    if not smtp_user or not smtp_pass:
        return False
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    noi_dung = (
        f"Mã OTP đặt lại mật khẩu của bạn là: {ma_otp}\n\n"
        "Mã có hiệu lực trong 10 phút và chỉ dùng được 1 lần. Không chia sẻ mã này cho bất kỳ ai, kể cả người tự xưng là quản trị viên. Nếu bạn không yêu cầu, hãy bỏ qua email này.\n\n"
        "— Hệ thống Giám sát & Dự báo Chất lượng Không khí TP.HCM"
    )
    msg = MIMEText(noi_dung, "plain", "utf-8")
    msg["Subject"] = "Mã OTP đặt lại mật khẩu"
    msg["From"] = smtp_user
    msg["To"] = den_email
    if port == 465:
        # Cổng 465: kết nối mã hóa SSL ngay từ đầu
        with smtplib.SMTP_SSL(host, port, timeout=30) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
    return True


def gui_mail_chung(den_email: str, tieu_de: str, noi_dung: str) -> bool:
    """Gửi email văn bản thường qua SMTP đã cấu hình. Trả False nếu chưa cấu hình."""
    from email.header import Header
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    if not smtp_user or not smtp_pass:
        return False
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    msg = MIMEText(noi_dung, "plain", "utf-8")
    msg["Subject"] = Header(tieu_de, "utf-8")
    msg["From"] = smtp_user
    msg["To"] = den_email
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo(); server.starttls(); server.ehlo()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
    return True
