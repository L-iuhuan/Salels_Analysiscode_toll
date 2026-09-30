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
          if (el.type === 'path' || el.type === 'rect' || el.type === 'polygon') {
            const b = el.getBoundingRect();
            // cumulative transform
            let m = [1,0,0,1,0,0];
            let n = el;
            const mul = (a, b2) => [
              a[0]*b2[0]+a[2]*b2[1], a[1]*b2[0]+a[3]*b2[1],
              a[0]*b2[2]+a[2]*b2[3], a[1]*b2[2]+a[3]*b2[3],
              a[0]*b2[4]+a[2]*b2[5]+a[4], a[1]*b2[4]+a[3]*b2[5]+a[5]
            ];
            while (n && n !== zr) {
              if (n.transform) m = mul(m, n.transform);
              n = n.parent;
            }
            const x = m[0]*b.x + m[2]*b.y + m[4];
            const y = m[1]*b.x + m[3]*b.y + m[5];
            const w = Math.abs(m[0])*b.width, h = Math.abs(m[3])*b.height;
            out.push({type: el.type, x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h),
              stroke: el.style ? el.style.stroke : null, fill: el.style ? el.style.fill : null, lw: el.style ? el.style.lineWidth : null,
              pathdata: el.shape && el.shape.path ? String(el.shape.path).slice(0,200) : null});
          }
        });
      });
      return out;
    }""")
    for it in info:
        print(json.dumps(it, ensure_ascii=False))
    b.close()
