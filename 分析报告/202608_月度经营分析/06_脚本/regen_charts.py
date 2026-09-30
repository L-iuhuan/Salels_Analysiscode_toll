# -*- coding: utf-8 -*-
r"""重生成chart2(环比瀑布带起终点)/chart2b(同比瀑布)/chart3(修正四因子序列)"""
import json
import ssl
import urllib.request
import os

OUTDIR = r"C:\Users\910373\AppData\Local\Temp\opencode\build\charts"
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

SER = {  # 月: (量, 结构, 价, 成本)
    "1月": (799, -66, -131, 28),
    "2月": (-1122, 53, -48, -16),
    "3月": (269, 293, -190, 12),
    "4月": (667, -32, 105, 16),
    "5月": (-859, 400, -72, -27),
    "6月": (430, -364, -57, -73),
    "7月": (369, -229, -82, -66),
    "8月": (-461, 171, 62, 8),
}

charts = {
    "chart2_毛利桥环比": {
        "type": "waterfall", "source": "chart-visualization-skills",
        "title": "8月环比毛利桥:7月可比毛利2274万→8月2054万(万元)", "width": 660, "height": 400,
        "axisYTitle": "万元",
        "data": [
            {"category": "7月可比毛利", "value": 2274, "isTotal": True},
            {"category": "量效应", "value": -461},
            {"category": "价效应", "value": 62},
            {"category": "成本效应", "value": 8},
            {"category": "结构效应", "value": 171},
            {"category": "8月可比毛利", "value": 2054, "isTotal": True},
        ],
    },
    "chart2b_毛利桥同比": {
        "type": "waterfall", "source": "chart-visualization-skills",
        "title": "8月同比毛利桥:去年8月可比毛利1989万→今年8月1868万(万元)", "width": 660, "height": 400,
        "axisYTitle": "万元",
        "data": [
            {"category": "去年8月可比毛利", "value": 1989, "isTotal": True},
            {"category": "量效应", "value": 313},
            {"category": "价效应", "value": -470},
            {"category": "成本效应", "value": -33},
            {"category": "结构效应", "value": 70},
            {"category": "今年8月可比毛利", "value": 1868, "isTotal": True},
        ],
    },
    "chart3_四因子月度": {
        "type": "line", "source": "chart-visualization-skills",
        "title": "毛利桥四因子月度序列(2026年1-8月,万元)", "width": 660, "height": 400,
        "axisYTitle": "万元",
        "data": [],
    },
}
for m, (q, s, p, c) in SER.items():
    charts["chart3_四因子月度"]["data"] += [
        {"time": m, "value": q, "group": "量效应"},
        {"time": m, "value": s, "group": "结构效应"},
        {"time": m, "value": p, "group": "价效应"},
        {"time": m, "value": c, "group": "成本效应"},
    ]

results = {}
for name, payload in charts.items():
    req = urllib.request.Request(
        "https://antv-studio.alipay.com/api/gpt-vis",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
        r = json.loads(resp.read().decode("utf-8"))
    if not r.get("success"):
        results[name] = "API-FAIL " + str(r.get("errorMessage"))
        continue
    fn = os.path.join(OUTDIR, name + ".png")
    with urllib.request.urlopen(urllib.request.Request(r["resultObj"]), context=ctx, timeout=120) as resp2:
        data = resp2.read()
    open(fn, "wb").write(data)
    results[name] = "OK {}KB".format(len(data) // 1024)

open(os.path.join(OUTDIR, "regen_result.txt"), "w", encoding="utf-8").write("\n".join(f"{k}: {v}" for k, v in results.items()))
print("REGEN_DONE")
