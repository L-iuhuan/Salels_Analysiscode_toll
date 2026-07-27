# -*- coding: utf-8 -*-
"""阶段二c:合并 agent 摘要 -> 01_function_cards.json"""
import json, os, sys

ANALYSIS_DIR = r"E:\3-其他资料\数据分析\project_analysis"
CARDS_JSON = os.path.join(ANALYSIS_DIR, "01_function_cards.json")
AGENT_JSON = os.path.join(ANALYSIS_DIR, "_tools", "agent_summaries.json")

cards = json.load(open(CARDS_JSON, encoding="utf-8"))
agent = json.load(open(AGENT_JSON, encoding="utf-8"))
smap = {a["file"].replace("\\", "/"): a["summary"] for a in agent}
# 按 sha1 传播:同一内容只需一个摘要
sha_summary = {}
for c in cards:
    f = c["file"].replace("\\", "/")
    if f in smap:
        sha_summary[c["sha1"]] = smap[f]
filled = 0
for c in cards:
    f = c["file"].replace("\\", "/")
    if f in smap:
        c["summary"] = smap[f]; c["summary_source"] = "agent"; filled += 1
    elif c.get("summary_source") == "needs_agent" and c["sha1"] in sha_summary:
        c["summary"] = sha_summary[c["sha1"]]; c["summary_source"] = "agent_via_dup"; filled += 1
left = [c["file"] for c in cards if not c.get("summary")]
with open(CARDS_JSON, "w", encoding="utf-8") as f:
    json.dump(cards, f, ensure_ascii=False, indent=2)
print(json.dumps({"filled": filled, "still_empty": len(left), "empty_files": left[:10]}, ensure_ascii=False))
