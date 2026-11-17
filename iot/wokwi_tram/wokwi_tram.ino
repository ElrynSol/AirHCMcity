/*
  AirHCM – Trạm cảm biến chất lượng không khí (MÔ PHỎNG trên Wokwi, ESP32)

  Phần cứng ảo:
    - DHT22 (GPIO15): nhiệt độ, độ ẩm
    - Biến trở 1 (GPIO34): PM2.5  0–300 µg/m³   } Wokwi không có cảm biến bụi,
    - Biến trở 2 (GPIO35): PM10   0–500 µg/m³   } biến trở đóng vai cảm biến PMS5003
    - Công tắc gạt (GPIO27): TỰ ĐỘNG (PM dao động theo "ngày" nén 10 phút) / THỦ CÔNG (theo biến trở)
    - OLED SSD1306 (I2C 21/22): số đo + AQI tại chỗ
    - NeoPixel (GPIO4): màu mức AQI theo QĐ 1459/QĐ-TCMT

  Gửi MQTT mỗi 5 giây tới  airhcm/<DU_AN>/tram/<MA>/do  (JSON). Backend AirHCM nhận, lưu bảng du_lieu_iot
  (cờ mô phỏng), tính AQI trung bình 1 phút và phát cảnh báo khi vượt ngưỡng.
  AQI hiển thị trên OLED là AQI tức thời tính ngay trên thiết bị (edge) bằng cùng bảng ngưỡng với ml/tinh_aqi.py.
*/
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <DHTesp.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_NeoPixel.h>

// ---- Cấu hình (DU_AN, KHOA phải trùng .env của backend: MQTT_DU_AN, IOT_KHOA_THIET_BI) ----
const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASS = "";
const char* MQTT_HOST = "broker.hivemq.com";
const int   MQTT_PORT = 1883;
const char* DU_AN     = "dhtnmt-1250080037";
const char* KHOA      = "airhcm-demo-2026";
const char* MA        = "IOT01";
const char* TEN       = "Trạm IoT Quận 3 (mô phỏng)";
const float VI_DO = 10.7840, KINH_DO = 106.6880;   // không trùng trạm có sẵn trên bản đồ
const unsigned long CHU_KY_GUI = 5000;

const int PIN_DHT = 15, PIN_PM25 = 34, PIN_PM10 = 35, PIN_CHE_DO = 27, PIN_LED = 4;

DHTesp dht;
WiFiClient wifi;
PubSubClient mqtt(wifi);
Adafruit_SSD1306 oled(128, 64, &Wire, -1);
Adafruit_NeoPixel led(1, PIN_LED, NEO_GRB + NEO_KHZ800);

// ---- VN_AQI (QĐ 1459/QĐ-TCMT): bảng nồng độ BP_i và mốc AQI I_i ----
const float BP25[] = {0, 25, 50, 80, 150, 250, 350, 500};
const float BP10[] = {0, 50, 150, 250, 350, 420, 500, 600};
const int   I_AQI[] = {0, 50, 100, 150, 200, 300, 400, 500};
const char* TEN_MUC[] = {"Tot", "Trung binh", "Kem", "Xau", "Rat xau", "Nguy hai"};
const uint32_t MAU_MUC[] = {0x00E400, 0xFFFF00, 0xFF7E00, 0xFF0000, 0x8F3F97, 0x7E0023};

int aqiThanhPhan(float c, const float* bp) {
  if (c < 0) return -1;
  for (int i = 0; i < 7; i++)
    if (c <= bp[i + 1]) return lround((I_AQI[i + 1] - I_AQI[i]) / (bp[i + 1] - bp[i]) * (c - bp[i]) + I_AQI[i]);
  return 500;
}
int mucAqi(int aqi) {
  const int nguong[] = {50, 100, 150, 200, 300};
  for (int i = 0; i < 5; i++) if (aqi <= nguong[i]) return i;
  return 5;
}

float pm25 = 0, pm10 = 0, nhietDo = NAN, doAm = NAN;
int aqi = 0, muc = 0;
bool tuDong = true;
unsigned long lanGui = 0, lanDoc = 0, lanThuMqtt = 0, soGoi = 0;
char topic[96];

void ketNoiWifi() {
  WiFi.begin(WIFI_SSID, WIFI_PASS, 6);
  while (WiFi.status() != WL_CONNECTED) { delay(250); Serial.print("."); }
  Serial.printf("\nWiFi OK, IP %s\n", WiFi.localIP().toString().c_str());
}

void giuKetNoiMqtt() {
  if (mqtt.connected() || millis() - lanThuMqtt < 3000) return;
  lanThuMqtt = millis();
  String id = String("airhcm-") + MA + "-" + String((uint32_t)esp_random(), HEX);
  if (mqtt.connect(id.c_str())) Serial.println("MQTT OK");
  else Serial.printf("MQTT loi %d, thu lai...\n", mqtt.state());
}

void docCamBien() {
  TempAndHumidity th = dht.getTempAndHumidity();
  if (!isnan(th.temperature)) { nhietDo = th.temperature; doAm = th.humidity; }
  tuDong = digitalRead(PIN_CHE_DO) == HIGH;
  if (tuDong) {
    // "Một ngày" nén còn 10 phút: cao điểm giao thông sáng/tối + nhiễu đo
    float pha = (millis() % 600000UL) / 600000.0 * 2 * PI;
    pm25 = 26 + 10 * cos(pha) + 6 * cos(2 * pha) + random(-25, 26) / 10.0;
    pm10 = pm25 * (1.45 + random(0, 20) / 100.0);
  } else {
    pm25 = analogRead(PIN_PM25) / 4095.0 * 300.0;
    pm10 = max(pm25, analogRead(PIN_PM10) / 4095.0f * 500.0f);   // PM10 luôn ≥ PM2.5 (PM2.5 là một phần của PM10)
  }
  pm25 = max(0.0f, pm25);
  aqi = max(aqiThanhPhan(pm25, BP25), aqiThanhPhan(pm10, BP10));
  muc = mucAqi(aqi);
  led.setPixelColor(0, MAU_MUC[muc]);
  led.show();
}

void guiMqtt() {
  if (!mqtt.connected()) return;
  JsonDocument d;
  d["khoa"] = KHOA; d["ten"] = TEN; d["vi_do"] = VI_DO; d["kinh_do"] = KINH_DO;
  d["che_do"] = tuDong ? "tu_dong" : "thu_cong";
  d["pm25"] = round(pm25 * 10) / 10.0; d["pm10"] = round(pm10 * 10) / 10.0;
  if (!isnan(nhietDo)) { d["nhiet_do"] = nhietDo; d["do_am"] = doAm; }
  d["aqi_thiet_bi"] = aqi;
  char buf[384];
  size_t n = serializeJson(d, buf);
  if (mqtt.publish(topic, (const uint8_t*)buf, n)) { soGoi++; Serial.println(buf); }
}

void veOled() {
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);
  oled.setTextSize(1);
  oled.setCursor(0, 0);
  oled.printf("AirHCM %s  %s", MA, tuDong ? "TU DONG" : "THU CONG");
  oled.setCursor(0, 10);
  oled.printf("WiFi %s MQTT %s #%lu", WiFi.status() == WL_CONNECTED ? "OK" : "--", mqtt.connected() ? "OK" : "--", soGoi);
  oled.setCursor(0, 22); oled.printf("PM2.5 %6.1f ug/m3", pm25);
  oled.setCursor(0, 31); oled.printf("PM10  %6.1f ug/m3", pm10);
  oled.setCursor(0, 40);
  if (isnan(nhietDo)) oled.print("DHT22 --");
  else oled.printf("%.1fC  %.0f%%RH", nhietDo, doAm);
  oled.setCursor(0, 52); oled.setTextSize(1);
  oled.printf("AQI %3d %s", aqi, TEN_MUC[muc]);
  oled.display();
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_CHE_DO, INPUT_PULLUP);
  dht.setup(PIN_DHT, DHTesp::DHT22);
  led.begin(); led.setBrightness(80);
  Wire.begin(21, 22);
  oled.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  oled.clearDisplay(); oled.setTextColor(SSD1306_WHITE); oled.setCursor(0, 0);
  oled.print("AirHCM: dang ket noi WiFi..."); oled.display();
  snprintf(topic, sizeof(topic), "airhcm/%s/tram/%s/do", DU_AN, MA);
  ketNoiWifi();
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(512);
  randomSeed(esp_random());
}

void loop() {
  giuKetNoiMqtt();
  mqtt.loop();
  if (millis() - lanDoc >= 1000) { lanDoc = millis(); docCamBien(); veOled(); }
  if (millis() - lanGui >= CHU_KY_GUI) { lanGui = millis(); guiMqtt(); }
}
