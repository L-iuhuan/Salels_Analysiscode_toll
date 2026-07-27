@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title 半导体销售分析 · 一键运行控制台
color 0B

REM 切换到脚本所在目录（无论从哪里双击都正确）
cd /d "%~dp0"

:MENU
cls
echo.
echo ════════════════════════════════════════════════════
echo    半导体销售分析 · 一键运行控制台
echo    项目目录: %CD%
echo ════════════════════════════════════════════════════
echo.
echo   [1] 全量重跑 (清洗 + 分析 + 看板)            约 10 分钟
echo   [2] 只生成看板 (用现有 Gold 数据)             约 2 分钟
echo   [3] 只跑客户分析                              约 5 分钟
echo   [4] 只跑产品分析                              约 3 分钟
echo   [5] 更新产品生命周期看板 (C 面)                约 1 分钟
echo   [6] 打开最新看板 (浏览器)                      立即
echo   [7] 强制清空 Silver 缓存重跑                  约 15 分钟
echo   [8] 退出
echo.
echo ────────────────────────────────────────────────────

set /p choice="请输入选项 [1-8]: "

if "%choice%"=="1" goto FULL_RUN
if "%choice%"=="2" goto DASHBOARD_ONLY
if "%choice%"=="3" goto CUSTOMER_ONLY
if "%choice%"=="4" goto PRODUCT_ONLY
if "%choice%"=="5" goto LIFECYCLE_ONLY
if "%choice%"=="6" goto OPEN_DASHBOARD
if "%choice%"=="7" goto FORCE_SILVER
if "%choice%"=="8" goto END

echo.
echo [!] 输入无效，请输入 1-8
timeout /t 2 >nul
goto MENU

:FULL_RUN
call "%~dp01_全量重跑.bat" "from_menu"
goto MENU

:DASHBOARD_ONLY
call "%~dp02_只生成看板.bat" "from_menu"
goto MENU

:CUSTOMER_ONLY
call "%~dp03_只跑客户分析.bat" "from_menu"
goto MENU

:PRODUCT_ONLY
call "%~dp04_只跑产品分析.bat" "from_menu"
goto MENU

:LIFECYCLE_ONLY
call "%~dp05_产品生命周期看板.bat" "from_menu"
goto MENU

:OPEN_DASHBOARD
call "%~dp06_打开最新看板.bat" "from_menu"
goto MENU

:FORCE_SILVER
cls
color 0E
echo.
echo ? 警告：将强制清空 Silver 缓存并重跑全量管道（约 15 分钟）
echo.
set /p confirm="确认继续？(y/n): "
if /i not "%confirm%"=="y" (
    color 0B
    goto MENU
)
color 0B
echo.
echo ════════════════════════════════════════════════════
echo   强制清空 Silver 缓存 + 全量重跑
echo ════════════════════════════════════════════════════
set start_time=%TIME%

if exist "output\silver\.silver_checksum" (
    del /q "output\silver\.silver_checksum"
    echo [√] 已删除 .silver_checksum 缓存标记
)

python run_all.py --force-silver
if errorlevel 1 (
    color 0C
    echo.
    echo [?] 管道执行失败，错误码 %errorlevel%
    color 0B
    pause
    goto MENU
)

echo.
echo [√] 全量管道完成，开始生成看板...
python dashboard\generate_dashboard.py
if errorlevel 1 (
    color 0C
    echo.
    echo [?] 看板生成失败，错误码 %errorlevel%
    color 0B
    pause
    goto MENU
)

echo.
echo ════════════════════════════════════════════════════
echo  [√] 全部完成！开始时间 %start_time%，结束时间 %TIME%
echo  看板路径：dashboard\dashboard_a.html
echo ════════════════════════════════════════════════════
pause
goto MENU

:END
echo.
echo 再见
timeout /t 1 >nul
exit /b 0
