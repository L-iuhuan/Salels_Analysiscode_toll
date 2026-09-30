# -*- coding: utf-8 -*-
import sys, pathlib
from playwright.sync_api import sync_playwright

HTML = sys.argv[1]
OUT = pathlib.Path(r"C:\Users\910373\AppData\Local\Temp\opencode\geo_probe")

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=3)
    pg.goto(pathlib.Path(HTML).as_uri())
    pg.wait_for_timeout(2500)
    pg.evaluate("typeof initGeo==='function' && initGeo()")
    pg.wait_for_timeout(1500)
    pg.locator("#geoMap").scroll_into_view_if_needed()
    pg.wait_for_timeout(300)
    # find the main map canvas and crop bottom-right region via clip
    box = pg.locator("#geoMap").bounding_box()
    print("geoMap box:", box)
    # clip: bottom-right 500x420 of geoMap
    clip = {"x": box["x"] + box["width"] - 560, "y": box["y"] + box["height"] - 400, "width": 560, "height": 400}
    pg.screenshot(path=str(OUT / "mainmap_se_corner.png"), clip=clip)
    # query zrender: what groups exist in main chart, and their bounding
    info = pg.evaluate("""() => {
      const chart = TABS.charts.get('geoMap');
      const zr = chart.getZr();
      const out = [];
      zr.storage.getRoots().forEach(g => {
        g.traverse(el => {
          if (el.type === 'polygon' || el.type === 'path' || el.type === 'group') {
            const b = el.getBoundingRect ? el.getBoundingRect() : null;
            if (b && b.width < 120 && b.height < 160 && b.width > 5) {
              out.push({type: el.type, w: Math.round(b.width), h: Math.round(b.height), x: Math.round(b.x), y: Math.round(b.y), silent: el.silent});
            }
          }
        });
      });
      return out.slice(0, 40);
    }""")
    for it in info:
        print(it)
    b.close()
print("done")
