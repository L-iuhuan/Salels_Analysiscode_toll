# -*- coding: utf-8 -*-
r"""生成5张报告图表PNG via AntV gpt-vis API"""
import json
import ssl
import urllib.request
import os

OUTDIR = r"C:\Users\910373\AppData\Local\Temp\opencode\build\charts"
os.makedirs(OUTDIR, exist_ok=True)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

charts = {
    "chart1_月度趋势": {
        "type": "dual-axes", "source": "chart-visualization-skills",
        "title": "2026年月度收入与毛利率走势(1-8月)", "width": 640, "height": 360,
        "categories": ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月"],
        "series": [
            {"type": "column", "data": [8615, 5257, 6375, 8536, 6928, 7369, 7760, 6903], "axisYTitle": "收入(万元)"},
            {"type": "line", "data": [34.94, 33.22, 34.88, 34.77, 34.80, 32.63, 30.25, 30.68], "axisYTitle": "毛利率(%)"},
        ],
    },
    "chart2_毛利桥环比": {
        "type": "waterfall", "source": "chart-visualization-skills",
        "title": "8月环比毛利桥四因子(万元,可比447个SKU)", "width": 640, "height": 380,
        "axisYTitle": "万元",
        "data": [
            {"category": "量效应", "value": -436},
            {"category": "价效应", "value": 62},
            {"category": "成本效应", "value": 8},
            {"category": "结构效应", "value": 2671},
            {"category": "可比毛利净变动", "value": -220, "isTotal": True},
        ],
    },
    "chart3_四因子月度": {
        "type": "line", "source": "chart-visualization-skills",
        "title": "毛利桥四因子月度序列(2-8月,万元)", "width": 640, "height": 380,
        "axisYTitle": "万元",
        "data": [
            {"time": "2月", "value": -1216, "group": "量效应"}, {"time": "2月", "value": 1592, "group": "结构效应"}, {"time": "2月", "value": -48, "group": "价效应"}, {"time": "2月", "value": -16, "group": "成本效应"},
            {"time": "3月", "value": 329, "group": "量效应"}, {"time": "3月", "value": 1756, "group": "结构效应"}, {"time": "3月", "value": -190, "group": "价效应"}, {"time": "3月", "value": 12, "group": "成本效应"},
            {"time": "4月", "value": 667, "group": "量效应"}, {"time": "4月", "value": 2563, "group": "结构效应"}, {"time": "4月", "value": 105, "group": "价效应"}, {"time": "4月", "value": 16, "group": "成本效应"},
            {"time": "5月", "value": -882, "group": "量效应"}, {"time": "5月", "value": 2259, "group": "结构效应"}, {"time": "5月", "value": -72, "group": "价效应"}, {"time": "5月", "value": -27, "group": "成本效应"},
            {"time": "6月", "value": 460, "group": "量效应"}, {"time": "6月", "value": 1748, "group": "结构效应"}, {"time": "6月", "value": -57, "group": "价效应"}, {"time": "6月", "value": -73, "group": "成本效应"},
            {"time": "7月", "value": 357, "group": "量效应"}, {"time": "7月", "value": 2414, "group": "结构效应"}, {"time": "7月", "value": -82, "group": "价效应"}, {"time": "7月", "value": -66, "group": "成本效应"},
            {"time": "8月", "value": -436, "group": "量效应"}, {"time": "8月", "value": 2671, "group": "结构效应"}, {"time": "8月", "value": 62, "group": "价效应"}, {"time": "8月", "value": 8, "group": "成本效应"},
        ],
    },
    "chart4_中兴康讯": {
        "type": "dual-axes", "source": "chart-visualization-skills",
        "title": "中兴康讯1-8月分品类收入与利润(万元)", "width": 640, "height": 380,
        "categories": ["DCDC-18V-降压2~4A", "LDO通用/双通道", "PSE", "DCDC-18V-降压5~12A", "USB及其他"],
        "series": [
            {"type": "column", "data": [1939, 96, 93, 88, 39], "axisYTitle": "收入(万元)"},
            {"type": "line", "data": [-225, 27, 33, 22, 15], "axisYTitle": "利润(万元)"},
        ],
    },
    "chart5_KA利润变化": {
        "type": "bar", "source": "chart-visualization-skills",
        "title": "KA客户利润同比变化TOP(1-8月,万元)", "width": 640, "height": 400,
        "axisXTitle": "利润同比变化(万元)", "stack": False,
        "data": [
            {"category": "追觅", "value": -505},
            {"category": "中兴康讯", "value": -333},
            {"category": "小米集团", "value": -222},
            {"category": "长虹集团", "value": -64},
            {"category": "海信集团", "value": -38},
            {"category": "创维数字", "value": 82},
            {"category": "TPLINK", "value": 84},
            {"category": "大华集团", "value": 87},
            {"category": "海康威视", "value": 323},
            {"category": "石头", "value": 331},
        ],
    },
}

results = {}
for name, payload in charts.items():
    req = urllib.request.Request(
        "https://antv-studio.alipay.com/api/gpt-vis",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
        r = json.loads(resp.read().decode("utf-8"))
    if not r.get("success"):
        results[name] = f"API-FAIL {r.get('errorMessage')}"
        continue
    url = r["resultObj"]
    fn = os.path.join(OUTDIR, name + ".png")
    req2 = urllib.request.Request(url)
    with urllib.request.urlopen(req2, context=ctx, timeout=120) as resp2:
        data = resp2.read()
    open(fn, "wb").write(data)
    results[name] = f"OK {len(data)//1024}KB -> {fn}"

open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\charts\gen_result.txt", "w", encoding="utf-8").write("\n".join(f"{k}: {v}" for k, v in results.items()))
print("CHARTS_DONE")
