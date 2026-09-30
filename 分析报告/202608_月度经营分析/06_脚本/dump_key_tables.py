# -*- coding: utf-8 -*-
import json
d = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\july_full.json", encoding="utf-8"))
out = []
for t in d["tables"]:
    if t["ti"] in (4, 8, 9, 12, 13, 18, 19, 21, 22, 28, 29):
        out.append("== 表%d (%dx%d) ==" % (t["ti"], t["rows"], t["cols"]))
        for row in t["cells"]:
            out.append(" | ".join((c or "")[:22] for c in row))
        out.append("")
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\key_tables.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
