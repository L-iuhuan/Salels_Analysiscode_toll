@echo off
title 3 - 只跑客户分析
color 0B
cd /d "%~dp0"

cls
echo.
echo ====================================================
echo   [3] 只跑客户分析 (run_customer.py)
echo ====================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    color 0C
    echo [ERROR] 未找到 Python
    pause
    exit /b 1
)

set start_time=%TIME%
echo 开始时间: %start_time%
echo.

python run_customer.py
if errorlevel 1 (
    color 0C
    echo.
    echo [ERROR] 客户分析失败，错误码 %errorlevel%
    if not "%~1"=="from_menu" pause
    exit /b 1
)

color 0A
echo.
echo ====================================================
echo  [OK] 客户分析完成
echo  开始: %start_time%   结束: %TIME%
echo  产物: output\gold\客户全景.csv 等
echo ====================================================
echo.
echo 提示：如需更新看板，请运行 2_只生成看板.bat

if not "%~1"=="from_menu" pause
exit /b 0