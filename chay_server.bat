@echo off
chcp 65001 >nul
REM Chạy máy chủ AirHCM trên Windows: bấm đúp file này, rồi mở http://localhost:8000
REM Điện thoại cùng Wi-Fi truy cập: dùng chay_server_dien_thoai.bat
if not exist "%~dp0venv\Scripts\python.exe" (
  echo Chua cai dat: chuot phai cai_dat.ps1 ^> Run with PowerShell
  pause & exit /b 1
)
cd /d "%~dp0backend"
"%~dp0venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1 --reload
pause
