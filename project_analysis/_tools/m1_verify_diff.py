# -*- coding: utf-8 -*-
"""M1复核:独立对比②与③的10个覆盖目录的全部文件哈希,确认真实差异集。"""
import hashlib, os, json

ROOT = r"E:\3-其他资料\数据分析"
SRC2 = os.path.join(ROOT, "工作文件", "semiconductor_analysis")
SRC3 = os.path.join(ROOT, "看板流水线", "processing")
DIRS = ["config", "shared", "data_pipeline", "product_lifecycle", "customer_analysis",
        "cross_reference", "b2b_v2", "analysis", "reports", "core"]

def sha(p):
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

diff, only2, only3, same = [], [], [], 0
for top in DIRS:
    d2, d3 = os.path.join(SRC2, top), os.path.join(SRC3, top)
    files2, files3 = set(), set()
    for dp, dn, fn in os.walk(d2):
        dn[:] = [x for x in dn if x != "__pycache__"]
        for f in fn:
            if not f.endswith(".pyc"):
                files2.add(os.path.relpath(os.path.join(dp, f), d2))
    for dp, dn, fn in os.walk(d3):
        dn[:] = [x for x in dn if x != "__pycache__"]
        for f in fn:
            if not f.endswith(".pyc"):
                files3.add(os.path.relpath(os.path.join(dp, f), d3))
    for rel in sorted(files2 & files3):
        if sha(os.path.join(d2, rel)) != sha(os.path.join(d3, rel)):
            diff.append(f"{top}/{rel}")
        else:
            same += 1
    only2 += [f"{top}/{r}" for r in sorted(files2 - files3)]
    only3 += [f"{top}/{r}" for r in sorted(files3 - files2)]

print(json.dumps({"相同": same, "②③不同": diff, "仅②有": only2, "仅③有": only3},
                 ensure_ascii=False, indent=1))
