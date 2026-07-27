@echo off
title 1 - 全量重跑（清洗 + 分析 + 看板）
color 0B
cd /d "%~dp0"

cls
echo.
echo ====================================================
echo   [1] 全量重跑：silver - product - customer - 看板
echo ====================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    color 0C
    echo [ERROR] 未找到 Python，请先安装 Python 3.10+ 并加入 PATH
    pause
    exit /b 1
)

set start_time=%TIME%
echo 开始时间: %start_time%
echo.

echo ----------------------------------------------------
echo 步骤 1/3: 运行全量管道 (run_all.py)
echo ----------------------------------------------------
python run_all.py --force-silver
if errorlevel 1 (
    color 0C
    echo.
    echo [ERROR] 全量管道执行失败，错误码 %errorlevel%
    echo 提示：请查看上方红色错误信息排查
    if not "%~1"=="from_menu" pause
    exit /b 1
)

echo.
echo ----------------------------------------------------
echo 步骤 2/3: 生成综合看板 (generate_dashboard.py)
echo ----------------------------------------------------
python dashboard\generate_dashboard.py
if errorlevel 1 (
    color 0C
    echo.
    echo [ERROR] 看板生成失败，错误码 %errorlevel%
    if not "%~1"=="from_menu" pause
    exit /b 1
)

echo.
echo ----------------------------------------------------
echo 步骤 3/3: 产品生命周期看板 (generate_v4.py)
echo ----------------------------------------------------
set "latest_xlsx="
for /f "delims=" %%f in ('dir /b /od /a-d "output\report\产品生命周期报告_v4.0_*.xlsx" 2^>nul') do (
    set "latest_xlsx=output\report\%%f"
)
if defined latest_xlsx (
    echo 使用源文件: %latest_xlsx%
    python generate_v4.py "%latest_xlsx%" -o dashboard\product_lifecycle.html
    if errorlevel 1 (
        color 0E
        echo [警告] C面看板生成失败，错误码 %errorlevel%，A面已生成可继续使用
    ) else (
        echo [OK] C面产品生命周期看板已更新
    )
) else (
    color 0E
    echo [警告] 未找到产品生命周期报告Excel，跳过C面生成
)

color 0A
echo.
echo ====================================================
echo  [OK] 全量重跑完成！
echo  开始: %start_time%
echo  结束: %TIME%
echo  看板: %CD%\dashboard\dashboard_a.html
echo ====================================================
echo.
echo 提示：双击 6_打开最新看板.bat 可直接打开看板
echo.

if not "%~1"=="from_menu" pause
exit /b 0