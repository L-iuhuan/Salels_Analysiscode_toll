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
      const comps = [];
      zr.storage.getRoots().forEach(root => {
        root.traverse(el => {
          if (el.type === 'compound') {
            const b = el.getBoundingRect();
            comps.push({
              x: Math.round((el.position ? el.position[0] : 0) + b.x),
              y: Math.round((el.position ? el.position[1] : 0) + b.y),
              w: Math.round(b.width), h: Math.round(b.height),
              nsub: (el.shape.paths || []).length,
              fill: el.style && el.style.fill
            });
          }
        });
      });
      // also count non-compound paths (lines etc.)
      let npath = 0, npoly = 0, nrect = 0;
      zr.storage.getRoots().forEach(root => {
        root.traverse(el => {
          if (el.type === 'path') npath++;
          else if (el.type === 'polygon') npoly++;
          else if (el.type === 'rect') nrect++;
        });
      });
      return {ncomp: comps.length, comps: comps, npath: npath, npoly: npoly, nrect: nrect};
    }""")
    print("ncomp:", info["ncomp"], "npath:", info["npath"], "npoly:", info["npoly"], "nrect:", info["nrect"])
    for c in info["comps"]:
        print(c["x"], c["y"], c["w"], c["h"], "subs=", c["nsub"], c["fill"])
    b.close()
