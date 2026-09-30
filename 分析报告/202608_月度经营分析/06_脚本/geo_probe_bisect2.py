# -*- coding: utf-8 -*-
import sys, pathlib, json
from playwright.sync_api import sync_playwright

HTML = sys.argv[1]
GEO = json.load(open(r"E:\3-其他资料\数据分析\sales_analytics_platform\dashboard\geo\china.json", encoding="utf-8"))

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1000})
    pg.goto(pathlib.Path(HTML).as_uri())
    pg.wait_for_timeout(2500)
    res = pg.evaluate("""(geo) => {
      const chart = TABS.charts.get('geoMap');
      const opt = chart.getOption();
      const feats = geo.features;
      const cv = document.querySelector('#geoMap canvas');
      const countInk = () => {
        const tmp = document.createElement('canvas');
        tmp.width = cv.width; tmp.height = cv.height;
        const tctx = tmp.getContext('2d');
        tctx.fillStyle = '#fff';
        tctx.fillRect(0, 0, tmp.width, tmp.height);
        tctx.drawImage(cv, 0, 0);
        const dpr = cv.width / cv.clientWidth;
        const d = tctx.getImageData(Math.round(780*dpr), Math.round(420*dpr), Math.round(160*dpr), Math.round(180*dpr)).data;
        let n = 0;
        for (let i = 0; i < d.length; i += 4) {
          if (d[i] < 245 || d[i+1] < 245 || d[i+2] < 245) n++;
        }
        return n;
      };
      const results = [];
      for (let k = -1; k < feats.length; k++) {
        const subset = k < 0 ? feats : feats.filter((f, i) => i !== k);
        echarts.registerMap('china', {type: 'FeatureCollection', features: subset});
        chart.setOption(opt, true);
        results.push({skip: k < 0 ? 'ALL' : String((feats[k].properties && (feats[k].properties.name || feats[k].properties.adcode)) || '?'), ink: countInk()});
      }
      return results;
    }""", GEO)
    for r in res:
        print(r["skip"], r["ink"])
    b.close()
