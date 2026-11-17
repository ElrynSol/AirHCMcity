# Cài/sửa lịch đồng bộ dữ liệu tự động trong Windows Task Scheduler (chạy lại nhiều lần không sao).
#   Chuột phải file này > Run with PowerShell   (không cần quyền Administrator)
# - Tác vụ "AQI_DongBoHangNgay": 7:30 mỗi ngày; máy tắt/ngủ lúc đó thì chạy ngay khi bật lại; cần có mạng;
#   chạy bằng pythonw (không bật cửa sổ đen), thư mục làm việc = thư mục dự án.
# - Tắt (không xóa) tác vụ cũ "Dong bo du lieu chat luong khong khi" gọi chay_dong_bo.bat (trùng lặp).
# Gỡ: Unregister-ScheduledTask -TaskName AQI_DongBoHangNgay

$ErrorActionPreference = 'Stop'
$Goc = Split-Path -Parent $MyInvocation.MyCommand.Path
$Pythonw = Join-Path $Goc 'venv\Scripts\pythonw.exe'
$Script = Join-Path $Goc 'data_pipeline\dong_bo_hang_ngay.py'
if (-not (Test-Path $Pythonw)) { throw "Không thấy $Pythonw - hãy tạo venv trước (python -m venv venv; pip install -r requirements.txt)" }
if (-not (Test-Path $Script)) { throw "Không thấy $Script" }

$TenTacVu = 'AQI_DongBoHangNgay'
$HanhDong = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$Script`" --nguon lich_windows" -WorkingDirectory $Goc
$KichHoat = New-ScheduledTaskTrigger -Daily -At '07:30'
$CaiDat = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable -AllowStartIfOnBatteries `
          -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
$MoTa = 'AirHCM: tải dữ liệu Open-Meteo + Sentinel-5P, tự lấy bù ngày thiếu (data_pipeline\dong_bo_hang_ngay.py). Lịch sử xem ở trang Trạng thái dữ liệu.'

if (Get-ScheduledTask -TaskName $TenTacVu -ErrorAction SilentlyContinue) {
    Set-ScheduledTask -TaskName $TenTacVu -Action $HanhDong -Trigger $KichHoat -Settings $CaiDat | Out-Null
    Write-Host "Đã cập nhật tác vụ $TenTacVu"
} else {
    Register-ScheduledTask -TaskName $TenTacVu -Action $HanhDong -Trigger $KichHoat -Settings $CaiDat -Description $MoTa | Out-Null
    Write-Host "Đã tạo tác vụ $TenTacVu"
}

$Cu = Get-ScheduledTask -TaskName 'Dong bo du lieu chat luong khong khi' -ErrorAction SilentlyContinue
if ($Cu -and $Cu.State -ne 'Disabled') {
    try {
        Disable-ScheduledTask -TaskName 'Dong bo du lieu chat luong khong khi' -ErrorAction Stop | Out-Null
        Write-Host "Đã tắt tác vụ cũ 'Dong bo du lieu chat luong khong khi' (trùng lặp)"
    } catch {
        # Tác vụ cũ tạo bằng quyền Administrator: không tắt được thì để nó gọi chay_dong_bo.bat (đã sửa đúng đường dẫn),
        # thành lần chạy bù buổi chiều; khóa tệp trong script đảm bảo không chạy chồng.
        Write-Host "Tác vụ cũ 'Dong bo du lieu chat luong khong khi' cần quyền Administrator để tắt; vẫn giữ (gọi chay_dong_bo.bat đã sửa = lần bù buổi chiều)."
    }
}

$T = Get-ScheduledTask -TaskName $TenTacVu
$I = Get-ScheduledTaskInfo -TaskName $TenTacVu
Write-Host ("Lệnh     : {0} {1}" -f $T.Actions[0].Execute, $T.Actions[0].Arguments)
Write-Host ("Thư mục  : {0}" -f $T.Actions[0].WorkingDirectory)
Write-Host ("Lần chạy kế: {0}" -f $I.NextRunTime)
