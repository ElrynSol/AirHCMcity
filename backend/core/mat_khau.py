"""Chính sách mật khẩu (theo hướng dẫn NIST SP 800-63B / OWASP ASVS, có điều chỉnh cho người dùng phổ thông).

Áp dụng khi đăng ký, đổi mật khẩu và đặt lại mật khẩu. Tài khoản cũ có mật khẩu yếu vẫn đăng nhập được,
nhưng lần đổi mật khẩu kế tiếp phải theo chính sách mới.
"""

import re
import unicodedata

DO_DAI_TOI_THIEU = 10
DO_DAI_TOI_DA = 128   # chặn chuỗi quá dài làm chậm hàm băm (tấn công từ chối dịch vụ)

# Mật khẩu phổ biến nhất (rút gọn từ các danh sách rò rỉ công khai) + biến thể tiếng Việt thường gặp
_PHO_BIEN = {
    "123456", "123456789", "12345678", "1234567890", "password", "password1", "password123", "qwerty", "qwerty123",
    "abc123", "abc12345", "111111", "123123", "1q2w3e4r", "1qaz2wsx", "iloveyou", "admin", "admin123", "admin@123",
    "welcome", "welcome1", "letmein", "monkey", "dragon", "football", "baseball", "sunshine", "princess", "zaq12wsx",
    "matkhau", "matkhau123", "anhyeuem", "emyeuanh", "yeuem", "yeuanh", "123456aa", "aa123456", "vietnam", "vietnam123",
    "hochiminh", "saigon", "saigon123", "airhcm", "airhcm123", "khongkhi", "khongkhi123", "abcd1234", "1234abcd",
    "passw0rd", "p@ssw0rd", "p@ssword", "qwertyuiop", "asdfghjkl", "zxcvbnm", "0123456789", "987654321",
}


def _bo_dau(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def kiem_tra_mat_khau(mat_khau: str, email: str = "", ho_ten: str = "") -> str | None:
    """Trả về thông báo lỗi (tiếng Việt) nếu mật khẩu không đạt, None nếu đạt."""
    mk = mat_khau or ""
    if len(mk) < DO_DAI_TOI_THIEU:
        return f"Mật khẩu phải có ít nhất {DO_DAI_TOI_THIEU} ký tự"
    if len(mk) > DO_DAI_TOI_DA:
        return f"Mật khẩu tối đa {DO_DAI_TOI_DA} ký tự"
    if not re.search(r"[^\W\d_]", mk) or not re.search(r"\d", mk):
        return "Mật khẩu phải có cả chữ cái và chữ số"
    thuong = _bo_dau(mk)
    if thuong in _PHO_BIEN or re.sub(r"[\d!@#$%^&*._-]+$", "", thuong) in _PHO_BIEN:
        return "Mật khẩu quá phổ biến, dễ bị đoán. Hãy chọn mật khẩu khác"
    if len(set(mk)) < 4:
        return "Mật khẩu lặp lại quá nhiều ký tự giống nhau"
    ten_email = _bo_dau((email or "").split("@")[0])
    if len(ten_email) >= 4 and ten_email in thuong:
        return "Mật khẩu không được chứa phần tên trong email"
    for tu in _bo_dau(ho_ten or "").split():
        if len(tu) >= 4 and tu in thuong:
            return "Mật khẩu không được chứa họ tên của bạn"
    return None
