@echo off
rem 自动生成:按依赖顺序执行
cd /d %~dp0
python run_v2.8.py
if errorlevel 1 (echo [失败] run_v2.8.py & exit /b 1)
pause
