# -*- coding: utf-8 -*-
import json
r = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\recompute.json", encoding="utf-8"))
out = ["月 | 收入 | 毛利率 | 量 | 结构 | 价 | 成本 | dGP | 量3 | 残差"]
for s in r["月度序列_重算"]:
    out.append("{} | {:.0f} | {:.2f}% | {:.0f} | {:.0f} | {:.0f} | {:.0f} | {:.0f} | {:.0f} | {}".format(
        s["月"], s["收入万"], s["毛利率"] * 100, s["量"], s["结构"], s["价"], s["成本"], s["dGP"], s["量3"], s["求和残差"]))
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\series_check.txt", "w", encoding="utf-8").write("\n".join(out))
print("OK")
