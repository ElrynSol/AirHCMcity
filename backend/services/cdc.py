"""CDC gọn bằng PostgreSQL LISTEN/NOTIFY (thay cho Debezium + Kafka Connect ở quy mô đồ án).

- Trigger trên `tram_quan_trac`  -> thông báo kênh `cdc_tram`  (thêm/sửa/xóa trạm, kể cả sửa trực tiếp bằng pgAdmin/SQL)
- Trigger trên `du_lieu_tram_mat_dat` -> kênh `cdc_du_lieu` (có dữ liệu mới nạp vào)
Luồng nền LISTEN nhận thông báo rồi phát lên bus sự kiện: tram.da_tao / tram.da_sua / tram.da_xoa / du_lieu.da_nap.
"""

from core import config  # noqa: F401
import json
import select
import threading
import time

from sqlalchemy import text
from database import engine
from core import events, logbus

_DDL_TRAM = [
    """
    CREATE OR REPLACE FUNCTION fn_cdc_tram() RETURNS trigger AS $$
    DECLARE r RECORD;
    BEGIN
        IF TG_OP = 'DELETE' THEN r := OLD; ELSE r := NEW; END IF;
        PERFORM pg_notify('cdc_tram', json_build_object('op', TG_OP, 'tram_id', r.id, 'ma_tram', r.ma_tram)::text);
        RETURN NULL;
    END $$ LANGUAGE plpgsql
    """,
]
_TRG_TRAM = ("trg_cdc_tram",
             "CREATE TRIGGER trg_cdc_tram AFTER INSERT OR UPDATE OR DELETE ON tram_quan_trac "
             "FOR EACH ROW EXECUTE PROCEDURE fn_cdc_tram()")

_DDL_DL = """
    CREATE OR REPLACE FUNCTION fn_cdc_du_lieu() RETURNS trigger AS $$
    DECLARE j text;
    BEGIN
        SELECT json_build_object('op', TG_OP, 'so_dong', count(*),
                                 'tram_ids', COALESCE(json_agg(DISTINCT tram_id), '[]'::json))::text
          INTO j FROM nt;
        PERFORM pg_notify('cdc_du_lieu', j);
        RETURN NULL;
    END $$ LANGUAGE plpgsql
"""
_TRG_DL = [
    ("trg_cdc_du_lieu_ins",
     "CREATE TRIGGER trg_cdc_du_lieu_ins AFTER INSERT ON du_lieu_tram_mat_dat "
     "REFERENCING NEW TABLE AS nt FOR EACH STATEMENT EXECUTE PROCEDURE fn_cdc_du_lieu()"),
    ("trg_cdc_du_lieu_upd",
     "CREATE TRIGGER trg_cdc_du_lieu_upd AFTER UPDATE ON du_lieu_tram_mat_dat "
     "REFERENCING NEW TABLE AS nt FOR EACH STATEMENT EXECUTE PROCEDURE fn_cdc_du_lieu()"),
]


def _co_trigger(conn, ten: str) -> bool:
    return conn.execute(text("SELECT 1 FROM pg_trigger WHERE tgname = :n AND NOT tgisinternal"), {"n": ten}).fetchone() is not None


def tao_trigger():
    """Tạo hàm + trigger nếu chưa có (chạy lại nhiều lần vẫn an toàn)."""
    try:
        with engine.begin() as conn:
            for ddl in _DDL_TRAM:
                conn.execute(text(ddl))
            if not _co_trigger(conn, _TRG_TRAM[0]):
                conn.execute(text(_TRG_TRAM[1]))
                logbus.ghi("INFO", "cdc", "tao_trigger", "Đã tạo trigger theo dõi bảng tram_quan_trac")
    except Exception as exc:
        logbus.ghi("WARN", "cdc", "tao_trigger", f"Không tạo được trigger trạm: {exc}")
    try:
        with engine.begin() as conn:
            conn.execute(text(_DDL_DL))
            for ten, ddl in _TRG_DL:
                if not _co_trigger(conn, ten):
                    conn.execute(text(ddl))
                    logbus.ghi("INFO", "cdc", "tao_trigger", f"Đã tạo trigger {ten} theo dõi bảng du_lieu_tram_mat_dat")
    except Exception as exc:
        logbus.ghi("WARN", "cdc", "tao_trigger", f"Không tạo được trigger dữ liệu (sự kiện nạp dữ liệu sẽ chỉ chạy theo lịch 6 giờ): {exc}")


def _chuyen_thanh_su_kien(kenh: str, payload: str):
    try:
        d = json.loads(payload)
    except ValueError:
        return
    if kenh == "cdc_tram":
        chu_de = {"INSERT": "tram.da_tao", "UPDATE": "tram.da_sua", "DELETE": "tram.da_xoa"}.get(d.get("op"))
        if chu_de:
            events.publish(chu_de, d)
    elif kenh == "cdc_du_lieu":
        events.publish("du_lieu.da_nap", d)


dang_nghe = False


def _vong_lang_nghe():
    global dang_nghe
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    dsn = engine.url.set(drivername="postgresql").render_as_string(hide_password=False)
    while True:
        conn = None
        try:
            conn = psycopg2.connect(dsn)
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cur = conn.cursor()
            cur.execute("LISTEN cdc_tram; LISTEN cdc_du_lieu;")
            dang_nghe = True
            logbus.ghi("INFO", "cdc", "bat_dau_nghe", "Đang lắng nghe thay đổi: cdc_tram, cdc_du_lieu")
            while True:
                if select.select([conn], [], [], 30)[0]:
                    conn.poll()
                    while conn.notifies:
                        n = conn.notifies.pop(0)
                        _chuyen_thanh_su_kien(n.channel, n.payload)
        except Exception as exc:
            dang_nghe = False
            logbus.ghi("WARN", "cdc", "mat_ket_noi", f"{type(exc).__name__}: {exc} — thử lại sau 10 giây")
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
            time.sleep(10)


def khoi_dong():
    threading.Thread(target=_vong_lang_nghe, name="cdc-listener", daemon=True).start()
