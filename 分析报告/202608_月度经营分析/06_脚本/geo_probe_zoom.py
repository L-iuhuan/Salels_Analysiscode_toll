# -*- coding: utf-8 -*-
import sys, pathlib
from playwright.sync_api import sync_playwright

HTML = sys.argv[1]
OUT = pathlib.Path(r"C:\Users\910373\AppData\Local\Temp\opencode\geo_probe")

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=2)
    pg.goto(pathlib.Path(HTML).as_uri())
    pg.wait_for_timeout(2500)
    pg.evaluate("typeof initGeo==='function' && initGeo()")
    pg.wait_for_timeout(1500)
    pg.locator("#geoNhInset").screenshot(path=str(OUT / "inset_zoom.png"))
    # main map full
    pg.locator("#geoMap").screenshot(path=str(OUT / "geomap_full.png"))
    b.close()
print("done")
