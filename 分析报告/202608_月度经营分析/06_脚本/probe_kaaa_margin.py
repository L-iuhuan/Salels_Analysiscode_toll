# -*- coding: utf-8 -*-
"""快速探针：实测 A 面 kaaaLine 卡宽 + 当前横轴标签实际渲染数量 + margin 表品类页字段现状"""
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
        r = await page.evaluate("""() => {
            const el = document.getElementById('kaaaLine');
            const card = document.getElementById('sec-kaaaLine');
            const ec = el ? window.echarts && echarts.getInstanceByDom(el) : null;
            let labels = 0, total = 0;
            if (ec) {
                const opt = ec.getOption();
                total = opt.xAxis[0].data.length;
                // 实际渲染的标签数：interval 未设时 echarts 自动抽稀
                const m = ec.getModel().getComponent('xAxis', 0);
                labels = m.axis.scale._extent ? total : total; // fallback
            }
            return {
                cardW: card ? card.clientWidth : 0,
                chartW: el ? el.clientWidth : 0,
                chartH: el ? el.clientHeight : 0,
                months: total,
                kaaRevLen: (typeof KAA_REV !== 'undefined') ? Object.keys(KAA_REV).length : 0
            };
        }""")
        print('卡宽实测:', r, '| JS错误:', errors[:3] if errors else '无')
        # margin 表品类页现状：点品类Tab → 数行数 → 点KA筛选 → 数行数
        r2 = await page.evaluate("""() => {
            const out = {};
            marginTab('cat');
            out.catRows_pline默认 = document.querySelectorAll('#marginTable > div').length - 1;
            marginFilter('KA');
            out.catRows_KA筛选 = document.querySelectorAll('#marginTable > div').length - 1;
            marginFilter('all');
            // 抽一条品类数据看字段
            out.catFirst = (typeof CAT_MARGINS !== 'undefined' && CAT_MARGINS.length) ? Object.keys(CAT_MARGINS[0]) : [];
            return out;
        }""")
        print('margin表现状:', r2)
        await browser.close()

asyncio.run(main())
