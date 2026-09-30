# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright
JS = """
(function(){
  if(typeof echarts==='undefined')return 'echarts undefined';
  var m=echarts.getMap('china');
  if(!m)return 'no built-in china';
  var f=(m.geoJSON&&m.geoJSON.features)||[];
  return 'built-in china features='+f.length+' names sample='+f.slice(0,3).map(function(x){return x.properties&&x.properties.name}).join('/');
})()
"""
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.goto("https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js")
    pg.wait_for_timeout(1500)
    print(pg.evaluate(JS))
    b.close()
