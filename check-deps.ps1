# Stock Analyzer - 依赖检查与修复脚本
# Windows PowerShell
# 运行方式: .\check-deps.ps1

$ErrorActionPreference = "Continue"

function Test-Command($cmd) {
    try {
        $null = Get-Command $cmd -ErrorAction Stop
        return $true
    } catch { return $false }
}

function Get-CommandVersion($cmd, $args = "--version") {
    try {
        $v = & $cmd $args 2>&1
        return ($v | Out-String).Trim().Split("`n")[0]
    } catch { return "未找到" }
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Stock Analyzer - 依赖检查" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$issues = @()
$allOk = $true

# Node.js
Write-Host "Node.js:" -ForegroundColor White
if (Test-Command "node") {
    $v = node --version
    Write-Host "  $v" -ForegroundColor Green
    if ($v -match "^v(\d+)\.") {
        $major = [int]$Matches[1]
        if ($major -lt 18) {
            Write-Host "  [警告] 建议升级到 18.x 或更高" -ForegroundColor Yellow
            $issues += "Node.js 版本过低 ($v < 18)"
        }
    }
} else {
    Write-Host "  [错误] 未找到 Node.js" -ForegroundColor Red
    Write-Host "  下载: https://nodejs.org/" -ForegroundColor Yellow
    $issues += "Node.js 未安装"
    $allOk = $false
}

# npm
Write-Host ""
Write-Host "npm:" -ForegroundColor White
if (Test-Command "npm") {
    $v = npm --version
    Write-Host "  $v" -ForegroundColor Green
} else {
    Write-Host "  [错误] 未找到 npm" -ForegroundColor Red
    $issues += "npm 未安装"
    $allOk = $false
}

# Python
Write-Host ""
Write-Host "Python:" -ForegroundColor White
if (Test-Command "python") {
    $v = python --version 2>&1
    Write-Host "  $v" -ForegroundColor Green
    if ($v -match "(\d+)\.(\d+)") {
        $major = [int]$Matches[1]; $minor = [int]$Matches[2]
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
            Write-Host "  [警告] 建议升级到 Python 3.10+" -ForegroundColor Yellow
        }
    }
    # 检查pip
    if (Test-Command "pip") {
        Write-Host "  pip: 可用" -ForegroundColor Green
    } else {
        Write-Host "  [警告] pip 未找到" -ForegroundColor Yellow
    }
} else {
    Write-Host "  [错误] 未找到 Python" -ForegroundColor Red
    Write-Host "  下载: https://www.python.org/downloads/" -ForegroundColor Yellow
    $issues += "Python 未安装"
    $allOk = $false
}

# Rust
Write-Host ""
Write-Host "Rust:" -ForegroundColor White
if (Test-Command "rustc") {
    $v = rustc --version
    Write-Host "  $v" -ForegroundColor Green
} else {
    Write-Host "  [错误] 未找到 Rust" -ForegroundColor Red
    Write-Host "  安装: https://rustup.rs/" -ForegroundColor Yellow
    $issues += "Rust 未安装"
    $allOk = $false
}

# Visual Studio Build Tools (for Rust)
Write-Host ""
Write-Host "Visual Studio Build Tools (C++编译):" -ForegroundColor White
$vsPath = "C:\Program Files\Microsoft Visual Studio\2022\BuildTools"
$vsPath2 = "C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools"
if ((Test-Path $vsPath) -or (Test-Path $vsPath2)) {
    Write-Host "  已安装" -ForegroundColor Green
} else {
    # 检查是否有cl.exe
    if (Test-Command "cl") {
        Write-Host "  MSVC编译器: 可用" -ForegroundColor Green
    } else {
        Write-Host "  [警告] 未安装Build Tools，Rust编译可能失败" -ForegroundColor Yellow
        Write-Host "  下载: https://visualstudio.microsoft.com/visual-cpp-build-tools/" -ForegroundColor Yellow
        $issues += "Visual Studio Build Tools 未安装"
    }
}

# Python包检查
Write-Host ""
Write-Host "Python包 (backend/requirements.txt):" -ForegroundColor White
$missing = @()
$required = @("akshare", "baostock", "fastapi", "sqlalchemy", "pandas", "numpy", "httpx", "uvicorn")
foreach ($pkg in $required) {
    $installed = pip show $pkg 2>&1
    if ($installed -match "WARNING") {
        $missing += $pkg
        Write-Host "  [缺失] $pkg" -ForegroundColor Red
    } else {
        Write-Host "  [OK] $pkg" -ForegroundColor Green
    }
}

if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Host "安装缺失的Python包:" -ForegroundColor Yellow
    Write-Host "  pip install -r backend/requirements.txt" -ForegroundColor White
    $issues += "Python包缺失: $($missing -join ', ')"
}

# 总结
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
if ($allOk -and $missing.Count -eq 0) {
    Write-Host "  所有依赖检查通过!" -ForegroundColor Green
} else {
    Write-Host "  发现 $($issues.Count) 个问题" -ForegroundColor Yellow
    Write-Host ""
    foreach ($issue in $issues) {
        Write-Host "  - $issue" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "下一步:"
if ($issues.Count -gt 0 -or -not $allOk) {
    Write-Host "  1. 安装缺失的依赖" -ForegroundColor White
    Write-Host "  2. pip install -r backend/requirements.txt" -ForegroundColor White
    Write-Host "  3. python backend/db/database.py  # 初始化数据库" -ForegroundColor White
    Write-Host "  4. npm install && npm run tauri dev  # 开发模式" -ForegroundColor White
} else {
    Write-Host "  1. npm install" -ForegroundColor White
    Write-Host "  2. npm run tauri dev  # 开发模式" -ForegroundColor White
    Write-Host "  3. .\build.ps1  # 打包" -ForegroundColor White
}
Write-Host ""