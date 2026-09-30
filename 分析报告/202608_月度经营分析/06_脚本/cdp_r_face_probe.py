# -*- coding: utf-8 -*-
"""一次性 CDP 探针：R 面 v2 新格式渲染验证（替代 30s 超时的存量门禁脚本跑大产物）。"""
from playwright.sync_api import sync_playwright

html = r"E:\3-其他资料\数据分析\sales_analytics_platform\output\dashboard\销售数据分析看板_2026年08月.html"
errors = []
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page()
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("file:///" + html.replace("\\", "/"), timeout=120000)
    page.evaluate("() => switchTab('R')")
    page.wait_for_selector("#tabR .kc", timeout=60000)
    n_kc = page.locator("#tabR .kc").count()
    rhtml = page.inner_html("#tabR")
    b.close()
print("R面 KPI 卡数:", n_kc)
print("持续列表头:", "持续" in rhtml, "| 连续第 3 月:", "连续第 3 月" in rhtml)
print("较上月表头:", "较上月" in rhtml, "| 较上月恶化:", "较上月恶化" in rhtml)
print("行动种子:", "自动种子" in rhtml)
print("备注·本月解除:", "本月解除" in rhtml)
print("JS错误数:", len(errors))
for e in errors[:5]:
    print("  ERR:", e[:200])
