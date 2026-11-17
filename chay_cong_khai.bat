@echo off
chcp 65001 >nul
REM Đưa AirHCM đang chạy trên máy này ra Internet (HTTPS) bằng Cloudflare Tunnel — miễn phí, không cần tài khoản.
REM Bấm đúp file này. Link có dạng https://<chữ-ngẫu-nhiên>.trycloudflare.com, đổi mỗi lần chạy.
REM Web chỉ truy cập được khi máy tính đang bật và cửa sổ này còn mở. Đóng cửa sổ = tắt link công khai.

set "CF=C:\Program Files (x86)\cloudflared\cloudflared.exe"
if not exist "%CF%" set "CF=C:\Program Files\cloudflared\cloudflared.exe"
if not exist "%CF%" (
  echo Chua co cloudflared. Dang cai bang winget...
  winget install --id Cloudflare.cloudflared -e --accept-source-agreements --accept-package-agreements
  set "CF=C:\Program Files (x86)\cloudflared\cloudflared.exe"
)

REM Máy chủ chưa chạy thì mở nó trong cửa sổ riêng
curl -s -o nul http://127.0.0.1:8000/ || (
  echo Khoi dong may chu AirHCM...
  start "AirHCM may chu" cmd /c "%~dp0chay_server.bat"
  timeout /t 15 /nobreak >nul
)

REM Đã tạo đường hầm cố định (tên "airhcm", cấu hình ở %USERPROFILE%\.cloudflared\config.yml) thì dùng tên miền riêng
if exist "%USERPROFILE%\.cloudflared\config.yml" (
  echo.
  echo ================================================================================
  echo  Link cong khai CO DINH:  https://airhcmcity.asia
  echo  Dong cua so nay de tat link.
  echo ================================================================================
  echo.
  "%CF%" tunnel --no-autoupdate run airhcm
  pause
  exit /b
)

echo.
echo ================================================================================
echo  Tim dong co chu  https://....trycloudflare.com  ben duoi: do la link cong khai.
echo  Gui link do cho dien thoai (4G) / giang vien. Dong cua so nay de tat link.
echo ================================================================================
echo.
"%CF%" tunnel --no-autoupdate --url http://127.0.0.1:8000
pause
