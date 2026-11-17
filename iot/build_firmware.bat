@echo off
chcp 65001 >nul
REM Biên dịch firmware ESP32 cho Wokwi trong VS Code (arduino-cli).
REM Kết quả: <project>\build\<project>.ino.merged.bin + .elf  — wokwi.toml của mỗi project trỏ tới đây.
REM Chạy lại file này mỗi khi sửa .ino, rồi mở diagram.json trong VS Code và bấm F1 > "Wokwi: Start Simulator".
cd /d "%~dp0"
set URL=https://espressif.github.io/arduino-esp32/package_esp32_index.json
where arduino-cli >nul 2>nul || (echo Chua cai arduino-cli: winget install ArduinoSA.CLI & exit /b 1)
arduino-cli core list | findstr /c:"esp32:esp32" >nul
if errorlevel 1 (
  echo Cai bo bien dich ESP32 lan dau, mat vai phut...
  arduino-cli core update-index --additional-urls %URL% || exit /b 1
  arduino-cli core install esp32:esp32 --additional-urls %URL% || exit /b 1
)
arduino-cli lib install "PubSubClient" "ArduinoJson" "DHT sensor library for ESPx" "Adafruit SSD1306" "Adafruit GFX Library" "Adafruit NeoPixel" "LiquidCrystal I2C" >nul || exit /b 1
for %%P in (wokwi_tram wokwi_bang_dien_tu) do (
  echo.
  echo === Bien dich %%P ===
  arduino-cli compile --fqbn esp32:esp32:esp32 --output-dir "%%P\build" "%%P" || (echo LOI khi bien dich %%P & exit /b 1)
)
echo.
echo Xong. Mo iot\wokwi_tram\diagram.json (hoac wokwi_bang_dien_tu) trong VS Code, F1 ^> Wokwi: Start Simulator
