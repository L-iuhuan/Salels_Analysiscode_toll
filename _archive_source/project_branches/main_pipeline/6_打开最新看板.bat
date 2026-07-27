@echo off
title 6 - 打开最新看板（本地服务器）
cd /d "%~dp0"

set "dash=%~dp0dashboard\dashboard_a.html"

if not exist "%dash%" (
    color 0C
    echo.
    echo [ERROR] 看板文件不存在：
    echo     %dash%
    echo.
    echo 请先运行：
    echo   [1] 1_全量重跑.bat
    echo   或 [2] 2_只生成看板.bat
    echo.
    if not "%~1"=="from_menu" pause
    exit /b 1
)

echo.
echo ============================================================
echo   在本地 HTTP 服务器打开看板（解决 file:// 跨源问题）
echo ============================================================
echo.

REM 定位 python
set "PY="
for /f "delims=" %%i in ('where python 2^>nul') do (
    if not defined PY set "PY=%%i"
)
if not defined PY set "PY=py"

REM 找空闲端口，从 8899 开始
set "PORT=8899"

REM 先关掉之前遗留的同端口进程（可选，忽略错误）
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%p >nul 2>&1
)

echo 启动 HTTP 服务器 http://127.0.0.1:%PORT%/  ...
echo 目录: %~dp0dashboard
echo.

REM 在 dashboard 目录启动服务器（后台窗口）
start "看板本地服务(端口%PORT%)" cmd /k "cd /d ""%~dp0dashboard"" && %PY% -m http.server %PORT% --bind 127.0.0.1"

REM 等 2 秒让服务器起来
timeout /t 2 >nul

echo 打开浏览器...
start "" "http://127.0.0.1:%PORT%/dashboard_a.html"

echo.
echo 提示：
echo   - 关闭"看板本地服务(端口%PORT%)"那个黑窗口即可停止服务
echo   - 如果浏览器打不开，手动访问：http://127.0.0.1:%PORT%/dashboard_a.html
echo.

if not "%~1"=="from_menu" (
    timeout /t 3 >nul
)
exit /b 0
