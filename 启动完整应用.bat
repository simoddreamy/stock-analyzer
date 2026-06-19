@echo off
chcp 65001 >nul
title Stock Analyzer

cd /d "%~dp0"

echo ========================================
echo   Stock Analyzer 一键启动
echo ========================================
echo.

:: 启动后端
echo [1/2] 启动后端服务 (端口 18080)...
start "StockBackend" cmd /k "cd /d \"%~dp0backend\" && python -m uvicorn main:app --host 0.0.0.0 --port 18080"

:: 等待后端就绪
timeout /t 3 /nobreak >nul

:: 启动前端 Tauri
echo [2/2] 启动前端 Tauri 应用...
start "" "%~dp0frontend\src-tauri\target\release\stock_analyzer.exe"

echo.
echo 启动完成！后端窗口不要关闭。
pause