-- Các bảng số liệu môi trường (không khai báo trong models.py vì do pipeline thu thập ghi vào).
-- Máy chủ chạy tệp này mỗi lần khởi động: CSDL mới được tạo đủ bảng, CSDL đã có thì không thay đổi gì.
-- Cấu trúc trích từ CSDL đang vận hành (pg_dump --schema-only), viết lại dạng IF NOT EXISTS.

ALTER TABLE tram_quan_trac ADD COLUMN IF NOT EXISTS nhom_o_nhiem character varying(50);

CREATE TABLE IF NOT EXISTS du_lieu_tram_mat_dat (
    id serial PRIMARY KEY,
    ngay_do date NOT NULL,
    khu_vuc character varying(255) DEFAULT 'TP.HCM',
    pm25_mean double precision,
    pm10_mean double precision,
    co_mean double precision,
    no2_mean double precision,
    so2_mean double precision,
    o3_mean double precision,
    nguon_du_lieu character varying(50) DEFAULT 'Open-Meteo',
    ngay_cap_nhat timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    nhiet_do_mean double precision,
    do_am_mean double precision,
    gio_toc_do_mean double precision,
    mua_tong double precision,
    tram_id integer REFERENCES tram_quan_trac(id),
    pm25_smoothed double precision,
    pm10_smoothed double precision,
    o3_smoothed double precision,
    CONSTRAINT uq_tram_ngay_tram2 UNIQUE (ngay_do, tram_id)
);
CREATE INDEX IF NOT EXISTS idx_mat_dat_tram_ngay ON du_lieu_tram_mat_dat (tram_id, ngay_do DESC);
CREATE INDEX IF NOT EXISTS idx_ngay_do_tram ON du_lieu_tram_mat_dat (ngay_do);

CREATE TABLE IF NOT EXISTS du_lieu_gee_tphcm (
    id serial PRIMARY KEY,
    ngay_do date NOT NULL,
    khu_vuc character varying(255),
    no2_mean double precision,
    co_mean double precision,
    so2_mean double precision,
    ngay_cap_nhat timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    tram_id integer REFERENCES tram_quan_trac(id),
    CONSTRAINT uq_gee_ngay_tram UNIQUE (ngay_do, tram_id)
);
CREATE INDEX IF NOT EXISTS idx_gee_tram_ngay ON du_lieu_gee_tphcm (tram_id, ngay_do DESC);
CREATE INDEX IF NOT EXISTS idx_ngay_do ON du_lieu_gee_tphcm (ngay_do);

CREATE TABLE IF NOT EXISTS tram_do_that (
    ma integer PRIMARY KEY,
    ten text NOT NULL,
    nha_cung_cap text,
    la_cam_bien_re boolean,
    ma_cam_bien_pm25 integer,
    toado geometry(Point, 4326),
    cap_nhat timestamp with time zone DEFAULT now() NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_tram_do_that_toado ON tram_do_that USING gist (toado);

CREATE TABLE IF NOT EXISTS do_that_gio (
    ma_tram integer NOT NULL REFERENCES tram_do_that(ma) ON DELETE CASCADE,
    gio timestamp without time zone NOT NULL,
    pm25 real NOT NULL,
    PRIMARY KEY (ma_tram, gio)
);

CREATE TABLE IF NOT EXISTS lich_su_dong_bo (
    id serial PRIMARY KEY,
    bat_dau timestamp without time zone DEFAULT now() NOT NULL,
    ket_thuc timestamp without time zone,
    nguon_kich_hoat character varying(30) NOT NULL,
    trang_thai character varying(20) DEFAULT 'dang_chay' NOT NULL,
    openmeteo_tu date,
    openmeteo_den date,
    so_dong_openmeteo integer,
    gee_tu date,
    gee_den date,
    so_dong_gee integer,
    ghi_chu text
);
