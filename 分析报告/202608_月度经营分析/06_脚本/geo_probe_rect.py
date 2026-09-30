# -*- coding: utf-8 -*-
import sys, pathlib, json
from playwright.sync_api import sync_playwright

HTML = sys.argv[1]
OUT = pathlib.Path(r"C:\Users\910373\AppData\Local\Temp\opencode\geo_probe")

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1100}, device_scale_factor=2)
    pg.goto(pathlib.Path(HTML).as_uri())
    pg.wait_for_timeout(3000)
    pg.locator("#geoMap").scroll_into_view_if_needed()
    pg.wait_for_timeout(400)
    meta = pg.evaluate("""() => {
      const chart = TABS.charts.get('geoMap');
      const zr = chart.getZr();
      let rects = [];
      zr.storage.getRoots().forEach(root => {
        root.traverse(el => {
          if (el.type === 'rect') {
            let chain = [], n = el;
            while (n && n !== zr) { chain.push(n.type + (n.name ? ':' + n.name : '') + (n.zlevel !== undefined ? '' : '')); n = n.parent; }
            rects.push({chain: chain.join(' < '), z: el.z, zlevel: el.zlevel, shape: JSON.stringify(el.shape).slice(0, 200)});
            el.__dbg = true;
            el.attr('invisible', true);
          }
        });
      });
      return rects;
    }""")
    print(json.dumps(meta, ensure_ascii=False, indent=1))
    box = pg.locator("#geoMap").bounding_box()
    clip = {"x": box["x"] + box["width"] - 420, "y": box["y"] + box["height"] - 340, "width": 420, "height": 340}
    pg.screenshot(path=str(OUT / "rect_hidden.png"), clip=clip)
    b.close()
