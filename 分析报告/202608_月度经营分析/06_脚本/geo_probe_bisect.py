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
      const feats = geo.features;
      const region = {x: 740, y: 390, w: 220, h: 220};
      const dom = document.createElement('div');
      dom.style.cssText = 'position:fixed;left:0;top:0;width:1008px;height:620px;z-index:-1;opacity:0.01;pointer-events:none;';
      document.body.appendChild(dom);
      const countInk = () => {
        const cv = dom.querySelector('canvas');
        const tmp = document.createElement('canvas');
        tmp.width = cv.width; tmp.height = cv.height;
        const tctx = tmp.getContext('2d');
        tctx.fillStyle = '#fff';
        tctx.fillRect(0, 0, tmp.width, tmp.height);
        tctx.drawImage(cv, 0, 0);
        const dpr = cv.width / 1008;
        const d = tctx.getImageData(region.x*dpr, region.y*dpr, region.w*dpr, region.h*dpr).data;
        let n = 0;
        for (let i = 0; i < d.length; i += 4) {
          if (d[i] < 245 || d[i+1] < 245 || d[i+2] < 245) n++;
        }
        return n;
      };
      const results = [];
      for (let k = -1; k < feats.length; k++) {
        const subset = k < 0 ? feats : feats.filter((f, i) => i !== k);
        echarts.registerMap('china_bisect', {type: 'FeatureCollection', features: subset});
        const c = echarts.init(dom, null, {devicePixelRatio: 1});
        c.setOption({animation: false, series: [{type: 'map', map: 'china_bisect', roam: false,
          label: {show: false}, emphasis: {disabled: true},
          itemStyle: {areaColor: '#EEF1F5', borderColor: '#CBD5E1', borderWidth: 0.5}}]});
        const ink = countInk();
        const cv = dom.querySelector('canvas');
        results.push({skip: k < 0 ? 'ALL' : String((feats[k].properties && (feats[k].properties.name || feats[k].properties.adcode)) || '?'), ink: ink, cvw: cv ? cv.width : -1});
        c.dispose();
      }
      document.body.removeChild(dom);
      return results;
    }""", GEO)
    for r in res:
        print(r["skip"], r["ink"])
    b.close()
