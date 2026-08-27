# -*- coding: utf-8 -*-
r"""
共享层 · Excel COM 解密读取 + 快照注入（r16 从 scripts\ingest_snapshot.py 抽取，消除重复实现）
=====================================================================

DSE/亿赛通密文 Excel（文件头非 ZIP/PK）无法被 calamine/openpyxl 读取；
全员电脑装有 DSE 客户端 + Office，可经 Excel COM 透明解密读取。

本模块提供：
  read_encrypted_com(path, sheet_name, strict=False)  → (df, used_sheet)
       COM 解密读；strict=True 时指定 sheet 不存在返回 (None, None)。
       源为 UNC 路径时先复制到本地临时文件再 COM（COM 只读本地文件）。
  write_erp_snapshot(df, source_path, warehouse_root, sheet_name, read_seconds=None)
       COM 成功后按 ingest 同款落仓：data_warehouse\<YYYYMM>\erp_snapshot.parquet + manifest
       （r17：manifest source 写 name+size+sha256_full 作身份键，弃 mtime；补全审计字段
       columns/columns_hash/sums/read_seconds；原子写）。
  derive_period / coerce_object_columns / coerce_datetime_columns / sha256_head / sha256_full
  / column_sums（ingest_snapshot 与流水线注入共用的小工具，从 ingest 原样迁来，行为不变）

调用方：
  - scripts\ingest_snapshot.py（原 _read_encrypted_com/_derive_period/... 改从此导入，行为不变）
  - processing\shared\data_cleaning.read_excel_auto 的 COM 兜底（快照 miss + calamine 失败后）
"""

import datetime
import hashlib
import json
import os
import re
import shutil
import tempfile
import time

import pandas as pd

_SHA_HEAD = 8 * 1024 * 1024  # sha256 前 8MB


def naive_cell(v):
    """COM 返回的 datetime 单元：去时区（win32timezone 非标准，pandas 会推断成无法序列化的 datetime64[tz]）。"""
    if isinstance(v, datetime.datetime):
        if v.tzinfo is not None:
            try:
                return v.replace(tzinfo=None)
            except Exception:
                return v
    return v


def resolve_sheet(ws_names, prefer):
    """优先 prefer（如 DATA_SHEET_NAME），缺失回退首个 sheet。"""
    if prefer in ws_names:
        return prefer
    return ws_names[0] if ws_names else None


def read_encrypted_com(path, sheet_name, strict=False):
    """DSE 加密文件：COM 解密读（ReadOnly 打开，读目标 sheet UsedRange，首行作列名）。

    用 DispatchEx 创建新实例（避免 attach 到残留/损坏的 Excel 实例导致 Workbooks 不可用）。
    strict=True 时 sheet 不存在返回 (None, None)，不回退首个 sheet（可选 sheet 用）。
    UNC 源（\\ 开头）先复制到本地临时文件再 COM（COM 只读本地文件，规避 UNC+COM 未验证路径）。
    返回 (DataFrame, used_sheet) 或 (None, None)。
    """
    import win32com.client
    cleanup = None
    if isinstance(path, str) and path.startswith("\\\\"):
        # gamma 加固：mkstemp 唯一名（并发互踩防护）+ 保留扩展名（COM 依赖扩展名推断格式）
        # + copy2 失败删半成品再 raise（避免残留半截临时文件）
        fd, _local = tempfile.mkstemp(prefix="dse_com_",
                                      suffix=os.path.splitext(os.path.basename(path))[1] or ".tmp")
        os.close(fd)
        try:
            shutil.copy2(path, _local)
        except Exception:
            try:
                os.remove(_local)
            except OSError:
                pass
            raise
        path = _local
        cleanup = _local
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
        if strict and sheet_name not in names:
            return None, None
        target = sheet_name if strict else resolve_sheet(names, sheet_name)
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
        rows = [[naive_cell(c) for c in r] for r in rows]
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
        if cleanup and os.path.exists(cleanup):
            try:
                os.remove(cleanup)
            except OSError:
                pass


def derive_period(df, filename):
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


def coerce_object_columns(df):
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


def coerce_datetime_columns(df):
    """tz-aware datetime64 列 → 字符串（去掉时区、格式化为 naive 时间串），pyarrow 可写。

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


def sha256_head(path, n=_SHA_HEAD):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(n))
    return h.hexdigest()


def sha256_full(path, chunk=1024 * 1024):
    """全量文件 sha256（r17，宪法 R3：8MB 头会漏检文件后部修正，作身份键必须全量）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


# 关键数值列合计：逻辑名 → 源列候选（raw 列名 vs 重命名后列名）
SUM_COLS = {
    "金额": ["金额", "RMB 未税金额小计"],
    "利润": ["利润"],
    "数量": ["数量", "发货数量"],
}


def column_sums(df):
    """关键数值列合计（金额/利润/数量），取源列候选第一个存在的列。

    r17：从 scripts\ingest_snapshot.py 迁入共享层，供 ingest 与快照注入复用。
    """
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


def write_erp_snapshot(df, source_path, warehouse_root, sheet_name, read_seconds=None):
    """COM 解密成功后按 ingest 同款落仓：写 data_warehouse\<YYYYMM>\erp_snapshot.parquet + manifest（r17 升级）。

    manifest source 写 name+size+sha256_full（身份键，弃 mtime；mtime 仅保留展示/审计），
    并补全 ingest 同款审计字段（columns / columns_hash / sums / read_seconds）。
    保守策略：目标 period 目录已有 manifest 且其 source.name 与当前源不同时不覆盖（避免挤占
    他人快照，如同名周期下的副本）；同名且 sha256_full 相同视为同源允许覆盖更新。
    写入原子化：manifest 先写同目录临时文件再 os.replace。
    返回 parquet 路径；被跳过/无写入返回 None。写仓失败由调用方捕获（仅告警不阻断读取）。
    """
    period = derive_period(df, os.path.basename(source_path))
    out_dir = os.path.join(warehouse_root, period)
    mf_path = os.path.join(out_dir, "manifest.json")
    if os.path.isfile(mf_path):
        try:
            with open(mf_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if existing.get("source", {}).get("name") != os.path.basename(source_path):
                print(f"  [注入跳过] data_warehouse/{period}/manifest.json 已属于其他源"
                      f"（{existing.get('source', {}).get('name')}），不覆盖；本次 COM 结果直接使用")
                return None
            # 同名：sha256_full 相同视为同源允许覆盖更新（不同则源已变，同样允许覆盖为新版本）
        except (json.JSONDecodeError, OSError):
            pass  # manifest 损坏/不可读 → 覆盖重写
    os.makedirs(out_dir, exist_ok=True)
    pq_path = os.path.join(out_dir, "erp_snapshot.parquet")
    df = coerce_object_columns(df)
    df = coerce_datetime_columns(df)
    df.to_parquet(pq_path, index=False)
    st = os.stat(source_path)
    cols_hash = hashlib.sha256("\n".join(str(c) for c in df.columns).encode("utf-8")).hexdigest()
    manifest = {
        "source": {
            "name": os.path.basename(source_path),
            "size": st.st_size,
            "mtime": st.st_mtime,                        # 展示/审计，不作身份键
            "sha256_full": sha256_full(source_path),
        },
        "ingest": {
            "time": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "decrypt_path": "com",
            "sheet": sheet_name,
            "period": period,
            "read_seconds": round(read_seconds, 1) if read_seconds is not None else None,
        },
        "data": {
            "row_count": int(len(df)),
            "column_count": int(len(df.columns)),
            "columns_hash": cols_hash,
            "columns": [str(c) for c in df.columns],
            "sums": column_sums(df),
        },
        "cust_info": {"file": None, "row_count": None},
    }
    # 原子写：先写同目录临时文件再 os.replace（避免半写 manifest 被并发读）
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
    print(f"  [注入] 已写 parquet+manifest（period={period}）: {pq_path}")
    return pq_path
