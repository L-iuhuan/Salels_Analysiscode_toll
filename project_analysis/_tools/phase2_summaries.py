# -*- coding: utf-8 -*-
"""阶段二b:启发式摘要生成 + 低置信清单导出。
先读 docstring/头部注释生成摘要初稿;无线索的文件导出待 agent 补写。
"""
import json, os, re

ANALYSIS_DIR = r"E:\3-其他资料\数据分析\project_analysis"
CARDS_JSON = os.path.join(ANALYSIS_DIR, "01_function_cards.json")

def heuristic_summary(card):
    doc = (card.get("docstring") or "").strip()
    if doc:
        first = re.split(r"[\n。!?]", doc)[0].strip()
        first = re.sub(r"^[=\-*#\s]+|[=\-*#\s]+$", "", first)
        if 4 <= len(first) <= 80:
            return first, "docstring"
        return doc[:60], "docstring_trunc"
    head = (card.get("head_comment") or "").strip()
    if head and len(head) >= 4:
        return head[:60], "head_comment"
    return "", "needs_agent"

def main():
    cards = json.load(open(CARDS_JSON, encoding="utf-8"))
    needs, seen = [], set()
    src_cnt = {}
    for c in cards:
        s, src = heuristic_summary(c)
        c["summary"] = s
        c["summary_source"] = src
        src_cnt[src] = src_cnt.get(src, 0) + 1
        if src == "needs_agent" and c["sha1"] not in seen:
            seen.add(c["sha1"])
            needs.append({"file": c["file"], "loc": c.get("loc", 0),
                          "key_libraries": c["key_libraries"],
                          "internal_imports": c["internal_imports"]})
    with open(CARDS_JSON, "w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)
    needs_path = os.path.join(ANALYSIS_DIR, "01_needs_agent_summary.json")
    with open(needs_path, "w", encoding="utf-8") as f:
        json.dump(needs, f, ensure_ascii=False, indent=2)
    print(json.dumps({"summary_sources": src_cnt, "needs_agent_unique": len(needs)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
