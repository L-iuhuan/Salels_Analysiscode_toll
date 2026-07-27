# -*- coding: utf-8 -*-
"""阶段五:独立业务分支提取与重组。
从原始位置【复制】(绝不移动/修改原件)到 project_branches/<分支>/。
规则:
- 忽略 __pycache__/*.pyc/各项目 output 产出目录
- 数据文件 >50MB 不复制,记入 README 与 skipped_big
- 每个分支生成 requirements.txt / run.bat / run.sh / README.md
输出: project_analysis/05_branches_report.md + 05_branches_report.json
"""
import json, os, shutil, sys

ROOT = r"E:\3-其他资料\数据分析"
SRC_MAIN = os.path.join(ROOT, "工作文件", "semiconductor_analysis")   # ② 最新版
SRC_DOC = os.path.join(ROOT, "semiconductor_analysis")                # ① 文档版
SRC_DASH = os.path.join(ROOT, "看板流水线")                            # ③
SRC_PL = os.path.join(ROOT, "产品生命周期评估")                         # ⑤
SRC_WORK = os.path.join(ROOT, "工作文件")
BRANCHES = os.path.join(ROOT, "project_branches")
ANALYSIS_DIR = os.path.join(ROOT, "project_analysis")

BIG_LIMIT = 50 * 1024 * 1024  # 50MB
IGNORE_NAMES = {"__pycache__", ".pytest_cache", ".claude", ".codegraph", ".solomd", "nul_"}

report = {"branches": {}, "skipped_big": [], "missing": []}

def should_skip(path):
    parts = set(os.path.normpath(path).split(os.sep))
    return bool(parts & IGNORE_NAMES) or path.endswith(".pyc")

def copy_file(src, dst):
    if not os.path.exists(src):
        report["missing"].append(os.path.relpath(src, ROOT)); return 0
    if os.path.getsize(src) > BIG_LIMIT:
        report["skipped_big"].append({"file": os.path.relpath(src, ROOT).replace("\\", "/"),
                                      "mb": round(os.path.getsize(src) / 1048576, 1)})
        return 0
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return 1

def copy_dir(src, dst, extra_ignore=()):
    n = 0
    if not os.path.isdir(src):
        report["missing"].append(os.path.relpath(src, ROOT)); return 0
    for dp, dn, fn in os.walk(src):
        dn[:] = [d for d in dn if d not in IGNORE_NAMES and d not in extra_ignore]
        for f in fn:
            if f in extra_ignore or f.endswith(".pyc"):
                continue
            s = os.path.join(dp, f)
            rel = os.path.relpath(s, src)
            n += copy_file(s, os.path.join(dst, rel))
    return n

def w(branch, name, content):
    p = os.path.join(BRANCHES, branch, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)

RUN_SH = "#!/usr/bin/env bash\nset -e\ncd \"$(dirname \"$0\")\"\n{cmds}\n"
RUN_BAT = "@echo off\nrem 自动生成:按依赖顺序执行\ncd /d %~dp0\n{cmds}\npause\n"

def gen_runners(branch, cmds):
    bat = "\n".join(f'python {c}' + '\nif errorlevel 1 (echo [失败] ' + c + ' & exit /b 1)' for c in cmds)
    sh = "\n".join(f"python {c}" for c in cmds)
    w(branch, "run.bat", RUN_BAT.format(cmds=bat))
    w(branch, "run.sh", RUN_SH.format(cmds=sh))

def done(branch, n_files, note=""):
    report["branches"][branch] = {"files_copied": n_files, "note": note}

# ============================================================
# 1. main_pipeline(主流水线,以②为基准)
# ============================================================
B = "main_pipeline"
dst = os.path.join(BRANCHES, B)
n = 0
for d in ["config", "shared", "data_pipeline", "product_lifecycle", "customer_analysis",
          "cross_reference", "b2b_v2", "analysis", "reports", "core", "optimizer", "docs"]:
    n += copy_dir(os.path.join(SRC_MAIN, d), os.path.join(dst, d),
                  extra_ignore=("output", "outputs", "test_output"))
for f in ["run_all.py", "run_customer.py", "run_product.py", "CLAUDE.md", "一键运行说明.md",
          "1_全量重跑.bat", "2_只生成看板.bat", "3_只跑客户分析.bat", "4_只跑产品分析.bat",
          "5_产品生命周期看板.bat", "6_打开最新看板.bat", "启动菜单.bat"]:
    n += copy_file(os.path.join(SRC_MAIN, f), os.path.join(dst, f))
# ①的文档与依赖清单(②缺失)
for f, alias in [("requirements.txt", "requirements.txt"), ("README.md", "docs/旧版README_参考.md"),
                 ("AGENTS.md", "docs/AGENTS_参考.md"), ("PIPELINE_NODE_MAP.md", "docs/PIPELINE_NODE_MAP_参考.md")]:
    n += copy_file(os.path.join(SRC_DOC, f), os.path.join(dst, alias))
# ① scripts/ 下的 silver 下游脚本
n += copy_dir(os.path.join(SRC_DOC, "scripts"), os.path.join(dst, "scripts"))
# data 只带小文件
n += copy_file(os.path.join(SRC_MAIN, "data", "部门-人员-职务对应.md"), os.path.join(dst, "data", "部门-人员-职务对应.md"))
w(B, "data/README_数据说明.txt",
  "将任一月份的 财务分析-N月.xlsx 放入本目录即可运行(程序自动取第一个 .xlsx,或用 --data 指定)。\n"
  "原始样例位置(未复制,体积>50MB):\n"
  "  E:\\3-其他资料\\数据分析\\工作文件\\semiconductor_analysis\\data\\财务分析-6月（7.6）.xlsx (219.7MB)\n"
  "  E:\\3-其他资料\\数据分析\\semiconductor_analysis\\data\\财务分析-5月（6.3）.xlsx (216.2MB)\n")
gen_runners(B, ["run_all.py --stage silver,product,customer,kpi,cross_ref"])
done(B, n, "主流水线:silver→product→customer→kpi→cross_ref")

# ============================================================
# 2. dashboard_chain(看板流水线,③原样提取)
# ============================================================
B = "dashboard_chain"
dst = os.path.join(BRANCHES, B)
n = copy_dir(SRC_DASH, dst, extra_ignore=("output",))
gen_runners(B, ["run_chain.py"])
done(B, n, "看板便携包:processing→generate_dashboard→dashboard_a.html")

# ============================================================
# 3. deep_dive_h1_report(2026H1 深度分析报告群)
# ============================================================
B = "deep_dive_h1_report"
dst = os.path.join(BRANCHES, B)
n = 0
core_scripts = ["analysis1.py", "analysis2.py", "analysis3.py", "analysis4.py",
                "scout.py", "diag.py", "asp_check.py", "audit.py", "audit_pline.py", "audit_html.py",
                "bridge2.py", "bridge3.py", "ka_list.py", "recompute_asp.py",
                "deep_all.py", "deep_action.py", "deep_sales_products.py", "deep_zxkx.py",
                "run_action.py", "run_audit.py", "run_deep.py", "run_sp.py", "run_zxkx.py",
                "make_word.py", "append_word_appendix.py", "template.html",
                "fix_fonts.py", "fix_header_repeat.py", "fix_price.py", "fix_valign.py"]
for f in core_scripts:
    n += copy_file(os.path.join(SRC_MAIN, f), os.path.join(dst, f))
for f in ["fix_word_24.py", "fix_word_75.py", "fix_word_bridge.py", "fix_word_ch9.py", "fix_word_zxkx.py"]:
    n += copy_file(os.path.join(SRC_MAIN, f), os.path.join(dst, "fix_word_归档", f))
gen_runners(B, ["deep_all.py", "deep_action.py", "deep_sales_products.py", "deep_zxkx.py", "make_word.py"])
done(B, n, "H1报告链:deep_*→md→make_word→docx;含大量硬编码桌面路径")

# ============================================================
# 4. eda_forecast(EDA + 出货预测实验)
# ============================================================
B = "eda_forecast"
dst = os.path.join(BRANCHES, B)
n = 0
for f in ["eda_analysis_v3.py", "run_longtail_forecast.py", "run_full_forecast_v3.py"]:
    n += copy_file(os.path.join(SRC_WORK, f), os.path.join(dst, f))
w(B, "data_说明.txt", "输入数据未复制(>50MB): E:\\3-其他资料\\数据分析\\工作文件\\财务分析-5月（6.3）(1).xlsx (216.2MB)\n"
  "运行前请将数据路径配置到脚本头部变量中。\n")
gen_runners(B, ["eda_analysis_v3.py", "run_full_forecast_v3.py"])
done(B, n, "EDA迭代终版v3 + 长尾/全量出货预测")

# ============================================================
# 5. recession_risk_opt(衰退风险优化)
# ============================================================
B = "recession_risk_opt"
dst = os.path.join(BRANCHES, B)
n = copy_dir(os.path.join(SRC_DOC, "recession_risk_opt"), dst,
             extra_ignore=("output", "figs", "backtest_results"))
# backtest_results 里的 md 报告保留(文档价值),figs 忽略
n += copy_file(os.path.join(SRC_DOC, "recession_risk_opt", "backtest_results", "衰退风险模型测试报告_v20260526.md"),
               os.path.join(dst, "backtest_results", "衰退风险模型测试报告_v20260526.md"))
gen_runners(B, ["pipeline.py", "generate_snapshot.py"])
done(B, n, "衰退风险:phase1-5 + phaseA/B + snapshot;样本数据已随包(samples.pkl 3MB)")

# ============================================================
# 6. quarterly_forecast(季度预测包)
# ============================================================
B = "quarterly_forecast"
dst = os.path.join(BRANCHES, B)
n = copy_dir(os.path.join(SRC_MAIN, "quarterly_forecast_package"), dst,
             extra_ignore=("output",))
w(B, "data_说明.txt", "输入:原始出货明细 Excel(未复制,>50MB)。\n"
  "样例: E:\\3-其他资料\\数据分析\\工作文件\\semiconductor_analysis\\data\\财务分析-6月（7.6）.xlsx\n")
gen_runners(B, ["run_quarterly_forecast.py", "run_customer_forecast.py"])
done(B, n, "产品线+客户双维度季度预测(statsmodels ETS)")

# ============================================================
# 7. unified_forecast(统一预测系统,5版本,存疑)
# ============================================================
B = "unified_forecast"
dst = os.path.join(BRANCHES, B)
n = 0
n += copy_file(os.path.join(SRC_DOC, "unified_forecast_v3.py"), os.path.join(dst, "unified_forecast_v3.py"))
n += copy_file(os.path.join(SRC_DOC, "unified_forecast_system.py"), os.path.join(dst, "unified_forecast_system.py"))
for v in ["v1", "v2", "v3"]:
    n += copy_file(os.path.join(SRC_DOC, f"unified_forecast_system_backup_{v}.py"),
                   os.path.join(dst, "_archive", f"unified_forecast_system_backup_{v}.py"))
gen_runners(B, ["unified_forecast_v3.py"])
done(B, n, "统一预测系统;依赖 quarterly_forecast 分支的输出CSV")

# ============================================================
# 8. product_lifecycle_legacy_v28(已淘汰的 v2.8 独立旧项目)
# ============================================================
B = "product_lifecycle_legacy_v28"
dst = os.path.join(BRANCHES, B)
n = 0
for f in ["run_v2.8.py", "config.xlsx", "产品生命周期量化评估方案_v2.8.md",
          "产品生命周期量化评估方案_v2.8.pdf", "产品生命周期量化评估方案_v2.8_汇报.html",
          "product_dashboard_v4-演示.html", "product_dashboard_v4-演示_精简.html"]:
    n += copy_file(os.path.join(SRC_PL, f), os.path.join(dst, f))
n += copy_dir(os.path.join(SRC_PL, "product_data"), os.path.join(dst, "product_data"))
n += copy_dir(os.path.join(SRC_PL, "产品生命周期量化评估方案_v2.9"), os.path.join(dst, "产品生命周期量化评估方案_v2.9"),
              extra_ignore=("output",))
for f in ["build_config.py", "build_html.py", "excel_helper.py", "generate_dashboard_v4.py",
          "run.py", "模型测试.py", "setup.bat", "README.txt"]:
    n += copy_file(os.path.join(SRC_PL, "backup", f), os.path.join(dst, "backup_code", f))
w(B, "data_说明.txt", "输入: 所有的出货明细5.9.xlsx(137MB,未复制)\n"
  "位置: E:\\3-其他资料\\数据分析\\产品生命周期评估\\所有的出货明细5.9.xlsx\n"
  "注意: 本项目已被 main_pipeline 分支的 product_lifecycle/ 包取代,仅存档参考。\n")
gen_runners(B, ["run_v2.8.py"])
done(B, n, "v2.8旧项目存档(config.xlsx驱动);v2.9迭代在子目录")

# ============================================================
# 9. _orphans
# ============================================================
B = "_orphans"
dst = os.path.join(BRANCHES, B)
n = 0
temp_files = ["dashboard/audit_cats.py", "dashboard/audit_cats2.py", "dashboard/audit_deep.py",
              "dashboard/audit_rhythm.py", "dashboard/audit_small.py", "dashboard/audit_alerts.py",
              "dashboard/audit_data.py", "dashboard/audit_final.py", "dashboard/audit_new.py",
              "dashboard/check_cust.py", "dashboard/check_data.py", "dashboard/check_kpi.py",
              "dashboard/check_names.py", "dashboard/final_check.py", "dashboard/find_col2.py",
              "dashboard/find_col5.py", "dashboard/verify_ytd.py", "peek.py"]
for f in temp_files:
    n += copy_file(os.path.join(SRC_MAIN, f), os.path.join(dst, "temp_临时检查", f.replace("/", "_")))
work_temp = ["check_col.py", "check_cust.py", "check_kpi2.py", "data_inventory.py", "final_audit.py",
             "final_check.py", "find_col.py", "find_col2.py", "find_col3.py", "find_col4.py",
             "find_col5.py", "verify_raw.py", "verify_syntax.py", "verify.py", "verify_word.py", "test.py"]
for f in work_temp:
    n += copy_file(os.path.join(SRC_MAIN, f), os.path.join(dst, "temp_临时检查", f))
for f in ["linked_list_cycle.py", "lru_cache_decorator.py", "majority_element.py",
          "optimize_duplicates.py", "race_condition_clear_demo.py", "thread_race_condition_demo.py"]:
    n += copy_file(os.path.join(SRC_DOC, f), os.path.join(dst, "junk_与数据分析无关", f))
for f in ["_debug_f1f.py", "_debug_mw.py", "_explore_shipping.py", "_step1_c6_compute.py", "_step2_test_c6.py",
          "detailed_excel_analysis.py", "parse_excel_file.py", "safe_divide.py"]:
    n += copy_file(os.path.join(SRC_DOC, f), os.path.join(dst, "debug_存疑", f))
for f in ["runall.py", "run2.py", "run3.py", "run4.py", "generate_v4.py"]:
    n += copy_file(os.path.join(SRC_MAIN, f), os.path.join(dst, "uncertain_存疑", f))
done(B, n, "孤儿收容:temp/junk/debug/uncertain 四类")

# ============================================================
# 汇总报告
# ============================================================
with open(os.path.join(ANALYSIS_DIR, "05_branches_report.json"), "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print(json.dumps({b: v["files_copied"] for b, v in report["branches"].items()}, ensure_ascii=False))
print("missing:", len(report["missing"]), report["missing"][:10])
print("skipped_big:", [(s["file"], s["mb"]) for s in report["skipped_big"]])
