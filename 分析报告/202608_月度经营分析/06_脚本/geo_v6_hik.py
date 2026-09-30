# -*- coding: utf-8 -*-
import glob, io, json, os, re, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = r"E:\3-其他资料\数据分析"
html = max(glob.glob(os.path.join(ROOT, "sales_analytics_platform", "output", "dashboard", "*.html")), key=os.path.getmtime)
src = open(html, encoding="utf-8").read()
def extract(name):
    m = re.search(r"var " + name + r" = (\{.*?\}|\[.*?\]);(?=\s*(?:var |</script>|\n))", src, re.S)
    return m.group(1) if m else None
geo = json.loads(extract("GEO_TOP5"))
print("GEO_TOP5 keys:", list(geo.keys()) if isinstance(geo, dict) else type(geo))
zj = geo.get("浙江") if isinstance(geo, dict) else None
print("浙江 entries:")
for e in (zj or []):
    print("  ", {k: e[k] for k in e if k != "trend"})
# 海康 in 浙江 top5?
hk = [e for e in (zj or []) if "海康" in str(e.get("n", ""))]
print("海康 entry:", hk)
# E_CUST_MONTHLY: find 海康威视
cm = json.loads(extract("E_CUST_MONTHLY"))
# structure? keys likely cust keys -> monthly arrays
print("E_CUST_MONTHLY type:", type(cm).__name__, "len:", len(cm))
def find_hk(obj, path=""):
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if "海康" in str(k):
                hits.append((path + "/" + str(k), v))
            else:
                hits += find_hk(v, path + "/" + str(k)[:30])
    return hits
hits = find_hk(cm)
for p, v in hits[:5]:
    print("PATH", p)
    print("VAL", json.dumps(v, ensure_ascii=False)[:500])
