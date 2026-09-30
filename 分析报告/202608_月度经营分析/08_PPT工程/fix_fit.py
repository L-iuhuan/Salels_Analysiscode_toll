# -*- coding: utf-8 -*-
"""fix_fit.py - 图表图片 fit 统一为 contain（防裁切标签）；封面背景除外."""
import glob
import os
import re

PAGES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pptd", "pages")
for f in sorted(glob.glob(os.path.join(PAGES, "*.page"))):
    if os.path.basename(f) == "1_cover.page":
        continue  # 封面背景满版 cover 是设计意图
    with open(f, encoding="utf-8") as fh:
        t = fh.read()
    lines = t.split("\n")
    out = []
    changed = False
    for idx, ln in enumerate(lines):
        out.append(ln)
        m = re.match(r"(\s*)src: media/p\S+", ln)
        if m:
            nxt = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
            if not nxt.startswith("fit:"):
                indent = m.group(1)
                out.append(f"{indent}fit:")
                out.append(f"{indent}  mode: contain")
                changed = True
    t2 = "\n".join(out)
    t2 = t2.replace("mode: cover", "mode: contain")
    if t2 != t:
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(t2)
        print("FIXED", os.path.basename(f))
print("done")
