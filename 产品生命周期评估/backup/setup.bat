@echo off
chcp 65001 >nul
echo ========================================
echo   产品生命周期分析工具 - 环境安装
echo ========================================
echo.

REM 检查 Python 是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.8+
    echo 下载地址：https://www.python.org/downloads/ 
    pause
    exit /b 1
)

echo [1/2] 正在从清华源安装依赖库...
pip install pandas openpyxl numpy python-calamine statsmodels chinese_calendar -i https://pypi.tuna.tsinghua.edu.cn/simple -q

if errorlevel 1 (
    echo [错误] 安装失败，请检查网络连接
    pause
    exit /b 1
)

echo [2/2] 安装完成！

echo.
echo ========================================
echo   安装成功！双击 run.py 即可运行
echo   运行前请先配置 config.xlsx
echo ========================================
pause