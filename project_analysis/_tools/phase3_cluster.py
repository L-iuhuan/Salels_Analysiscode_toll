# -*- coding: utf-8 -*-
"""阶段三:功能去重与聚类。
输入: 01_function_cards.json
输出: 02_clusters.md (人类可读) + 02_clusters.json (供阶段四/五使用)
聚类维度:
  A. 跨项目版本变体组: 剥离项目根前缀后路径相同的文件(同一模块的不同年代版本)
  B. 完全重复组(同sha1) 在组内标注
  C. 唯一脚本: 按目录分组列出
  另打标签: junk(与数据分析无关) / temp(临时脚本)
"""
import json, os, re
from collections import defaultdict

ANALYSIS_DIR = r"E:\3-其他资料\数据分析\project_analysis"
CARDS_JSON = os.path.join(ANALYSIS_DIR, "01_function_cards.json")

PROJECT_PREFIXES = ["semiconductor_analysis_before/", "semiconductor_analysis/",
                    "工作文件/semiconductor_analysis/"]
BACKUP_HINTS = ("_before", "backup", "备份", "old")

def norm_key(path):
    for p in PROJECT_PREFIXES:
        if path.startswith(p):
            return path[len(p):]
    return path

def tag_of(card):
    s = card.get("summary", "")
    if "与数据分析无关" in s:
        return "junk"
    if re.search(r"临时(检查|入口|调试)脚本", s):
        return "temp"
    return "normal"

def recommend(members):
    """返回 (推荐file, 理由)"""
    def score(c):
        sc = 0
        fp = c["file"]
        if not any(h in fp.lower() for h in BACKUP_HINTS) and "_before/" not in fp:
            sc += 100
        sc += min(c.get("loc", 0), 500) / 500 * 10
        if c["has_main_guard"]:
            sc += 3
        qn = c.get("quality_notes", "")
        sc -= qn.count(";") + qn.count("语法错误") * 2
        sc += c["last_modified"].__hash__() % 0  # placeholder
        return sc
    live = [m for m in members if not any(h in m["file"].lower() for h in BACKUP_HINTS)
            and "semiconductor_analysis_before/" not in m["file"]]
    pool = live if live else members
    best = max(pool, key=lambda c: (c["last_modified"], c.get("loc", 0)))
    same = len({m["sha1"] for m in members}) == 1
    if same:
        reason = f"{len(members)}个完全相同的副本,推荐保留最常用项目位置的最新副本"
    else:
        reason = f"内容有差异,推荐非备份目录中最后修改({best['last_modified'][:10]})的版本"
    return best["file"], reason

def diff_desc(base, other):
    parts = []
    dl = other.get("loc", 0) - base.get("loc", 0)
    if dl:
        parts.append(f"行数{'多' if dl>0 else '少'}{abs(dl)}行")
    if other["has_main_guard"] != base["has_main_guard"]:
        parts.append("有main保护" if other["has_main_guard"] else "无main保护")
    io_b = set(base["inputs"]) | set(base["outputs"])
    io_o = set(other["inputs"]) | set(other["outputs"])
    if io_b != io_o and (io_b or io_o):
        parts.append("IO路径不同")
    if other.get("summary", "")[:20] != base.get("summary", "")[:20]:
        parts.append(f"摘要差异: {other.get('summary','')[:40]}")
    return "; ".join(parts) if parts else "结构相近"

def main():
    cards = json.load(open(CARDS_JSON, encoding="utf-8"))
    for c in cards:
        c["tag"] = tag_of(c)
        c["variant_key"] = norm_key(c["file"])
    groups = defaultdict(list)
    for c in cards:
        groups[c["variant_key"]].append(c)

    variant_groups = {k: v for k, v in groups.items() if len(v) > 1}
    singletons = {k: v[0] for k, v in groups.items() if len(v) == 1}
    identical_grp = {k: v for k, v in variant_groups.items() if len({m["sha1"] for m in v}) == 1}
    diverged_grp = {k: v for k, v in variant_groups.items() if len({m["sha1"] for m in v}) > 1}

    md = ["# 02 功能聚类报告\n",
          f"- 脚本总数: {len(cards)}(唯一内容 {len({c['sha1'] for c in cards})})",
          f"- 聚类单元(variant_key)总数: **{len(groups)}**",
          f"- 其中跨项目多版本组: {len(variant_groups)}(完全相同副本组 {len(identical_grp)},内容分叉组 {len(diverged_grp)})",
          f"- 唯一脚本: {len(singletons)}",
          f"- 标签分布: normal={sum(1 for c in cards if c['tag']=='normal')}, "
          f"temp(临时脚本)={sum(1 for c in cards if c['tag']=='temp')}, "
          f"junk(与数据分析无关)={sum(1 for c in cards if c['tag']=='junk')}\n",
          "> 说明: 「项目根前缀」指 semiconductor_analysis/、semiconductor_analysis_before/、",
          "> 工作文件/semiconductor_analysis/ —— 三者被识别为同一项目的不同年代副本。\n"]

    md.append("## A. 内容分叉的多版本组(需人工关注)\n")
    rec_map = {}
    for k in sorted(diverged_grp):
        members = sorted(diverged_grp[k], key=lambda c: -len(c["file"]))
        rec_file, reason = recommend(members)
        base = next(m for m in members if m["file"] == rec_file)
        rec_map[k] = rec_file
        sm = base.get("summary") or "(无摘要)"
        md.append(f"### `{k}` — {sm}\n")
        md.append(f"**推荐保留: `{rec_file}`** — {reason}\n")
        md.append("| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |")
        md.append("|---|---|---|---|---|---|")
        for m in sorted(members, key=lambda c: c["last_modified"], reverse=True):
            d = "(推荐)" if m["file"] == rec_file else diff_desc(base, m)
            md.append(f"| {m['file']} | {m.get('loc',0)} | {m['last_modified'][:10]} | "
                      f"{'√' if m['has_main_guard'] else '×'} | {m['tag']} | {d} |")
        md.append("")

    md.append("## B. 完全相同的多副本组(仅保留一份即可)\n")
    md.append("| 模块 | 副本数 | 副本位置 | 推荐保留 |")
    md.append("|---|---|---|---|")
    for k in sorted(identical_grp):
        members = identical_grp[k]
        rec_file, _ = recommend(members)
        rec_map[k] = rec_file
        locs = "<br>".join(m["file"] for m in members)
        md.append(f"| {k} | {len(members)} | {locs} | {rec_file} |")

    md.append("\n## C. 唯一脚本(无跨项目副本)\n")
    by_dir = defaultdict(list)
    for k, c in singletons.items():
        d = os.path.dirname(c["file"]) or "(根)"
        by_dir[d].append(c)
        rec_map[k] = c["file"]
    for d in sorted(by_dir):
        md.append(f"### {d}\n")
        md.append("| 文件 | 摘要 | 行数 | main | 标签 | 结论 |")
        md.append("|---|---|---|---|---|---|")
        for c in sorted(by_dir[d], key=lambda x: x["file"]):
            concl = {"normal": "唯一版本,建议保留",
                     "temp": "临时脚本,建议归档不入流水线",
                     "junk": "与数据分析无关,建议移出项目"}[c["tag"]]
            md.append(f"| {os.path.basename(c['file'])} | {c.get('summary','')[:38]} | "
                      f"{c.get('loc',0)} | {'√' if c['has_main_guard'] else '×'} | {c['tag']} | {concl} |")
        md.append("")

    uncertain = [k for k, v in diverged_grp.items()
                 if max(m["last_modified"] for m in v)[:10] == min(m["last_modified"] for m in v)[:10]]
    if uncertain:
        md.append("\n## D. 存疑(同日内分叉,无法按时间判断)\n")
        for k in uncertain:
            md.append(f"- `{k}`")
    with open(os.path.join(ANALYSIS_DIR, "02_clusters.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    with open(os.path.join(ANALYSIS_DIR, "02_clusters.json"), "w", encoding="utf-8") as f:
        json.dump({"groups": {k: [m["file"] for m in v] for k, v in groups.items()},
                   "recommended": rec_map,
                   "tags": {c["file"]: c["tag"] for c in cards}}, f, ensure_ascii=False, indent=2)
    print(json.dumps({"units": len(groups), "diverged": len(diverged_grp),
                      "identical": len(identical_grp), "singletons": len(singletons),
                      "uncertain": len(uncertain)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
