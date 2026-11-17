# Cài AirHCM trên Windows (chạy được nhiều lần): chuột phải file này > Run with PowerShell
#   hoặc:  powershell -ExecutionPolicy Bypass -File cai_dat.ps1 [-Dev]
# Việc làm: tìm Python 3.11+ → tạo/sửa venv (tự tạo lại nếu venv hỏng do chuyển thư mục) → cài thư viện
#           → tạo .env với khóa ngẫu nhiên → tạo CSDL + PostGIS → kiểm tra toàn bộ môi trường.
# Cần cài trước: Python 3.12 (python.org) và PostgreSQL 17 + PostGIS (Stack Builder). Không muốn cài: dùng Docker (README).
param([switch]$Dev)
$ErrorActionPreference = 'Stop'
$Goc = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Goc
[Console]::OutputEncoding = [Text.Encoding]::UTF8
function Buoc($m) { Write-Host "`n== $m" -ForegroundColor Cyan }

# 1. Python
Buoc 'Tìm Python 3.11+'
$py = $null; $pyArg = @()
foreach ($ung in 'py -3.12', 'py -3.13', 'py -3.11', 'python', 'python3') {
  $p = $ung.Split(' ')
  $a = @($p | Select-Object -Skip 1)
  try {
    $v = & $p[0] @a -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    if ($LASTEXITCODE -eq 0 -and $v -and [version]$v -ge [version]'3.11') { $py = $p[0]; $pyArg = $a; break }
  } catch {}
}
if (-not $py) { throw 'Không tìm thấy Python 3.11+. Cài Python 3.12 từ https://www.python.org/downloads/ (tích "Add python.exe to PATH").' }
Write-Host "Dùng: $py $($pyArg -join ' ') (Python $v)"

# 2. venv (venv Windows ghi cứng đường dẫn: chuyển thư mục dự án là hỏng pip.exe/uvicorn.exe → tạo lại)
Buoc 'Môi trường ảo venv'
$vpy = Join-Path $Goc 'venv\Scripts\python.exe'
$hong = $false
if (Test-Path $vpy) {
  $cfg = Get-Content (Join-Path $Goc 'venv\pyvenv.cfg') -ErrorAction SilentlyContinue | Out-String
  $tao = ($cfg -split "`n" | Where-Object { $_ -match '^command' }) -join ''
  try { & $vpy -c "import sys" 2>$null; if ($LASTEXITCODE -ne 0) { $hong = $true } } catch { $hong = $true }
  if ($tao -and $tao -notmatch [regex]::Escape((Join-Path $Goc 'venv'))) { Write-Host 'venv được tạo ở thư mục khác (đã chuyển dự án) → tạo lại'; $hong = $true }
}
if ($hong) { Remove-Item -Recurse -Force (Join-Path $Goc 'venv') }
if (-not (Test-Path $vpy)) { & $py @pyArg -m venv venv; Write-Host 'Đã tạo venv' } else { Write-Host 'venv còn tốt' }

# 3. Thư viện
Buoc 'Cài thư viện (lần đầu vài phút)'
& $vpy -m pip install --upgrade pip --quiet
$req = if ($Dev) { 'requirements-dev.txt' } else { 'requirements.txt' }
& $vpy -m pip install -r $req --quiet
if ($LASTEXITCODE -ne 0) { throw 'Cài thư viện thất bại (xem lỗi ở trên)' }

# 4. .env
Buoc 'Tệp cấu hình .env'
$env_ = Join-Path $Goc '.env'
if (-not (Test-Path $env_)) {
  Copy-Item (Join-Path $Goc '.env.example') $env_
  $jwt = & $vpy -c "import secrets; print(secrets.token_urlsafe(48))"
  $mk = Read-Host 'Mật khẩu tài khoản postgres của PostgreSQL trên máy này'
  $nd = Get-Content $env_ -Encoding UTF8
  $nd = $nd -replace '^JWT_SECRET_KEY=.*', "JWT_SECRET_KEY=$jwt" -replace '^DB_PASS=.*', "DB_PASS=$mk"
  [IO.File]::WriteAllLines($env_, $nd, (New-Object Text.UTF8Encoding $false))
  Write-Host 'Đã tạo .env (khóa JWT ngẫu nhiên). Mở .env để điền SMTP, GEMINI_API_KEY nếu cần.'
} else { Write-Host 'Giữ .env hiện có' }

# 5. Kiểm tra + tạo CSDL
Buoc 'Kiểm tra môi trường, tạo CSDL + PostGIS nếu thiếu'
& $vpy dong_goi\kiem_tra_moi_truong.py --tao-csdl
$kq = $LASTEXITCODE
Write-Host "`nChạy máy chủ:  chay_server.bat   (rồi mở http://localhost:8000)" -ForegroundColor Green
if ($Host.Name -eq 'ConsoleHost') { Read-Host 'Nhấn Enter để đóng' | Out-Null }
exit $kq
