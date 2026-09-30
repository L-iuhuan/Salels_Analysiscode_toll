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
        var w=document.getElementById('geoMap').parentElement;
        var out=[];
        [].forEach.call(w.querySelectorAll('*'),function(el){
          var rc=el.getBoundingClientRect();
          if(rc.width<20||rc.height<20)return;
          out.push([el.tagName, el.id||'', (el.getAttribute('style')||'').slice(0,80), Math.round(rc.left), Math.round(rc.top), Math.round(rc.width), Math.round(rc.height)]);
        });
        return out;
      })()""")
    for x in r:
        print(x)
    b.close()
