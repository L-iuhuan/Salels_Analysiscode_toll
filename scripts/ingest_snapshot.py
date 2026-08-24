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
import re
import sys
import time

import numpy as np
import pandas as pd

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PLATFORM = os.path.join(_REPO_ROOT, "sales_analytics_platform")
DEFAULT_DATA_DIR = os.path.join(DEFAULT_PLATFORM, "data")
DATA_WAREHOUSE = os.path.join(DEFAULT_PLATFORM, "data_warehouse")

_SHA_HEAD = 8 * 1024 * 1024  # sha256 前 8MB
# 关键数值列合计：逻辑名 → 源列候选（raw 列名 vs 重命名后列名）
SUM_COLS = {
    "金额": ["金额", "RMB 未税金额小计"],
    "利润": ["利润"],
    "数量": ["数量", "发货数量"],
}


def _sha256_head(path, n=_SHA_HEAD):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(n))
    return h.hexdigest()


def is_encrypted(path):
    with open(path, "rb") as f:
        return f.read(4) != b"PK\x03\x04"


def _latest_excel(data_dir):
    xs = [f for f in os.listdir(data_dir)
          if f.startswith("财务分析-") and f.endswith(".xlsx") and not f.startswith("~$")]
    if not xs:
        return None
    return os.path.join(data_dir, max(xs, key=lambda n: os.path.getmtime(os.path.join(data_dir, n))))


def _resolve_sheet(ws_names, prefer):
    """优先 prefer（DATA_SHEET_NAME），缺失回退首个 sheet。"""
    if prefer in ws_names:
        return prefer
    return ws_names[0] if ws_names else None


def _read_plain(path, sheet_name):
    sys.path.insert(0, os.path.join(DEFAULT_PLATFORM, "processing"))
    from shared.data_cleaning import read_excel_auto
    try:
        return read_excel_auto(path, sheet_name=sheet_name)
    except Exception:
        # sheet 名不匹配（年份翻页等）时回退首个 sheet
        return read_excel_auto(path, sheet_name=0)


def _naive_cell(v):
    """COM 返回的 datetime 单元：去时区（win32timezone 非标准，pandas 会推断成无法序列化的 datetime64[tz]）。"""
    if isinstance(v, datetime.datetime):
        if v.tzinfo is not None:
            try:
                return v.replace(tzinfo=None)
            except Exception:
                return v
    return v


def _read_encrypted_com(path, sheet_name):
    """DSE 加密文件：COM 解密读（ReadOnly 打开，读目标 sheet UsedRange，首行作列名）。

    用 DispatchEx 创建新实例（避免 attach 到残留/损坏的 Excel 实例导致 Workbooks 不可用）。
    """
    import win32com.client
    excel = win32com.client.DispatchEx("Excel.Application")
    # 已有 Excel 实例时 Visible/DisplayAlerts 可能不可设置，失败不阻断（解密读仍可用）
    for attr, val in (("Visible", False), ("DisplayAlerts", False), ("EnableEvents", False)):
        try:
            setattr(excel, attr, val)
        except Exception:
            pass
    wb = None
    try:
        t0 = time.time()
        wb = excel.Workbooks.Open(path, ReadOnly=True, UpdateLinks=0, IgnoreReadOnlyRecommended=True)
        names = [wb.Sheets(i).Name for i in range(1, wb.Sheets.Count + 1)]
        target = _resolve_sheet(names, sheet_name)
        ws = wb.Sheets(names.index(target) + 1)
        used = ws.UsedRange
        data = used.Value
        print(f"  [COM] 打开 {time.time() - t0:.1f}s | sheet='{target}' | UsedRange {used.Rows.Count}x{used.Columns.Count}")
        # 归一为二维
        if not isinstance(data, (tuple, list)):
            data = ((data,),)
        rows = list(data)
        # COM 日期单元可能带非标准时区（win32timezone），先逐单元去时区，避免 pandas 推断出
        # 无法迭代/序列化的 datetime64[tz] 列
        rows = [[_naive_cell(c) for c in r] for r in rows]
        # 列名去重：COM 表头可能有重复列（如"细分市场（新）"出现两次），重名会使 df[col] 返回 DataFrame
        cols = [str(c) for c in rows[0]]
        seen = {}
        out_cols = []
        for c in cols:
            if c in seen:
                seen[c] += 1
                out_cols.append(f"{c}_{seen[c]}")
            else:
                seen[c] = 0
                out_cols.append(c)
        df = pd.DataFrame([list(r) for r in rows[1:]], columns=out_cols)
        # 清理 COM 幽灵空列/空行
        df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
        return df, target
    finally:
        if wb is not None:
            try:
                wb.Close(False)
            except Exception:
                pass
        try:
            excel.Quit()
        except Exception:
            pass


def _derive_period(df, filename):
    """YYYYMM：优先数据最大月份（发货日期/日期列），回退文件名"财务分析-X月"。"""
    for col in df.columns:
        if "发货日期" in str(col) or "日期" in str(col):
            try:
                d = pd.to_datetime(df[col], errors="coerce").dropna()
                if len(d):
                    return d.max().strftime("%Y%m")
            except Exception:
                pass
            break
    m = re.search(r"(\d{1,2})月", filename)
    if m:
        month = int(m.group(1))
        now = datetime.datetime.now()
        year = now.year if month <= now.month else now.year - 1
        return f"{year}{month:02d}"
    return datetime.datetime.now().strftime("%Y%m")


def _column_sums(df):
    """关键数值列合计（金额/利润/数量），取源列候选第一个存在的列。"""
    sums = {}
    for logical, cands in SUM_COLS.items():
        for c in cands:
            if c in df.columns:
                s = pd.to_numeric(df[c], errors="coerce").sum()
                sums[logical] = round(float(s), 2) if pd.notna(s) else None
                break
        else:
            sums[logical] = None
    return sums


def _coerce_object_columns(df):
    """混合类型 object 列统一为字符串（保留 NaN 为空），保证 pyarrow 可写。

    ERP 原始列如"产品品类（新）"可能是 str 与 int 混排（如数值型品类码），
    pyarrow 无法推断单一类型。仅处理 object 列中的非字符串单元：
    str 原样、NaN/None 留空、其他转 str；不影响 金额/利润/数量 等数值列合计。
    """
    df = df.copy()
    for c in df.columns:
        if df[c].dtype == object:
            mask = ~df[c].map(lambda x: isinstance(x, str))
            if mask.any():
                df[c] = df[c].map(
                    lambda x: x if isinstance(x, str)
                    else (None if x is None or pd.isna(x) else str(x)))
    return df


def _coerce_datetime_columns(df):
    """tz-aware datetime64 列 → 字符串（去掉时区、格式化为 naive 时间串）。

    COM 返回的日期带 win32timezone 非标准时区，pandas tz_localize / pyarrow 序列化均无法处理；
    strip tzinfo 后转 "YYYY-MM-DD HH:MM:SS" 字符串，pd.to_datetime 可再解析（stage_silver 正是如此）。
    """
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            if getattr(df[c].dtype, "tz", None) is not None:
                df[c] = df[c].map(
                    lambda v: None if pd.isna(v)
                    else v.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S"))
    return df


def main():
    ap = argparse.ArgumentParser(description="W1 快照仓 · ERP 明文快照 ingest")
    ap.add_argument("--data", default=None, help="源 Excel 路径（默认 data\\ 下最新 财务分析-*.xlsx）")
    ap.add_argument("--platform-dir", default=DEFAULT_PLATFORM, help="平台目录")
    args = ap.parse_args()

    platform = os.path.abspath(args.platform_dir)
    data_dir = os.path.join(platform, "data")
    warehouse = os.path.join(platform, "data_warehouse")

    # 定位源文件
    if args.data:
        xlsx = os.path.abspath(args.data)
    else:
        xlsx = _latest_excel(data_dir)
    if not xlsx or not os.path.isfile(xlsx):
        print(f"[错误] 未找到源 Excel（--data 指定或 data\\ 下最新 财务分析-*.xlsx）")
        sys.exit(1)
    print(f"[源] {xlsx}")
    st = os.stat(xlsx)
    enc = is_encrypted(xlsx)
    print(f"  大小 {st.st_size/1e6:.1f}MB | mtime {st.st_mtime} | 加密: {'是(COM)' if enc else '否(calamine)'}")

    # 读取（按加密路径）
    sys.path.insert(0, os.path.join(platform, "processing"))
    from config.settings import DATA_SHEET_NAME

    t0 = time.time()
    if enc:
        df, sheet_used = _read_encrypted_com(xlsx, DATA_SHEET_NAME)
        decrypt_path = "com"
    else:
        df = _read_plain(xlsx, DATA_SHEET_NAME)
        sheet_used = DATA_SHEET_NAME
        decrypt_path = "calamine"
    read_s = time.time() - t0
    print(f"[读] {len(df)} 行 x {len(df.columns)} 列 | {read_s:.1f}s | 路径={decrypt_path} | sheet={sheet_used}")

    # 对账数字
    sums = _column_sums(df)
    print("\n[对账表]")
    print(f"  行数   : {len(df):,}")
    print(f"  金额合计: {sums['金额']:,.2f}")
    print(f"  利润合计: {sums['利润']:,.2f}")
    print(f"  数量合计: {sums['数量']:,.2f}")

    # 生成快照
    period = _derive_period(df, os.path.basename(xlsx))
    out_dir = os.path.join(warehouse, period)
    os.makedirs(out_dir, exist_ok=True)
    pq_path = os.path.join(out_dir, "erp_snapshot.parquet")
    df = _coerce_object_columns(df)      # 混合类型 object 列统一为字符串，保证 pyarrow 可写
    df = _coerce_datetime_columns(df)    # tz-aware datetime 列转 naive（COM 时区 pyarrow 无法序列化）
    df.to_parquet(pq_path, index=False)
    print(f"\n[写] {pq_path}")

    cols_hash = hashlib.sha256("\n".join(str(c) for c in df.columns).encode("utf-8")).hexdigest()
    manifest = {
        "source": {
            "name": os.path.basename(xlsx),
            "size": st.st_size,
            "mtime": st.st_mtime,
            "sha256_8mb": _sha256_head(xlsx),
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
    }
    mf_path = os.path.join(out_dir, "manifest.json")
    with open(mf_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"[写] {mf_path}")
    print(f"\n[OK] 快照已生成（period={period}，decrypt={decrypt_path}）")
    sys.exit(0)


if __name__ == "__main__":
    main()
