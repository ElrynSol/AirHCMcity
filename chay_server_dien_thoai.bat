@echo off
chcp 65001 >nul
REM Chạy backend cho điện thoại thật / máy ảo cùng Wi-Fi truy cập (nghe trên mọi địa chỉ mạng, cổng 8000).
REM Lần đầu: cho phép cổng 8000 qua tường lửa (mở CMD bằng quyền Administrator, chạy 1 lần):
REM   netsh advfirewall firewall add rule name="AirHCM 8000" dir=in action=allow protocol=TCP localport=8000 profile=private
cd /d "%~dp0backend"
echo.
echo  Nhap mot trong cac dia chi sau vao app AirHCM tren dien thoai (cung Wi-Fi):
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do for /f "tokens=*" %%b in ("%%a") do echo     http://%%b:8000
echo  (May ao Android tu dung http://10.0.2.2:8000)
echo.
"..\venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000
