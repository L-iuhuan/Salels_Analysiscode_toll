# -*- coding: utf-8 -*-
"""产品生命周期弹窗修复探针：DATA.history 月份标签 + 产物单位 + 弹窗实开验证"""
import sys, glob, os, re, asyncio, json
sys.stdout.reconfigure(encoding='utf-8')

BASE = r'E:\3-其他资料\数据分析\sales_analytics_platform'
html_path = max(glob.glob(os.path.join(BASE, 'output', 'dashboard', '销售数据分析看板_*.html')), key=os.path.getmtime)
html = open(html_path, encoding='utf-8').read()

# 1. DATA.history.months 注入检查
m = re.search(r'"history"\s*:\s*\{', html)
print('history 键存在:', bool(m))
has_months = '"months":' in html or re.search(r'months\s*:\s*\[', html)
print('months 标签注入:', bool(has_months))
mm = re.search(r'"months"\s*:\s*\[([^\]]{0,80})\]', html)
print('months 样例:', mm.group(1)[:80] if mm else '(数组写法不同，搜 fmtQty 与图例)')

# 2. 产物单位贯穿
checks = {
    '图例带单位': '销量(颗)' in html and '毛利率(%)' in html,
    '轴名带单位': "name: '销量(颗)'" in html or '销量(颗)' in html,
    'fmtQty 定义': 'function fmtQty' in html,
    'tooltip 单位格式': '万颗' in html,
    'X轴真实月份回退': 'hist.months ? hist.months.slice().reverse()' in html.replace('  ', ' '),
}
for k, v in checks.items():
    print(('PASS' if v else 'FAIL'), k)

# 3. 弹窗实开验证（切 C 面→点产品行→读图表 option）
from playwright.async_api import async_playwright

async def open_modal():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1600, 'height': 1000})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        await page.goto('file:///' + html_path.replace('\\', '/'), timeout=120000)
        await page.wait_for_timeout(6000)
        await page.evaluate("TABS.navigate('C')")
        await page.wait_for_timeout(3500)
        # 点第一行产品打开弹窗
        clicked = await page.evaluate("""() => {
            const rows = document.querySelectorAll('#table-body tr.table-row');
            if (!rows.length) return '无产品行';
            rows[0].click();
            return rows[0].cells[0].innerText.split(/\\s|数据不足/)[0];
        }""")
        await page.wait_for_timeout(2500)
        r = await page.evaluate("""() => {
            const el = document.getElementById('detail-chart');
            if (!el) return {err: '弹窗图表容器不存在'};
            const ec = window.echarts ? echarts.getInstanceByDom(el) : null;
            if (!ec) return {err: '图表未初始化'};
            const o = ec.getOption();
            return {
                xLabels: (o.xAxis[0].data || []).slice(0, 12),
                seriesNames: o.series.map(s => s.name),
                yNames: o.yAxis.map(y => y.name),
                drawerTitle: document.getElementById('appDrawerTitle') ? document.getElementById('appDrawerTitle').innerText : ''
            };
        }""")
        print()
        print('弹窗产品:', clicked)
        print('X轴标签:', json.dumps(r.get('xLabels'), ensure_ascii=False) if 'xLabels' in r else r)
        print('系列名:', r.get('seriesNames'), '| 轴名:', r.get('yNames'))
        drawer = await page.query_selector('#appDrawer')
        if drawer:
            await drawer.screenshot(path=r'C:\Users\910373\AppData\Local\Temp\opencode\proddrawer_after.png')
            print('弹窗截图: proddrawer_after.png')
        print('JS错误:', errors[:3] if errors else '无')
        await browser.close()

asyncio.run(open_modal())
