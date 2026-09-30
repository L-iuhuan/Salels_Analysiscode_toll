# -*- coding: utf-8 -*-
"""R 面全貌截图（切 R tab 后 full_page）+ 顶部卡片区特写"""
import sys, glob, os, asyncio
sys.stdout.reconfigure(encoding='utf-8')
from playwright.async_api import async_playwright

html_path = max(glob.glob(r'E:\3-其他资料\数据分析\sales_analytics_platform\output\dashboard\销售数据分析看板_*.html'), key=os.path.getmtime)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1600, 'height': 1000})
        await page.goto('file:///' + html_path.replace('\\', '/'), timeout=120000)
        await page.wait_for_timeout(5000)
        await page.evaluate("TABS.navigate('R')")
        await page.wait_for_timeout(2500)
        await page.screenshot(path=r'C:\Users\910373\AppData\Local\Temp\opencode\rface_full.png', full_page=True)
        # 卡片区特写
        el = await page.query_selector('.kpi-bar')
        if el:
            await el.screenshot(path=r'C:\Users\910373\AppData\Local\Temp\opencode\rface_kpi.png')
        print('截图完成: rface_full.png(全页) + rface_kpi.png(卡片)')
        await browser.close()

asyncio.run(main())
