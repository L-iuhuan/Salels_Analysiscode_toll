@echo off
title 5 - 更新产品生命周期看板 (C 面)
color 0B
cd /d "%~dp0"

cls
echo.
echo ====================================================
echo   [5] 更新产品生命周期看板 (generate_v4.py)
echo ====================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    color 0C
    echo [ERROR] 未找到 Python
    pause
    exit /b 1
)

REM 找最新的产品生命周期 Excel
set "latest_xlsx="
for /f "delims=" %%f in ('dir /b /od /a-d "output\report\产品生命周期报告_v4.0_*.xlsx" 2^>nul') do (
    set "latest_xlsx=output\report\%%f"
)

if not defined latest_xlsx (
    color 0E
    echo [!] 未找到 output\report\产品生命周期报告_v4.0_*.xlsx
    echo 请先运行选项 4 生成产品分析 Excel
    echo.
    if not "%~1"=="from_menu" pause
    exit /b 1
)

echo 使用源文件: %latest_xlsx%
echo.

set start_time=%TIME%

python generate_v4.py "%latest_xlsx%" -o dashboard\product_lifecycle.html
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
echo  [OK] C 面产品生命周期看板已更新
echo  开始: %start_time%   结束: %TIME%
echo  产物: dashboard\product_lifecycle.html
echo ====================================================
echo.
echo 提示：需重跑 2_只生成看板.bat 让 dashboard_a.html 嵌入新内容

if not "%~1"=="from_menu" pause
exit /b 0