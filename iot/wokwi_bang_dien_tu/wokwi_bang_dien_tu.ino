/*
  AirHCM – Bảng điện tử công bố AQI (MÔ PHỎNG trên Wokwi, ESP32)

  Nhận bản tin AQI do backend AirHCM phát qua MQTT (retained, 30 giây/lần và ngay khi trạm IoT vượt ngưỡng):
    airhcm/<DU_AN>/bang/aqi  →  {"t":"09:48","tp":{"aqi":49,"muc_i":0,...},"iot":{"ma":"IOT01","aqi":180,"muc_i":3,...}}

  Phần cứng ảo:
    - LCD 20x4 I2C (0x27, SDA21/SCL22): AQI toàn TP.HCM (CSDL) + AQI trạm IoT thời gian thực
    - 6 LED màu theo 6 mức QĐ 1459 (Tốt → Nguy hại) cho trạm IoT: GPIO 13, 12, 14, 27, 26, 25
    - Còi (GPIO33): kêu khi trạm IoT chuyển lên mức Kém trở lên; nút (GPIO32) tắt/bật tiếng
  QĐ 1459 có nêu bảng điện tử là một kênh công bố AQI; thiết bị này mô phỏng kênh đó.
*/
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASS = "";
const char* MQTT_HOST = "broker.hivemq.com";
const int   MQTT_PORT = 1883;
const char* DU_AN     = "dhtnmt-1250080037";   // trùng MQTT_DU_AN của backend

const int LED_MUC[6] = {13, 12, 14, 27, 26, 25};
const int PIN_COI = 33, PIN_NUT = 32;
const char* TEN_MUC[] = {"Tot", "Trung binh", "Kem", "Xau", "Rat xau", "Nguy hai"};

WiFiClient wifi;
PubSubClient mqtt(wifi);
LiquidCrystal_I2C lcd(0x27, 20, 4);
char topic[80];
int mucIotTruoc = -1;
bool tatTieng = false;
unsigned long lanNhan = 0, lanThuMqtt = 0;

void dongLcd(int hang, const String& s) {
  String t = s;
  while (t.length() < 20) t += ' ';
  lcd.setCursor(0, hang);
  lcd.print(t.substring(0, 20));
}

void keu(int lan) {
  if (tatTieng) return;
  for (int i = 0; i < lan; i++) { tone(PIN_COI, 1800, 150); delay(250); }
}

void hienLed(int muc) {
  for (int i = 0; i < 6; i++) digitalWrite(LED_MUC[i], i == muc ? HIGH : LOW);
}

void khiNhan(char* t, byte* payload, unsigned int len) {
  JsonDocument d;
  if (deserializeJson(d, payload, len)) return;
  lanNhan = millis();
  JsonObject tp = d["tp"], iot = d["iot"];
  dongLcd(0, String("AirHCM - AQI ") + (const char*)(d["t"] | "--:--"));
  if (!tp.isNull()) {
    int m = tp["muc_i"] | 0;
    dongLcd(1, String("TP.HCM ") + (int)(tp["aqi"] | 0) + " " + TEN_MUC[constrain(m, 0, 5)]);
  } else dongLcd(1, "TP.HCM: chua co");
  if (!iot.isNull()) {
    int m = constrain((int)(iot["muc_i"] | 0), 0, 5);
    dongLcd(2, String((const char*)(iot["ma"] | "IoT")) + " " + (int)(iot["aqi"] | 0) + " " + TEN_MUC[m]);
    dongLcd(3, String("Cap nhat ") + (int)(iot["tuoi_giay"] | 0) + "s truoc" + (tatTieng ? " [MUTE]" : ""));
    hienLed(m);
    if (m >= 2 && m > mucIotTruoc && mucIotTruoc >= 0) keu(3);   // lên mức Kém trở lên: kêu 3 tiếng
    mucIotTruoc = m;
  } else {
    dongLcd(2, "Tram IoT: offline");
    dongLcd(3, "");
    hienLed(-1);
  }
}

void giuKetNoiMqtt() {
  if (mqtt.connected() || millis() - lanThuMqtt < 3000) return;
  lanThuMqtt = millis();
  String id = String("airhcm-bang-") + String((uint32_t)esp_random(), HEX);
  if (mqtt.connect(id.c_str())) { mqtt.subscribe(topic, 1); Serial.println("MQTT OK, nghe " + String(topic)); }
}

void setup() {
  Serial.begin(115200);
  for (int i = 0; i < 6; i++) pinMode(LED_MUC[i], OUTPUT);
  pinMode(PIN_NUT, INPUT_PULLUP);
  lcd.init(); lcd.backlight();
  dongLcd(0, "AirHCM - Bang AQI");
  dongLcd(1, "Dang ket noi WiFi...");
  snprintf(topic, sizeof(topic), "airhcm/%s/bang/aqi", DU_AN);
  WiFi.begin(WIFI_SSID, WIFI_PASS, 6);
  while (WiFi.status() != WL_CONNECTED) delay(250);
  dongLcd(1, "Cho ban tin AQI...");
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(1024);
  mqtt.setCallback(khiNhan);
}

void loop() {
  giuKetNoiMqtt();
  mqtt.loop();
  if (digitalRead(PIN_NUT) == LOW) {            // nút tắt/bật tiếng
    tatTieng = !tatTieng;
    dongLcd(3, tatTieng ? "Da tat tieng" : "Da bat tieng");
    delay(400);
  }
  if (lanNhan && millis() - lanNhan > 90000) {   // quá 90 giây không có bản tin
    dongLcd(0, "AirHCM - MAT KET NOI");
    lanNhan = 0;
  }
}
