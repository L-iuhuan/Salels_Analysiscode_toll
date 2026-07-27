# -*- coding: utf-8 -*-
"""M3 残留解剖(2): ALL / E_SEL_MONTHS 原值 + D_DEPT_LIST 差异字段"""
import json, re, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

VAR_RE = re.compile(r"var\s+([A-Z_0-9]+)\s*=\s*(.*);\s*$")
def extract(path):
    vs = {}
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("var "):
                m = VAR_RE.match(line.rstrip("\n"))
                if m: vs[m.group(1)] = m.group(2)
    return vs

pa = extract(r"E:\3-其他资料\数据分析\sales_analytics_platform\dashboard\dashboard_a.html")
ba = extract(r"E:\3-其他资料\数据分析\工作文件\semiconductor_analysis\dashboard\dashboard_a.html")

for v in ["ALL", "E_SEL_MONTHS"]:
    print(f"{v}:\n  平台: {pa.get(v,'')}\n  ②  : {ba.get(v,'')}\n")

a = json.loads(pa["D_DEPT_LIST"]); b = json.loads(ba["D_DEPT_LIST"])
for i, (x, y) in enumerate(zip(a, b)):
    if x != y:
        print(f"D_DEPT_LIST[{i}] {x.get('name')}:")
        for k in set(x) | set(y):
            if x.get(k) != y.get(k):
                print(f"  {k}: 平台={x.get(k)!r}  ②={y.get(k)!r}")

# F_PRODUCT_LIST / PROD_CHANGE: 验证"同集合不同序"
fa = json.loads(pa["F_PRODUCT_LIST"]); fb = json.loads(ba["F_PRODUCT_LIST"])
na = sorted(p["name"] for p in fa); nb = sorted(p["name"] for p in fb)
print(f"\nF_PRODUCT_LIST: 名称集合相同={na==nb} (平台{len(na)} ②{len(nb)})")
# 同名产品的字段值是否一致
ma = {p["name"]: p for p in fa}; mb = {p["name"]: p for p in fb}
diff_names = [n for n in na if ma[n] != mb[n]]
print(f"同名字段值有差异的产品数: {len(diff_names)}  示例: {diff_names[:5]}")
if diff_names:
    n = diff_names[0]
    for k in set(ma[n]) | set(mb[n]):
        if ma[n].get(k) != mb[n].get(k):
            print(f"  {n}.{k}: 平台={ma[n].get(k)!r}  ②={mb[n].get(k)!r}")

ca = json.loads(pa["PROD_CHANGE"]); cb = json.loads(ba["PROD_CHANGE"])
ia = sorted(c["cid"] for c in ca); ib = sorted(c["cid"] for c in cb)
print(f"\nPROD_CHANGE: cid集合相同={ia==ib} (平台{len(ia)} ②{len(ib)})")
xa = {c["cid"]: c for c in ca}; xb = {c["cid"]: c for c in cb}
diffc = [c for c in ia if xa[c] != xb[c]]
print(f"同cid字段值有差异的客户数: {len(diffc)}  示例: {diffc[:5]}")
if diffc:
    c0 = diffc[0]
    ka, kb = json.dumps(xa[c0], ensure_ascii=False, sort_keys=True), json.dumps(xb[c0], ensure_ascii=False, sort_keys=True)
    for i in range(min(len(ka), len(kb))):
        if ka[i] != kb[i]:
            print(f"  {c0} 首个字符差异@{i}: 平台...{ka[max(0,i-40):i+60]}...\n{' '*16}②  ...{kb[max(0,i-40):i+60]}...")
            break
