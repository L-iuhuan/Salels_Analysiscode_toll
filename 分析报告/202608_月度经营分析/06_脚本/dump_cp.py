# -*- coding: utf-8 -*-
import json
jf = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\july_full.json", encoding="utf-8"))
out = []
for p in jf["paragraphs"]:
    if p["i"] in (37, 38, 72, 103, 206, 234, 297, 453, 550):
        t = p["t"]
        out.append(f"para {p['i']}: {t}")
        out.append("  codepoints[:20]: " + " ".join(f"{ord(c):04X}" for c in t[:20]))
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\cp_dump.txt", "w", encoding="utf-8").write("\n".join(out))
print("done")
