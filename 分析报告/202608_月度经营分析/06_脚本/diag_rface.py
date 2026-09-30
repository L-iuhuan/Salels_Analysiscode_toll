# -*- coding: utf-8 -*-
"""诊断：提取 R 面 kpi-bar HTML + 截图 R 面全貌"""
import sys, glob, os, re, asyncio
sys.stdout.reconfigure(encoding='utf-8')

BASE = r'E:\3-其他资料\数据分析\sales_analytics_platform'
html_path = max(glob.glob(os.path.join(BASE, 'output', 'dashboard', '销售数据分析看板_*.html')), key=os.path.getmtime)
html = open(html_path, encoding='utf-8').read()

# 1. kpi-bar HTML（R 面区段——找含 跟踪事项 的 kpi-bar）
i = html.find('跟踪事项')
seg_start = html.rfind('<div class="kpi-bar"', 0, i)
seg = html[seg_start:seg_start + 1600]
print('=== kpi-bar HTML ===')
print(seg[:1500])

# 2. 截图 R 面
from playwright.async_api import async_playwright

async def shot():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1600, 'height': 1000})
        await page.goto('file:///' + html_path.replace('\\', '/'), timeout=120000)
        await page.wait_for_timeout(5000)
        # 切到 R 面 tab
        await page.evaluate("TABS.navigate('R')")
        await page.wait_for_timeout(2500)
        el = await page.query_selector('#face-r, [data-face="R"], #faceR')
        if el:
            await el.screenshot(path=r'C:\Users\910373\AppData\Local\Temp\opencode\rface_full.png')
            print('截图: rface_full.png')
        else:
            await page.screenshot(path=r'C:\Users\910373\AppData\Local\Temp\opencode\rface_full.png', full_page=False)
            print('整页截图(未找到R面容器): rface_full.png')
        await browser.close()

asyncio.run(shot())
