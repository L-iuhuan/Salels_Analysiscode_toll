# -*- coding: utf-8 -*-
import glob, io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright
ROOT = r"E:\3-其他资料\数据分析"
html = max(glob.glob(os.path.join(ROOT, "sales_analytics_platform", "output", "dashboard", "*.html")), key=os.path.getmtime)
url = "file:///" + html.replace("\\", "/").replace(" ", "%20")
OUT = os.path.join(os.environ.get("TEMP", r"C:\Temp"), "opencode")
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1100})
    pg.goto(url, wait_until="domcontentloaded")
    pg.wait_for_timeout(2500)
    pg.evaluate("document.getElementById('sec-geo').scrollIntoView()")
    pg.wait_for_timeout(800)
    # 主图右下角区域裁剪（南海区域）
    box = pg.evaluate("var r=document.getElementById('geoMap').getBoundingClientRect();[r.left,r.top,r.width,r.height]")
    pg.screenshot(path=os.path.join(OUT, "geo_v6_main_se.png"), clip={"x": box[0]+box[2]*0.55, "y": box[1]+box[3]*0.55, "width": box[2]*0.45, "height": box[3]*0.45})
    # 全 geo 区
    g = pg.evaluate("var r=document.getElementById('sec-geo').getBoundingClientRect();[r.left,r.top,r.width,r.height]")
    pg.screenshot(path=os.path.join(OUT, "geo_v6_full.png"), clip={"x": g[0], "y": g[1], "width": min(g[2],1560), "height": min(g[3],1050)})
    b.close()
