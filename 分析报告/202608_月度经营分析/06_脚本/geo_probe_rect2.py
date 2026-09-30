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
      let out = null;
      zr.storage.getRoots().forEach(root => {
        root.traverse(el => {
          if (el.type === 'rect' && out === null) {
            const g = el.parent;
            const sibs = (g.children && g.children.length) ? Array.prototype.map.call(g.children, function(c){ return {type: c.type, name: c.name || '', fill: c.style ? c.style.fill : null, text: c.style && c.style.text ? String(c.style.text).slice(0,30) : null, silent: c.silent}; }) : String(g.children);
            // region info on group?
            out = {
              groupProps: Object.keys(g).filter(k => /region|geo|data/i.test(k)),
              groupName: g.name,
              sibs: sibs,
              rectShape: el.shape,
              rectStyle: {stroke: el.style.stroke, fill: el.style.fill, lineWidth: el.style.lineWidth}
            };
          }
        });
      });
      // get region list from geo model
      const geoModel = chart.getModel().getComponent('geo', 0) || chart.getModel().getComponent('series', 0);
      const coordSys = geoModel.coordinateSystem;
      const regions = coordSys.regions ? coordSys.regions.map(r => ({name: r.name, center: r.center && r.center.slice(), rect: r.getBoundingRect ? [Math.round(r.getBoundingRect().x), Math.round(r.getBoundingRect().y), Math.round(r.getBoundingRect().width), Math.round(r.getBoundingRect().height)] : null})) : null;
      return {rect: out, regions: regions};
    }""")
    print(json.dumps(info, ensure_ascii=False, indent=1))
    b.close()
