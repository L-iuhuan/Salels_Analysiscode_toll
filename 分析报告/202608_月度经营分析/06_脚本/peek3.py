# -*- coding: utf-8 -*-
import json
rd = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\report_data.json", encoding="utf-8"))
out = []
out.append("== zengliu (增加及流失) ==")
z = rd["zengliu"]
out.append(f"type={type(z).__name__}")
if isinstance(z, dict):
    for k, v in z.items():
        out.append(f"--- {k} ---")
        out.append(json.dumps(v, ensure_ascii=False)[:2000])
else:
    out.append(json.dumps(z, ensure_ascii=False)[:4000])
out.append("")
out.append("== pl_top (产品线) ==")
out.append(json.dumps(rd["pl_top"], ensure_ascii=False))
out.append("")
out.append("== cost_up (成本上升品类) ==")
out.append(json.dumps(rd["cost_up"], ensure_ascii=False))
out.append("")
out.append("== bands ==")
out.append(json.dumps(rd["bands"], ensure_ascii=False))
out.append("")
out.append("== newp ==")
out.append(json.dumps(rd["newp"], ensure_ascii=False))
out.append("")
out.append("== dom_top 数码/充电头 newm ==")
for d in rd["dom_top"]:
    out.append(f"{d['name']}: newm={d.get('newm')}, newrev={d.get('newrev')}, pen={d.get('pen')}, m_y={d.get('m_y')}")
out.append("")
out.append("== dom_new_top ==")
out.append(json.dumps(rd["dom_new_top"], ensure_ascii=False))
out.append("")
out.append("== dcdc18 ==")
out.append(json.dumps(rd["dcdc18"], ensure_ascii=False))
out.append("== sti ==")
out.append(json.dumps(rd["sti"], ensure_ascii=False))
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\peek3.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
