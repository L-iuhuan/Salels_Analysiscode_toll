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
        // regions rendered by this chart
        var regs=cs.map && cs.map._map ? null : null;
        var regions=(cs.regions||[]).map(function(rg){return rg.name});
        var m=echarts.getMap('china');
        var feats=((m.geoJSON||m).features||[]).length;
        // 画布该点颜色
        var cv=document.querySelector('#geoMap canvas');
        var ctx=cv.getContext('2d');
        var dpr=cv.width/cv.getBoundingClientRect().width;
        function px(x,y){var d=ctx.getImageData(Math.round(x*dpr),Math.round(y*dpr),1,1).data;return d[0]+','+d[1]+','+d[2];}
        return {regionCount:regions.length, hasJD:regions.indexOf('')>=0||regions.indexOf('南海诸岛')>=0,
                blankRegions:regions.filter(function(n){return !n}).length,
                registeredFeats:feats,
                sampleBoxTop:px(800,460), sampleBoxMid:px(820,500), sampleOutside:px(700,500)};
      })()""")
    print(r)
    b.close()
