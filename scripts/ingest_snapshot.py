#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
W1 快照仓 · ERP 明文快照 ingest（批次④b 拍板实施）
=====================================================================

月度流程：ERP Excel 放入 data\ → 人工核对加工完成 → 跑本脚本生成明文快照 →
之后文件即使被 DSE 加密，跑批也不受影响（直接读 data_warehouse 快照）。

用法：
  python scripts/ingest_snapshot.py                          # 默认取 data\ 下最新"财务分析-*.xlsx"
  python scripts/ingest_snapshot.py --data <xlsx路径>        # 指定源 Excel

行为：
  - 加密检测：文件头非 `PK\x03\x04` → 判定 DSE 加密 → 走 COM 解密读（win32com，
    ReadOnly 打开，读目标 sheet（config DATA_SHEET_NAME，缺失回退首个 sheet）UsedRange，
    首行作列名转 DataFrame）；明文 → read_excel_auto（calamine）。
  - 快照落点：sales_analytics_platform\data_warehouse\YYYYMM\erp_snapshot.parquet + manifest.json
    （YYYYMM 从数据最大月份推，回退文件名"财务分析-X月"）。
  - manifest 记录：源文件名/size/mtime/sha256前8MB、行数、列名列表哈希、关键数值列合计
    [金额/利润/数量]、ingest 时间、解密路径[calamine|com]。
  - 打印对账表（行数 + 关键合计），成功 exit 0，失败 exit 1。
"""

import argparse
import datetime
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time

import numpy as np
import pandas as pd

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PLATFORM = os.path.join(_REPO_ROOT, "sales_analytics_platform")
DEFAULT_DATA_DIR = os.path.join(DEFAULT_PLATFORM, "data")
# 共享盘数据目录：内置默认值（r14：财务月度 Excel 直接投放共享盘，全员 DSE 客户端透明解密）。
# 可被命令行 --share-dir / 环境变量 SALES_DATA_SHARE_DIR 覆盖，显式空串 "" = 禁用共享盘扫描。
# 单点配置纪律：数据共享夹独立于代码共享夹（r14b 用户拍板）；本默认值与
# run_chain.py、壳端 lib.rs DEFAULT_DATA_SHARE_PATH 三处同源，变更时必须同步修改。
DIR_DATA_SHARE = r"\\192.168.8.3\财务部\财务电子档案备份\D1经营分析"
DATA_WAREHOUSE = os.path.join(DEFAULT_PLATFORM, "data_warehouse")

# r16：COM 解密读 + 快照写入小工具统一从共享层导入（原 _read_encrypted_com/_derive_period/...
# 已抽取到 shared\excel_com.py，此处仅导入，行为不变）
_PROC_DIR = os.path.join(DEFAULT_PLATFORM, "processing")
if _PROC_DIR not in sys.path:
    sys.path.insert(0, _PROC_DIR)
from shared.excel_com import (  # noqa: E402
    read_encrypted_com, derive_period, column_sums,
    coerce_object_columns, coerce_datetime_columns, sha256_head, sha256_full,
)


def is_encrypted(path):
    with open(path, "rb") as f:
        return f.read(4) != b"PK\x03\x04"


def _latest_excel(data_dir, share_dir=DIR_DATA_SHARE):
    """合并扫描本地+共享盘取 mtime 最新的"财务分析-*.xlsx"（r14）。

    共享盘目录不可达/不存在时 try/except OSError 静默回退纯本地（保持现状行为）。
    share_dir 为空串/None 时跳过共享盘扫描（禁用，回退纯本地）。
    """
    def _scan(d):
        if not os.path.isdir(d):
            return []
        return [os.path.join(d, f) for f in os.listdir(d)
                if f.startswith("财务分析-") and f.endswith(".xlsx") and not f.startswith("~$")]

    xs = _scan(data_dir)
    shared = []
    if share_dir:
        try:
            shared = _scan(share_dir)
        except OSError:
            pass  # 共享盘不可达/不存在：静默回退本地
    xs += shared
    if not xs:
        return None
    # 同 mtime 时优先共享盘（本地常为共享盘历史副本、mtime 一致）：r14 以共享盘为月度权威源
    def _rank(p):
        return (os.path.getmtime(p), 1 if p in shared else 0)
    return max(xs, key=_rank)


def _read_plain(path, sheet_name):
    sys.path.insert(0, os.path.join(DEFAULT_PLATFORM, "processing"))
    from shared.data_cleaning import read_excel_auto
    try:
        return read_excel_auto(path, sheet_name=sheet_name)
    except Exception:
        # sheet 名不匹配（年份翻页等）时回退首个 sheet
        return read_excel_auto(path, sheet_name=0)


def _read_sheet_optional(path, sheet_name, enc):
    """读取可选 sheet（如客户信息表）；sheet 不存在或读取失败返回 None，绝不回退到首个 sheet。"""
    if enc:
        df, _used = read_encrypted_com(path, sheet_name, strict=True)
        return df
    sys.path.insert(0, os.path.join(DEFAULT_PLATFORM, "processing"))
    from shared.data_cleaning import read_excel_auto
    try:
        xls = pd.ExcelFile(path)
        if sheet_name not in xls.sheet_names:
            return None
        return read_excel_auto(path, sheet_name=sheet_name)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="W1 快照仓 · ERP 明文快照 ingest")
    ap.add_argument("--data", default=None, help="源 Excel 路径（默认 data\\ 下最新 财务分析-*.xlsx）")
    ap.add_argument("--platform-dir", default=DEFAULT_PLATFORM, help="平台目录")
    ap.add_argument("--share-dir", default=None,
                    help="共享盘数据目录（默认 环境变量 SALES_DATA_SHARE_DIR > 内置 DIR_DATA_SHARE；显式传空串 \"\" = 禁用共享盘扫描）")
    args = ap.parse_args()

    platform = os.path.abspath(args.platform_dir)
    data_dir = os.path.join(platform, "data")
    warehouse = os.path.join(platform, "data_warehouse")

    # 共享盘目录解析（r14b，高→低）：--share-dir > 环境变量 > 内置默认；空串=禁用
    if args.share_dir is not None:
        share_dir = args.share_dir.strip()          # 显式传空串 "" = 禁用共享盘扫描
    else:
        share_dir = os.environ.get("SALES_DATA_SHARE_DIR", "").strip()
        if not share_dir:
            share_dir = DIR_DATA_SHARE

    # 定位源文件
    if args.data:
        xlsx = os.path.abspath(args.data)
    else:
        xlsx = _latest_excel(data_dir, share_dir)
    if not xlsx or not os.path.isfile(xlsx):
        print(f"[错误] 未找到源 Excel（--data 指定或 data\\ 下最新 财务分析-*.xlsx）")
        sys.exit(1)
    # r14 保护：最终确定的源若是共享盘 UNC 路径，先复制到本地 data\ 再用本地副本继续——
    # COM 只读本地文件，避免 UNC+COM 未验证路径；DSE 密文共享盘/本地字节级一致，复制即可。
    if xlsx.startswith("\\\\"):
        os.makedirs(data_dir, exist_ok=True)
        local_copy = os.path.join(data_dir, os.path.basename(xlsx))
        shutil.copy2(xlsx, local_copy)
        xlsx = local_copy
        print(f"[数据] 源为共享盘 UNC，已复制到本地副本（COM 只读本地文件）: {xlsx}")
    print(f"[源] {xlsx}")
    st = os.stat(xlsx)
    enc = is_encrypted(xlsx)
    print(f"  大小 {st.st_size/1e6:.1f}MB | mtime {st.st_mtime} | 加密: {'是(COM)' if enc else '否(calamine)'}")

    # 读取（按加密路径）
    sys.path.insert(0, os.path.join(platform, "processing"))
    from config.settings import DATA_SHEET_NAME

    t0 = time.time()
    if enc:
        df, sheet_used = read_encrypted_com(xlsx, DATA_SHEET_NAME)
        decrypt_path = "com"
    else:
        df = _read_plain(xlsx, DATA_SHEET_NAME)
        sheet_used = DATA_SHEET_NAME
        decrypt_path = "calamine"
    read_s = time.time() - t0
    print(f"[读] {len(df)} 行 x {len(df.columns)} 列 | {read_s:.1f}s | 路径={decrypt_path} | sheet={sheet_used}")

    # 对账数字
    sums = column_sums(df)
    print("\n[对账表]")
    print(f"  行数   : {len(df):,}")
    print(f"  金额合计: {sums['金额']:,.2f}")
    print(f"  利润合计: {sums['利润']:,.2f}")
    print(f"  数量合计: {sums['数量']:,.2f}")

    # 生成快照
    period = derive_period(df, os.path.basename(xlsx))
    out_dir = os.path.join(warehouse, period)
    os.makedirs(out_dir, exist_ok=True)
    pq_path = os.path.join(out_dir, "erp_snapshot.parquet")
    df = coerce_object_columns(df)      # 混合类型 object 列统一为字符串，保证 pyarrow 可写
    df = coerce_datetime_columns(df)    # tz-aware datetime 列转 naive（COM 时区 pyarrow 无法序列化）
    df.to_parquet(pq_path, index=False)
    print(f"\n[写] {pq_path}")

    # 客户信息表 sheet 一并入快照（stage_silver 需要；源文件没有该 sheet 则记 None，
    # 跑批时回退 build_cust_info 从 ERP 列构建客户属性）
    cust_df = _read_sheet_optional(xlsx, "客户信息表", enc)
    cust_rows = None
    if cust_df is not None:
        cust_df = coerce_object_columns(cust_df)
        cust_df = coerce_datetime_columns(cust_df)
        cust_pq = os.path.join(out_dir, "cust_info.parquet")
        cust_df.to_parquet(cust_pq, index=False)
        cust_rows = int(len(cust_df))
        print(f"[写] {cust_pq}（客户信息表 {cust_rows} 行）")
    else:
        print("  [提示] 源文件无“客户信息表”sheet，跑批将从 ERP 列构建客户属性（build_cust_info）")

    cols_hash = hashlib.sha256("\n".join(str(c) for c in df.columns).encode("utf-8")).hexdigest()
    manifest = {
        "source": {
            "name": os.path.basename(xlsx),
            "size": st.st_size,
            "mtime": st.st_mtime,                       # 展示/审计，不作身份键
            "sha256_8mb": sha256_head(xlsx),            # 保留兼容（旧 find_matching_snapshot）
            "sha256_full": sha256_full(xlsx),           # r17 身份键（宪法 R3 全量哈希）
        },
        "ingest": {
            "time": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "decrypt_path": decrypt_path,
            "sheet": sheet_used,
            "period": period,
            "read_seconds": round(read_s, 1),
        },
        "data": {
            "row_count": int(len(df)),
            "column_count": int(len(df.columns)),
            "columns_hash": cols_hash,
            "columns": [str(c) for c in df.columns],
            "sums": sums,
        },
        "cust_info": {
            "file": "cust_info.parquet" if cust_rows is not None else None,
            "row_count": cust_rows,
        },
    }
    mf_path = os.path.join(out_dir, "manifest.json")
    # r17 原子写：先写同目录临时文件再 os.replace（避免半写 manifest 被并发读）
    fd, tmp_mf = tempfile.mkstemp(suffix=".json", prefix="manifest_", dir=out_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        os.replace(tmp_mf, mf_path)
    except Exception:
        try:
            os.remove(tmp_mf)
        except OSError:
            pass
        raise
    print(f"[写] {mf_path}")
    print(f"\n[OK] 快照已生成（period={period}，decrypt={decrypt_path}）")
    sys.exit(0)


if __name__ == "__main__":
    main()
