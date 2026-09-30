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
    pg = b.new_page(viewport={"width": 1600, "height": 1100}, device_scale_factor=2)
    pg.goto(url, wait_until="domcontentloaded")
    pg.wait_for_timeout(2500)
    pg.evaluate("document.getElementById('sec-geo').scrollIntoView()")
    pg.wait_for_timeout(800)
    box = pg.evaluate("var r=document.getElementById('geoMap').getBoundingClientRect();[r.left,r.top,r.width,r.height]")
    # 主画布右下 30% 区域放大
    pg.screenshot(path=os.path.join(OUT, "geo_v6_zoom.png"),
                  clip={"x": box[0] + box[2] * 0.62, "y": box[1] + box[3] * 0.60,
                        "width": box[2] * 0.38, "height": box[3] * 0.40})
    b.close()
