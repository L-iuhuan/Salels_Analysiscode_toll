# -*- coding: utf-8 -*-
import sys, pathlib, json
from playwright.sync_api import sync_playwright

HTML = sys.argv[1]
OUT = pathlib.Path(r"C:\Users\910373\AppData\Local\Temp\opencode\geo_probe")
GEO = json.load(open(r"E:\3-其他资料\数据分析\sales_analytics_platform\dashboard\geo\china.json", encoding="utf-8"))

NAMES = ["台湾省", "100000_JD", "海南省", "香港特别行政区", "澳门特别行政区", "广东省"]

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1100}, device_scale_factor=2)
    pg.goto(pathlib.Path(HTML).as_uri())
    pg.wait_for_timeout(2800)
    pg.locator("#geoMap").scroll_into_view_if_needed()
    pg.wait_for_timeout(400)
    box = pg.locator("#geoMap").bounding_box()
    clip = {"x": box["x"] + box["width"] - 420, "y": box["y"] + box["height"] - 340, "width": 420, "height": 340}
    for nm in NAMES:
        pg.evaluate("""(arg) => {
          const chart = TABS.charts.get('geoMap');
          const feats = arg.geo.features.filter(f => {
            const p = f.properties || {};
            return String(p.name || p.adcode) === arg.name;
          });
          echarts.registerMap('china', {type: 'FeatureCollection', features: feats});
          const opt = chart.getOption();
          chart.setOption(opt, true);
        }""", {"geo": GEO, "name": nm})
        pg.wait_for_timeout(150)
        pg.screenshot(path=str(OUT / f"only_{nm.replace('|','_')}.png"), clip=clip)
    b.close()
print("done")
