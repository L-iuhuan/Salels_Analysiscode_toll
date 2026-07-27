@echo off
title 2 - 只生成看板（不重跑管道）
color 0B
cd /d "%~dp0"

cls
echo.
echo ====================================================
echo   [2] 只生成看板（用现有 Gold 数据，不重跑管道）
echo ====================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    color 0C
    echo [ERROR] 未找到 Python，请先安装 Python 3.10+ 并加入 PATH
    pause
    exit /b 1
)

if not exist "output\gold\客户全景.csv" (
    color 0E
    echo [!] 警告：output\gold\客户全景.csv 不存在
    echo 这意味着 Gold 数据尚未生成，请先运行选项 1（全量重跑）
    echo.
    set /p continue="仍要继续吗？(y/n): "
    if /i not "%continue%"=="y" exit /b 1
)

set start_time=%TIME%
echo 开始时间: %start_time%
echo.
echo 正在生成看板...
echo.

python dashboard\generate_dashboard.py
if errorlevel 1 (
    color 0C
    echo.
    echo [ERROR] 看板生成失败，错误码 %errorlevel%
    if not "%~1"=="from_menu" pause
    exit /b 1
)

color 0A
echo.
echo ====================================================
echo  [OK] 看板生成完成！
echo  开始: %start_time%
echo  结束: %TIME%
echo  路径: %CD%\dashboard\dashboard_a.html
echo ====================================================
echo.

if not "%~1"=="from_menu" pause
exit /b 0