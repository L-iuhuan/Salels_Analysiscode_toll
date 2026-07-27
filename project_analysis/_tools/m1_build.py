# -*- coding: utf-8 -*-
"""M1: 以③为骨架构建 sales_analytics_platform,②模块原子覆盖。
只复制/新增,不修改任何原始文件。全程写 M1 执行日志。
"""
import csv, json, os, shutil, stat, sys, datetime

def is_junction(p):
    """Python 3.11 兼容:用 reparse point 属性判断 junction/symlink。"""
    try:
        return bool(os.stat(p, follow_symlinks=False).st_file_attributes
                    & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except (OSError, AttributeError):
        return os.path.islink(p)

ROOT = r"E:\3-其他资料\数据分析"
SRC3 = os.path.join(ROOT, "看板流水线")
SRC2 = os.path.join(ROOT, "工作文件", "semiconductor_analysis")
SRC1 = os.path.join(ROOT, "semiconductor_analysis")
DST = os.path.join(ROOT, "sales_analytics_platform")
LOG = {"overwritten": [], "added_from_2": [], "kept_3_version": [], "only_in_3": [],
       "notes": []}

IGNORE = {"__pycache__", ".pytest_cache"}
OVERLAY_DIRS = ["config", "shared", "data_pipeline", "product_lifecycle", "customer_analysis",
                "cross_reference", "b2b_v2", "analysis", "reports", "core"]
KEEP_3 = {  # 处理目录相对路径 -> 保留③版本(不覆盖)
    os.path.normpath("config/settings.py"),
    os.path.normpath("analysis/pricing/pricing_customer.py"),
}

# ②③ .py 哈希(用于覆盖日志)
hash_map = {}
with open(os.path.join(ROOT, "project_analysis", "00_file_inventory.csv"), encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["extension"] == ".py":
            hash_map[r["file_path"].replace("\\", "/")] = r["sha1"]

def sha_of(rel):
    return hash_map.get(rel.replace("\\", "/"), "")

# ---- 1. 拷贝③骨架 ----
n3 = 0
for item in os.listdir(SRC3):
    s = os.path.join(SRC3, item)
    d = os.path.join(DST, item)
    if os.path.isdir(s):
        for dp, dn, fn in os.walk(s):
            dn[:] = [x for x in dn if x not in IGNORE and not is_junction(os.path.join(dp, x))]
            for f in fn:
                if f.endswith(".pyc"):
                    continue
                sp = os.path.join(dp, f)
                rel = os.path.relpath(sp, s)
                os.makedirs(os.path.join(d, os.path.dirname(rel)), exist_ok=True)
                shutil.copy2(sp, os.path.join(d, rel))
                n3 += 1
    else:
        os.makedirs(DST, exist_ok=True)
        shutil.copy2(s, d)
        n3 += 1
LOG["notes"].append(f"③骨架拷贝 {n3} 文件")

# ---- 2. ②原子覆盖 ----
for top in OVERLAY_DIRS:
    src_dir = os.path.join(SRC2, top)
    dst_dir = os.path.join(DST, "processing", top)
    if not os.path.isdir(src_dir):
        LOG["notes"].append(f"②缺少目录 {top},跳过"); continue
    for dp, dn, fn in os.walk(src_dir):
        dn[:] = [x for x in dn if x not in IGNORE]
        for f in fn:
            if f.endswith(".pyc"):
                continue
            sp = os.path.join(dp, f)
            rel = os.path.relpath(sp, src_dir)
            keep_key = os.path.normpath(os.path.join(top, rel))
            tp = os.path.join(dst_dir, rel)
            os.makedirs(os.path.dirname(tp), exist_ok=True)
            rel2 = f"工作文件/semiconductor_analysis/{top}/{rel}".replace("\\", "/")
            rel3 = f"看板流水线/processing/{top}/{rel}".replace("\\", "/")
            if keep_key in KEEP_3:
                LOG["kept_3_version"].append(rel3); continue
            if os.path.exists(tp):
                h2, h3 = sha_of(rel2), sha_of(rel3)
                if h2 and h3 and h2 != h3:
                    LOG["overwritten"].append({"file": f"processing/{top}/{rel}".replace("\\", "/"),
                                               "sha_②": h2[:10], "sha_③": h3[:10]})
                shutil.copy2(sp, tp)
            else:
                shutil.copy2(sp, tp)
                LOG["added_from_2"].append(f"processing/{top}/{rel}".replace("\\", "/"))
    # ③有而②无
    if os.path.isdir(dst_dir):
        for dp, dn, fn in os.walk(dst_dir):
            for f in fn:
                tp = os.path.join(dp, f)
                rel = os.path.relpath(tp, dst_dir)
                if not os.path.exists(os.path.join(src_dir, rel)) and not f.endswith(".pyc"):
                    LOG["only_in_3"].append(f"processing/{top}/{rel}".replace("\\", "/"))

# ---- 3. test/ 落包根 + 根conftest ----
tcount = 0
src_test = os.path.join(SRC2, "test")
for dp, dn, fn in os.walk(src_test):
    dn[:] = [x for x in dn if x not in IGNORE]
    for f in fn:
        if f.endswith(".pyc"): continue
        sp = os.path.join(dp, f)
        rel = os.path.relpath(sp, src_test)
        tp = os.path.join(DST, "test", rel)
        os.makedirs(os.path.dirname(tp), exist_ok=True)
        shutil.copy2(sp, tp); tcount += 1
with open(os.path.join(DST, "conftest.py"), "w", encoding="utf-8") as f:
    f.write('''"""pytest 根配置(合并版):注入 processing/ 入 sys.path,排除非pytest脚本。"""
import sys, os
_PKG = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_PKG, "processing"))
collect_ignore = ["test/batch_a_test.py", "test/fallback.py"]
''')
LOG["notes"].append(f"test/ 落包根 {tcount} 文件 + 根conftest.py(注入processing/)")

# ---- 4. docs 合并(①文档资产) ----
os.makedirs(os.path.join(DST, "docs", "①文档参考"), exist_ok=True)
for f in ["README.md", "AGENTS.md", "PIPELINE_NODE_MAP.md", "STATUS.md"]:
    sp = os.path.join(SRC1, f)
    if os.path.exists(sp):
        shutil.copy2(sp, os.path.join(DST, "docs", "①文档参考", f))
LOG["notes"].append("①文档4份并入 docs/①文档参考/")

# ---- 5. 数据文件(用户批准复制) ----
os.makedirs(os.path.join(DST, "data"), exist_ok=True)
src_xlsx = os.path.join(SRC2, "data", "财务分析-6月（7.6）.xlsx")
shutil.copy2(src_xlsx, os.path.join(DST, "data", "财务分析-6月（7.6）.xlsx"))
src_md = os.path.join(SRC2, "data", "部门-人员-职务对应.md")
if os.path.exists(src_md):
    shutil.copy2(src_md, os.path.join(DST, "data", "部门-人员-职务对应.md"))
LOG["notes"].append("数据: 财务分析-6月（7.6）.xlsx(219.7MB)+部门-人员.md 已复制到 data/")

# ---- 6. 包根入口 bat ----
bats = {
"1_全量重跑.bat": "@echo off\nchcp 65001 >nul\ncd /d %~dp0\npython run_chain.py --force-silver\npause\n",
"2_只生成看板.bat": "@echo off\nchcp 65001 >nul\ncd /d %~dp0\npython run_chain.py --skip-processing\npause\n",
"3_只跑数据处理.bat": "@echo off\nchcp 65001 >nul\ncd /d %~dp0\npython run_chain.py --skip-dashboard\npause\n",
}
for name, content in bats.items():
    with open(os.path.join(DST, name), "w", encoding="gbk") as f:
        f.write(content)
LOG["notes"].append("包根bat入口3个(调run_chain.py)")

with open(os.path.join(ROOT, "project_analysis", "m1_build_log.json"), "w", encoding="utf-8") as f:
    json.dump(LOG, f, ensure_ascii=False, indent=2)
print(json.dumps({"骨架③": n3, "覆盖(哈希不同)": len(LOG["overwritten"]),
                  "②新增": len(LOG["added_from_2"]), "保留③版本": LOG["kept_3_version"],
                  "③独有": LOG["only_in_3"]}, ensure_ascii=False, indent=1))
