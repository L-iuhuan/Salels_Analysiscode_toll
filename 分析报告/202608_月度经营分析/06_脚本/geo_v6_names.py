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
        var regions=(cs.regions||[]).map(function(rg){return rg.name});
        var m=echarts.getMap('china_nh');
        var nhFeats=((m.geoJSON||m).features||[]).map(function(f){return (f.properties&&f.properties.name)+'|'+((f.properties||{}).adcode||'')});
        return {regions:regions, nhFeats:nhFeats};
      })()""")
    print("regions(35):", r["regions"])
    print("china_nh feats:", r["nhFeats"])
    b.close()
