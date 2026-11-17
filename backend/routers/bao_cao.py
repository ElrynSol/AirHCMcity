"""Xuất báo cáo Excel và PDF (phía máy chủ)."""

from core import config  # noqa: F401  (nạp .env, đường dẫn dự án và ml/ vào sys.path trước)
from database import get_db
from fastapi import Depends
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment
from openpyxl.styles import Font
from openpyxl.styles import PatternFill
from sqlalchemy import text
from sqlalchemy.orm import Session
import io
import models
from fastapi import APIRouter

# core/config.py đã thêm ml/ vào sys.path nên import trực tiếp, không cần sys.path.append.
from tinh_aqi import tinh_aqi_tong_hop, phan_loai_aqi

router = APIRouter()

HEADERS = ['Ngày', 'PM2.5 (µg/m³)', 'PM10 (µg/m³)', 'O3 (µg/m³)', 'NO2 (mol/m²)',
           'CO (mol/m²)', 'SO2 (mol/m²)', 'Nhiệt độ (°C)', 'Độ ẩm (%)', 'AQI', 'Mức độ']


def _lay_du_lieu(tram_id: int, so_ngay: int, db: Session):
    """Truy vấn và gộp dữ liệu 1 trạm theo ngày. Dùng chung cho cả Excel lẫn PDF.
    Trả về (tram, danh_sach_dong) với mỗi dòng là list theo đúng thứ tự HEADERS."""
    tram = db.query(models.TramQuanTrac).filter(models.TramQuanTrac.id == tram_id).first()
    if not tram:
        raise HTTPException(status_code=404, detail="Không tìm thấy trạm")

    ve_tinh = db.execute(text("""
        SELECT ngay_do, no2_mean, co_mean, so2_mean
        FROM du_lieu_gee_tphcm WHERE tram_id = :tram_id
        ORDER BY ngay_do DESC LIMIT :n
    """), {"tram_id": tram_id, "n": so_ngay}).fetchall()

    mat_dat = db.execute(text("""
        SELECT ngay_do,
               COALESCE(pm25_smoothed, pm25_mean) AS pm25_mean,
               COALESCE(pm10_smoothed, pm10_mean) AS pm10_mean,
               COALESCE(o3_smoothed, o3_mean) AS o3_mean,
               nhiet_do_mean, do_am_mean
        FROM du_lieu_tram_mat_dat WHERE tram_id = :tram_id
        ORDER BY ngay_do DESC LIMIT :n
    """), {"tram_id": tram_id, "n": so_ngay}).fetchall()

    mat_dat_dict = {str(r.ngay_do): r for r in mat_dat}
    ve_tinh_dict = {str(r.ngay_do): r for r in ve_tinh}
    tat_ca_ngay = sorted(set(list(mat_dat_dict.keys()) + list(ve_tinh_dict.keys())), reverse=True)

    dong = []
    for ngay in tat_ca_ngay:
        md = mat_dat_dict.get(ngay)
        vt = ve_tinh_dict.get(ngay)
        pm25 = md.pm25_mean if md else None
        pm10 = md.pm10_mean if md else None
        aqi, _ = tinh_aqi_tong_hop(pm25=pm25, pm10=pm10)
        muc_do = phan_loai_aqi(aqi) if aqi else "--"
        dong.append([
            ngay, pm25, pm10,
            md.o3_mean if md else None,
            vt.no2_mean if vt else None,
            vt.co_mean if vt else None,
            vt.so2_mean if vt else None,
            md.nhiet_do_mean if md else None,
            md.do_am_mean if md else None,
            aqi, muc_do,
        ])
    return tram, dong


@router.get("/api/v1/xuat-bao-cao-excel")
def xuat_bao_cao_excel(tram_id: int, so_ngay: int = 30, db: Session = Depends(get_db)):
    """Xuất báo cáo Excel đầy đủ cho 1 trạm."""
    tram, dong = _lay_du_lieu(tram_id, so_ngay, db)

    wb = Workbook()
    ws = wb.active
    ws.title = "Báo cáo quan trắc"

    ws.merge_cells('A1:K1')
    ws['A1'] = f"BÁO CÁO DỮ LIỆU QUAN TRẮC CHẤT LƯỢNG KHÔNG KHÍ - TRẠM {tram.ma_tram}"
    ws['A1'].font = Font(bold=True, size=14)
    ws['A1'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A2:K2')
    ws['A2'] = f"{tram.ten_tram} | Khoảng thời gian: {so_ngay} ngày gần nhất"
    ws['A2'].alignment = Alignment(horizontal='center')

    for col, h in enumerate(HEADERS, 1):
        cell = ws.cell(row=4, column=col, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1A73E8", end_color="1A73E8", fill_type="solid")
        cell.alignment = Alignment(horizontal='center')

    row_idx = 5
    for r in dong:
        for col, val in enumerate(r, 1):
            ws.cell(row=row_idx, column=col, value=val)
        row_idx += 1

    for col in range(1, 12):
        ws.column_dimensions[chr(64 + col)].width = 15

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    filename = f"baocao_{tram.ma_tram}_{so_ngay}ngay.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ---------- PDF phía máy chủ (reportlab) ----------
_FONT_DANG_KY = None


def _dang_ky_font():
    """Đăng ký một font Unicode để hiển thị tiếng Việt trong PDF.
    Thử lần lượt: Arial (Windows) -> DejaVuSans (Linux) -> trả 'Helvetica' nếu không có (mất dấu)."""
    global _FONT_DANG_KY
    if _FONT_DANG_KY:
        return _FONT_DANG_KY
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os
    ung_vien = [
        ("AppFont", r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
        ("AppFont", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("AppFont", r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"),
    ]
    for ten, thuong, dam in ung_vien:
        if os.path.exists(thuong):
            try:
                pdfmetrics.registerFont(TTFont(ten, thuong))
                if os.path.exists(dam):
                    pdfmetrics.registerFont(TTFont(ten + "-Bold", dam))
                else:
                    pdfmetrics.registerFont(TTFont(ten + "-Bold", thuong))
                _FONT_DANG_KY = ten
                return ten
            except Exception:
                continue
    _FONT_DANG_KY = "Helvetica"  # dự phòng: chạy được nhưng có thể mất dấu tiếng Việt
    return _FONT_DANG_KY


@router.get("/api/v1/xuat-bao-cao-pdf")
def xuat_bao_cao_pdf(tram_id: int, so_ngay: int = 30, db: Session = Depends(get_db)):
    """Xuất báo cáo PDF do máy chủ sinh trực tiếp (không phụ thuộc chức năng in trình duyệt)."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    except ImportError:
        raise HTTPException(status_code=500,
                            detail="Chưa cài thư viện reportlab. Chạy: pip install reportlab")

    tram, dong = _lay_du_lieu(tram_id, so_ngay, db)
    font = _dang_ky_font()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"Bao cao {tram.ma_tram}")
    ss = getSampleStyleSheet()
    kieu_tieu_de = ParagraphStyle('tieu_de', parent=ss['Title'], fontName=font + "-Bold", fontSize=15)
    kieu_phu = ParagraphStyle('phu', parent=ss['Normal'], fontName=font, fontSize=10, textColor=colors.HexColor('#444444'))
    kieu_ghi_chu = ParagraphStyle('ghi_chu', parent=ss['Normal'], fontName=font, fontSize=8, textColor=colors.HexColor('#777777'))
    kieu_th = ParagraphStyle('th', parent=ss['Normal'], fontName=font + "-Bold", fontSize=7.5,
                             textColor=colors.white, alignment=1, leading=9)

    els = []
    els.append(Paragraph(f"BÁO CÁO DỮ LIỆU QUAN TRẮC CHẤT LƯỢNG KHÔNG KHÍ — TRẠM {tram.ma_tram}", kieu_tieu_de))
    els.append(Paragraph(f"{tram.ten_tram} &nbsp;|&nbsp; {so_ngay} ngày gần nhất", kieu_phu))
    els.append(Spacer(1, 6 * mm))

    def fmt(v):
        if v is None:
            return ""
        if isinstance(v, float):
            return f"{v:.2f}"
        return str(v)

    hang_tieu_de = [Paragraph(h, kieu_th) for h in HEADERS]  # Paragraph để tiêu đề cột tự xuống dòng
    data = [hang_tieu_de] + [[fmt(x) for x in r] for r in dong]
    col_w = [22 * mm, 20 * mm, 20 * mm, 18 * mm, 22 * mm, 20 * mm, 22 * mm, 18 * mm, 16 * mm, 14 * mm, 22 * mm]
    bang = Table(data, colWidths=col_w, repeatRows=1)
    bang.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font),
        ('FONTNAME', (0, 0), (-1, 0), font + "-Bold"),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1A73E8')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#CCCCCC')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F3F6FB')]),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    els.append(bang)
    els.append(Spacer(1, 6 * mm))
    els.append(Paragraph(
        "Ghi chú: PM2.5, PM10, O3 là sản phẩm mô hình CAMS (Open-Meteo, độ phân giải ~45 km), không phải số đo trực tiếp tại trạm; "
        "NO2, CO, SO2 là tổng cột khí quyển từ vệ tinh Sentinel-5P (mol/m²). Số liệu mang tính tham khảo học thuật.", kieu_ghi_chu))

    doc.build(els)
    buffer.seek(0)
    filename = f"baocao_{tram.ma_tram}_{so_ngay}ngay.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
