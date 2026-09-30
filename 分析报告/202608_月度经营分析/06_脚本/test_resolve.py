# -*- coding: utf-8 -*-
import json
jf = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\july_full.json", encoding="utf-8"))
JP = [p["t"] for p in jf["paragraphs"] if p["t"]]
tests = ["2.1 整改跟踪", "H1整改清单", "放量但利润不增", "关键结论", "该单品", "两极分化", "净增SKU", "结构效应在", "推广方向", "整改跟踪", "落地率"]
res = []
for kw in tests:
    hits = [t for t in JP if kw in t]
    res.append(f"{kw!r}: {'HIT ' + repr(hits[0][:36]) if hits else 'NO-HIT'}")
# 检查特殊字符: 打印含'整改跟踪'文本的码点
for t in JP:
    if "整改跟踪" in t:
        res.append("codepoints: " + " ".join(f"{ord(c):04X}" for c in t[:14]))
        break
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\resolve_test.txt", "w", encoding="utf-8").write("\n".join(res))
print("done")
