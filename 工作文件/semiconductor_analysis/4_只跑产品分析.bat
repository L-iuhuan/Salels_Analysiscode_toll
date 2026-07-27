@echo off
title 4 - 只跑产品分析
color 0B
cd /d "%~dp0"

cls
echo.
echo ====================================================
echo   [4] 只跑产品生命周期分析 (run_product.py)
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

python run_product.py
if errorlevel 1 (
    color 0C
    echo.
    echo [ERROR] 产品分析失败，错误码 %errorlevel%
    if not "%~1"=="from_menu" pause
    exit /b 1
)

color 0A
echo.
echo ====================================================
echo  [OK] 产品分析完成
echo  开始: %start_time%   结束: %TIME%
echo  产物: output\report\产品生命周期报告_v4.0_*.xlsx
echo ====================================================
echo.
echo 提示：如需更新 C 面看板，请运行 5_产品生命周期看板.bat

if not "%~1"=="from_menu" pause
exit /b 0