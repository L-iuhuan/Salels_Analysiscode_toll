# -*- coding: utf-8 -*-
import glob, io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright
ROOT = r"E:\3-其他资料\数据分析"
html = max(glob.glob(os.path.join(ROOT, "sales_analytics_platform", "output", "dashboard", "*.html")), key=os.path.getmtime)
url = "file:///" + html.replace("\\", "/").replace(" ", "%20")
SHOT = r"C:\Users\910373\AppData\Local\Temp\opencode"
ok = True
def check(name, cond, detail=""):
    global ok
    print(("PASS" if cond else "FAIL"), name, detail)
    if not cond: ok = False
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
        var opt=c.getOption();
        var s=opt.series[0];
        var insetStyle=document.getElementById('geoNhInset').style.display;
        var chipBg=(document.querySelector('#geoMap').parentElement.querySelector('span[style*="background:#D1D5DB"]')||{}).style?true:false;
        return {regionCount:regions.length, hasNh:regions.indexOf('南海诸岛')>=0,
                seriesMap:s.map, selectedMode:s.selectedMode,
                emph:s.emphasis&&s.emphasis.itemStyle&&s.emphasis.itemStyle.areaColor,
                base:s.itemStyle&&s.itemStyle.areaColor,
                insetStyle:insetStyle, chipBg:chipBg,
                gd:(typeof geoAbroadToggle==='undefined')};
      })()""")
    check("item1 regionCount=34", r["regionCount"] == 34, str(r["regionCount"]))
    check("item1 主图无南海诸岛region", not r["hasNh"])
    check("item1 seriesMap=china_main", r["seriesMap"] == "china_main", r["seriesMap"])
    check("item1 inset可见", r["insetStyle"] != "none", r["insetStyle"])
    check("item2 无数据chip=#D1D5DB", r["chipBg"] is True)
    check("item2 底图areaColor=#D1D5DB", r["base"] == "#D1D5DB", r["base"])
    check("item3 selectedMode=false", r["selectedMode"] is False, str(r["selectedMode"]))
    check("item3 emphasis蓝系非黄", r["emph"] == "#BFDBFE", r["emph"])
    check("item4 geoAbroadToggle已删", r["gd"] is True)
    # item4 DOM: 行onclick=geoOpenDrawer、无geoAbX展开行
    d = pg.evaluate("""
      (function(){
        var el=document.getElementById('geoAbroad');
        var rows=el.querySelectorAll('div[onclick^="geoOpenDrawer"]');
        var bad=el.querySelectorAll('[id^="geoAbX"],[onclick^="geoAbroadToggle"]');
        return {rowCount:rows.length, badCount:bad.length,
                firstOnclick:rows.length?rows[0].getAttribute('onclick'):''};
      })()""")
    check("item4 行点击=geoOpenDrawer", d["rowCount"] > 0 and "geoOpenDrawer" in d["firstOnclick"], d["firstOnclick"][:50])
    check("item4 无展开行/旧handler", d["badCount"] == 0, str(d["badCount"]))
    # item4 点击海外行 -> drawer 打开
    pg.evaluate("document.getElementById('geoAbroad').querySelector('div[onclick^=\"geoOpenDrawer\"]').click()")
    pg.wait_for_timeout(800)
    dr = pg.evaluate("""
      (function(){
        var d=document.querySelector('.geo-drawer, [id*=\"geoDrawer\"], .drawer');
        var vis=false,txt='';
        document.querySelectorAll('div').forEach(function(x){var st=getComputedStyle(x);if((st.position==='fixed'||st.position==='absolute')&&st.display!=='none'&&st.visibility!=='hidden'&&x.offsetHeight>80&&x.innerText&&x.innerText.length>10&&x.innerText.length<600){vis=true;txt=x.innerText.slice(0,80);}});
        return {vis:vis,txt:txt};
      })()""")
    check("item4 点击行弹出明细", dr["vis"], dr["txt"].replace("\n"," "))
    pg.wait_for_timeout(400)
    pg.screenshot(path=os.path.join(SHOT, "geo_v6_after.png"))
    b.close()
print("ALL_PASS" if ok else "HAS_FAIL")
