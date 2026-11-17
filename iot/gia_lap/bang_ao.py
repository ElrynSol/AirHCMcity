"""Bảng điện tử ảo bằng Python — nhận đúng bản tin AQI mà backend phát cho ESP32 bảng điện tử (kiểm thử chiều hệ thống → thiết bị).

    venv\\Scripts\\python.exe iot\\gia_lap\\bang_ao.py
"""
import argparse
import json
import random

import paho.mqtt.client as mqtt

ap = argparse.ArgumentParser()
ap.add_argument("--broker", default="broker.hivemq.com")
ap.add_argument("--du-an", default="dhtnmt-1250080037")
a = ap.parse_args()
topic = f"airhcm/{a.du_an}/bang/aqi"


def khi_nhan(_c, _u, msg):
    d = json.loads(msg.payload)
    tp, iot = d.get("tp") or {}, d.get("iot") or {}
    print(f"[{d.get('t')}] TP.HCM AQI {tp.get('aqi', '--')} ({tp.get('muc', '--')}) | "
          f"IoT {iot.get('ma', '--')} AQI {iot.get('aqi', '--')} ({iot.get('muc', '--')})")


c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"airhcm-bang-ao-{random.randint(0, 99999)}")
c.on_connect = lambda cl, *_: cl.subscribe(topic, qos=1)
c.on_message = khi_nhan
c.connect(a.broker, 1883, 30)
print("Nghe", topic, "(Ctrl+C để dừng)")
c.loop_forever()
