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
      const opt = chart.getOption();
      const r = {n_series: opt.series.length, series: opt.series.map(s => ({type: s.type, map: s.map}))};
      const zr = chart.getZr();
      const found = [];
      zr.storage.getRoots().forEach(root => {
        const sidx = (root.dataIndex !== undefined && root.seriesIndex !== undefined) ? root.seriesIndex : (root.__seriesIndex !== undefined ? root.__seriesIndex : null);
        root.traverse(el => {
          const b = el.getBoundingRect ? el.getBoundingRect() : null;
          if (!b) return;
          // region of interest: bottom-right of canvas (canvas ~1008x620)
          if (b.x > 700 && b.y > 350 && b.width < 300 && b.height < 300) {
            found.push({
              type: el.type,
              seriesIndex: el.seriesIndex !== undefined ? el.seriesIndex : (el.parent && el.parent.seriesIndex),
              name: el.name,
              style: el.style ? {fill: el.style.fill, stroke: el.style.stroke, lineWidth: el.style.lineWidth} : null,
              x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height),
              path: el.shape && el.shape.path ? String(el.shape.path).slice(0, 120) : null,
            });
          }
        });
      });
      r.found = found.slice(0, 25);
      return r;
    }""")
    print(json.dumps(info, ensure_ascii=False, indent=1))
    b.close()
