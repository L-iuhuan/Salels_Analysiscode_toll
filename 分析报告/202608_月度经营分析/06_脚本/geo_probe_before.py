# -*- coding: utf-8 -*-
"""CDP probe for geo section of dashboard product (pre-fix diagnosis)."""
import sys, json, pathlib
from playwright.sync_api import sync_playwright

HTML = sys.argv[1] if len(sys.argv) > 1 else None
OUT = pathlib.Path(r"C:\Users\910373\AppData\Local\Temp\opencode\geo_probe")
OUT.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1000})
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto(pathlib.Path(HTML).as_uri())
    pg.wait_for_timeout(2500)
    # make sure geo map built
    pg.evaluate("typeof initGeo==='function' && initGeo()")
    pg.wait_for_timeout(1500)
    info = pg.evaluate("""() => {
      const r = {};
      const china = echarts.getMap('china');
      r.china_features = china.geoJSON.features.map(f => (f.properties&&f.properties.name)||'?');
      const nh = echarts.getMap('china_nh');
      r.nh_ok = !!nh;
      if (nh) r.nh_features = nh.geoJSON.features.map(f => ({name:(f.properties&&f.properties.name)||'?', polys:f.geometry.coordinates.length}));
      const inset = document.getElementById('geoNhInset');
      r.inset_display = inset ? getComputedStyle(inset).display : 'MISSING';
      const chart = TABS.charts.get('geoMap');
      r.geoMap_option = chart ? {
        selectedMode: chart.getOption().series[0].selectedMode,
        emphasisArea: chart.getOption().series[0].emphasis && chart.getOption().series[0].emphasis.itemStyle,
        itemStyleArea: chart.getOption().series[0].itemStyle && chart.getOption().series[0].itemStyle.areaColor,
        pieces: chart.getOption().visualMap[0].pieces
      } : null;
      return r;
    }""")
    print(json.dumps(info, ensure_ascii=False, indent=1))
    el = pg.locator("#sec-geo")
    el.screenshot(path=str(OUT / "sec_geo_before.png"))
    b.close()
print("console errors:", errors[:5])
