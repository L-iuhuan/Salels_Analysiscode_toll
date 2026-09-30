# -*- coding: utf-8 -*-
import sys, re
sys.stdout.reconfigure(encoding='utf-8')
# 1. 面序：从模板取 TABS 定义与导航按钮顺序
tpl = open(r'E:\3-其他资料\数据分析\sales_analytics_platform\dashboard\template.html', encoding='utf-8').read()
m = re.search(r'TABS\s*=\s*\{[^}]{0,500}\}', tpl, re.S)
print('TABS定义(截断):', (m.group(0)[:400] if m else '未找到'))
faces = re.findall(r"['\"]?order['\"]?\s*:\s*\d+|face\s*:\s*['\"][A-Z]", tpl)
print('face键序线索:', faces[:20])
# 导航条按钮顺序（找 nav/tab 容器内的按钮声明）
nav = re.findall(r'<button[^>]*data-tab="([A-Za-z]+)"[^>]*>|navigate\(\'([A-Z])\'', tpl)
print('按钮/导航线索:', nav[:20])
# 2. faces.yaml 面注册顺序
fy = open(r'E:\3-其他资料\数据分析\sales_analytics_platform\dashboard\faces.yaml', encoding='utf-8').read()
top = re.findall(r'^([A-Za-z_]+):', fy, re.M)
print('faces.yaml 顶层键序:', top[:20])
