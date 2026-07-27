# -*- coding: utf-8 -*-
"""阶段四:数据流拓扑重建。
输入: 01_function_cards.json + 02_clusters.json + 00_file_inventory.csv
输出: 03_data_flow_auto.json (组件/边/孤儿) + 03_shared_modules.md
方法: 对推荐版本集合(dedup)提取 脚本-数据 引用边,并查集成组件。
路径归一化: 去 ./、反斜杠、项目根前缀;先精确匹配,再唯一 basename 匹配。
"""
import json, os, csv
from collections import defaultdict

ANALYSIS_DIR = r"E:\3-其他资料\数据分析\project_analysis"
cards = json.load(open(os.path.join(ANALYSIS_DIR, "01_function_cards.json"), encoding="utf-8"))
clusters = json.load(open(os.path.join(ANALYSIS_DIR, "02_clusters.json"), encoding="utf-8"))
recommended = set(clusters["recommended"].values())
tags = clusters["tags"]

# 实际存在的数据文件(用于区分"代码引用"与"真实文件")
inv = list(csv.DictReader(open(os.path.join(ANALYSIS_DIR, "00_file_inventory.csv"), encoding="utf-8-sig")))
data_files = {r["file_path"].replace("\\", "/") for r in inv if r["role"] in ("数据",)}
data_basenames = defaultdict(list)
for d in data_files:
    data_basenames[os.path.basename(d)].append(d)

PROJECT_MARKERS = ("semiconductor_analysis_before/", "semiconductor_analysis/",
                   "工作文件/semiconductor_analysis/", "看板流水线/processing/",
                   "看板流水线/")

def norm_ref(p):
    p = p.strip().replace("\\", "/").lstrip("./")
    for m in PROJECT_MARKERS:
        if p.startswith(m):
            p = p[len(m):]
    return p

def canon(cards):
    seen = {}
    for c in cards:
        if c["file"] in recommended:
            seen[c["file"]] = c
    return list(seen.values())

scripts = canon(cards)

# ---- 边: script --writes--> data, script --reads--> data ----
writes, reads = defaultdict(set), defaultdict(set)   # data -> set(script)
ref_exists = {}
for c in scripts:
    f = c["file"]
    proj_prefix = f.rsplit("/", 1)[0] if "/" in f else ""
    for o in c["outputs"]:
        n = norm_ref(o)
        writes[n].add(f)
    for i in c["inputs"]:
        n = norm_ref(i)
        reads[n].add(f)

all_data = set(writes) | set(reads)
# 数据节点分类
def classify(d):
    w, r = d in writes, d in reads
    if w and r: return "intermediate"
    if w: return "final"
    return "raw"

# ---- 连通组件(脚本为节点,共享数据为连接) ----
parent = {c["file"]: c["file"] for c in scripts}
def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]; x = parent[x]
    return x
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb: parent[rb] = ra

for d in all_data:
    linked = list(writes.get(d, set()) | reads.get(d, set()))
    for s in linked[1:]:
        union(linked[0], s)

comps = defaultdict(lambda: {"scripts": [], "data": set()})
for c in scripts:
    comps[find(c["file"])]["scripts"].append(c["file"])
for d, ws in writes.items():
    for s in ws:
        if s in parent: comps[find(s)]["data"].add(d)
for d, rs in reads.items():
    for s in rs:
        if s in parent: comps[find(s)]["data"].add(d)

comp_list = []
for root, comp in comps.items():
    sc = sorted(comp["scripts"])
    dt = sorted(comp["data"])
    edges = []
    for d in dt:
        for w in writes.get(d, ()):
            if w in sc: edges.append({"from": w, "to": d, "kind": "write"})
        for r in reads.get(d, ()):
            if r in sc: edges.append({"from": d, "to": r, "kind": "read"})
    comp_list.append({
        "scripts": sc,
        "data": [{"ref": d, "class": classify(d),
                  "exists_on_disk": any(os.path.basename(d) == os.path.basename(x) for x in data_files)} for d in dt],
        "edges": edges,
        "tags": list({tags.get(s, "normal") for s in sc}),
    })
comp_list.sort(key=lambda x: -len(x["scripts"]))

# ---- 公共基础设施模块(被>=2个脚本 import 的项目内模块) ----
mod_users = defaultdict(set)
for c in scripts:
    for m in c["internal_imports"]:
        mod_users[m].add(c["file"])
shared_mods = sorted(((m, sorted(u)) for m, u in mod_users.items() if len(u) >= 2),
                     key=lambda x: -len(x[1]))

with open(os.path.join(ANALYSIS_DIR, "03_data_flow_auto.json"), "w", encoding="utf-8") as f:
    json.dump({"components": comp_list,
               "shared_modules": [{"module": m, "used_by": u} for m, u in shared_mods]},
              f, ensure_ascii=False, indent=2)

md = ["# 公共基础设施模块(被≥2个脚本引用)\n",
      "| 模块 | 引用脚本数 | 引用方(前8) |", "|---|---|---|"]
for m, u in shared_mods:
    md.append(f"| {m} | {len(u)} | {'<br>'.join(os.path.basename(x) for x in u[:8])} |")
with open(os.path.join(ANALYSIS_DIR, "03_shared_modules.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(md) + "\n")

print(json.dumps({
    "components": len(comp_list),
    "largest": [{"scripts": len(c["scripts"]), "data": len(c["data"]),
                 "tags": c["tags"], "sample": c["scripts"][:3]} for c in comp_list[:8]],
    "shared_modules": len(shared_mods),
    "isolated_scripts": sum(1 for c in comp_list if len(c["scripts"]) == 1 and not c["data"]),
}, ensure_ascii=False, indent=2))
