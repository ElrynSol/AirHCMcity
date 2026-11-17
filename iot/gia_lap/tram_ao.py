"""Trạm IoT ảo bằng Python — gửi đúng định dạng gói tin của ESP32 trên Wokwi (dùng để kiểm thử / dự phòng khi trình diễn).

Chạy từ thư mục gốc dự án:
    venv\\Scripts\\python.exe iot\\gia_lap\\tram_ao.py                 # tự động: PM2.5 dao động theo giờ trong ngày
    venv\\Scripts\\python.exe iot\\gia_lap\\tram_ao.py --dot-bien 90   # sau 90 giây PM2.5 tăng vọt (trình diễn cảnh báo)
    venv\\Scripts\\python.exe iot\\gia_lap\\tram_ao.py --ma IOT02 --vi-do 10.85 --kinh-do 106.77
"""
import argparse
import json
import math
import random
import time
from datetime import datetime

import paho.mqtt.client as mqtt

ap = argparse.ArgumentParser()
ap.add_argument("--broker", default="broker.hivemq.com")
ap.add_argument("--du-an", default="dhtnmt-1250080037", help="phải trùng MQTT_DU_AN của backend")
ap.add_argument("--khoa", default="airhcm-demo-2026", help="phải trùng IOT_KHOA_THIET_BI của backend")
ap.add_argument("--ma", default="IOT01")
ap.add_argument("--ten", default="Trạm IoT Quận 3 (mô phỏng)")
ap.add_argument("--vi-do", type=float, default=10.7840)
ap.add_argument("--kinh-do", type=float, default=106.6880)
ap.add_argument("--chu-ky", type=float, default=5, help="giây giữa 2 lần gửi")
ap.add_argument("--dot-bien", type=float, default=None, help="sau N giây chuyển sang PM2.5 cao (≈120 µg/m³) trong 3 phút")
a = ap.parse_args()

topic = f"airhcm/{a.du_an}/tram/{a.ma}/do"
c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"airhcm-tram-ao-{a.ma}-{random.randint(0, 99999)}")
c.connect(a.broker, 1883, 30)
c.loop_start()
print(f"Gửi tới {a.broker} · {topic} mỗi {a.chu_ky}s (Ctrl+C để dừng)")

bat_dau = time.time()
while True:
    gio = datetime.now().hour + datetime.now().minute / 60
    nen = 24 + 9 * math.cos((gio - 7) / 24 * 2 * math.pi)          # cao điểm sáng ~7h, thấp buổi chiều
    pm25 = nen + random.gauss(0, 2)
    che_do = "tu_dong"
    t = time.time() - bat_dau
    if a.dot_bien is not None and a.dot_bien <= t < a.dot_bien + 180:
        pm25 = 120 + random.gauss(0, 6)
        che_do = "dot_bien"
    pm25 = max(1.0, pm25)
    goi = {"khoa": a.khoa, "ten": a.ten, "vi_do": a.vi_do, "kinh_do": a.kinh_do, "che_do": che_do,
           "pm25": round(pm25, 1), "pm10": round(pm25 * random.uniform(1.4, 1.7), 1),
           "nhiet_do": round(29 + 3 * math.sin((gio - 9) / 24 * 2 * math.pi) + random.gauss(0, .3), 1),
           "do_am": round(min(100, 72 - 10 * math.sin((gio - 9) / 24 * 2 * math.pi) + random.gauss(0, 1)), 1)}
    c.publish(topic, json.dumps(goi), qos=1)
    print(datetime.now().strftime("%H:%M:%S"), che_do, "PM2.5", goi["pm25"], "PM10", goi["pm10"])
    time.sleep(a.chu_ky)
