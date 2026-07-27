# -*- coding: utf-8 -*-
"""阶段一:全量资产扫描 -> 00_file_inventory.csv + 00_inventory_summary.md
只读操作:不修改任何原始文件。输出写入 project_analysis/。
"""
import os, sys, csv, hashlib, json
from datetime import datetime

ROOT = r"E:\3-其他资料\数据分析"
OUT_DIR = os.path.join(ROOT, "project_analysis")
EXCLUDE_DIRS = {"CoStrict", "project_analysis", "project_branches", "__pycache__"}
# __pycache__ 目录整体排除(构建产物噪声),在摘要中注明

ROLE_MAP = {
    ".py": "代码", ".bat": "代码", ".js": "代码",
    ".csv": "数据", ".xlsx": "数据", ".xls": "数据", ".pkl": "数据",
    ".db": "数据", ".zip": "数据", ".rar": "数据",
    ".png": "输出", ".pdf": "输出", ".svg": "输出", ".html": "输出",
    ".md": "文档", ".txt": "文档", ".docx": "文档", ".pptx": "文档",
    ".gitignore": "配置", ".code-workspace": "配置", ".tag": "配置",
    ".silver_checksum": "配置",
}
CONFIG_NAME_HINTS = ("config", "setting", "settings", "params", "threshold")

def guess_role(ext: str, name: str) -> str:
    ext = ext.lower()
    if ext == ".json":
        stem = os.path.splitext(name)[0].lower()
        if any(h in stem for h in CONFIG_NAME_HINTS):
            return "配置"
        return "数据"
    return ROLE_MAP.get(ext, "未知")

def sha1_of(path: str) -> str:
    h = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rows = []
    skipped_pycache = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            rel = os.path.relpath(fp, ROOT)
            try:
                st = os.stat(fp)
            except OSError:
                continue
            ext = os.path.splitext(fn)[1]
            row = {
                "file_path": rel,
                "file_name": fn,
                "extension": ext.lower() or "(无)",
                "size_kb": round(st.st_size / 1024, 1),
                "last_modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "role": guess_role(ext, fn),
                "sha1": sha1_of(fp) if ext.lower() == ".py" else "",
            }
            rows.append(row)
    rows.sort(key=lambda r: r["file_path"])

    csv_path = os.path.join(OUT_DIR, "00_file_inventory.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # ---- 摘要 ----
    from collections import Counter
    role_cnt = Counter(r["role"] for r in rows)
    ext_cnt = Counter(r["extension"] for r in rows)
    top10 = sorted(rows, key=lambda r: -r["size_kb"])[:10]
    total_mb = sum(r["size_kb"] for r in rows) / 1024
    # 顶层目录统计
    topdir_cnt = Counter(r["file_path"].split(os.sep)[0] for r in rows)
    # py 重复哈希统计
    py_hashes = Counter(r["sha1"] for r in rows if r["sha1"])
    dup_groups = {h: c for h, c in py_hashes.items() if c > 1}
    py_total = sum(1 for r in rows if r["extension"] == ".py")
    py_unique = len(py_hashes)

    md = []
    md.append("# 00 资产清单摘要\n")
    md.append(f"- 扫描根目录: `{ROOT}`")
    md.append(f"- 排除目录: CoStrict / project_analysis / project_branches / __pycache__(构建产物)")
    md.append(f"- 扫描时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md.append(f"- 文件总数: **{len(rows)}**,总大小: **{total_mb:,.1f} MB**\n")
    md.append("## 按 role 统计\n")
    md.append("| role | 数量 |\n|---|---|")
    for role, c in role_cnt.most_common():
        md.append(f"| {role} | {c} |")
    md.append("\n## 按扩展名统计(Top 15)\n")
    md.append("| 扩展名 | 数量 |\n|---|---|")
    for ext, c in ext_cnt.most_common(15):
        md.append(f"| {ext} | {c} |")
    md.append("\n## 按顶层目录统计\n")
    md.append("| 目录 | 文件数 |\n|---|---|")
    for d, c in topdir_cnt.most_common():
        md.append(f"| {d} | {c} |")
    md.append("\n## .py 文件重复度预检(SHA1)\n")
    md.append(f"- .py 文件总数: {py_total}")
    md.append(f"- 唯一内容(SHA1 去重后): **{py_unique}**")
    md.append(f"- 存在重复的哈希组数: {len(dup_groups)},涉及文件数: {sum(dup_groups.values())}")
    md.append("\n## 最大的 10 个文件\n")
    md.append("| 文件 | 大小(MB) | role |\n|---|---|---|")
    for r in top10:
        md.append(f"| {r['file_path']} | {r['size_kb']/1024:,.1f} | {r['role']} |")
    md_path = os.path.join(OUT_DIR, "00_inventory_summary.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print(json.dumps({"csv": csv_path, "md": md_path, "total_files": len(rows),
                      "py_total": py_total, "py_unique": py_unique}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
