# -*- coding: utf-8 -*-
import sys, pathlib, json
from playwright.sync_api import sync_playwright

HTML = sys.argv[1]

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1100})
    pg.goto(pathlib.Path(HTML).as_uri())
    pg.wait_for_timeout(3000)
    info = pg.evaluate("""() => {
      const chart = TABS.charts.get('geoMap');
      const zr = chart.getZr();
      const out = [];
      zr.storage.getRoots().forEach(root => {
        root.traverse(el => {
          if (el.type === 'compound') {
            const b = el.getBoundingRect();
            // Taiwan compound earlier observed around x 788 y 452 (css)
            if (b.width > 60 && b.width < 120 && b.height > 60 && b.height < 120) {
              const sub = (el.shape.paths || []).map(pp => {
                const pb = pp.getBoundingRect();
                return {type: pp.type, x: Math.round(pb.x), y: Math.round(pb.y), w: Math.round(pb.width), h: Math.round(pb.height), np: (pp.shape.points || []).length};
              });
              out.push({x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height), subs: sub});
            }
          }
        });
      });
      return out;
    }""")
    print(json.dumps(info, ensure_ascii=False, indent=1))
    b.close()
