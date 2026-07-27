# -*- coding: utf-8 -*-
import os, re, json
ROOT = r"E:\3-其他资料\数据分析"
out = {}
# ② output 基线新鲜度
for d in ["silver", "gold", "report"]:
    p = os.path.join(ROOT, "工作文件", "semiconductor_analysis", "output", d)
    if os.path.isdir(p):
        files = [(f, os.path.getmtime(os.path.join(p, f))) for f in os.listdir(p) if os.path.isfile(os.path.join(p, f))]
        if files:
            import datetime
            f, t = max(files, key=lambda x: x[1])
            out[f"②output/{d}"] = f"{f} @ {datetime.datetime.fromtimestamp(t).strftime('%Y-%m-%d %H:%M')}"
# dashboard_a.html 基线
for k, p in [("②", os.path.join(ROOT, "工作文件", "semiconductor_analysis", "dashboard", "dashboard_a.html")),
             ("③", os.path.join(ROOT, "看板流水线", "dashboard", "dashboard_a.html"))]:
    out[f"dashboard_a.html {k}"] = (f"{os.path.getsize(p)/1048576:.1f}MB" if os.path.exists(p) else "不存在")
# ③ requirements.txt
req = os.path.join(ROOT, "看板流水线", "requirements.txt")
out["③requirements"] = open(req, encoding="utf-8").read().strip().splitlines() if os.path.exists(req) else "不存在"
# unified 输出路径常量
for f in ["unified_forecast_v3.py", "unified_forecast_system.py"]:
    src = open(os.path.join(ROOT, "semiconductor_analysis", f), encoding="utf-8").read()
    consts = re.findall(r"(?:OUTPUT|RANKING|RESULT|REPORT)[A-Z_]*\s*=\s*r?[\"']([^\"']+)[\"']", src)[:8]
    out[f] = consts
print(json.dumps(out, ensure_ascii=False, indent=1))
