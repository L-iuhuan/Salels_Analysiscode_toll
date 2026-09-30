# -*- coding: utf-8 -*-
import json
sup = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\supplement.json", encoding="utf-8"))
rd = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\report_data.json", encoding="utf-8"))
out = []
out.append("桥_环比: " + json.dumps(sup["桥_环比"], ensure_ascii=False))
out.append("中兴康讯_品类YTD: " + json.dumps(sup["中兴康讯_品类YTD"], ensure_ascii=False))
out.append("中兴康讯_合计: " + json.dumps(sup["中兴康讯_合计"], ensure_ascii=False))
out.append("KA利润拖累TOP: " + json.dumps(sup["KA利润拖累TOP"], ensure_ascii=False))
out.append("KA利润提升TOP: " + json.dumps(sup["KA利润提升TOP"], ensure_ascii=False))
out.append("cls: " + json.dumps(rd["cls"], ensure_ascii=False)[:900])
out.append("top20类型: " + str(type(rd["top20"]).__name__))
t = rd["top20"]
if isinstance(t, list):
    out.append("top20前3: " + json.dumps(t[:3], ensure_ascii=False))
else:
    out.append("top20keys: " + json.dumps(list(t.keys())[:10], ensure_ascii=False))
    out.append("top20样例: " + json.dumps(t, ensure_ascii=False)[:600])
c36 = rd.get("cases36", [])
out.append("cases36类型: " + str(type(c36).__name__))
if isinstance(c36, list):
    out.append("cases36: " + json.dumps(c36[:5], ensure_ascii=False))
else:
    out.append("cases36: " + json.dumps(c36, ensure_ascii=False)[:800])
out.append("sku_var: " + json.dumps(rd["sku_var"], ensure_ascii=False)[:600])
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\peek2.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
