# -*- coding: utf-8 -*-
"""修复后验证：margin表品类页KA/AA筛选恢复 + kaaaLine横轴32月全显"""
import sys, asyncio, glob, os
sys.stdout.reconfigure(encoding='utf-8')
from playwright.async_api import async_playwright

OUT = r'E:\3-其他资料\数据分析\sales_analytics_platform\output\dashboard'
html = max(glob.glob(os.path.join(OUT, '销售数据分析看板_*.html')), key=os.path.getmtime)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1600, 'height': 900})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        await page.goto('file:///' + html.replace('\\', '/'), timeout=120000)
        await page.wait_for_timeout(6000)
        # 1. margin 表品类页筛选验证
        r1 = await page.evaluate("""() => {
            const rows = () => document.querySelectorAll('#marginTable > div').length - 1;
            marginTab('cat'); const all = rows();
            marginFilter('KA'); const ka = rows();
            marginFilter('AA'); const aa = rows();
            marginFilter('all'); marginTab('cat');
            const first = document.querySelector('#marginTable > div:nth-child(2)');
            const cells = first ? first.innerText.split('\\n') : [];
            return {all, ka, aa, firstRow: cells.slice(0, 7)};
        }""")
        print('margin表(品类页): 全部=%s行 | KA筛选=%s行 | AA筛选=%s行' % (r1['all'], r1['ka'], r1['aa']))
        print('品类首行(名称/全部收入/毛利率/KA收入/KA利率/AA收入/AA利率):', r1['firstRow'])
        # 2. kaaaLine 横轴配置验证
        r2 = await page.evaluate("""() => {
            const el = document.getElementById('kaaaLine');
            const ec = window.echarts ? echarts.getInstanceByDom(el) : null;
            if (!ec) return null;
            const o = ec.getOption();
            return {
                months: o.xAxis[0].data.length,
                interval: o.xAxis[0].axisLabel.interval,
                hasFormatter: typeof o.xAxis[0].axisLabel.formatter === 'function'
            };
        }""")
        print('kaaaLine: 月份数=%s | interval=%s(0=全显) | formatter=%s' % (r2['months'], r2['interval'], r2['hasFormatter']))
        # 3. 图卡截图存证
        el = await page.query_selector('#sec-kaaaLine')
        await el.screenshot(path=r'C:\Users\910373\AppData\Local\Temp\opencode\kaaa_fix_after.png')
        print('截图: Temp\\opencode\\kaaa_fix_after.png | JS错误:', errors[:3] if errors else '无')
        await browser.close()

asyncio.run(main())
