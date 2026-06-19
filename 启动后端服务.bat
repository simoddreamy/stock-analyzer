@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

title Stock Analyzer Backend

echo ==========================================
echo  Stock Analyzer 后端服务
echo ==========================================
echo.

cd /d "%~dp0"
cd /d "%~dp0backend"

:: 检查端口 18080 是否已被占用
netstat -ano | findstr ":18080 " | findstr "LISTENING" >nul
if !errorlevel! == 0 (
    echo [错误] 端口 18080 已被占用，后端可能已在运行！
    echo.
    echo 请检查以下进程是否正在运行：
    netstat -ano | findstr ":18080 "
    echo.
    echo 如果后端已在运行，请直接使用前端，无需重新启动。
    echo.
    pause
    exit /b 1
)

echo [信息] 端口 18080 可用，开始启动后端服务...
echo.

python -m uvicorn main:app --host 0.0.0.0 --port 18080
if !errorlevel! neq 0 (
    echo.
    echo [错误] 后端启动失败，请检查上面的错误信息。
    pause
    exit /b 1
)

pause