# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright
JS = """
(() => {
function feat(name){return {type:'Feature',properties:{name:name},geometry:{type:'Polygon',coordinates:[[[100,20],[101,20],[101,21],[100,21],[100,20]]]}};}
var results={};
var el=document.createElement('div');el.style.width='400px';el.style.height='300px';document.body.appendChild(el);
var ch=echarts.init(el);
// Step1: register china(34模拟:2 feats) then china_nh(1 feat 南海诸岛)
echarts.registerMap('china',{type:'FeatureCollection',features:[feat('北京市'),feat('上海市')]});
echarts.registerMap('china_nh',{type:'FeatureCollection',features:[feat('南海诸岛')]});
ch.setOption({series:[{type:'map',map:'china'}]});
var cs=ch.getModel().getComponent('series',0).coordinateSystem;
results.step1=(cs.regions||[]).map(function(r){return r.name});
// Step2: dispose and re-register china with different content; re-render
ch.dispose();
var el2=document.createElement('div');el2.style.width='400px';el2.style.height='300px';document.body.appendChild(el2);
var ch2=echarts.init(el2);
echarts.registerMap('china',{type:'FeatureCollection',features:[feat('北京市')]});
ch2.setOption({series:[{type:'map',map:'china'}]});
var cs2=ch2.getModel().getComponent('series',0).coordinateSystem;
results.step2=(cs2.regions||[]).map(function(r){return r.name});
results.step2registered=((echarts.getMap('china').geoJSON||{}).features||[]).length;
// Step3: same instance re-setOption after re-register
echarts.registerMap('china',{type:'FeatureCollection',features:[feat('北京市'),feat('天津市')]});
ch2.setOption({series:[{type:'map',map:'china'}]},true);
var cs3=ch2.getModel().getComponent('series',0).coordinateSystem;
results.step3=(cs3.regions||[]).map(function(r){return r.name});
return results;
})()
"""
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.goto("https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js")
    pg.wait_for_timeout(1500)
    # goto js url doesn't exec; use a data page + script tag
    pg2 = b.new_page()
    pg2.set_content("<html><body><script src='https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js'></script></body></html>")
    pg2.wait_for_timeout(2000)
    print(pg2.evaluate(JS))
    b.close()
