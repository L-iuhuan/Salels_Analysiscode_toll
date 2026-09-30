# -*- coding: utf-8 -*-
import sys, pathlib
from playwright.sync_api import sync_playwright

HTML = sys.argv[1]
OUT = pathlib.Path(r"C:\Users\910373\AppData\Local\Temp\opencode\geo_probe")

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1100}, device_scale_factor=3)
    pg.goto(pathlib.Path(HTML).as_uri())
    pg.wait_for_timeout(3000)
    pg.locator("#geoMap").scroll_into_view_if_needed()
    pg.wait_for_timeout(500)
    box = pg.locator("#geoMap").bounding_box()
    # bottom-right 420x340
    clip = {"x": box["x"] + box["width"] - 420, "y": box["y"] + box["height"] - 340, "width": 420, "height": 340}
    pg.screenshot(path=str(OUT / "se_corner_pure.png"), clip=clip)
    b.close()
print("done")
