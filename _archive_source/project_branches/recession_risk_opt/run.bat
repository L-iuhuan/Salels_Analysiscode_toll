@echo off
rem 自动生成:按依赖顺序执行
cd /d %~dp0
python pipeline.py
if errorlevel 1 (echo [失败] pipeline.py & exit /b 1)
python generate_snapshot.py
if errorlevel 1 (echo [失败] generate_snapshot.py & exit /b 1)
pause
