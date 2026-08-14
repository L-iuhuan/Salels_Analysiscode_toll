#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
看板流水线 · 一键编排器
=====================================================================
一条命令完成「数据处理 → 生成看板」：

  前段  processing/run_all.py            读 data/ 里的原始Excel → 产出到 output/{silver,gold,report}
  后段  dashboard/generate_dashboard.py  读 output/ 和 data/     → 生成 dashboard/dashboard_a.html

前段产出直接写进 output/，后段从同一个 output/ 取数 —— 单一输入、单一输出，无需任何同步/拷贝。
output/ 里的中间结果（gold/silver CSV、产品报告Excel）也可直接拿去做其它分析。

用法：
  python run_chain.py                        # 全流程（数据处理 + 生成看板）
  python run_chain.py --skip-processing      # 数据没变，只用现有 output/ 重新生成看板（快）
  python run_chain.py --force-silver         # 强制重算Silver层（改了清洗配置后）
  python run_chain.py --data "D:/path/数据.xlsx"   # 临时指定原始Excel（默认自动找 data/ 里最新的）

所有路径都相对本脚本所在目录解析，整个文件夹可随意移动/拷贝到其它电脑。
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

# 本脚本所在目录 = 便携包根目录（一切路径的锚点，保证可移植）
PKG = os.path.dirname(os.path.abspath(__file__))

DIR_DATA = os.path.join(PKG, "data")        # 唯一输入目录：原始Excel + 部门-人员.md
DIR_PROC = os.path.join(PKG, "processing")  # 前段代码
DIR_OUT = os.path.join(PKG, "output")       # 唯一输出目录：silver/gold/report（前段写、后段读、也可做其它分析）
DIR_DASH = os.path.join(PKG, "dashboard")   # 后段代码 + 生成的看板
DASH_HTML = os.path.join(DIR_DASH, "dashboard_a.html")
CONFIG_PATH = os.path.join(PKG, "chain_config.json")

PERSONNEL_CANONICAL = "部门-人员-职务对应.md"   # 后段写死读取的人员文件名

DEFAULT_CONFIG = {
    "raw_excel": "",                 # 留空 = 自动找 data/ 里最新的 .xlsx
    "personnel_md": PERSONNEL_CANONICAL,
    "stages": "silver,product,customer,kpi,cross_ref",
}


def banner(msg):
    print("\n" + "=" * 64)
    print(msg)
    print("=" * 64)


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[警告] chain_config.json 读取失败({e})，使用默认配置")
    return cfg


def find_raw_excel(cfg):
    """定位原始Excel：优先 --data / 配置项，否则自动找 data/ 里最新的 .xlsx。"""
    cand = (cfg.get("raw_excel") or "").strip()
    if cand:
        p = cand if os.path.isabs(cand) else os.path.join(DIR_DATA, cand)
        if os.path.exists(p):
            return p
        print(f"[警告] 配置的 raw_excel '{cand}' 不存在，改为自动检测 data/ 目录")
    if not os.path.isdir(DIR_DATA):
        return ""
    xs = [os.path.join(DIR_DATA, f) for f in os.listdir(DIR_DATA)
          if f.endswith(".xlsx") and not f.startswith("~$")]
    return max(xs, key=os.path.getmtime) if xs else ""   # 最新的一份


def run_subprocess(cmd, cwd, title):
    """流式运行子进程并计时，返回(returncode, 秒)。输出直接透传到控制台。"""
    banner(f"▶ {title}")
    print(f"  命令: {' '.join(cmd)}")
    t0 = time.perf_counter()
    rc = subprocess.run(cmd, cwd=cwd).returncode
    dt = time.perf_counter() - t0
    print(f"  [完成] {title} 耗时 {dt:.1f}s (exit={rc})")
    return rc, dt


def _is_junction_or_link(path):
    """Python 3.11 兼容的联接判断(reparse point)。

    [合并修改#4] 原代码 os.path.isjunction 为 Python 3.12+ API,
    在本机 Python 3.11 下会 AttributeError,改为 st_file_attributes 判断。
    """
    if not os.path.lexists(path):
        return False
    try:
        return bool(os.stat(path, follow_symlinks=False).st_file_attributes
                    & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
    except (OSError, AttributeError):
        return os.path.islink(path)


def _ensure_junction(link, target, label):
    """把 link 联接到 target 并自检有效性(防静默输出分裂)。"""
    os.makedirs(target, exist_ok=True)
    if _is_junction_or_link(link) and os.path.realpath(link) == os.path.realpath(target):
        return
    if _is_junction_or_link(link):
        os.remove(link)
    elif os.path.isdir(link):
        shutil.rmtree(link, ignore_errors=True)
    rc = subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                        capture_output=True, text=True)
    if rc.returncode != 0:
        raise RuntimeError(f"无法创建目录联接 {link} -> {target}\n{rc.stdout}{rc.stderr}")
    # [合并修改#4] 自检:联接必须真实可用,否则立即终止并提示重建
    if not (_is_junction_or_link(link) and os.path.isdir(link)):
        raise RuntimeError(
            f"目录联接自检失败: {link} 未指向 {target}\n"
            f"请手动执行: mklink /J \"{link}\" \"{target}\"")
    print(f"  已联接: {label}")


def ensure_output_junction():
    """统一输入/输出:processing/output 与 processing/data 均联接到包根目录。

    [合并修改#4] 原版只联接 output; council 评审发现 customer_analysis 等模块
    自行计算 DATA_DIR=processing/data(空目录),显式 --data 之外会静默读空。
    现增加 data 联接,与 output 同理:两处写法最终都落到包根 data/,模块零改动。
    """
    _ensure_junction(os.path.join(DIR_PROC, "output"), DIR_OUT,
                     "processing\\output  →  output\\")
    _ensure_junction(os.path.join(DIR_PROC, "data"), DIR_DATA,
                     "processing\\data    →  data\\")


def main():
    ap = argparse.ArgumentParser(description="看板流水线 · 一键编排器")
    ap.add_argument("--data", default=None, help="原始Excel路径（默认自动找 data/ 最新）")
    ap.add_argument("--skip-processing", action="store_true", help="跳过数据处理，直接用 output/ 现有结果生成看板")
    ap.add_argument("--skip-dashboard", action="store_true", help="只做数据处理，不生成看板")
    ap.add_argument("--force-silver", action="store_true", help="强制重算Silver层")
    ap.add_argument("--stages", default=None, help="前段阶段（逗号分隔），默认用配置")
    args = ap.parse_args()

    cfg = load_config()
    if args.data:
        cfg["raw_excel"] = args.data
    if args.stages:
        cfg["stages"] = args.stages

    banner("看板流水线")
    print(f"  目录: {PKG}")
    print(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # ── 定位原始Excel ──
    raw_path = find_raw_excel(cfg)
    if not raw_path:
        print(f"\n[错误] 未找到原始Excel。请把 数据文件.xlsx 放进：\n  {DIR_DATA}")
        sys.exit(1)
    print(f"  数据源: {raw_path}")

    # ── 统一输入:把 --data 指定的原始Excel接入 data/ ──
    # 后段 generate_dashboard.py 不接收 --data,只扫描 data/ 目录按 mtime 取最新;
    # 运行器同步代码时排除 data/(保护本地数据),所以必须把用户指定的文件接进来,
    # 否则数据处理跑完后后段必报 "data/ 目录下未找到 .xlsx 文件"
    os.makedirs(DIR_DATA, exist_ok=True)
    raw_in_data = os.path.join(DIR_DATA, os.path.basename(raw_path))
    if os.path.abspath(raw_path) != os.path.abspath(raw_in_data):
        shutil.copy2(raw_path, raw_in_data)
        # 抬升接入文件的 mtime,保证后段"取最新"永远选中本次指定的文件(不改动源文件)
        os.utime(raw_in_data, None)
        print(f"  已接入数据源到 data/: {os.path.basename(raw_path)}")

    # 人员对应表基准版随代码分发(包根),本地 data/ 缺失时接入(后段F面从 data/ 读取)
    p_base = os.path.join(PKG, PERSONNEL_CANONICAL)
    p_in_data = os.path.join(DIR_DATA, PERSONNEL_CANONICAL)
    if os.path.exists(p_base) and not os.path.exists(p_in_data):
        shutil.copy2(p_base, p_in_data)
        print(f"  已接入人员对应表到 data/")

    # 人员对应表（后段F面要用），缺失仅提示不阻断
    p_md = os.path.join(DIR_DATA, cfg.get("personnel_md", PERSONNEL_CANONICAL))
    if not os.path.exists(p_md):
        print(f"  [提示] 未找到 {p_md}（看板 F 面的部门/人员映射会缺失）")

    t_all = time.perf_counter()

    # ── 统一输出目录：processing/output 联接到包根 output/（前段产出落单一目录）──
    ensure_output_junction()

    # ── 步骤 1/2：数据处理（前段，产出直接写 output/）──
    if not args.skip_processing:
        fe = [sys.executable, os.path.join(DIR_PROC, "run_all.py"),
              "--data", raw_path, "--stage", cfg["stages"]]
        if args.force_silver:
            fe.append("--force-silver")
        rc, _ = run_subprocess(fe, DIR_PROC, "步骤 1/2 · 数据处理 (processing/run_all.py)")
        if rc != 0:
            print(f"\n[错误] 数据处理失败(exit={rc})，已停止。请先看上面的报错。")
            sys.exit(rc)
    else:
        print("\n[跳过] 数据处理（--skip-processing），直接用 output/ 现有结果")

    # ── 步骤 2/2：生成看板（后段，从 output/ 和 data/ 取数）──
    if not args.skip_dashboard:
        print("[STAGE 6/6] 生成看板", flush=True)
        be = [sys.executable, os.path.join(DIR_DASH, "generate_dashboard.py")]
        rc, _ = run_subprocess(be, DIR_DASH, "步骤 2/2 · 生成看板 (generate_dashboard.py)")
        if rc != 0:
            print(f"\n[错误] 看板生成失败(exit={rc})。请先看上面的报错。")
            sys.exit(rc)
    else:
        print("\n[跳过] 看板生成（--skip-dashboard）")

    # ── 汇总 ──
    banner("完成")
    print(f"  总耗时: {time.perf_counter() - t_all:.1f}s")
    if not args.skip_dashboard and os.path.exists(DASH_HTML):
        print(f"  看板:   {DASH_HTML}  ({os.path.getsize(DASH_HTML)/1e6:.1f} MB)")
        print(f"  中间结果(可做其它分析): {DIR_OUT}")
        print(f"  用浏览器打开上面的看板文件即可查看。")
    else:
        print(f"  数据处理产出位于: {DIR_OUT}")


if __name__ == "__main__":
    main()
