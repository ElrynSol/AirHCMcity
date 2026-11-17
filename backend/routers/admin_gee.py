"""Quản trị: chạy xử lý dữ liệu Google Earth Engine nền."""

from core import config  # noqa: F401  (nạp .env và đường dẫn dự án trước)
from datetime import datetime
from fastapi import BackgroundTasks
from fastapi import Depends
from fastapi import HTTPException
import models
import uuid
from fastapi import APIRouter
from core.security import require_admin
from core import logbus

router = APIRouter()


gee_jobs = {}


def _run_gee_job(job_id: str, start_date: str, end_date: str):
    gee_jobs[job_id] = {"status": "running", "message": "Đang truy vấn GEE cho các trạm..."}
    try:
        from download_gee_data import run as run_gee_download
        run_gee_download(start_date, end_date)
        logbus.ghi("INFO", "du_lieu", "gee_hoan_tat", f"GEE {start_date} → {end_date} xong")
        gee_jobs[job_id] = {"status": "completed", "message": "Đã cập nhật dữ liệu GEE. Dự báo theo phường/xã đã dùng dữ liệu mới."}
    except Exception as exc:
        logbus.ghi("ERROR", "du_lieu", "gee_that_bai", f"{type(exc).__name__}: {exc}")
        gee_jobs[job_id] = {"status": "failed", "message": str(exc)}


@router.post("/api/v1/admin/xu-ly-du-lieu-gee")
def start_gee_processing(
    payload: dict,
    background_tasks: BackgroundTasks,
    admin: models.NguoiDung = Depends(require_admin)
):
    try:
        start_date = datetime.strptime(payload.get("tu_ngay", ""), "%Y-%m-%d").date()
        end_date = datetime.strptime(payload.get("den_ngay", ""), "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Ngày phải theo định dạng YYYY-MM-DD")
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="Ngày bắt đầu phải trước hoặc bằng ngày kết thúc")
    if (end_date - start_date).days > 180:
        raise HTTPException(status_code=400, detail="Mỗi lần chỉ xử lý tối đa 180 ngày")
    if any(job.get("status") == "running" for job in gee_jobs.values()):
        raise HTTPException(status_code=409, detail="Đang có một tác vụ GEE chạy")
    job_id = str(uuid.uuid4())
    gee_jobs[job_id] = {"status": "queued", "message": "Đã xếp hàng xử lý dữ liệu GEE"}
    logbus.ghi("INFO", "du_lieu", "gee_bat_dau", f"Chạy GEE {start_date} → {end_date}", nguoi_dung=admin.email)
    background_tasks.add_task(_run_gee_job, job_id, start_date.isoformat(), end_date.isoformat())
    return {"job_id": job_id, **gee_jobs[job_id]}


@router.get("/api/v1/admin/tien-do-gee/{job_id}")
def get_gee_processing_status(job_id: str, admin: models.NguoiDung = Depends(require_admin)):
    job = gee_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ")
    return {"job_id": job_id, **job}
