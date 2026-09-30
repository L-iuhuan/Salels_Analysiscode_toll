# -*- coding: utf-8 -*-
import sys, pathlib, json
from playwright.sync_api import sync_playwright

HTML = sys.argv[1]

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1000})
    pg.goto(pathlib.Path(HTML).as_uri())
    pg.wait_for_timeout(2500)
    info = pg.evaluate("""() => {
      const gm = document.getElementById('geoMap');
      const dump = (el, depth) => {
        const r = {tag: el.tagName, id: el.id, cls: el.className && String(el.className).slice(0,40), w: el.clientWidth, h: el.clientHeight, children: []};
        if (depth < 3) Array.from(el.children).forEach(c => r.children.push(dump(c, depth+1)));
        return r;
      };
      const tree = dump(gm, 0);
      // any absolutely positioned elements inside geoMap's offsetParent chain?
      const rel = gm.parentElement;
      const relDump = dump(rel, 0);
      return {geoMap: tree, parent: relDump};
    }""")
    print(json.dumps(info, ensure_ascii=False, indent=1))
    b.close()
