# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright
JS = """
(() => {
function feat(name){return {type:'Feature',properties:{name:name},geometry:{type:'Polygon',coordinates:[[[100,20],[101,20],[101,21],[100,21],[100,20]]]}};}
var results={};
function render(mapName){
  var el=document.createElement('div');el.style.width='300px';el.style.height='200px';document.body.appendChild(el);
  var ch=echarts.init(el);
  ch.setOption({series:[{type:'map',map:mapName}]});
  var cs=ch.getModel().getComponent('series',0).coordinateSystem;
  var r=(cs.regions||[]).map(function(x){return x.name});
  ch.dispose();el.remove();
  return r;
}
echarts.registerMap('china_main',{type:'FeatureCollection',features:[feat('北京市'),feat('上海市')]});
results.chinaMain=render('china_main');
echarts.registerMap('china_nh',{type:'FeatureCollection',features:[feat('南海诸岛'),feat('JD')]});
results.chinaNh=render('china_nh');
echarts.registerMap('guangdong',{type:'FeatureCollection',features:[feat('广州市')]});
results.guangdong=render('guangdong');
return results;
})()
"""
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.set_content("<html><body><script src='https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js'></script></body></html>")
    pg.wait_for_timeout(2000)
    print(pg.evaluate(JS))
    b.close()
