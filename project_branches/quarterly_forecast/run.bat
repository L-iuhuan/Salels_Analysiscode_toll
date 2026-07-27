@echo off
rem 自动生成:按依赖顺序执行
cd /d %~dp0
python run_quarterly_forecast.py
if errorlevel 1 (echo [失败] run_quarterly_forecast.py & exit /b 1)
python run_customer_forecast.py
if errorlevel 1 (echo [失败] run_customer_forecast.py & exit /b 1)
pause
