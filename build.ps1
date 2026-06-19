$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FrontendDir = Join-Path $ProjectRoot "frontend"
$BackendDir = Join-Path $ProjectRoot "backend"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Stock Analyzer Build Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Check environment
Write-Host "" -ForegroundColor Cyan
Write-Host "[1/4] Checking environment..." -ForegroundColor Yellow

$checks = @(
    @{Name="Node.js"; Cmd="node"},
    @{Name="npm"; Cmd="npm"},
    @{Name="Python"; Cmd="python"},
    @{Name="Rust"; Cmd="C:\Users\Administrator\.cargo\bin\rustc.exe"},
    @{Name="Cargo"; Cmd="C:\Users\Administrator\.cargo\bin\cargo.exe"}
)

foreach ($c in $checks) {
    $exists = Get-Command $c.Cmd -ErrorAction SilentlyContinue
    if ($exists) {
        $v = & $c.Cmd --version 2>&1 | Select-Object -First 1
        Write-Host "  [OK] $($c.Name): $v" -ForegroundColor Green
    } else {
        Write-Host "  [MISSING] $($c.Name)" -ForegroundColor Red
    }
}

# Install frontend deps
Write-Host "" -ForegroundColor Cyan
Write-Host "[2/4] Installing frontend dependencies..." -ForegroundColor Yellow
Push-Location $FrontendDir
npm install
if ($LASTEXITCODE -ne 0) {
    Write-Host "  npm install failed" -ForegroundColor Red
    Pop-Location
    exit 1
}
Pop-Location

# Build Vue3 frontend
Write-Host "" -ForegroundColor Cyan
Write-Host "[3/4] Building Vue3 frontend..." -ForegroundColor Yellow
Push-Location $FrontendDir
npm run build
if ($LASTEXITCODE -ne 0) {
    Write-Host "  npm run build failed" -ForegroundColor Red
    Pop-Location
    exit 1
}
Pop-Location

# Build Tauri app
Write-Host "" -ForegroundColor Cyan
Write-Host "[4/4] Building Tauri application..." -ForegroundColor Yellow
Push-Location $FrontendDir
$env:Path = $env:Path + ";C:\Users\Administrator\.cargo\bin"
npm run tauri build 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  tauri build failed" -ForegroundColor Red
    Pop-Location
    exit 1
}
Pop-Location

# Find output
Write-Host "" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Build complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan

$nsisDir = Join-Path $FrontendDir "src-tauri\target\release\bundle\nsis"
if (Test-Path $nsisDir) {
    Write-Host "" -ForegroundColor White
    Write-Host "Windows installer:" -ForegroundColor White
    Get-ChildItem $nsisDir -Filter "*.exe" | ForEach-Object {
        $mb = [math]::Round($_.Length / 1MB, 1)
        Write-Host "  $($_.Name) ($mb MB)" -ForegroundColor White
    }
}

$exeFile = Join-Path $FrontendDir "src-tauri\target\release\StockAnalyzer.exe"
if (Test-Path $exeFile) {
    $mb = [math]::Round((Get-Item $exeFile).Length / 1MB, 1)
    Write-Host "" -ForegroundColor White
    Write-Host "Main executable:" -ForegroundColor White
    Write-Host "  $exeFile ($mb MB)" -ForegroundColor White
}

Write-Host ""