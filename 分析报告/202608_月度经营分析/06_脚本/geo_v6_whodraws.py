# -*- coding: utf-8 -*-
import glob, io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright
ROOT = r"E:\3-其他资料\数据分析"
html = max(glob.glob(os.path.join(ROOT, "sales_analytics_platform", "output", "dashboard", "*.html")), key=os.path.getmtime)
url = "file:///" + html.replace("\\", "/").replace(" ", "%20")
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1100})
    pg.goto(url, wait_until="domcontentloaded")
    pg.wait_for_timeout(2500)
    r = pg.evaluate("""
      (function(){
        var c=TABS.charts.get('geoMap');
        var cs=c.getModel().getComponent('series',0).coordinateSystem;
        var m=echarts.getMap('china');
        var feats=(m.geoJSON||m).features||[];
        var out=[];
        feats.forEach(function(f){
          var pr=f.properties||{};
          (f.geometry.coordinates||[]).forEach(function(poly,pi){
            var xs=[],ys=[];
            poly.forEach(function(ring){ring.forEach(function(pt){var p=cs.dataToPoint(pt);xs.push(p[0]);ys.push(p[1]);});});
            var bb=[Math.min.apply(0,xs),Math.min.apply(0,ys),Math.max.apply(0,xs),Math.max.apply(0,ys)];
            // 画布右下区域 (700~1000, 420~620)
            if(bb[2]>700&&bb[3]>420&&bb[0]<1000&&bb[1]<620){
              out.push({name:pr.name||'(blank)',adcode:pr.adcode,pi:pi,px:[Math.round(bb[0]),Math.round(bb[1]),Math.round(bb[2]),Math.round(bb[3])]});
            }
          });
        });
        return out.slice(0,30);
      })()""")
    for x in r:
        print(x)
    b.close()
