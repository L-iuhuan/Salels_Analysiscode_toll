@echo off
rem 自动生成:按依赖顺序执行
cd /d %~dp0
python run_all.py --stage silver,product,customer,kpi,cross_ref
if errorlevel 1 (echo [失败] run_all.py --stage silver,product,customer,kpi,cross_ref & exit /b 1)
pause
