# Sao lưu cơ sở dữ liệu AirHCM ra NGOÀI thư mục dự án (không bị đồng bộ lên OneDrive / GitHub).
#   Chuột phải tệp này > Run with PowerShell        (hoặc: powershell -ExecutionPolicy Bypass -File sao_luu_csdl.ps1)
#   Tự đặt lịch hằng ngày lúc 02:30:                 powershell -ExecutionPolicy Bypass -File sao_luu_csdl.ps1 -DatLich
# Bản sao lưu: %USERPROFILE%\.airhcm\sao_luu\airhcm_<ngày-giờ>.zip (bên trong là tệp .sql), giữ 14 bản mới nhất.
# Khôi phục: giải nén rồi  psql -U postgres -d air_quality_db -f airhcm_<...>.sql
# Bản sao lưu chứa tài khoản người dùng: KHÔNG gửi qua mạng, không để trong thư mục đồng bộ đám mây.
param([switch]$DatLich)
$ErrorActionPreference = 'Stop'
$goc = $PSScriptRoot
$dich = Join-Path $env:USERPROFILE '.airhcm\sao_luu'
New-Item -ItemType Directory -Force -Path $dich | Out-Null

if ($DatLich) {
    $hd = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`""
    $tg = New-ScheduledTaskTrigger -Daily -At '02:30'
    Register-ScheduledTask -TaskName 'AirHCM_SaoLuuCSDL' -Action $hd -Trigger $tg -Description 'Sao lưu CSDL AirHCM hằng ngày' -Force | Out-Null
    Write-Host "Đã đặt lịch sao lưu hằng ngày 02:30 (Task Scheduler: AirHCM_SaoLuuCSDL)."
    return
}

# Đọc cấu hình CSDL từ .env (không in mật khẩu)
$env_ = @{}
Get-Content (Join-Path $goc '.env') -Encoding UTF8 | Where-Object { $_ -match '^\s*([A-Z_]+)\s*=\s*(.*)$' } | ForEach-Object {
    $env_[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'") }
$pg = Get-ChildItem 'C:\Program Files\PostgreSQL\*\bin\pg_dump.exe' -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
if (-not $pg) { $pg = Get-Command pg_dump -ErrorAction SilentlyContinue }
if (-not $pg) { throw 'Không tìm thấy pg_dump (cài PostgreSQL hoặc thêm thư mục bin vào PATH).' }

$ten = 'airhcm_' + (Get-Date -Format 'yyyyMMdd_HHmm')
$sql = Join-Path $dich "$ten.sql"
$env:PGPASSWORD = $env_['DB_PASS']
try {
    $maychu = if ($env_['DB_HOST']) { $env_['DB_HOST'] } else { 'localhost' }
    $cong = if ($env_['DB_PORT']) { $env_['DB_PORT'] } else { '5432' }
    & $pg.FullName -h $maychu -p $cong -U $env_['DB_USER'] -d $env_['DB_NAME'] --no-owner -f $sql
    if ($LASTEXITCODE -ne 0) { throw "pg_dump lỗi (mã $LASTEXITCODE)" }
} finally { Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue }
Compress-Archive -Path $sql -DestinationPath (Join-Path $dich "$ten.zip") -Force
Remove-Item $sql
Get-ChildItem $dich -Filter 'airhcm_*.zip' | Sort-Object Name -Descending | Select-Object -Skip 14 | Remove-Item
$f = Get-Item (Join-Path $dich "$ten.zip")
Write-Host ("Đã sao lưu: {0} ({1:N1} MB). Đang giữ {2} bản trong {3}" -f $f.Name, ($f.Length / 1MB), (Get-ChildItem $dich -Filter 'airhcm_*.zip').Count, $dich)
