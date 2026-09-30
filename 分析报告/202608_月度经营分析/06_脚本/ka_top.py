# -*- coding: utf-8 -*-
import json
sup = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\supplement.json", encoding="utf-8"))
out = []
for k in ("KA利润拖累TOP", "KA利润提升TOP"):
    out.append(f"== {k} ==")
    for it in sup[k]:
        vals = list(it.values())
        out.append(f"{vals[0]}: YTD利润{vals[1]}, 同比{vals[2]:+.0f}")
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\ka_top.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
