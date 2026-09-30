# -*- coding: utf-8 -*-
"""月度数据修复终验：20DB 弹窗图表数值 vs silver 真实月度"""
import sys, glob, os, asyncio, json
sys.stdout.reconfigure(encoding='utf-8')
from playwright.async_api import async_playwright

html_path = max(glob.glob(r'E:\3-其他资料\数据分析\sales_analytics_platform\output\dashboard\销售数据分析看板_*.html'), key=os.path.getmtime)

EXPECTED = [0, 120000, 237272, 0, 97005, 240000, 0, 0, 0, 120000, 0, 240000]  # 25-09→26-08 由 silver 对拍所得

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1600, 'height': 1000})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        await page.goto('file:///' + html_path.replace('\\', '/'), timeout=120000)
        await page.wait_for_timeout(6000)
        await page.evaluate("TABS.navigate('C')")
        await page.wait_for_timeout(3500)
        # 直接调用 openDetail('20DB')（若列表里没有该产品则点首行）
        r = await page.evaluate("""() => {
            const names = DATA.table.map(r => r['产品名称']);
            const target = names.find(n => n && n.indexOf('20DB') > -1) || names[0];
            openDetail(target);
            return target;
        }""")
        await page.wait_for_timeout(2500)
        r2 = await page.evaluate("""() => {
            const el = document.getElementById('detail-chart');
            const ec = el && window.echarts ? echarts.getInstanceByDom(el) : null;
            if (!ec) return {err: 'no chart'};
            const o = ec.getOption();
            return {
                xLabels: o.xAxis[0].data.slice(0, 12),
                sales: o.series[0].data,
                gm: o.series[1].data,
                histHasMonthly: !!(DATA.history[document.getElementById('appDrawerTitle').innerText] || {}).monthly_sales
            };
        }""")
        print('弹窗产品:', r)
        print('X轴:', json.dumps(r2.get('xLabels'), ensure_ascii=False))
        print('销量序列:', json.dumps(r2.get('sales')))
        print('毛利率序列:', json.dumps(r2.get('gm')))
        print('monthly 数组在 DATA:', r2.get('histHasMonthly'))
        got = r2.get('sales') or []
        match = all(abs(float(a) - b) < 1 for a, b in zip(got, EXPECTED)) if len(got) == 12 else False
        print('与 silver 真实月度一致:', match)
        drawer = await page.query_selector('#appDrawer')
        if drawer:
            await drawer.screenshot(path=r'C:\Users\910373\AppData\Local\Temp\opencode\proddrawer_monthly.png')
            print('截图: proddrawer_monthly.png')
        print('JS错误:', errors[:3] if errors else '无')
        await browser.close()

asyncio.run(main())
