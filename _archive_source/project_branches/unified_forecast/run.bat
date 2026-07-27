@echo off
rem 自动生成:按依赖顺序执行
cd /d %~dp0
python unified_forecast_v3.py
if errorlevel 1 (echo [失败] unified_forecast_v3.py & exit /b 1)
pause
