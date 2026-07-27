@echo off
rem 自动生成:按依赖顺序执行
cd /d %~dp0
python deep_all.py
if errorlevel 1 (echo [失败] deep_all.py & exit /b 1)
python deep_action.py
if errorlevel 1 (echo [失败] deep_action.py & exit /b 1)
python deep_sales_products.py
if errorlevel 1 (echo [失败] deep_sales_products.py & exit /b 1)
python deep_zxkx.py
if errorlevel 1 (echo [失败] deep_zxkx.py & exit /b 1)
python make_word.py
if errorlevel 1 (echo [失败] make_word.py & exit /b 1)
pause
