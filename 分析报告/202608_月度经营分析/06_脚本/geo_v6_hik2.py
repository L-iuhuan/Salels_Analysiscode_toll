# -*- coding: utf-8 -*-
import glob, io, json, os, re, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = r"E:\3-其他资料\数据分析"
html = max(glob.glob(os.path.join(ROOT, "sales_analytics_platform", "output", "dashboard", "*.html")), key=os.path.getmtime)
src = open(html, encoding="utf-8").read()
def extract(name):
    m = re.search(r"var " + name + r" = (\{.*?\}|\[.*?\]);(?=\s*(?:var |</script>|\n))", src, re.S)
    return m.group(1) if m else None
cm = json.loads(extract("E_CUST_MONTHLY"))
hk = cm["海康威视"]
cur_years = sorted({k[:4] for k in hk})
print("years:", cur_years, "months:", len(hk))
for y in cur_years:
    vals = {m: hk.get("%s-%s" % (y, m), {}).get("r", 0) for m in ["01","02","03","04","05","06","07","08"]}
    ytd = sum(vals.values())
    print(y, "YTD(1-8月):", round(ytd, 2), "月度:", {m: round(v,1) for m, v in vals.items()})
y_cur = max(cur_years); y_prev = str(int(y_cur) - 1)
a = sum(hk.get("%s-%02d" % (y_cur, m), {}).get("r", 0) for m in range(1, 9))
b = sum(hk.get("%s-%02d" % (y_prev, m), {}).get("r", 0) for m in range(1, 9))
print("本年YTD:", round(a,2), "上年同期YTD:", round(b,2))
print("yoy %%:", round((a - b) / b * 100, 1) if b else "inf")
# 全年 vs 全年(若上年有全年)?
full_prev = sum(v["r"] for k, v in hk.items() if k.startswith(y_prev))
print("上年全年:", round(full_prev, 2), "yoy全年口径%%:", round((a - full_prev) / full_prev * 100, 1))
# 近12月口径（r=1834.7 对应 GEO r）-> 找近12月窗口
months_sorted = sorted(hk.keys())
last12 = months_sorted[-12:]
s12 = sum(hk[m]["r"] for m in last12)
prev12 = months_sorted[-24:-12]
s12p = sum(hk[m]["r"] for m in prev12) if len(prev12) == 12 else None
print("last12:", last12[0], "->", last12[-1], "=", round(s12, 1))
print("prev12:", prev12[0] if prev12 else None, "->", prev12[-1] if prev12 else None, "=", round(s12p, 1) if s12p else None,
      "yoy%%=", round((s12 - s12p) / s12p * 100, 1) if s12p else "NA")
