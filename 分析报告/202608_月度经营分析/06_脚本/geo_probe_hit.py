# -*- coding: utf-8 -*-
import sys, pathlib, json
from playwright.sync_api import sync_playwright

HTML = sys.argv[1]

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1000})
    pg.goto(pathlib.Path(HTML).as_uri())
    pg.wait_for_timeout(2500)
    pg.evaluate("typeof initGeo==='function' && initGeo()")
    pg.wait_for_timeout(1200)
    info = pg.evaluate("""() => {
      const chart = TABS.charts.get('geoMap');
      const zr = chart.getZr();
      const W = zr.getWidth(), H = zr.getHeight();
      // box approx center based on earlier probe: x 788-868, y 452-540 css
      const pts = [[810,470],[830,500],[850,520],[800,530],[828,496]];
      const hits = [];
      pts.forEach(pt => {
        const els = [];
        zr.storage.getRoots().forEach(root => {
          root.traverse(el => {
            if (el.contain && el.contain(pt[0], pt[1])) {
              // walk up to find a named ancestor
              let n = el, chain = [];
              while (n) {
                chain.push(n.type + (n.name ? ':' + n.name : '') + (n.dataIndex !== undefined ? '[di=' + n.dataIndex + ']' : ''));
                n = n.parent;
              }
              els.push(chain.join(' < '));
            }
          });
        });
        hits.push({pt: pt, els: els.slice(0, 6)});
      });
      return hits;
    }""")
    print(json.dumps(info, ensure_ascii=False, indent=1))
    b.close()
