# -*- coding: utf-8 -*-
"""取证：R 面当前渲染的 ①节双表 HTML 结构 ②badge 覆盖统计 ③新 CSS 定位类检查 + 全页截图"""
import sys, glob, os, re, asyncio
sys.stdout.reconfigure(encoding='utf-8')

BASE = r'E:\3-其他资料\数据分析\sales_analytics_platform'
html_path = max(glob.glob(os.path.join(BASE, 'output', 'dashboard', '销售数据分析看板_*.html')), key=os.path.getmtime)
html = open(html_path, encoding='utf-8').read()

# 1. 重点风险① 节的 HTML（双表区域结构）
i1 = html.find('重点风险①')
i2 = html.find('重点风险②')
sec1 = html[i1:i2] if i1 >= 0 and i2 > i1 else ''
tables = re.findall(r'<table[^>]*>', sec1)
print('=== 重点风险① 节 ===')
print('表格标签数:', len(tables), '| </table> 数:', sec1.count('</table>'), '| div 开:', sec1.count('<div'), 'div 闭:', sec1.count('</div>'))
print('节 HTML 头 600 字:')
print(sec1[:600])

# 2. badge 覆盖统计（哪些表有 chip 哪些没有）
print()
print('=== badge 分布（按节）===')
for m in re.finditer(r'<h3>([^<]{0,40})</h3>', html):
    title = m.group(1)
    seg_end = html.find('<h3>', m.end())
    seg = html[m.end():seg_end if seg_end > 0 else m.end() + 5000]
    n_badge = seg.count('badge-')
    n_td = seg.count('<td')
    n_th = seg.count('<th')
    if n_td > 0:
        print('%-42s td=%3d badge=%3d' % (title[:40], n_td, n_badge))

# 3. 新 CSS 中的定位/布局类检查（overlap 嫌疑）
tpl = open(os.path.join(BASE, 'dashboard', 'template.html'), encoding='utf-8').read()
fr = re.findall(r'\.face-risk[^{]*\{[^}]*\}', tpl)
print()
print('=== .face-risk CSS 规则数:', len(fr), '===')
for r in fr:
    if any(k in r for k in ['position', 'margin', 'grid', 'flex', 'float', 'width', 'height']):
        print(' ', r.strip()[:130])

# 4. 截图
from playwright.async_api import async_playwright
async def shot():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1600, 'height': 1000})
        await page.goto('file:///' + html_path.replace('\\', '/'), timeout=120000)
        await page.wait_for_timeout(5000)
        await page.evaluate("TABS.navigate('R')")
        await page.wait_for_timeout(2500)
        await page.screenshot(path=r'C:\Users\910373\AppData\Local\Temp\opencode\rface_bug.png', full_page=True)
        # 重点风险① 元素特写
        els = await page.query_selector_all('h3')
        for e in els:
            t = await e.inner_text()
            if '重点风险①' in t:
                box = await e.bounding_box()
                await page.screenshot(path=r'C:\Users\910373\AppData\Local\Temp\opencode\rface_sec1.png',
                                      clip={'x': 0, 'y': box['y'] - 20, 'width': 1600, 'height': 900})
                break
        print('截图: rface_bug.png + rface_sec1.png')
        await browser.close()
asyncio.run(shot())
