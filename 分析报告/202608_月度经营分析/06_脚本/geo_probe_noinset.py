# -*- coding: utf-8 -*-
import sys, pathlib, json
from playwright.sync_api import sync_playwright

HTML = sys.argv[1]
OUT = pathlib.Path(r"C:\Users\910373\AppData\Local\Temp\opencode\geo_probe")

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=2)
    pg.goto(pathlib.Path(HTML).as_uri())
    pg.wait_for_timeout(2500)
    pg.evaluate("typeof initGeo==='function' && initGeo()")
    pg.wait_for_timeout(1200)
    # hide inset AND the manual legend to isolate main canvas
    pg.evaluate("document.getElementById('geoNhInset').style.display='none';")
    pg.wait_for_timeout(200)
    pg.locator("#geoMap").scroll_into_view_if_needed()
    pg.wait_for_timeout(200)
    pg.locator("#geoMap").screenshot(path=str(OUT / "geomap_noinset.png"))
    # probe large elements in bottom-right quadrant of main chart
    info = pg.evaluate("""() => {
      const chart = TABS.charts.get('geoMap');
      const zr = chart.getZr();
      const W = zr.getWidth(), H = zr.getHeight();
      const found = [];
      zr.storage.getRoots().forEach(root => {
        root.traverse(el => {
          if (el.type !== 'compound' && el.type !== 'polygon' && el.type !== 'path') return;
          const b = el.getBoundingRect ? el.getBoundingRect() : null;
          if (!b) return;
          const absx = (el.position ? el.position[0] : 0) + b.x;
          const absy = (el.position ? el.position[1] : 0) + b.y;
          if (absx > W*0.55 && absy > H*0.45) {
            found.push({type: el.type, x: Math.round(absx), y: Math.round(absy), w: Math.round(b.width), h: Math.round(b.height),
              fill: el.style ? el.style.fill : null, stroke: el.style ? el.style.stroke : null});
          }
        });
      });
      return {W: W, H: H, found: found.slice(0, 30)};
    }""")
    print(json.dumps(info, ensure_ascii=False, indent=1))
    b.close()
