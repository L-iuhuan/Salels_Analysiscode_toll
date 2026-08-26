#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
看板生成器 V9 - 统一数据源版本
- C面数据从 gold_product_portrait.csv 直接生成，无需单独运行 generate_v4.py
- 所有面(A/B/C/D/E/F)数据统一从同一数据源生成
用法: python dashboard/generate_dashboard.py
"""

import pandas as pd, numpy as np, os, json, re, math, glob, sys
from collections import Counter, defaultdict

PROJECT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GOLD = os.path.join(PROJECT, "output", "gold")
SILVER = os.path.join(PROJECT, "output", "silver")
OUT = os.path.join(os.path.dirname(__file__), "dashboard_a.html")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# 批次②：读取统一配置（sheet 名、Dashboard 语义列优先级），复用现有 config.settings
sys.path.insert(0, PROJECT)
sys.path.insert(0, os.path.join(PROJECT, "processing"))  # settings.py 内部 `from config.settings_product import *` 需要
try:
    from processing.config import settings as cfg
except Exception as _e:  # 兼容非标准目录下运行
    cfg = None
    print(f"  [警告] 未能导入 processing.config.settings: {_e}")

DATA_SHEET_NAME = getattr(cfg, "DATA_SHEET_NAME", "24-26")
DASHBOARD_COL_PRIORITY = getattr(cfg, "DASHBOARD_COL_PRIORITY", {}) or {}
DASHBOARD_AXIS_CLIP = getattr(cfg, "DASHBOARD_AXIS_CLIP", {"margin_pct": [1, 99], "asp_pct": [1, 99]})

# ========== 批次③ 车道D：看板自缓存（preagg.json）+ 展示层分位截断 ==========
import time as _time_mod
try:
    from shared import fingerprint as _fp
except Exception as _e:  # 兼容非标准目录下运行
    _fp = None
    print(f"  [警告] 未能导入 processing.shared.fingerprint: {_e}")

PREAGG_DIR = os.path.join(PROJECT, "output", "dashboard")
PREAGG_PATH = os.path.join(PREAGG_DIR, "preagg.json")
_NO_CACHE = ("--no-cache" in sys.argv)
_DASH_TIMING = os.environ.get("DASH_TIMING", "0") == "1"
_PROG_START = _time_mod.time()


def _timed(label, t0):
    """耗时打点（DASH_TIMING=1 时输出各段耗时）。"""
    dt = _time_mod.time() - t0
    if _DASH_TIMING:
        print(f"  [计时] {label}: {dt:.1f}s")
    return _time_mod.time()


def _fmt_axis(v):
    """轴边界格式化：保留 2 位小数（与预演报告口径一致）。"""
    return f"{float(v):.2f}"


def _compute_percentile_bounds(vals, pct):
    """对数值列表求 [低分位, 高分位]；空列表/非有限值安全回退。"""
    arr = [float(v) for v in vals if v is not None and v == v]  # 过滤 None/NaN
    arr = [v for v in arr if v != float("inf") and v != float("-inf")]
    if not arr:
        return 0.0, 0.0
    lo, hi = pct
    lo_v = float(np.percentile(arr, lo))
    hi_v = float(np.percentile(arr, hi))
    return lo_v, hi_v


def _margin_axis_bounds(c_data):
    """从 C面 table 的 近12月毛利率%（全产品群体）计算截断边界。

    注意：用全量产品群体（而非 DATA.scatter 的 x——后者会剔除增长率缺失的产品，
    导致 p1/p99 偏窄），与预演报告(impact_rehearsal)口径一致
    （raw[-662.56,100] -> p1~p99[-17.66,80.83]）。
    """
    _mpct = DASHBOARD_AXIS_CLIP.get("margin_pct", [1, 99])
    _vals = []
    for _r in (c_data.get("table") or []):
        _v = _r.get("近12月毛利率%")
        if _v is None:
            continue
        try:
            _fv = float(_v)
        except (TypeError, ValueError):
            continue
        if _fv == _fv:  # 非 NaN
            _vals.append(_fv)
    _lo, _hi = _compute_percentile_bounds(_vals, _mpct)
    return {"min": _fmt_axis(_lo), "max": _fmt_axis(_hi), "raw_min": _lo, "raw_max": _hi,
            "raw_abs_min": (min(_vals) if _vals else 0), "raw_abs_max": (max(_vals) if _vals else 0)}


def _asp_axis_bounds(prod_trend):
    """从 F面产品月度 ASP 趋势数组计算截断边界（正 ASP 值）。"""
    _apct = DASHBOARD_AXIS_CLIP.get("asp_pct", [1, 99])
    _vals = []
    for _td in (prod_trend or {}).values():
        for _v in (_td.get("asp") or []):
            try:
                _fv = float(_v)
            except (TypeError, ValueError):
                continue
            if _fv > 0:
                _vals.append(_fv)
    _lo, _hi = _compute_percentile_bounds(_vals, _apct)
    return {"min": _fmt_axis(_lo), "max": _fmt_axis(_hi), "raw_min": _lo, "raw_max": _hi,
            "raw_abs_min": (min(_vals) if _vals else 0), "raw_abs_max": (max(_vals) if _vals else 0)}


def _load_silver_rows(csv_path, usecols):
    """读 silver_cleaned_rows（批次④a 看板底座）：优先同名 .parquet（存在且 mtime>=CSV），否则 CSV（仅 usecols）。"""
    pq = os.path.splitext(csv_path)[0] + ".parquet"
    if os.path.exists(pq) and os.path.exists(csv_path) and os.path.getmtime(pq) >= os.path.getmtime(csv_path):
        try:
            df = pd.read_parquet(pq, columns=usecols)
            print(f"  [Silver] silver_cleaned_rows ← parquet ({len(df)} 行)")
            return df
        except Exception as _e:
            print(f"  [警告] parquet 读取失败，回退 CSV: {type(_e).__name__}: {_e}")
    df = pd.read_csv(csv_path, encoding="utf-8-sig", usecols=usecols, low_memory=False)
    print(f"  [Silver] silver_cleaned_rows ← CSV ({len(df)} 行)")
    return df


def resolve_dashboard_col(raw_cols, semantic, candidates):
    """按语义列名优先级解析列；全部候选都找不到则报错退出（避免静默用错列）。

    raw_cols   : 表头列名列表
    semantic   : 语义名（仅用于报错信息）
    candidates : 候选列名子串，按优先级排序，取第一个命中的
    """
    for cand in candidates:
        m = [c for c in raw_cols if cand in str(c)]
        if m:
            return m[0]
    raise SystemExit(
        f"[致命] Dashboard 直读 Excel 找不到语义列「{semantic}」，候选列名 {candidates} 均未命中表头。"
        f"请检查 data/ 下最新 Excel 的列名，或更新 config/settings.py 的 DASHBOARD_COL_PRIORITY。"
    )


def derive_periods(latest_period):
    """纯函数：从最新数据期推导全部周期/年份字符串（批次② 年份周期动态化）。

    入参 latest_period 可为 pd.Period / "YYYY-MM" / Timestamp，统一转 pd.Period。
    返回 dict，key 与主流程 L396~417 的派生变量一一对应，另加趋势/半年度周期键。
    注意：prev_y/prev_m = 上一月的年/月（沿用原 _prev_y/_prev_m 语义）；
          prev_year = 上一自然年（latest_y - 1，用于同比/半年度对比）。
    """
    p = pd.Period(latest_period, freq="M")
    latest = str(p)
    latest_y = p.year
    latest_m = p.month
    prev_p = p - 1
    prev_y = prev_p.year
    prev_m = prev_p.month
    prev_year = latest_y - 1   # 上一自然年（同比/半年度）
    yy_latest = latest_y % 100   # 2 位年份缩写（F面 JSON key 用，如 26h1）
    yy_prev = prev_year % 100    # 上一自然年的 2 位缩写（如 25h1）
    y0 = latest_y - 2   # 趋势图起始年（3 年窗口最旧年）
    y1 = latest_y - 1
    y2 = latest_y
    return {
        "latest": latest,
        "latest_y": latest_y,
        "latest_m": latest_m,
        "prev_period": str(prev_p),
        "prev_y": prev_y,
        "prev_m": prev_m,
        "prev_year": prev_year,
        "yy_latest": yy_latest,
        "yy_prev": yy_prev,
        "y0": y0, "y1": y1, "y2": y2,
        "years": [y0, y1, y2],
        "ytd_start": f"{latest_y}-01-01",
        "ytd_end": p.end_time.strftime("%Y-%m-%d"),
        "pytd_start": f"{prev_year}-01-01",
        "pytd_end": (p - 12).end_time.strftime("%Y-%m-%d"),
        "latest_month_start": p.start_time.strftime("%Y-%m-%d"),
        "latest_month_end": p.end_time.strftime("%Y-%m-%d"),
        "prev_month_start": prev_p.start_time.strftime("%Y-%m-%d"),
        "prev_month_end": prev_p.end_time.strftime("%Y-%m-%d"),
        "start_12m": str(p - 11),
        "prior12_end": str(p - 12),
        "cutoff_new": str(p - 12),
        "near6_start": str(p - 5),
        "prev6_start": str(p - 11),
        "prev6_end": str(p - 6),
        "t_mo_start": f"{y0}-01",       # 月度趋势表起始月
        "trend_months_start": f"{y0}-07",  # F面产品月度趋势起始月
        "h1_periods": {                  # F面半年对比（前年H1/前年H2/当年H1，key 用 2 位年份缩写）
            f"{yy_prev}h1": (f"{prev_year}-01-01", f"{prev_year}-06-30"),
            f"{yy_prev}h2": (f"{prev_year}-07-01", f"{prev_year}-12-31"),
            f"{yy_latest}h1": (f"{latest_y}-01-01", f"{latest_y}-06-30"),
        },
    }


def _selftest_periods():
    """纯函数自测：伪造 2027 年数据期，验证周期字符串推导正确。"""
    fake = pd.Period("2027-06", freq="M")
    d = derive_periods(fake)
    assert d["latest"] == "2027-06", d["latest"]
    assert d["latest_y"] == 2027, d["latest_y"]
    assert d["prev_y"] == 2027 and d["prev_m"] == 5, (d["prev_y"], d["prev_m"])   # 上一月=2027-05
    assert d["prev_year"] == 2026, d["prev_year"]                                   # 上一自然年=2026
    assert (d["y0"], d["y1"], d["y2"]) == (2025, 2026, 2027), d["years"]
    assert d["years"] == [2025, 2026, 2027]
    assert d["ytd_start"] == "2027-01-01"
    assert d["ytd_end"] == "2027-06-30"
    assert d["pytd_start"] == "2026-01-01"
    assert d["start_12m"] == "2026-07"
    assert d["prior12_end"] == "2026-06"
    assert list(d["h1_periods"].keys()) == ["26h1", "26h2", "27h1"], d["h1_periods"]
    assert d["h1_periods"]["27h1"] == ("2027-01-01", "2027-06-30")
    assert d["h1_periods"]["26h1"] == ("2026-01-01", "2026-06-30")
    assert d["h1_periods"]["26h2"] == ("2026-07-01", "2026-12-31")
    assert d["t_mo_start"] == "2025-01"
    assert d["trend_months_start"] == "2025-07"
    # 2025-06 数据期（闰年/年中）回归
    d2 = derive_periods(pd.Period("2025-06", freq="M"))
    assert d2["latest"] == "2025-06" and d2["y0"] == 2023 and d2["y2"] == 2025
    assert d2["prev_year"] == 2024
    assert list(d2["h1_periods"].keys()) == ["24h1", "24h2", "25h1"]
    print(f"[自测] derive_periods(2027-06) 推导结果: {json.dumps({k: d[k] for k in ('latest', 'latest_y', 'prev_year', 'y0', 'y1', 'y2', 'years', 'ytd_start', 't_mo_start', 'trend_months_start', 'h1_periods')}, ensure_ascii=False)}")
    print("[自测] 纯函数周期推导 PASS")
    return True


if "--selftest" in sys.argv:
    _selftest_periods()
    sys.exit(0)

def j(v):
    if isinstance(v,(np.integer,)):return int(v)
    if isinstance(v,(np.floating,)):return round(float(v),2) if not np.isnan(v) else 0
    if isinstance(v,np.bool_):return bool(v)
    if pd.isna(v):return 0 if isinstance(v,(float,np.floating)) else ""
    return v

# ========== C面数据构建函数（从 generate_v4.py 移植） ==========
# C面DATA.table的27个字段
C_TABLE_FIELDS = [
    "产品名称", "所属参照组", "帕累托分类", "当前画像", "管理层摘要",
    "销量动能", "盈利健康",
    "近12月销量", "前12月销量",
    "近12月增长率%", "前12月增长率%", "营收增长率%",
    "当月毛利率%", "近12月毛利率%", "前12月毛利率%", "毛利率同比变化(pp)",
    "毛利率趋势斜率%/月",
    "综合评分", "综合风险等级", "风险主导因子",
    "通用策略建议",
    "ASP趋势%/月", "ASP趋势方向", "营收-毛利综合判断",
    "客户集中度-前1大%", "客户集中度-前3大%", "订货波动性CV",
    "特情说明",
]

C_PORTRAIT_TYPES = [
    "主动收缩", "健康扩张", "利润优化", "夕阳产品", "成长期",
    "新品观察", "清仓/偶发", "现金牛", "衰退期", "隐性衰退", "预警增长",
]
C_DECLINING_PORTRAITS = {"衰退期", "夕阳产品", "隐性衰退"}
C_GROWING_PORTRAITS = {"成长期", "健康扩张", "预警增长"}
C_HIGH_RISK_LABEL = "高风险"

def c_safe_val(v):
    """将值转换为JSON安全的Python原生类型。"""
    if v is None: return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)): return None
    if isinstance(v, (np.integer,)): return int(v)
    if isinstance(v, (np.floating,)): return float(v)
    if isinstance(v, (np.bool_,)): return bool(v)
    if isinstance(v, (np.ndarray,)): return v.tolist()
    return v

def c_mode_with_tiebreak(arr):
    """众数。平局时返回在数组中最先出现的值。"""
    counts = Counter(arr)
    if not counts: return None
    max_count = max(counts.values())
    for v in arr:
        if counts.get(v, 0) == max_count:
            return v
    return None

def build_c_table(df):
    """构建C面DATA.table：产品明细列表。"""
    records = []
    for _, row in df.iterrows():
        rec = {}
        for field in C_TABLE_FIELDS:
            v = row.get(field)
            if pd.isna(v):
                rec[field] = None
            else:
                rec[field] = c_safe_val(v)
        if rec.get("综合风险等级") is None:
            rec["综合风险等级"] = "暂无评分"
        rec["数据不足"] = False
        records.append(rec)
    return records

def build_c_kpi(table):
    """构建C面DATA.kpi：汇总统计。"""
    total = len(table)
    high_risk = sum(1 for r in table if r.get("综合风险等级") == C_HIGH_RISK_LABEL)
    declining = sum(1 for r in table if r.get("当前画像") in C_DECLINING_PORTRAITS)
    growing = sum(1 for r in table if r.get("当前画像") in C_GROWING_PORTRAITS)
    gm_sum = sales_sum = 0.0
    for r in table:
        gm = r.get("近12月毛利率%")
        sales = r.get("近12月销量")
        if gm is not None and sales is not None:
            gm_sum += float(gm) * float(sales)
            sales_sum += float(sales)
    avg_gm = round(gm_sum / sales_sum, 1) if sales_sum else 0.0
    growth_vals = [float(r.get("近12月增长率%")) for r in table if r.get("近12月增长率%") is not None]
    avg_growth = round(sum(growth_vals) / len(growth_vals), 1) if growth_vals else 0.0
    return {
        "total_products": total, "high_risk": high_risk, "extreme_risk": 0,
        "avg_gm": avg_gm, "avg_growth": avg_growth,
        "declining": declining, "growing": growing, "data_insufficient": 0,
    }

def build_c_charts(table):
    """构建C面DATA.charts：预计算分布。"""
    def count_field(field):
        cnt = {}
        for r in table:
            v = r.get(field)
            if v: cnt[v] = cnt.get(v, 0) + 1
        return cnt
    return {
        "portrait": count_field("当前画像"),
        "risk": count_field("综合风险等级"),
        "pareto": count_field("帕累托分类"),
        "summary": count_field("管理层摘要"),
        "profit_health": count_field("盈利健康"),
        "momentum": count_field("销量动能"),
        "营收-毛利综合判断": count_field("营收-毛利综合判断"),
        "风险主导因子": count_field("风险主导因子"),
        "ASP趋势方向": count_field("ASP趋势方向"),
    }

def build_c_filters(table):
    """构建C面DATA.filters：筛选下拉框的唯一值。"""
    unique = {}
    for key, field in [
        ("portrait", "当前画像"), ("risk", "综合风险等级"),
        ("pareto", "帕累托分类"), ("group", "所属参照组"),
        ("momentum", "销量动能"), ("profit", "盈利健康"),
        ("summary", "管理层摘要"),
    ]:
        vals = sorted(set(r.get(field) for r in table if r.get(field)))
        unique[key] = vals
    return unique

def build_c_scatter(df):
    """构建C面DATA.scatter：气泡图数据。"""
    scatter = []
    for _, row in df.iterrows():
        x = c_safe_val(row.get("近12月毛利率%"))
        y = c_safe_val(row.get("近12月增长率%"))
        if x is None or y is None: continue
        scatter.append({
            "name": c_safe_val(row.get("产品名称")),
            "group": c_safe_val(row.get("所属参照组")),
            "x": float(x), "y": float(y),
            "z": float(c_safe_val(row.get("近12月销量")) or 0),
            "risk": c_safe_val(row.get("综合风险等级")),
            "portrait": c_safe_val(row.get("当前画像")),
            "gm_trend": c_safe_val(row.get("毛利率趋势斜率%/月")),
        })
    return scatter

def build_c_history(df):
    """构建C面DATA.history：每产品12个月的时间序列。"""
    hist_cols = {"portrait": [], "gm": [], "sales": []}
    for col in df.columns:
        col_str = str(col).strip()
        m = re.match(r"当前画像_t-(\d+)", col_str)
        if m:
            hist_cols["portrait"].append((int(m.group(1)), col_str))
            continue
        m = re.match(r"近12月毛利率%_t-(\d+)", col_str)
        if m:
            hist_cols["gm"].append((int(m.group(1)), col_str))
            continue
        m = re.match(r"近12月销量_t-(\d+)", col_str)
        if m:
            hist_cols["sales"].append((int(m.group(1)), col_str))
            continue
    for key in hist_cols:
        hist_cols[key].sort(key=lambda x: x[0])
    portrait_cols = [c for _, c in hist_cols["portrait"][:12]]
    gm_cols = [c for _, c in hist_cols["gm"][:12]]
    sales_cols = [c for _, c in hist_cols["sales"][:12]]
    history = {}
    for _, row in df.iterrows():
        name = str(row.get("产品名称", ""))
        if not name: continue
        portraits = [str(row.get(pc)) if pd.notna(row.get(pc)) and row.get(pc) else "" for pc in portrait_cols]
        sales = []
        for sc in sales_cols:
            v = row.get(sc)
            try: sales.append(float(v) if pd.notna(v) else 0.0)
            except: sales.append(0.0)
        gm = []
        for gc in gm_cols:
            v = row.get(gc)
            try: gm.append(float(v) if pd.notna(v) else 0.0)
            except: gm.append(0.0)
        while len(portraits) < 12: portraits.append("")
        while len(sales) < 12: sales.append(0.0)
        while len(gm) < 12: gm.append(0.0)
        history[name] = {"portraits": portraits[:12], "sales": sales[:12], "gm": gm[:12]}
    return history

def build_c_sankey(table, history):
    """构建C面DATA.sankey：画像季度迁移桑基图。"""
    quarter_modes = {}
    for r in table:
        name = r.get("产品名称")
        if not name: continue
        curr = r.get("当前画像")
        hist = history.get(name)
        if not hist or not hist.get("portraits"): continue
        pts = hist["portraits"]
        q1 = list(reversed([p for p in pts[8:12] if p]))
        q2 = list(reversed([p for p in pts[4:8] if p]))
        q3 = list(reversed([p for p in pts[0:4] if p]))
        qm = {
            "Q1": c_mode_with_tiebreak(q1) if q1 else None,
            "Q2": c_mode_with_tiebreak(q2) if q2 else None,
            "Q3": c_mode_with_tiebreak(q3) if q3 else None,
            "Q4": curr,
        }
        quarter_modes[name] = qm
    transitions = {
        ("Q1", "Q2"): defaultdict(list),
        ("Q2", "Q3"): defaultdict(list),
        ("Q3", "Q4"): defaultdict(list),
    }
    for name, qm in quarter_modes.items():
        for (src_k, tgt_k), storage in transitions.items():
            src = qm.get(src_k)
            tgt = qm.get(tgt_k)
            if src and tgt: storage[(src, tgt)].append(name)
    nodes = []
    for q in ["Q1", "Q2", "Q3", "Q4"]:
        for p in C_PORTRAIT_TYPES:
            nodes.append({"name": f"{q}_{p}"})
    links = []
    for (src_q, tgt_q), storage in transitions.items():
        for (src_p, tgt_p), products in storage.items():
            links.append({"source": f"{src_q}_{src_p}", "target": f"{tgt_q}_{tgt_p}", "value": len(products), "products": products})
    return {"nodes": nodes, "links": links}

def load_product_report():
    """定位并读取最新产品生命周期报告Excel（含历史/桑基/数据月份）。

    返回 (df_snapshot, df_history, data_month, insuff_count)。
    若未找到报告则返回 (None, None, None, 0)，调用方回退gold快照（无历史/桑基/月份）。
    """
    report_dir = os.path.join(PROJECT, "output", "report")
    cands = sorted(
        [f for f in glob.glob(os.path.join(report_dir, "产品生命周期报告_v4.0_*.xlsx"))
         if not os.path.basename(f).startswith("~$")],
        key=os.path.getmtime, reverse=True,
    )
    if not cands:
        print("  [C面] 未找到产品生命周期报告，回退gold快照（历史/桑基/月份缺失）")
        return None, None, None, 0
    path = cands[0]
    print(f"  [C面] 产品报告: {os.path.basename(path)}")
    xls = pd.ExcelFile(path, engine="calamine")
    def _sheet(frag):
        for nm in xls.sheet_names:
            if frag in nm:
                return nm
        return None
    df_snap = pd.read_excel(path, sheet_name=_sheet("产品快照表") or xls.sheet_names[0], engine="calamine")
    df_snap.columns = [str(c).strip() for c in df_snap.columns]
    # 历史：主表自带 _t-N 列（Format A）则用主表，否则读"历史画像追踪"（Format B）
    hist_name = _sheet("历史画像追踪")
    has_hist_cols = any(re.match(r"当前画像_t-\d+", str(c)) for c in df_snap.columns)
    if has_hist_cols:
        df_hist = df_snap
    elif hist_name:
        df_hist = pd.read_excel(path, sheet_name=hist_name, engine="calamine")
        df_hist.columns = [str(c).strip() for c in df_hist.columns]
    else:
        df_hist = None
    # 数据月份
    data_month = None
    if "最新数据月份" in df_snap.columns:
        dm = df_snap["最新数据月份"].dropna()
        if not dm.empty:
            data_month = str(dm.iloc[0])
    # 数据不足产品数
    insuff = 0
    insuff_name = _sheet("数据不足")
    if insuff_name:
        try:
            insuff = len(pd.read_excel(path, sheet_name=insuff_name, engine="calamine"))
        except Exception:
            insuff = 0
    return df_snap, df_hist, data_month, insuff


def build_c_data(prod_df, hist_df=None, data_month=None, insuff_count=0):
    """构建完整的C面DATA对象。

    prod_df     : 产品当前快照（gold_product_portrait.csv，与A面产品列表同源）
    hist_df     : 历史画像追踪df（含 当前画像_t-N / 近12月毛利率%_t-N / 近12月销量_t-N）；
                  None 时回退用 prod_df（无历史则桑基图为空）
    data_month  : 数据月份（如 2026-06），写入 DATA.data_month
    insuff_count: 数据不足产品数，写入 kpi.data_insufficient
    """
    print("[C面] 构建DATA（统一数据源）...")
    table = build_c_table(prod_df)
    hist_src = hist_df if hist_df is not None else prod_df
    history = build_c_history(hist_src)
    kpi = build_c_kpi(table)
    kpi["data_insufficient"] = int(insuff_count)
    charts = build_c_charts(table)
    filters = build_c_filters(table)
    scatter = build_c_scatter(prod_df)
    sankey = build_c_sankey(table, history)
    data = {
        "kpi": kpi, "charts": charts, "scatter": scatter,
        "sankey": sankey, "table": table, "filters": filters,
        "history": history, "rfm": {}, "graph": {"nodes": [], "links": []},
    }
    if data_month:
        data["data_month"] = str(data_month)
    _nonempty_hist = sum(1 for v in history.values() if any(v.get("portraits", [])))
    print(f"  table: {len(table)} records")
    print(f"  history: {len(history)} products (非空历史:{_nonempty_hist})")
    print(f"  scatter: {len(scatter)} points")
    print(f"  sankey: {len(sankey['nodes'])} nodes, {len(sankey['links'])} links")
    print(f"  kpi: {kpi}")
    if data_month:
        print(f"  数据月份: {data_month}")
    return data

# ========== W4 插拔：faces.yaml 面开关（enabled/visible） ==========
_FACES_CFG = None

def _face_visible(face_id):
    """面是否可视（enabled 且 visible）。faces.yaml 缺失/异常时默认全部可视（向后兼容）。"""
    global _FACES_CFG
    if _FACES_CFG is None:
        try:
            import yaml as _yaml
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "faces.yaml"),
                      encoding="utf-8") as _f:
                _FACES_CFG = (_yaml.safe_load(_f) or {}).get("faces", {})
        except Exception:
            _FACES_CFG = {}
    _f = _FACES_CFG.get(face_id, {})
    return bool(_f.get("enabled", True)) and bool(_f.get("visible", True))


def _hide_invisible_faces(page_html):
    """插拔（W4）：faces.yaml 中不可见面的 tab 按钮从输出中移除（服务端，模板结构不动）。
    同时移除对应按钮的 JS 监听器——否则 getElementById 拿到 null，addEventListener 抛 TypeError 卡死后续 JS。"""
    _tab_names = {"A": "总览决策", "R": "风险与行动", "B": "客户360", "C": "产品生命周期",
                  "D": "销售能力", "E": "月度作战雷达", "F": "半年度专项"}
    for _fid, _fname in _tab_names.items():
        if not _face_visible(_fid):
            for _pat in (f'<button class="tab-btn" data-tab="{_fid}" id="btn{_fid}">{_fname}</button>',
                         f'<button class="tab-btn active" data-tab="{_fid}" id="btn{_fid}">{_fname}</button>'):
                page_html = page_html.replace(_pat + "\n", "").replace(_pat, "")
            _lis = f"document.getElementById('btn{_fid}').addEventListener('click',function(){{switchTab('{_fid}')}});"
            page_html = page_html.replace(_lis + "\n", "").replace(_lis, "")
    return page_html


# ========== 批次③ 车道D：看板自缓存（preagg.json）判定 ==========
# 指纹新鲜且缓存存在 → 走缓存路径（跳过全部重算，直接渲染），否则全算并写缓存。
_fp_cur = None
_cache_hit = False
_cached_obj = None
if not _NO_CACHE and _fp is not None:
    # 批次④a 集成修复：两侧（generate_dashboard 与 run_chain --dashboard-only 门禁）统一纳入 Excel 身份。
    # 恢复默认自动探测（excel_path=None → _latest_excel 自动取 data/ 最新 xlsx，8MB 头部 sha256 仅 ~50ms）。
    # 语义：用户放入新月份 Excel 但未全量跑时，--dashboard-only 必须报"请先全量跑"（台账未决#3 拍板结论）；
    # dashboard 数据源来自 silver 的事实由指纹 outputs 键表达，excel 键表达"输入是否已变"，两者不冲突。
    try:
        _fp_cur = _fp.compute_dashboard_fingerprint(PROJECT)
    except Exception as _e:
        _fp_cur = None
        print(f"  [缓存] 指纹计算失败: {_e}")
    if _fp_cur is not None and os.path.exists(PREAGG_PATH):
        try:
            with open(PREAGG_PATH, "r", encoding="utf-8") as _f:
                _cached_obj = json.load(_f)
            if _fp.fingerprints_equal(_cached_obj.get("fingerprint"), _fp_cur):
                _cache_hit = True
        except Exception as _e:
            _cached_obj = None
            print(f"  [缓存] preagg.json 读取/比对失败: {_e}")

if _cache_hit and _cached_obj:
    # ---- 缓存命中：跳过全部重算，直接进 JSON 注入 + 渲染 ----
    _T_CACHE0 = _time_mod.time()
    print("[缓存] preagg.json 命中，跳过重算，直接渲染")
    # Tauri 壳依赖的子阶段标记：原格式原样打印
    for _mk in [
        "[1/5] 加载数据...", "[2/5] YTD KPI...", "[3/5] 月度趋势...",
        "[4/5] 饼图+散点...", "[5/5] 客户列表+B面...",
        "[6/6] D面 销售能力...", "[7/7] E面 月度作战雷达...", "[8/8] F面H1汇总 + 部门级次 + 新品分析...",
    ]:
        print(_mk)

    _pl_c = _cached_obj.get("payload", {})
    _cached_replacements = _pl_c.get("replacements", {}) or {}
    _cached_data_block = _pl_c.get("data_block", "")
    _cached_asp_axis = _pl_c.get("asp_axis", {}) or {}

    # 重建 C面（轻量：读报告 + 构建 DATA，与全算路径同源；报告缺失回退 gold 快照）
    import pathlib as _pl_mod
    try:
        _prod_df_cache = pd.read_csv(os.path.join(GOLD, "gold_product_portrait.csv"))
    except Exception:
        _prod_df_cache = None
    _snap_df_c, _hist_df_c, _data_month_c, _insuff_c = load_product_report()
    _c_src_c = _snap_df_c if _snap_df_c is not None else _prod_df_cache
    c_data = build_c_data(_c_src_c, hist_df=_hist_df_c, data_month=_data_month_c, insuff_count=_insuff_c)
    c_data_json = json.dumps(c_data, ensure_ascii=False, separators=(",", ":"))
    print(f"  C_DATA JSON大小: {len(c_data_json):,} 字符")

    # 展示层截断：毛利率轴始终由当前 C面 scatter 现算（保证与全算路径一致）
    _mb = _margin_axis_bounds(c_data)
    print(f"  [截断] 毛利率轴: raw[{_mb['raw_abs_min']:.2f}, {_mb['raw_abs_max']:.2f}] "
          f"-> p{DASHBOARD_AXIS_CLIP.get('margin_pct', [1,99])[0]}~p{DASHBOARD_AXIS_CLIP.get('margin_pct', [1,99])[1]}[{_mb['min']}, {_mb['max']}]")

    _replacements = dict(_cached_replacements)
    _replacements["%%DATA_BLOCK%%"] = _cached_data_block
    _replacements["%%C_DATA_JSON%%"] = c_data_json
    _replacements["%%MARGIN_AXIS_MIN%%"] = _mb["min"]
    _replacements["%%MARGIN_AXIS_MAX%%"] = _mb["max"]
    _replacements["%%ASP_AXIS_MIN%%"] = _fmt_axis(_cached_asp_axis.get("min", 0))
    _replacements["%%ASP_AXIS_MAX%%"] = _fmt_axis(_cached_asp_axis.get("max", 0))
    # R面与 C面/毛利率轴同理"永远现算"：审定 md 内容毫秒级解析，不入缓存，
    # 保证"改审定文档 → --dashboard-only 秒级重渲染"流程不被缓存挡住。
    # 注意：缓存命中路径在脚本前段执行，全算路径的 latest 变量此时尚未定义，
    # 数据月份从缓存的 %%LATEST%% 占位符（如 2026-06）取。
    try:
        import generate_risk_face as _rface_c
        _r_month_c = str(_cached_replacements.get("%%LATEST%%", "")).replace("-", "")
        _replacements["%%R_FACE_HTML%%"] = _rface_c.build_r_face_inner_html(_r_month_c)
    except Exception as _e:
        _replacements["%%R_FACE_HTML%%"] = ('<div class="cb"><h3>风险与行动</h3><div class="note">'
                                            f'总体文档读取失败（{type(_e).__name__}: {_e}）</div></div>')

    # 渲染
    _template_c = _pl_mod.Path(__file__).parent / "template.html"
    _html_c = _template_c.read_text(encoding="utf-8")
    for _k_c, _v_c in _replacements.items():
        _html_c = _html_c.replace(_k_c, _v_c)
    _html_c = _hide_invisible_faces(_html_c)
    with open(OUT, "w", encoding="utf-8") as _f_c:
        _f_c.write(_html_c)
    _sz_c = os.path.getsize(OUT) / (1024 * 1024)
    print(f"\n[OK] {OUT} {_sz_c:.1f}MB | [缓存命中] 数据直接来自 preagg.json")
    print(f"  [缓存] 命中路径总耗时: {_time_mod.time() - _T_CACHE0:.1f}s (进程累计 {_time_mod.time() - _PROG_START:.1f}s)")

    # 轻量审计（HTML 内容检查；Raw=Silver 需 rex/silver，缓存路径跳过）
    _checks_c = [
        ("KPI占位符", "%%KPI_R%%" not in _html_c),
        ("TREND数据", "var TREND = {" in _html_c),
        ("SA列表", "var SA = [" in _html_c),
        ("PIE饼图", "var PIE = [" in _html_c),
        ("SCAT散点", "var SCAT = [" in _html_c),
        ("B_CUSTS", "var B_CUSTS = [" in _html_c),
        ("C面DATA", "const DATA = {" in _html_c and "TABS" in _html_c),
    ]
    _all_ok_c = True
    for _n_c, _ok_c in _checks_c:
        _s_c = "OK" if _ok_c else "FAIL"
        if not _ok_c:
            _all_ok_c = False
        print(f"  [{_s_c}] {_n_c}")
    print("  [SKIP] Raw=Silver验证（缓存命中，跳过真实数值校验）")
    print(f"{'全部通过' if _all_ok_c else '有检查失败'}")
    sys.exit(0)

# ========== 1. 加载 ==========
print("[1/5] 加载数据...")
_t_seg0 = _time_mod.time()  # 计时打点（DASH_TIMING=1 时输出各段耗时）
# Gold CSV（客户属性）
df = pd.read_csv(os.path.join(GOLD,"客户全景.csv"))
# C面产品数据
prod_df = pd.read_csv(os.path.join(GOLD,"gold_product_portrait.csv"))
# 批次④a：看板零 Excel 收口。默认读 silver_cleaned_rows（优先 parquet，生产 dtype 语义）；
# --from-excel 显式回退到原始 Excel 直读（行为与批次③完全一致）。
import glob as _glob
_FROM_EXCEL = ("--from-excel" in sys.argv)
if _FROM_EXCEL:
    # ── 原始 Excel 直读路径（显式回退开关，默认不走）──
    _xl_candidates = sorted(
        [f for f in _glob.glob(os.path.join(PROJECT, "data", "*.xlsx"))
         if not os.path.basename(f).startswith("~$")],
        key=os.path.getmtime, reverse=True
    )
    if not _xl_candidates:
        raise FileNotFoundError("data/ 目录下未找到 .xlsx 文件")
    excel_path = _xl_candidates[0]
    print(f"  数据源: {os.path.basename(excel_path)} (--from-excel 直读)")
    raw_all_cols = list(pd.read_excel(excel_path, sheet_name=DATA_SHEET_NAME, nrows=0, engine="calamine").columns)
    # 找到产品列（含"产品线"或"产品品种"关键字）
    prod_cols_avail = [c for c in raw_all_cols if "产品" in str(c) or "型号" in str(c)]
    # 优先选"产品线"列，其次"产品品种"
    prod_col = next((c for c in prod_cols_avail if "产品线" in str(c)),
                next((c for c in prod_cols_avail if "品种" in str(c)), None))
    # 语义列解析：品类 / 产品线（新） / 是否新品 / 实际业务员（优先级在 settings.DASHBOARD_COL_PRIORITY）
    _cfg_cands = DASHBOARD_COL_PRIORITY or {}
    cat_col = resolve_dashboard_col(raw_all_cols, "品类", _cfg_cands.get("category", ["产品品类（新）", "产品品类", "品类"]))
    pline_new_col = resolve_dashboard_col(raw_all_cols, "产品线（新）", _cfg_cands.get("product_line_new", ["型号_产品线（新）", "产品线（新）", "产品线"]))
    newprod_col = resolve_dashboard_col(raw_all_cols, "是否新品", _cfg_cands.get("is_new", ["是否新品", "新品标记"]))
    sales_col_raw = resolve_dashboard_col(raw_all_cols, "实际业务员", _cfg_cands.get("sales", ["实际业务员", "业务员", "销售员"]))
    # 存货名称列（用于A面产品型号变迁）
    item_col = next((c for c in raw_all_cols if "存货名称" in str(c)), None)
    keep_cols = ["发货日期","RMB 未税金额小计","利润","发货数量","终端客户名称_客户类别","终端客户简称","客户订单号"]
    if prod_col: keep_cols.append(prod_col)
    if cat_col: keep_cols.append(cat_col)
    if item_col: keep_cols.append(item_col)
    cat_new_col = cat_col
    if pline_new_col and pline_new_col not in keep_cols:
        keep_cols.append(pline_new_col)
    if newprod_col and newprod_col not in keep_cols:
        keep_cols.append(newprod_col)
    if sales_col_raw and sales_col_raw not in keep_cols:
        keep_cols.append(sales_col_raw)
    rex = pd.read_excel(excel_path, sheet_name=DATA_SHEET_NAME, usecols=keep_cols, engine="calamine")
    rex = rex[keep_cols]
    print(f"  产品列: {repr(prod_col)}  品类列: {repr(cat_col)}")
    rex["_d"] = pd.to_datetime(rex["发货日期"], errors="coerce")
    rex["_rev"] = pd.to_numeric(rex["RMB 未税金额小计"], errors="coerce").fillna(0)
    rex["_profit"] = pd.to_numeric(rex["利润"], errors="coerce").fillna(0)
    rex["_qty"] = pd.to_numeric(rex["发货数量"], errors="coerce").fillna(0)
    rex["_cust"] = rex["终端客户简称"].astype(str).str.strip()
    rex["_tier"] = rex["终端客户名称_客户类别"].astype(str)
    rex["_prod"] = rex[prod_col].astype(str) if prod_col else pd.Series("未知", index=rex.index)
    rex["_cat"] = rex[cat_col].astype(str).str.strip() if cat_col else pd.Series("未知", index=rex.index)
    rex["_item"] = rex[item_col].astype(str).str.strip() if item_col else pd.Series("未知", index=rex.index)
    rex["_cat_new"] = rex[cat_new_col].astype(str).str.strip() if cat_new_col else pd.Series("", index=rex.index)
    rex["_is_new"] = rex[newprod_col].astype(str).str.contains("是") if newprod_col else pd.Series(False, index=rex.index)
    rex["_ym"] = rex["_d"].dt.strftime("%Y-%m")
else:
    # ── Silver 底座（默认）：读 silver_cleaned_rows，列名已是 ERP_COL_MAP 归一后的标准名 ──
    _keep = ["发货日期","金额","利润","数量","客户类别","客户编号","客户订单号",
             "产品一级分类","产品品类","产品品种","型号_产品线（新）","新品标记","实际业务员"]
    _keep = [c for c in _keep if c in pd.read_csv(os.path.join(SILVER, "silver_cleaned_rows.csv"), nrows=0, encoding="utf-8-sig").columns]
    rex = _load_silver_rows(os.path.join(SILVER, "silver_cleaned_rows.csv"), _keep)
    # 语义列变量（与 --from-excel 路径同名，供下游 D面6a/E面7c 等使用）
    prod_col = "产品一级分类" if "产品一级分类" in rex.columns else None
    cat_col = "产品品类" if "产品品类" in rex.columns else None
    cat_new_col = cat_col
    item_col = "产品品种" if "产品品种" in rex.columns else None
    pline_new_col = "型号_产品线（新）" if "型号_产品线（新）" in rex.columns else None
    newprod_col = "新品标记" if "新品标记" in rex.columns else None
    sales_col_raw = "实际业务员" if "实际业务员" in rex.columns else None
    print(f"  产品列: {repr(prod_col)}  品类列: {repr(cat_col)}")
    rex["_d"] = pd.to_datetime(rex["发货日期"], errors="coerce")
    rex["_rev"] = pd.to_numeric(rex["金额"], errors="coerce").fillna(0)
    rex["_profit"] = pd.to_numeric(rex["利润"], errors="coerce").fillna(0)
    rex["_qty"] = pd.to_numeric(rex["数量"], errors="coerce").fillna(0)
    # 客户编号：silver 已将空客户 fillna("未知客户")；为与 --from-excel 路径（空客户→"nan"）逐字节一致，
    # 将"未知客户"映射回 "nan"（Step 0 已证：仅 1799 行空客户被 fillna，无真实客户叫"未知客户"）
    rex["_cust"] = rex["客户编号"].astype(str).str.strip().str.replace("未知客户", "nan")
    rex["_tier"] = rex["客户类别"].astype(str)
    rex["_prod"] = rex["产品一级分类"].astype(str) if "产品一级分类" in rex.columns else pd.Series("未知", index=rex.index)
    rex["_cat"] = rex["产品品类"].astype(str).str.strip() if "产品品类" in rex.columns else pd.Series("未知", index=rex.index)
    rex["_item"] = rex["产品品种"].astype(str).str.strip() if "产品品种" in rex.columns else pd.Series("未知", index=rex.index)
    rex["_cat_new"] = rex["产品品类"].astype(str).str.strip() if "产品品类" in rex.columns else pd.Series("", index=rex.index)
    rex["_is_new"] = rex["新品标记"].astype(str).str.contains("是") if "新品标记" in rex.columns else pd.Series(False, index=rex.index)
    rex["_ym"] = rex["_d"].dt.strftime("%Y-%m")

# ---- 自动检测最新月份及衍生日期变量（批次②：统一由纯函数 derive_periods 推导）----
_max_date = rex["_d"].max()
_latest_period = pd.Period(_max_date, freq="M")
_PD = derive_periods(_latest_period)
latest = _PD["latest"]
_latest_y = _PD["latest_y"]
_latest_m = _PD["latest_m"]
_prev_period = pd.Period(_PD["prev_period"], freq="M")
_prev_y = _PD["prev_y"]
_prev_m = _PD["prev_m"]
_prev_year = _PD["prev_year"]
_yy_latest = _PD["yy_latest"]
_yy_prev = _PD["yy_prev"]
ytd_start = _PD["ytd_start"]
ytd_end = _PD["ytd_end"]
pytd_start = _PD["pytd_start"]
pytd_end = _PD["pytd_end"]
latest_month_start = _PD["latest_month_start"]
latest_month_end = _PD["latest_month_end"]
prev_month_start = _PD["prev_month_start"]
prev_month_end = _PD["prev_month_end"]
start_12m = _PD["start_12m"]
prior12_end = _PD["prior12_end"]
cutoff_new = _PD["cutoff_new"]
near6_start = _PD["near6_start"]
prev6_start = _PD["prev6_start"]
prev6_end = _PD["prev6_end"]
# 年份/半年度动态化衍生（批次②）
_y0 = _PD["y0"]; _y1 = _PD["y1"]; _y2 = _PD["y2"]
_years = _PD["years"]
_h1_periods = _PD["h1_periods"]
_t_mo_start = _PD["t_mo_start"]
_trend_months_start = _PD["trend_months_start"]

print(f"  Raw Excel: {len(rex)}行 客户:{rex['_cust'].nunique()} 产品:{rex['_prod'].nunique()} 存货:{rex['_item'].nunique()}")

# ========== 2. KPI ==========
_timed("加载数据+rex构建", _t_seg0); _t_seg0 = _time_mod.time()
print("[2/5] YTD KPI...")
r26 = rex[(rex["_d"]>=ytd_start)&(rex["_d"]<=ytd_end)]
r25 = rex[(rex["_d"]>=pytd_start)&(rex["_d"]<=pytd_end)]
ytd_r = float(r26["_rev"].sum()); ytd_p = float(r26["_profit"].sum())
lytd_r = float(r25["_rev"].sum()); lytd_p = float(r25["_profit"].sum())

# KA+AA
kaaa_rex = r26[r26["_tier"].str.contains("KA|AA", na=False)]
kaaa_r25 = r25[r25["_tier"].str.contains("KA|AA", na=False)]
kaaa_yr = float(kaaa_rex["_rev"].sum()); kaaa_yp = float(kaaa_rex["_profit"].sum())
kaaa_sc = kaaa_rex["_cust"].nunique()

kpi_r = round(ytd_r/1e4,0); kpi_p = round(ytd_p/1e4,0); kpi_c = round((ytd_r-ytd_p)/1e4,0)
kpi_mg = round(ytd_p/ytd_r*100,1) if ytd_r>0 else 0
kpi_ry = round((ytd_r-lytd_r)/lytd_r*100,1) if lytd_r>0 else 0
kpi_py = round((ytd_p-lytd_p)/lytd_p*100,1) if lytd_p>0 else 0
prior_mg = round(lytd_p/lytd_r*100,1) if lytd_r>0 else 0
kpi_mg_yoy = round(kpi_mg-prior_mg,1)
kpi_sr = round(kaaa_yr/1e4,0); kpi_sp = round(kaaa_yp/1e4,0)
kpi_sm = round(kaaa_yp/kaaa_yr*100,1) if kaaa_yr>0 else 0
kpi_spt = round(kaaa_yr/ytd_r*100,1) if ytd_r>0 else 0
kpi_sc = kaaa_sc
# ASP
ytd_q = float(r26["_qty"].sum()); lytd_q = float(r25["_qty"].sum())
asp_ytd = round(ytd_r/ytd_q,4) if ytd_q>0 else 0
asp_lytd = round(lytd_r/lytd_q,4) if lytd_q>0 else 0
asp_yoy = round((asp_ytd-asp_lytd)/asp_lytd*100,1) if asp_lytd>0 else 0
latest_d = rex[(rex["_d"].dt.year==_latest_y)&(rex["_d"].dt.month==_latest_m)]
prev_d = rex[(rex["_d"].dt.year==_prev_y)&(rex["_d"].dt.month==_prev_m)]
may_r = float(latest_d["_rev"].sum()); may_q = float(latest_d["_qty"].sum())
apr_r = float(prev_d["_rev"].sum()); apr_q = float(prev_d["_qty"].sum())
asp_may = round(may_r/may_q,4) if may_q>0 else 0
asp_apr = round(apr_r/apr_q,4) if apr_q>0 else 0
asp_mom = round((asp_may-asp_apr)/asp_apr*100,1) if asp_apr>0 else 0
print(f"  ASP:{asp_ytd}元 同比:{asp_yoy}% 环比:{asp_mom}%")
print(f"  YTD收入:{kpi_r}万 利润:{kpi_p}万 毛利率:{kpi_mg}% KA+AA:{kpi_sc}个")

# ========== 3. 月度趋势 ==========
_timed("KPI/KA散点准备", _t_seg0); _t_seg0 = _time_mod.time()
print("[3/5] 月度趋势...")
t_mo = rex.groupby("_ym").agg(r=("_rev","sum"),p=("_profit","sum")).reset_index()
t_mo = t_mo[(t_mo["_ym"]>=_t_mo_start)&(t_mo["_ym"]<=f"{_latest_y}-12")].sort_values("_ym")
ml = ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"]

# 热点循环向量化：12 次逐月 DataFrame 布尔扫描 → 预聚合 dict + O(1) 定位（纯等价）
_t_mo_map = {str(row["_ym"]): (float(row["r"]), float(row["p"])) for _, row in t_mo.iterrows()}
def yd(yr):
    rv,ct,pf,mg=[None]*12,[None]*12,[None]*12,[None]*12
    for m in range(1,13):
        rec = _t_mo_map.get(f"{yr}-{m:02d}")
        if rec is not None:
            r,p = rec
            rv[m-1]=round(r/1e4,0);ct[m-1]=round((r-p)/1e4,0);pf[m-1]=round(p/1e4,0);mg[m-1]=round(p/r*100,1) if r>0 else 0
    return rv,ct,pf,mg
# 年份动态化：3 年窗口 [_y0,_y1,_y2]，JSON key 用 2 位年份缩写，形如 r24/c24/p24/m24（24=2024）
trend = {"mo": ml}
for _yr in _years:
    _kk = _yr % 100
    _rv,_ct,_pf,_mg = yd(_yr)
    trend[f"r{_kk}"]=_rv; trend[f"c{_kk}"]=_ct; trend[f"p{_kk}"]=_pf; trend[f"m{_kk}"]=_mg

# 分层趋势
trend_tiers = {}
for tier in ["KA","AA","KM","MM"]:
    ts = rex[rex["_tier"].str.contains(tier,na=False)]
    tm = ts.groupby("_ym").agg(r=("_rev","sum"),p=("_profit","sum")).reset_index()
    tm = tm[(tm["_ym"]>=_t_mo_start)&(tm["_ym"]<=f"{_latest_y}-12")].sort_values("_ym")
    _tm_map = {str(row["_ym"]): (float(row["r"]), float(row["p"])) for _, row in tm.iterrows()}
    def tyd(yr):
        trv,tct,tpf,tmg=[None]*12,[None]*12,[None]*12,[None]*12
        for m in range(1,13):
            rec = _tm_map.get(f"{yr}-{m:02d}")
            if rec is not None:
                r,p = rec
                trv[m-1]=round(r/1e4,0);tct[m-1]=round((r-p)/1e4,0);tpf[m-1]=round(p/1e4,0);tmg[m-1]=round(p/r*100,1) if r>0 else 0
        return trv,tct,tpf,tmg
    _tier_trend = {}
    for _yr in _years:
        _kk = _yr % 100
        _trv,_tct,_tpf,_tmg = tyd(_yr)
        _tier_trend[f"r{_kk}"]=_trv; _tier_trend[f"c{_kk}"]=_tct; _tier_trend[f"p{_kk}"]=_tpf; _tier_trend[f"m{_kk}"]=_tmg
    trend_tiers[tier] = _tier_trend
print(f"    分层趋势完成")

# KA+AA月度折线
kaaa_mo = rex[rex["_tier"].str.contains("KA|AA",na=False)].groupby("_ym").agg(r=("_rev","sum")).reset_index().sort_values("_ym")
kaa_rev = {}
for _,r in kaaa_mo.iterrows(): kaa_rev[str(r["_ym"])]=round(float(r["r"])/1e4,2)

# ========== 4. 饼图+散点 ==========
_timed("月度趋势/分层趋势", _t_seg0); _t_seg0 = _time_mod.time()
print("[4/5] 饼图+散点...")
# 饼图：K类客户（使用Excel raw数据中的有交易客户数）
# 统计有交易的客户数（按层级去重）
tier_cust_counts = {}
for tier in ["KA","AA","KM"]:
    if tier == "KA":
        mask = r26["_tier"].str.contains("KA", na=False) & ~r26["_tier"].str.contains("KM", na=False)
    else:
        mask = r26["_tier"].str.contains(tier, na=False)
    # 排除nan/空客户名
    valid = r26[mask]
    valid = valid[~valid["_cust"].isin(["nan","None","","未知客户"])]
    tier_cust_counts[tier] = valid["_cust"].nunique()
pie = [{"name":t,"value":int(tier_cust_counts.get(t,0))} for t in ["KA","AA","KM"]]
# K类收入 = KA+AA+KM 交易收入合计
kr = float(kaaa_rex["_rev"].sum()) + float(r26[r26["_tier"].str.contains("KM",na=False)]["_rev"].sum())
kpct = round(kr/ytd_r*100,1) if ytd_r>0 else 0

# KA散点
ka_rex = r26[r26["_tier"].str.contains("KA",na=False)]
ka_cust_ytd = ka_rex.groupby("_cust").agg(ytd_rev=("_rev","sum"),ytd_profit=("_profit","sum")).reset_index()
ka_cust_2025 = r25[r25["_tier"].str.contains("KA",na=False)].groupby("_cust").agg(ytd_rev_2025=("_rev","sum")).reset_index()
ka_s = ka_cust_ytd.merge(ka_cust_2025, on="_cust", how="left")
ka_s["g"]=((ka_s["ytd_rev"]-ka_s["ytd_rev_2025"].fillna(0))/ka_s["ytd_rev_2025"].replace(0,np.nan)*100).fillna(0)
ka_s["mg"]=(ka_s["ytd_profit"]/ka_s["ytd_rev"].replace(0,np.nan)*100).fillna(0)
# 关联Gold层属性
ki={}
for _,r in df[df["客户层级"]=="KA"].iterrows(): ki[str(r["客户名称"]).strip()]={"n":str(r.get("客户名称","")),"d":str(r.get("双轴分类",""))}
scat=[]
for _,r in ka_s.iterrows():
    name=r["_cust"]; info=ki.get(name,{})
    if r["ytd_rev"]>0 and abs(r["g"])<500 and str(name).strip() not in ("","nan","None"):
        scat.append({"n":info.get("n",name),"g":round(j(r["g"]),1),"mg":round(j(r["mg"]),1),"rev":round(float(r["ytd_rev"])/1e4,2),"d":info.get("d","")})

# ========== 5. 客户列表+B面 ==========
_timed("饼图+散点", _t_seg0); _t_seg0 = _time_mod.time()
print("[5/5] 客户列表+B面...")

# A面客户列表（KA+AA）
kaaa_gold = df[df["客户层级"].isin(["KA","AA"])]
# Raw Excel 按客户聚合YTD
cust_ytd_all = r26.groupby("_cust").agg(ytd_rev=("_rev","sum"),ytd_profit=("_profit","sum"),ytd_qty=("_qty","sum")).reset_index()
cust_2025_all = r25.groupby("_cust").agg(ytd_rev_2025=("_rev","sum")).reset_index()
# 按客户计算最新月vs上月环比
may26 = rex[(rex["_d"].dt.month==_latest_m)&(rex["_d"].dt.year==_latest_y)]
apr26 = rex[(rex["_d"].dt.month==_prev_m)&(rex["_d"].dt.year==_prev_y)]
cust_may = may26.groupby("_cust").agg(may_rev=("_rev","sum")).reset_index()
cust_apr = apr26.groupby("_cust").agg(apr_rev=("_rev","sum")).reset_index()

csa = []
for _, row in kaaa_gold.iterrows():
    name = str(row.get("客户名称","")).strip()
    cm = cust_ytd_all[cust_ytd_all["_cust"]==name]
    if len(cm)>0:
        ytd_rv = float(cm["ytd_rev"].sum()); ytd_pf = float(cm["ytd_profit"].sum())
        ytd_q = float(cm["ytd_qty"].sum())
    else: ytd_rv=0; ytd_pf=0; ytd_q=0
    c25 = cust_2025_all[cust_2025_all["_cust"]==name]
    rev_2025 = float(c25["ytd_rev_2025"].sum()) if len(c25)>0 else 0
    real_yoy = round(j(row.get("YoY同比增速",0))*100,1)  # 与B_CUSTS统一数据源
    # 真实环比：5月vs4月（从原始数据计算）
    cm_may = cust_may[cust_may["_cust"]==name]; cm_apr = cust_apr[cust_apr["_cust"]==name]
    r_may = float(cm_may["may_rev"].sum()) if len(cm_may)>0 else 0
    r_apr = float(cm_apr["apr_rev"].sum()) if len(cm_apr)>0 else 0
    real_mom = round((r_may-r_apr)/r_apr*100,1) if r_apr>0 else 0
    sr=str(row.get("策略详细建议","")); ss=sr.split("\n")[0][:30] if sr else ""; ss=ss.split("⭐")[0].strip()[:25] if "⭐" in ss else ss
    asp_val = round(ytd_rv/ytd_q,4) if ytd_q>0 else 0
    csa.append({"n":name,"r":round(ytd_rv/1e4,2),"p":round(ytd_pf/1e4,2),
        "g":real_mom,"y":real_yoy,"s":ss,"o":str(row.get("业务负责人","")),
        "t":str(row.get("客户层级","")),"d":str(row.get("双轴分类","")),"lc":str(row.get("客户生命周期","")),
        "rk":str(row.get("风险评级","")),"added":0,"removed":0,"id":str(row.get("客户编号","")),
        "npct":round(j(row.get("新品采购占比",0))*100,1),"asp":asp_val})
csa.sort(key=lambda x:-x["r"])

# KA KPI
ka_may = rex[(rex["_d"].dt.month==_latest_m)&(rex["_d"].dt.year==_latest_y)&(rex["_tier"].str.contains("KA",na=False))]
ka_apr = rex[(rex["_d"].dt.month==_prev_m)&(rex["_d"].dt.year==_prev_y)&(rex["_tier"].str.contains("KA",na=False))]
ka_rev_ytd = float(ka_rex["_rev"].sum()); ka_profit_ytd = float(ka_rex["_profit"].sum())
ka_qty_ytd = float(ka_rex["_qty"].sum())
ka_rev_may = float(ka_may["_rev"].sum()); ka_profit_may = float(ka_may["_profit"].sum())
ka_rev_apr = float(ka_apr["_rev"].sum())
ka_kpi = {
    "rev":round(ka_rev_ytd/1e4,0),"profit":round(ka_profit_ytd/1e4,0),
    "qty":round(ka_qty_ytd/1e4,0),"margin":round(ka_profit_ytd/ka_rev_ytd*100,1) if ka_rev_ytd>0 else 0,
    "rev_mom":round((ka_rev_may-ka_rev_apr)/ka_rev_apr*100,1) if ka_rev_apr>0 else 0,
    "profit_mom":round((ka_profit_may-ka_profit_ytd/_latest_m)/(ka_profit_ytd/_latest_m)*100,1) if ka_profit_ytd>0 else 0,
    "asp":round(ka_rev_ytd/ka_qty_ytd,4) if ka_qty_ytd>0 else 0,
    "asp_mom":round((ka_rev_may/float(ka_may["_qty"].sum())-ka_rev_apr/float(ka_apr["_qty"].sum()))/(ka_rev_apr/float(ka_apr["_qty"].sum()))*100,1) if ka_rev_apr>0 and float(ka_apr["_qty"].sum())>0 else 0,
    "added":0,"removed":0,
}

# AA KPI
aa_rex = r26[r26["_tier"].str.contains("AA",na=False)]
aa_may = rex[(rex["_d"].dt.month==_latest_m)&(rex["_d"].dt.year==_latest_y)&(rex["_tier"].str.contains("AA",na=False))]
aa_apr = rex[(rex["_d"].dt.month==_prev_m)&(rex["_d"].dt.year==_prev_y)&(rex["_tier"].str.contains("AA",na=False))]
aa_rev_ytd = float(aa_rex["_rev"].sum()); aa_profit_ytd = float(aa_rex["_profit"].sum())
aa_qty_ytd = float(aa_rex["_qty"].sum())
aa_rev_may = float(aa_may["_rev"].sum()); aa_profit_may = float(aa_may["_profit"].sum())
aa_rev_apr = float(aa_apr["_rev"].sum())
aa_kpi = {
    "rev":round(aa_rev_ytd/1e4,0),"profit":round(aa_profit_ytd/1e4,0),
    "qty":round(aa_qty_ytd/1e4,0),"margin":round(aa_profit_ytd/aa_rev_ytd*100,1) if aa_rev_ytd>0 else 0,
    "rev_mom":round((aa_rev_may-aa_rev_apr)/aa_rev_apr*100,1) if aa_rev_apr>0 else 0,
    "asp":round(aa_rev_ytd/aa_qty_ytd,4) if aa_qty_ytd>0 else 0,
    "asp_mom":round((aa_rev_may/float(aa_may["_qty"].sum())-aa_rev_apr/float(aa_apr["_qty"].sum()))/(aa_rev_apr/float(aa_apr["_qty"].sum()))*100,1) if aa_rev_apr>0 and float(aa_apr["_qty"].sum())>0 else 0,
    "added":0,"removed":0,
}

# B面客户数据（Gold属性 + Raw Excel财务）
cid_to_name = dict(zip(df["客户编号"].astype(str), df["客户名称"].astype(str).str.strip()))
# Raw Excel 按客户+YTD+月度数据
rex["_ym_full"] = rex["_d"].dt.strftime("%Y-%m")
# B面趋势：按客户+月聚合
cust_mo = rex.groupby(["_cust","_ym_full"]).agg(r=("_rev","sum"),p=("_profit","sum"),q=("_qty","sum")).reset_index()
all_custs = sorted(cust_mo["_cust"].unique())
ctr = {}
for cid in all_custs:
    cm = cust_mo[cust_mo["_cust"]==cid].sort_values("_ym_full").tail(25)
    pts = [{"m":str(r["_ym_full"]),"r":round(float(r["r"])/1e4,2),"p":round(float(r["p"])/1e4,2),"q":round(float(r["q"])/1e4,2)} for _,r in cm.iterrows()]
    if pts: ctr[cid]=pts
print(f"    趋势:{len(ctr)}客户")

# B面财务数据
cid_fin = {}
for cid in all_custs:
    cm = cust_mo[cust_mo["_cust"]==cid]
    def cmg(g):
        sr=float(g["r"].sum()); sp=float(g["p"].sum())
        return round(sp/sr*100,1) if sr>0 else 0
    def sc(g,c): return round(float(g[c].sum())/1e4,1)
    ytd_g=cm[(cm["_ym_full"]>=f"{_latest_y}-01")&(cm["_ym_full"]<=latest)]
    prior_g=cm[(cm["_ym_full"]>=f"{_latest_y-1}-01")&(cm["_ym_full"]<=str(_latest_period-12))]
    near12=cm[cm["_ym_full"]>=start_12m]
    prev_g=cm[cm["_ym_full"]==str(_prev_period)]; latest_g=cm[cm["_ym_full"]==latest]
    cid_fin[cid]={
        "ytd_rev":sc(ytd_g,"r"),"ytd_profit":sc(ytd_g,"p"),"ytd_mg":cmg(ytd_g),
        "prior_rev":sc(prior_g,"r"),"prior_profit":sc(prior_g,"p"),"prior_mg":cmg(prior_g),
        "prev_rev":sc(prev_g,"r"),"prev_profit":sc(prev_g,"p"),"prev_mg":cmg(prev_g),
        "latest_rev":sc(latest_g,"r"),"latest_profit":sc(latest_g,"p"),"latest_mg":cmg(latest_g),
        "near12_rev":sc(near12,"r"),"near12_profit":sc(near12,"p"),"near12_mg":cmg(near12),"ytd_cost":round(sc(ytd_g,"r")-sc(ytd_g,"p"),1),
    }

# B面品类数据
cutoff_12m = start_12m
cxp_12m_r = rex[(rex["_ym_full"]>=cutoff_12m)&(rex["_ym_full"]<=latest)]
cid_12m_data = {}
for cid, grp in cxp_12m_r.groupby("_cust"):
    uniq_prods = grp["_prod"].nunique()
    cat_rev = {}
    cat_agg = grp.groupby("_cat")["_rev"].sum().reset_index()
    for _,cr in cat_agg.iterrows(): cat_rev[str(cr["_cat"])]=round(float(cr["_rev"])/1e4,1)
    cid_12m_data[cid]={"prods":uniq_prods,"cats":len(cat_rev),"cat_rev":cat_rev}

# B面Top5产品
prank = {}
for cid, grp in cxp_12m_r.groupby("_cust"):
    prod_rev = grp.groupby("_prod")["_rev"].sum().reset_index()
    top = prod_rev.sort_values("_rev",ascending=False).head(5)
    prank[cid]=[str(p) for p in top["_prod"].tolist()]

# 产品型号变迁（全历史扫描：真正的新增=全历史从未出现，≥6000阈值）
# 预计算每客户的全历史品种集合（起始月 到 前12月结束）
# 热点循环向量化：客户×月 逐条过滤+逐月聚合 → 一次 groupby（先按 客户×月×品种 过滤
# q>=6000，再跨月汇总 rev/profit），与原有逐月逻辑纯等价。
print("    预计算客户全历史品种...")
customer_history_items = {}
customer_history_rev = {}
_kaaa_cust_set = set(kaaa_gold["客户名称"].astype(str).str.strip())
_hist_rex = rex[(rex["_ym_full"] <= prior12_end) & (rex["_cust"].isin(_kaaa_cust_set))]
_hist_month_agg = _hist_rex.groupby(["_cust", "_ym_full", "_item", "_cat_new"]).agg(
    r=("_rev", "sum"), p=("_profit", "sum"), q=("_qty", "sum")).reset_index()
_hist_month_agg = _hist_month_agg[_hist_month_agg["q"] >= 6000]
_hist_agg = _hist_month_agg.groupby(["_cust", "_item", "_cat_new"]).agg(
    r=("r", "sum"), p=("p", "sum")).reset_index()
for name in _kaaa_cust_set:
    customer_history_items[name] = set()
    customer_history_rev[name] = {}
for _, r in _hist_agg.iterrows():
    _nm = str(r["_cust"])
    _key = (str(r["_item"]), str(r["_cat_new"]))
    customer_history_items[_nm].add(_key)
    customer_history_rev[_nm][_key] = {"rev": float(r["r"]), "profit": float(r["p"])}

product_change_detail = []
# start_12m 已在数据加载阶段自动检测
# 热点循环向量化：客户×近12月 逐条过滤 → 一次 groupby 预聚合，逐客户只做 set 运算
_cur_rex = rex[(rex["_ym_full"] >= start_12m) & (rex["_ym_full"] <= latest) & (rex["_cust"].isin(_kaaa_cust_set))]
_cur_agg_all = _cur_rex.groupby(["_cust", "_item", "_cat_new"]).agg(
    r=("_rev", "sum"), p=("_profit", "sum"), q=("_qty", "sum")).reset_index()
_cur_agg_all = _cur_agg_all[_cur_agg_all["q"] >= 6000]
_cur_groups = {str(_nm): _grp for _nm, _grp in _cur_agg_all.groupby("_cust")}
for _, row in kaaa_gold.iterrows():
    name = str(row.get("客户名称", "")).strip(); tier = str(row.get("客户层级", ""))
    _cur_agg = _cur_groups.get(name)
    if _cur_agg is None:
        cur_items = set(); cur_lookup = {}
    else:
        cur_items = set(zip(_cur_agg["_item"].astype(str), _cur_agg["_cat_new"].astype(str)))
        cur_lookup = {(str(r["_item"]), str(r["_cat_new"])): r for _, r in _cur_agg.iterrows()}
    # 全历史品种
    all_hist = customer_history_items.get(name, set())
    # 流失 = 历史有但近12月无；新增 = 全历史从未出现
    lost_items = all_hist - cur_items
    gained_items = cur_items - all_hist
    if not lost_items and not gained_items: continue
    def item_label(item_name, cat_new_name):
        if cat_new_name and cat_new_name != "" and cat_new_name != "nan":
            return f"{cat_new_name} - {item_name}"
        return str(item_name)
    losses=[]; gains=[]
    hist_lookup = customer_history_rev.get(name, {})
    for item, cn in lost_items:
        hr = hist_lookup.get((item,cn), {"rev":0.0,"profit":0.0})
        losses.append({"name":item_label(item,cn),"rev":round(hr["rev"]/1e4,1),"profit":round(hr["profit"]/1e4,1)})
    for item, cn in gained_items:
        r = cur_lookup.get((item,cn),{})
        gains.append({"name":item_label(item,cn),"rev":round(float(r.get("r",0))/1e4,1),"profit":round(float(r.get("p",0))/1e4,1)})
    if losses or gains:
        product_change_detail.append({
            "cid":str(row.get("客户编号","")),"name":name,"tier":tier,"owner":str(row.get("业务负责人","")),
            "losses":sorted(losses,key=lambda x:(-x["rev"], x["name"])),"gains":sorted(gains,key=lambda x:(-x["rev"], x["name"])),
            "lost_count":len(lost_items),"gained_count":len(gained_items),
            "total_lost_rev":round(sum(l["rev"] for l in losses),1),"total_gained_rev":round(sum(g["rev"] for g in gains),1),
        })
print(f"    产品型号变迁:{len(product_change_detail)}客户")

# SA added/removed补丁（从product_change_detail取值）
cust_change_map = {}
for pc in product_change_detail:
    cust_change_map[pc["name"]] = {"added": pc["gained_count"], "removed": pc["lost_count"]}
for c in csa:
    ch = cust_change_map.get(c["n"], {})
    if ch: c["added"] = ch.get("added", 0); c["removed"] = ch.get("removed", 0)

# 客户热力图在D面数据生成后构建（见下文6n）

# B面 call 列表
all_sorted = df.sort_values("近12月收入",ascending=False)
# 新品标记（从cleaned_rows加载新品标记列）
cleaned_cols = ["客户编号","产品品种","新品标记","金额","数量","发货日期"]
raw_rows = pd.read_csv(os.path.join(SILVER,"silver_cleaned_rows.csv"), usecols=cleaned_cols)
raw_rows["cid"]=raw_rows["客户编号"].astype(str)
prod_first_all = raw_rows.groupby("产品品种")["发货日期"].min().to_dict()
# cutoff_new 已在数据加载阶段自动检测
raw_rows["_is_new_tag"]=raw_rows["新品标记"].astype(str).str.contains("是")
raw_rows["_in_2026"]=raw_rows["发货日期"].astype(str).str[:4]==str(_latest_y)
raw_rows["_first_date"]=raw_rows["产品品种"].map(prod_first_all).astype(str)
raw_rows["_is_true_new"]=raw_rows["_is_new_tag"]&raw_rows["_in_2026"]&(raw_rows["_first_date"]>=cutoff_new)
raw_new = raw_rows[raw_rows["_is_true_new"]]
new_detail={}
for cid, grp in raw_new.groupby("cid"):
    prods=grp.groupby("产品品种").agg(first_date=("发货日期","min"),total_rev=("金额","sum"),total_qty=("数量","sum")).reset_index()
    prods=prods[prods["total_qty"]>=6000].sort_values("total_rev",ascending=False)
    new_detail[cid]=[{"name":str(pr["产品品种"]),"first":str(pr["first_date"])[:10],"rev":round(float(pr["total_rev"])/1e4,1)} for _,pr in prods.iterrows()]
# A面整体新品渗透率（全量客户YTD，与ytd_r同源rex）
# 口径拍板（未决#13，2026-08-25）：纯 ERP"是否新品"标记口径；
# 去掉 M1 平台合并时代遗留的"近12月首发"过滤（实测滤掉 83% 标记新品收入，证据链见施工进度台账）
rex_true_new = r26[r26["_is_new"]]
new_pct = round(float(rex_true_new["_rev"].sum())/ytd_r*100,1) if ytd_r>0 else 0
# A面新品渗透率卡的实际注入值（JS npctVal 用）：与上行同口径的纯标记占比
new_flag_pct = new_pct

call=[]
for _,row in all_sorted.iterrows():
    cid=str(row.get("客户编号","")); name=str(row.get("客户名称","")).strip()
    fin=cid_fin.get(name,{})
    r_p=j(row.get("近12月收入",0)); p_p=j(row.get("近12月毛利",0))
    ld=j(row.get("距上次采购天数",0)); iv=j(row.get("常规平均采购间隔",60))
    np_=""; dev=""
    if iv>0:
        if ld==0: np_="本月已采购"; dev=""
        else:
            en=int(max(0,iv-ld))
            if en>0: np_="约"+str(en)+"天后"
            else: np_="已超期"+str(abs(int(ld-iv)))+"天"
            dev=""
    call.append({"id":cid,"n":name,
        "r":fin.get("ytd_rev",0),"p":fin.get("ytd_profit",0),
        "g":round(j(row.get("收入增长率",0))*100,1),"y":round(j(row.get("YoY同比增速",0))*100,1),
        "t":str(row.get("客户层级","")),"rk":str(row.get("风险评级","")),"lc":str(row.get("客户生命周期","")),
        "ac":str(row.get("活跃状态","")),"o":str(row.get("业务负责人","")),"ch":str(row.get("渠道类型","")),
        "mg":round(j(row.get("近12月毛利率",0)),1),"md":j(row.get("毛利率跌幅%",0)),
        "asp":round(j(row.get("ASP_加权",0)),2),"ad":round(j(row.get("ASP_跌幅%",0)),2),
        "lp":round(j(row.get("低价品种收入占比",0))*100,2),"hp":round(j(row.get("高价品种收入占比",0))*100,2),
        "pc":cid_12m_data.get(name,{}).get("prods",0),"ap":cid_12m_data.get(name,{}).get("prods",0),
        "cc":cid_12m_data.get(name,{}).get("cats",0),
        "ml":str(row.get("主导产品线","")),"mlp":round(j(row.get("主导产品线占比",0))*100,1),
        "mc":str(row.get("主导品类","")),"t3":round(j(row.get("品种集中度Top3",0))*100,1),
        "npct":round(j(row.get("新品采购占比",0))*100,1),"nf":str(row.get("是否采购新品","")),
        "st":str(row.get("策略详细建议","")),"sr":str(row.get("策略触发原因","")),"al":str(row.get("异常告警汇总","")),
        "cs":j(row.get("综合价值分",0)),"tl":str(row.get("综合价值层级","")),
        "v":j(row.get("价值贡献分",0)),"gs":j(row.get("增长动能分",0)),"sb":j(row.get("稳定关系分",0)),
        "pt":j(row.get("战略潜力分",0)),"ef":j(row.get("效率运营分",0)),
        "ld":ld,"iv":int(iv),"zp":j(row.get("零采购月占比",0)),"od":j(row.get("订单数",0)),
        "np":np_,"dv":dev,"cg":j(row.get("连续增长月数",0)),"cd":j(row.get("连续下滑月数",0)),
        "t5":prank.get(name,[]),"du":str(row.get("双轴分类","")),
        "cat_rev":cid_12m_data.get(name,{}).get("cat_rev",{}),
        "ytd_rev":fin.get("ytd_rev",0),"ytd_profit":fin.get("ytd_profit",0),"ytd_mg":fin.get("ytd_mg",0),
        "prior_rev":fin.get("prior_rev",0),"prior_profit":fin.get("prior_profit",0),"prior_mg":fin.get("prior_mg",0),
        "prev_rev":fin.get("prev_rev",0),"prev_profit":fin.get("prev_profit",0),"prev_mg":fin.get("prev_mg",0),
        "latest_rev":fin.get("latest_rev",0),"latest_profit":fin.get("latest_profit",0),"latest_mg":fin.get("latest_mg",0),
        "near12_rev":fin.get("near12_rev",0),"near12_profit":fin.get("near12_profit",0),"near12_mg":fin.get("near12_mg",0),
        "ytd_cost":fin.get("ytd_cost",0),"near12_cost":round(fin.get("near12_rev",0)-fin.get("near12_profit",0),1),
        "new_detail":(nd:=new_detail.get(cid,[])),"new_amt":round(j(row.get("新品采购额",0))/1e4,0),
        "new_count":len(nd),"new_latest_rev":round(sum(d["rev"] for d in nd if d["first"]>=latest_month_start),1),"new_ytd_rev":round(sum(d["rev"] for d in nd if d["first"]>=ytd_start),1),
    })

# ========== 6. D面 销售能力 ==========
_timed("A面客户列表+B面(含产品变迁)", _t_seg0); _t_seg0 = _time_mod.time()
print("[6/6] D面 销售能力...")

# 6a. 定位销售员列（使用加载阶段读到的 sales_col_raw）
sales_col = sales_col_raw
rex["_sales"] = rex[sales_col].astype(str).str.strip() if sales_col else pd.Series("未知", index=rex.index)
print(f"  销售员列: {repr(sales_col)}  唯一值: {rex['_sales'].nunique()}")

# 6b. 过滤有效销售员 + 仅保留当年在职（YTD有交易）
rex_valid_sales = rex[~(rex["_sales"].isin(["", "nan", "None", "未知"]))]
sales_2026_set = set(rex_valid_sales[(rex_valid_sales["_d"] >= ytd_start) & (rex_valid_sales["_d"] <= ytd_end)]["_sales"].unique())
print(f"  {_latest_y}在职销售员: {len(sales_2026_set)}人")

# 6c. YTD聚合（仅在职销售员，直接从rex过滤确保有_sales列）
r26_sales = rex[(rex["_d"] >= ytd_start) & (rex["_d"] <= ytd_end) & (rex["_sales"].isin(sales_2026_set))]
sales_ytd = r26_sales.groupby("_sales").agg(
    ytd_rev=("_rev", "sum"), ytd_profit=("_profit", "sum"),
    ytd_qty=("_qty", "sum"), ytd_orders=("客户订单号", "nunique"),
    cust_count=("_cust", "nunique"), prod_count=("_prod", "nunique")
).reset_index()

# 同比2025
r25_sales = rex[(rex["_d"] >= pytd_start) & (rex["_d"] <= pytd_end) & (rex["_sales"].isin(sales_2026_set))]
sales_2025 = r25_sales.groupby("_sales").agg(ytd_rev_2025=("_rev", "sum")).reset_index()
sales_ytd = sales_ytd.merge(sales_2025, on="_sales", how="left")
sales_ytd["ytd_rev_2025"] = sales_ytd["ytd_rev_2025"].fillna(0)
sales_ytd["rev_yoy"] = ((sales_ytd["ytd_rev"] - sales_ytd["ytd_rev_2025"]) / sales_ytd["ytd_rev_2025"].replace(0, np.nan) * 100).fillna(0)

# 环比：最新月 vs 上月
may26 = rex[(rex["_d"]>=latest_month_start)&(rex["_d"]<=latest_month_end)&(rex["_sales"].isin(sales_2026_set))]
apr26 = rex[(rex["_d"]>=prev_month_start)&(rex["_d"]<=prev_month_end)&(rex["_sales"].isin(sales_2026_set))]
may_agg = may26.groupby("_sales").agg(rev_may=("_rev","sum")).reset_index()
apr_agg = apr26.groupby("_sales").agg(rev_apr=("_rev","sum")).reset_index()
mom_df = may_agg.merge(apr_agg, on="_sales", how="left")
mom_df["rev_mom"] = ((mom_df["rev_may"] - mom_df["rev_apr"].fillna(0)) / mom_df["rev_apr"].replace(0, np.nan) * 100).fillna(0)
sales_ytd = sales_ytd.merge(mom_df[["_sales","rev_mom"]], on="_sales", how="left")
sales_ytd["rev_mom"] = sales_ytd["rev_mom"].fillna(0)

# 6d. 加载Gold销售画像
portrait_df = pd.read_csv(os.path.join(GOLD, "销售画像.csv"))
portrait_map = {}
for _, r in portrait_df.iterrows():
    name = str(r["业务负责人"]).strip()
    portrait_map[name] = {
        "cust_count": int(j(r.get("客户总数", 0))),
        "total_rev": round(float(j(r.get("总营收", 0))) / 1e4, 1),
        "ka_aa_count": int(j(r.get("KA_AA客户数", 0))),
        "volume_level": str(r.get("量级", "")),
        "forces": {
            "contribution": round(float(j(r.get("绝对贡献力", 50))), 1),
            "retention": round(float(j(r.get("客户维系力", 50))), 1),
            "category_expand": round(float(j(r.get("品类拓展力", 50))), 1),
            "pricing": round(float(j(r.get("定价博弈力", 50))), 1),
            "new_dev": round(float(j(r.get("新客开拓力", 50))), 1),
            "activation": round(float(j(r.get("客户激活力", 50))), 1),
            "upgrade": round(float(j(r.get("客户升级力", 50))), 1),
            "product_optimize": round(float(j(r.get("产品结构优化力", 50))), 1),
            "risk_resist": round(float(j(r.get("组合抗风险力", 50))), 1),
        },
        "score": round(float(j(r.get("综合能力分", 0))), 1),
        "level": str(r.get("能力等级", "")),
        "subgroup": str(r.get("亚组", "")),
    }

# 6e. 真实品类维度（从Raw Excel聚合，_cat已使用产品品类（新））
# 仅在职销售员 + YTD
sales_cat = rex[(rex["_d"] >= ytd_start) & (rex["_d"] <= ytd_end) & (rex["_sales"].isin(sales_2026_set))]
sc_agg = sales_cat.groupby(["_sales", "_cat"]).agg(
    cat_rev=("_rev", "sum"), cat_profit=("_profit", "sum"), cat_qty=("_qty", "sum")
).reset_index()
sc_agg["cat_mg"] = (sc_agg["cat_profit"] / sc_agg["cat_rev"].replace(0, np.nan) * 100).fillna(0)
# 按收入排序取Top8品类每人
sc_agg = sc_agg.sort_values(["_sales", "cat_rev"], ascending=[True, False])
cat_by_sales = {}
for name, grp in sc_agg.groupby("_sales"):
    top = grp.head(8)
    cat_by_sales[name] = []
    for _, r in top.iterrows():
        if r["cat_rev"] > 0:
            cat_by_sales[name].append({
                "cat": str(r["_cat"]),
                "rev": round(float(r["cat_rev"]) / 1e4, 2),
                "profit": round(float(r["cat_profit"]) / 1e4, 2),
                "mg": round(float(r["cat_mg"]), 1),
                "qty": round(float(r["cat_qty"]) / 1e4, 2),
            })

# 擅长产品线（从"产品线"列聚合，每人Top2）
# 批次④a 集成修复：silver 的"产品线"已归一为"产品一级分类"，而"型号_产品线（新）"是另一维度（E面）；
# 原先 `"产品线" in str(c)` 子串匹配在 silver 下会误命中"型号_产品线（新）"。改为精确名优先（产品一级分类/产品线），
# 保持 --from-excel（"产品线"列）与 silver（"产品一级分类"列）语义一致。
prod_line_col = None
for _cand in ["产品一级分类", "产品线"]:
    for _c in rex.columns:
        if _cand == str(_c):
            prod_line_col = _c
            break
    if prod_line_col:
        break
if prod_line_col is None:
    prod_line_col = next((c for c in rex.columns if "产品线" in str(c)), None)
if prod_line_col:
    rex["_prod_line"] = rex[prod_line_col].astype(str).str.strip()
    pl_agg = rex[(rex["_d"]>=ytd_start)&(rex["_d"]<=ytd_end)&(rex["_sales"].isin(sales_2026_set))].groupby(["_sales","_prod_line"])["_rev"].sum().reset_index()
    pl_agg = pl_agg.sort_values(["_sales","_rev"], ascending=[True,False])
    prod_line_by_sales = {}
    for name, grp in pl_agg.groupby("_sales"):
        top = grp.head(2)
        prod_line_by_sales[name] = [str(r["_prod_line"]) for _, r in top.iterrows() if r["_rev"] > 0]
else:
    prod_line_by_sales = {}

# 团队品类热力图数据（所有销售员 × 品类，按收入Top品类）
team_cats = sc_agg.groupby("_cat")["cat_rev"].sum().sort_values(ascending=False).head(15)
team_cat_names = list(team_cats.index)
print(f"  真实品类: {len(cat_by_sales)}人 {len(team_cat_names)}个品类")

# 6f. 加载销售人员周期表现（月度趋势）
sales_trend_df = pd.read_csv(os.path.join(GOLD, "销售人员周期表现.csv"))
sales_trend_map = {}
for name, grp in sales_trend_df.groupby("业务负责人"):
    name = str(name).strip()
    grp_sorted = grp.sort_values("月份")  # 全量月份（2024-01 ~ 2026-05）
    pts = []
    for _, r in grp_sorted.iterrows():
        pts.append({
            "m": str(r["月份"]),
            "r": round(float(j(r.get("月收入", 0))) / 1e4, 2),
            "p": round(float(j(r.get("月毛利", 0))) / 1e4, 2),
            "q": round(float(j(r.get("月数量", 0))) / 1e4, 2),
        })
    if pts:
        sales_trend_map[name] = pts
print(f"  趋势数据: {len(sales_trend_map)}人")

# 6g. 交叉销售机会汇总
cross_df = pd.read_csv(os.path.join(GOLD, "交叉销售建议.csv"))
cust_to_sales = rex_valid_sales.groupby("_cust")["_sales"].apply(lambda x: list(x.unique())).to_dict()
cross_by_sales = {}
for _, r in cross_df.iterrows():
    cid = str(r.get("客户编号", ""))
    sales_list = cust_to_sales.get(cid, [])
    for sname in sales_list:
        if sname not in cross_by_sales:
            cross_by_sales[sname] = []
        cross_by_sales[sname].append({
            "cust_id": cid,
            "rec_products": str(r.get("推荐品种", "")),
            "reason": str(r.get("推荐理由", ""))[:80],
        })

# 6h. 客户预测汇总（修复：预测值原为元，除以1e4转为万）
forecast_df = pd.read_csv(os.path.join(GOLD, "客户预测.csv"))
next_month = str(_latest_period + 1)
fc_next = forecast_df[forecast_df["预测月份"] == next_month]
fc_by_sales = {}
for _, r in fc_next.iterrows():
    cid = str(r.get("客户编号", ""))
    sales_list = cust_to_sales.get(cid, [])
    for sname in sales_list:
        if sname not in fc_by_sales:
            fc_by_sales[sname] = {"up": 0, "down": 0, "flat": 0, "total_rev": 0}
        direction = str(r.get("预测方向", ""))
        fc_by_sales[sname]["total_rev"] += float(j(r.get("预测收入", 0))) / 1e4  # 元→万
        if "上升" in direction:
            fc_by_sales[sname]["up"] += 1
        elif "下降" in direction:
            fc_by_sales[sname]["down"] += 1
        else:
            fc_by_sales[sname]["flat"] += 1

# 6i. 组装D面销售员列表
d_sales_list = []
for _, row in sales_ytd.iterrows():
    name = row["_sales"]
    pinfo = portrait_map.get(name, {})
    forces = pinfo.get("forces", {})
    real_cats = cat_by_sales.get(name, [])

    d_sales_list.append({
        "name": name,
        "cust_count": int(row["cust_count"]),
        "ka_aa_count": pinfo.get("ka_aa_count", 0),
        "ytd_rev": round(float(row["ytd_rev"]) / 1e4, 2),
        "ytd_profit": round(float(row["ytd_profit"]) / 1e4, 2),
        "ytd_mg": round(float(row["ytd_profit"]) / float(row["ytd_rev"]) * 100, 1) if float(row["ytd_rev"]) > 0 else 0,
        "ytd_qty": round(float(row["ytd_qty"]) / 1e4, 2),
        "ytd_orders": int(row["ytd_orders"]),
        "prod_count": int(row["prod_count"]),
        "rev_yoy": round(float(row["rev_yoy"]), 1),
        "rev_mom": round(float(row.get("rev_mom", 0)), 1),
        "score": pinfo.get("score", 0),
        "level": pinfo.get("level", ""),
        "subgroup": pinfo.get("subgroup", ""),
        "volume_level": pinfo.get("volume_level", ""),
        "forces": forces,
        "categories": real_cats,
        "top_category": real_cats[0]["cat"] if real_cats else "",
        "top_category2": real_cats[1]["cat"] if len(real_cats)>1 else "",
        "top_prod_lines": prod_line_by_sales.get(name, []),
        "cross_sell_count": len(cross_by_sales.get(name, [])),
        "cross_sell_items": cross_by_sales.get(name, [])[:10],
        "forecast": fc_by_sales.get(name, {"up": 0, "down": 0, "flat": 0, "total_rev": 0}),
    })
d_sales_list.sort(key=lambda x: -x["ytd_rev"])
print(f"  D面销售员: {len(d_sales_list)}人")

# 6j. D面KPI
d_total_rev = sum(s["ytd_rev"] for s in d_sales_list)
d_total_profit = sum(s["ytd_profit"] for s in d_sales_list)
d_avg_rev = round(d_total_rev / len(d_sales_list), 1) if d_sales_list else 0
d_a_level_count = sum(1 for s in d_sales_list if s["level"] == "A级")
d_avg_score = round(sum(s["score"] for s in d_sales_list) / len(d_sales_list), 1) if d_sales_list else 0
d_ka_aa_total = sum(s["ka_aa_count"] for s in d_sales_list)
d_kpi = {
    "team_rev": round(d_total_rev, 0),
    "team_profit": round(d_total_profit, 0),
    "team_mg": round(d_total_profit / d_total_rev * 100, 1) if d_total_rev > 0 else 0,
    "avg_rev": round(d_avg_rev, 0),
    "a_ratio": round(d_a_level_count / len(d_sales_list) * 100, 1) if d_sales_list else 0,
    "avg_score": d_avg_score,
    "headcount": len(d_sales_list),
    "ka_aa_total": d_ka_aa_total,
}
print(f"  D面KPI: 团队营收={d_kpi['team_rev']}万 人均={d_kpi['avg_rev']}万 A级占比={d_kpi['a_ratio']}%")

# 6k. 团队品类热力图数据（销售员×品类矩阵）
d_heatmap = {
    "sales_names": [s["name"] for s in d_sales_list],
    "cat_names": team_cat_names,
    "matrix": [],  # [[sales0_cat0_rev, sales0_cat1_rev, ...], ...]
}
for s in d_sales_list:
    scats = {c["cat"]: c["rev"] for c in s["categories"]}
    row = [round(scats.get(cn, 0), 1) for cn in team_cat_names]
    d_heatmap["matrix"].append(row)

# 6l. 短板诊断数据（每个销售员最低2个力 + 证据）
# 计算团队9力均值
force_keys = ["contribution","retention","category_expand","pricing","new_dev","activation","upgrade","product_optimize","risk_resist"]
force_labels_cn = {"contribution":"绝对贡献力","retention":"客户维系力","category_expand":"品类拓展力","pricing":"定价博弈力","new_dev":"新客开拓力","activation":"客户激活力","upgrade":"客户升级力","product_optimize":"产品结构优化力","risk_resist":"组合抗风险力"}
team_force_avg = {}
for fk in force_keys:
    vals = [s["forces"].get(fk, 50) for s in d_sales_list if s["forces"].get(fk, 0) > 0]
    team_force_avg[fk] = round(sum(vals)/len(vals), 1) if vals else 50

# 为客户维系力证据准备：每个客户同比数据（批次④a 向量化：逐客户过滤 → 一次 groupby）
cust_yoy_data = {}
# 使用rex而非r26（r26无_sales列）
r26_all = rex[(rex["_d"]>=ytd_start)&(rex["_d"]<=ytd_end)]
r25_all = rex[(rex["_d"]>=pytd_start)&(rex["_d"]<=pytd_end)]
_cy26 = r26_all.groupby("_cust")["_rev"].sum()
_cy25 = r25_all.groupby("_cust")["_rev"].sum()
for cid_name in rex_valid_sales["_cust"].unique():
    cy26 = float(_cy26.get(cid_name, 0.0))
    cy25 = float(_cy25.get(cid_name, 0.0))
    if cy25 > 0:
        cust_yoy_data[cid_name] = {"yoy": round((cy26-cy25)/cy25*100,1), "rev_26": round(cy26/1e4,2), "rev_25": round(cy25/1e4,2)}

# 为客户维系力证据准备：客户×存货名称 近6月vs前6月对比（批次④a 向量化：逐客户过滤 → 一次 groupby+merge）
cust_item_decline = {}
_cur6_ci = rex[(rex["_ym_full"]>=near6_start)&(rex["_ym_full"]<=latest)].groupby(["_cust","_item","_cat_new"]).agg(rev6=("_rev","sum")).reset_index()
_prev6_ci = rex[(rex["_ym_full"]>=prev6_start)&(rex["_ym_full"]<=prev6_end)].groupby(["_cust","_item","_cat_new"]).agg(prev_rev6=("_rev","sum")).reset_index()
_merged_ci = _cur6_ci.merge(_prev6_ci, on=["_cust","_item","_cat_new"], how="outer").fillna(0)
_merged_ci["decline"] = _merged_ci["prev_rev6"] - _merged_ci["rev6"]
_merged_ci = _merged_ci[_merged_ci["decline"]>0]
_valid_custs = set(rex_valid_sales["_cust"].unique())
for cid_name, _grp in _merged_ci.groupby("_cust"):
    if cid_name not in _valid_custs:
        continue
    _grp = _grp.sort_values("decline", ascending=False).head(3)
    cust_item_decline[cid_name] = []
    for _, dr in _grp.iterrows():
        label = f"{dr['_cat_new']} - {dr['_item']}" if dr["_cat_new"] and dr["_cat_new"]!="" else str(dr["_item"])
        cust_item_decline[cid_name].append({"item":label, "decline_rev":round(float(dr["decline"])/1e4,2)})

# 批次④a：预聚合 销售员→客户（保留首次出现顺序，等价于逐销售员 r26_all 过滤），供 6l/6l2 证据循环
_sales_cust_26 = {str(k): list(dict.fromkeys(v)) for k, v in r26_all.groupby("_sales")["_cust"].apply(list).items()}
_sales_cust_25 = {str(k): list(dict.fromkeys(v)) for k, v in r25_all.groupby("_sales")["_cust"].apply(list).items()}

for s in d_sales_list:
    forces = s["forces"]
    # 找最低2个力
    scored = [(fk, forces.get(fk, 50)) for fk in force_keys]
    scored.sort(key=lambda x: x[1])
    bottom2 = scored[:2]
    diagnosis = []
    for fk, score in bottom2:
        gap = round(team_force_avg.get(fk, 50) - score, 1)
        label_cn = force_labels_cn.get(fk, fk)
        evidence = []
        # 根据力的类型生成证据
        if fk == "retention":
            # 找该销售员名下同比降幅最大的客户
            sales_custs = _sales_cust_26.get(s["name"], [])
            cust_declines = [(cn, cust_yoy_data.get(cn,{}).get("yoy",0), cust_yoy_data.get(cn,{}).get("rev_26",0)) for cn in sales_custs if cn in cust_yoy_data and cust_yoy_data[cn]["yoy"]<0]
            cust_declines.sort(key=lambda x: x[1])
            for cn, yoy, rev26 in cust_declines[:3]:
                # 找该客户的具体下降产品
                ci_list = cust_item_decline.get(cn, [])
                item_str = "、".join([f"{ci['item']}(↓{ci['decline_rev']}万)" for ci in ci_list[:2]])
                evidence.append(f"客户{cn} · YTD同比{yoy}% · 收入{rev26}万" + (f" · {item_str}" if item_str else ""))
        elif fk == "activation":
            evidence.append(f"得分{score}分 · 团队均值{team_force_avg.get(fk,50)}分")
        elif fk == "new_dev":
            s26_custs = set(_sales_cust_26.get(s["name"], []))
            s25_custs = set(_sales_cust_25.get(s["name"], []))
            sales_new_custs_2026 = len(s26_custs - s25_custs)
            evidence.append(f"{_latest_y}年新客数: {sales_new_custs_2026}个")
        else:
            evidence.append(f"得分{score} · 团队均值{team_force_avg.get(fk,50)} · 差距{gap}")
        diagnosis.append({"force": label_cn, "force_key": fk, "score": score, "team_avg": team_force_avg.get(fk, 50), "gap": gap, "evidence": evidence})
    s["diagnosis"] = diagnosis
    s["shortboard"] = [d["force"] for d in diagnosis]

# 6l2. 能力画像（profile summary）：2强项+1弱项+具体证据
_force_evidence = {}  # 缓存每个销售员每项力的证据文本
for s in d_sales_list:
    nm = s["name"]
    _force_evidence[nm] = {}
    # 贡献力证据：营收排名 + 占比
    _force_evidence[nm]["contribution"] = f"YTD营收{round(s['ytd_rev'])}万，" + \
        f"团队排名第{sum(1 for x in d_sales_list if x['ytd_rev']>s['ytd_rev'])+1}/{len(d_sales_list)}，" + \
        f"贡献团队总营收{round(s['ytd_rev']/d_total_rev*100,1)}%"
    # 拓展力证据：产品线 + 品类数
    _force_evidence[nm]["category_expand"] = f"覆盖{s['prod_count']}条产品线" + \
        (f"（Top2：{'、'.join(s['top_prod_lines'][:2])}）" if s.get('top_prod_lines') else "")
    # 新客力证据
    s26custs = set(_sales_cust_26.get(nm, []))
    s25custs = set(_sales_cust_25.get(nm, []))
    new_cnt = len(s26custs - s25custs)
    _force_evidence[nm]["new_dev"] = f"{_latest_y}年新增{new_cnt}个客户"
    # 维系力证据：同比正增长客户TOP2
    if nm in cust_to_sales:
        scusts = set(cust_to_sales[nm]) if isinstance(cust_to_sales[nm], list) else {cust_to_sales[nm]}
    else:
        scusts = set(s26custs) | set(s25custs)
    pos_growth = []
    for cn in scusts:
        cd = cust_yoy_data.get(cn, {})
        if cd.get("yoy", 0) > 0:
            pos_growth.append((cn, cd["yoy"], cd.get("rev_26", 0)))
    pos_growth.sort(key=lambda x: -x[1])
    if pos_growth:
        top2 = pos_growth[:2]
        _force_evidence[nm]["retention"] = f"{len(pos_growth)}个老客户同比增长，" + \
            "、".join(f"{c}(+{g}%)" for c, g, _ in top2)
    else:
        _force_evidence[nm]["retention"] = f"老客户维系稳定"
    # 抗风险力证据
    top1_pct = s.get("top1_rev_pct", 0) or 0
    _force_evidence[nm]["risk_resist"] = f"TOP1客户仅占{top1_pct}%，" + \
        (f"{s['cust_count']}个客户高度分散" if top1_pct < 20 else f"{s['ka_aa_count']}个KA/AA客户结构优质")
    # 优化力证据
    _force_evidence[nm]["product_optimize"] = f"YTD毛利率{s.get('ytd_mg',0)}%"
    # 升级力证据
    _force_evidence[nm]["upgrade"] = f"升级力得分{s['forces'].get('upgrade',0)}分"
    # 定价力证据
    _force_evidence[nm]["pricing"] = f"定价力得分{s['forces'].get('pricing',0)}分"
    # 激活力证据
    _force_evidence[nm]["activation"] = f"激活力得分{s['forces'].get('activation',0)}分"

# 构建每人画像
_force_labels_cn_short = {"contribution":"贡献力","retention":"维系力","category_expand":"品类拓展力",
    "pricing":"定价力","new_dev":"新客开发力","activation":"客户激活力","upgrade":"产品升级力",
    "product_optimize":"产品优化力","risk_resist":"抗风险力"}
for s in d_sales_list:
    nm = s["name"]
    forces = s["forces"]
    # 找出高于和低于团队均值的力
    above = []; below = []
    for fk, label in _force_labels_cn_short.items():
        score = forces.get(fk, 0)
        team = team_force_avg.get(fk, 50)
        if score > team:
            above.append((fk, label, round(score, 1), round(team, 1), round(score - team, 1)))
        elif score < team:
            below.append((fk, label, round(score, 1), round(team, 1), round(team - score, 1)))
    above.sort(key=lambda x: -x[4])  # 差距从大到小
    below.sort(key=lambda x: -x[4])
    strengths = []
    for fk, label, score, team, gap in above[:2]:
        ev = _force_evidence.get(nm, {}).get(fk, "")
        strengths.append({"force": label, "score": score, "team_avg": team, "gap_above": gap, "evidence": ev})
    weakness = None
    if below:
        fk, label, score, team, gap = below[0]
        ev = _force_evidence.get(nm, {}).get(fk, "")
        weakness = {"force": label, "score": score, "team_avg": team, "gap_below": gap, "evidence": ev}
    rank = sum(1 for x in d_sales_list if x["ytd_rev"] > s["ytd_rev"]) + 1
    s["profile"] = {
        "rank": rank, "total": len(d_sales_list),
        "rev_pct": round(s["ytd_rev"] / d_total_rev * 100, 1),
        "strengths": strengths,
        "weakness": weakness,
    }

# 团队画像总结
_team_top1 = sorted(d_sales_list, key=lambda x: -x["ytd_rev"])[0]["name"]
_team_top_mg = sorted(d_sales_list, key=lambda x: -x["ytd_mg"])[0]
_team_most_custs = sorted(d_sales_list, key=lambda x: -x["cust_count"])[0]
D_TEAM_PROFILE = {
    "headcount": len(d_sales_list),
    "total_rev": round(d_total_rev, 0),
    "total_profit": round(d_total_profit, 0),
    "avg_score": d_avg_score,
    "a_count": d_a_level_count,
    "top_rev_name": _team_top1,
    "top_mg_name": _team_top_mg["name"], "top_mg_val": _team_top_mg["ytd_mg"],
    "most_custs_name": _team_most_custs["name"], "most_custs_val": _team_most_custs["cust_count"],
}
print(f"  能力画像: {len(d_sales_list)}人 · 团队总结已生成")

# 6m. 瀑布图数据（团队9力均值，供前端对比）
d_waterfall = {"team_avg": team_force_avg, "labels": [force_labels_cn[fk] for fk in force_keys]}

# 6n. 客户热力图（销售员 × Top33客户 × 利润金额万元）
# 批次④a 向量化：858 次 rex 布尔过滤（26人×33客户）→ 一次 groupby 预聚合（纯等价）
top33_custs = list(rex[(rex["_d"]>=ytd_start)&(rex["_d"]<=ytd_end)].groupby("_cust")["_rev"].sum().sort_values(ascending=False).head(33).index)
top33_custs = [c for c in top33_custs if c not in ("nan","None","","未知客户")]
_hm_rex = rex[(rex["_d"]>=ytd_start)&(rex["_d"]<=ytd_end)&(rex["_cust"].isin(top33_custs))]
_hm_agg = _hm_rex.groupby(["_sales","_cust"]).agg(rev=("_rev","sum"), profit=("_profit","sum")).reset_index()
_hm_map = {(str(_r["_sales"]), str(_r["_cust"])): (float(_r["rev"]), float(_r["profit"])) for _, _r in _hm_agg.iterrows()}
d_cust_heatmap = {"sales_names": [s["name"] for s in d_sales_list], "cust_names": top33_custs, "matrix": [], "detail": {}}
for s in d_sales_list:
    row = []
    s_total_profit = s["ytd_profit"]
    for cn in top33_custs:
        rec = _hm_map.get((s["name"], cn))
        rev = 0.0; profit = 0.0
        if rec is not None:
            rev = rec[0]; profit = rec[1]
        mg = round(profit/rev*100, 1) if rev > 0 else 0
        pct = round((profit/1e4)/s_total_profit*100, 1) if s_total_profit > 0 else 0
        row.append(round(profit/1e4, 2))
        d_cust_heatmap["detail"][f"{s['name']}|{cn}"] = {"r": round(rev/1e4,2), "p": round(profit/1e4,2), "mg": mg, "pct": pct}
    d_cust_heatmap["matrix"].append(row)
print(f"    客户热力图(利润): {len(top33_custs)}客户 x {len(d_sales_list)}销售员")

# ========== 7. E面 月度作战雷达 ==========
_timed("D面销售能力(含客户热力图)", _t_seg0); _t_seg0 = _time_mod.time()
print("[7/7] E面 月度作战雷达...")

# 产品线（新）列（已在keep_cols中）
# [批次⑤ P1] 本块原在 7c 之前，上移至预分组字典构建之前（纯列新增，提前不影响任何计算结果）
if pline_new_col and pline_new_col in rex.columns:
    rex["_pline_new"] = rex[pline_new_col].astype(str).str.strip()
else:
    rex["_pline_new"] = "未知"

# 7a. 全量月度KPI（所有月份 + 所有客户）
rex["_yr"] = rex["_d"].dt.year
all_months = sorted(rex["_ym"].unique())

# [批次⑤ P1 性能优化] 一次性 groupby 预分组，替代循环内 rex[rex[键]==值] 全表布尔扫描。
# groupby(sort=False) 组内保留原始行序，与布尔过滤结果逐行一致 → 下游计算零变化。
# 实测(191,725行)：object 列逐元素比较(comp_method_OBJECT_ARRAY) 34,305次/52.6s，占看板总耗时45%。
# 此后 rex 只读（不再新增列），字典在 7/8 节全程复用。
_REX_BY_YM = {k: g for k, g in rex.groupby("_ym", sort=False)}
# (月份, 销售员) 二级预分组：7d 的 TOP1/异动逐销售员取数用（不过滤 sales_2026_set，
# 与原 rex[(rex["_ym"]==prev_m)&(rex["_sales"]==name)] 无 isin 过滤的口径一致）
_BY_YM_SALES_ALL = {m2: {k: g for k, g in gg.groupby("_sales", sort=False)} for m2, gg in _REX_BY_YM.items()}

e_monthly_kpi = {}
for m in all_months:
    dm = _REX_BY_YM[m]  # [批次⑤ P1] 预分组，等价于 rex[rex["_ym"] == m]
    e_monthly_kpi[m] = {
        "rev": round(float(dm["_rev"].sum()) / 1e4, 2),
        "profit": round(float(dm["_profit"].sum()) / 1e4, 2),
        "mg": round(float(dm["_profit"].sum()) / float(dm["_rev"].sum()) * 100, 1) if float(dm["_rev"].sum()) > 0 else 0,
        "qty": round(float(dm["_qty"].sum()) / 1e4, 2),
        "asp": round(float(dm["_rev"].sum()) / float(dm["_qty"].sum()), 4) if float(dm["_qty"].sum()) > 0 else 0,
        "custs": int(dm["_cust"].nunique()),
        "items": int(dm["_item"].nunique()),
    }
    # 按层级
    for tier in ["KA", "AA", "KM", "MM"]:
        dt = dm[dm["_tier"].str.contains(tier, na=False)]
        e_monthly_kpi[m][f"{tier}_rev"] = round(float(dt["_rev"].sum()) / 1e4, 2)
        e_monthly_kpi[m][f"{tier}_custs"] = int(dt["_cust"].nunique())

# 7b. 客户月度数据（用于势能矩阵）
e_cust_monthly = {}
for m in all_months:
    dm = _REX_BY_YM[m]  # [批次⑤ P1] 预分组，等价于 rex[rex["_ym"] == m]
    cagg = dm.groupby("_cust").agg(rev=("_rev","sum"), profit=("_profit","sum"), qty=("_qty","sum")).reset_index()
    for _, r in cagg.iterrows():
        cid = str(r["_cust"]); rev = float(r["rev"]); profit = float(r["profit"])
        if cid in ("nan","None","","未知客户"): continue
        if cid not in e_cust_monthly: e_cust_monthly[cid] = {}
        e_cust_monthly[cid][m] = {
            "r": round(rev/1e4, 2), "p": round(profit/1e4, 2),
            "mg": round(profit/rev*100, 1) if rev > 0 else 0, "q": round(float(r["qty"])/1e4, 2)
        }

# 7c. 首次大量导入检测 (≥6000, 从2024-01到当前月的前一月检查历史)
# (_pline_new 已在 7a 前就绪 —— [批次⑤ P1] 上移)

# 产品线/品类YTD毛利率表（A面显示用）
ytd_all = rex[(rex["_d"]>=ytd_start)&(rex["_d"]<=ytd_end)]
# [批次⑥] YTD 按产品线/品类预分组，替代循环内等值全表过滤（组内行序一致，等价）
_YTD_BY_PLINE = {k: g for k, g in ytd_all.groupby("_pline_new", sort=False)}
_YTD_BY_CAT = {k: g for k, g in ytd_all.groupby("_cat", sort=False)}
pline_margins = []
for pline_name in sorted(ytd_all["_pline_new"].dropna().unique()):
    if pline_name in ("nan","None","","未知"): continue
    pd_data = _YTD_BY_PLINE[pline_name]  # [批次⑥] 预分组，等价于 ytd_all[ytd_all["_pline_new"]==pline_name]
    r=float(pd_data["_rev"].sum());p=float(pd_data["_profit"].sum())
    ka_d=pd_data[pd_data["_tier"].str.contains("KA",na=False)];ka_r=float(ka_d["_rev"].sum());ka_p=float(ka_d["_profit"].sum())
    aa_d=pd_data[pd_data["_tier"].str.contains("AA",na=False)&~pd_data["_tier"].str.contains("KA",na=False)];aa_r=float(aa_d["_rev"].sum());aa_p=float(aa_d["_profit"].sum())
    pline_margins.append({"name":pline_name,"rev":round(r/1e4,1),"profit":round(p/1e4,1),"mg":round(p/r*100,1)if r>0 else 0,"ka_rev":round(ka_r/1e4,1),"ka_mg":round(ka_p/ka_r*100,1)if ka_r>0 else 0,"aa_rev":round(aa_r/1e4,1),"aa_mg":round(aa_p/aa_r*100,1)if aa_r>0 else 0})
pline_margins.sort(key=lambda x:-x["rev"])
cat_margins = []
for cat_name in sorted(ytd_all["_cat"].dropna().unique()):
    if cat_name in ("nan","None",""): continue
    cd=_YTD_BY_CAT[cat_name];r=float(cd["_rev"].sum())  # [批次⑥] 预分组，等价于 ytd_all[ytd_all["_cat"]==cat_name]
    if r<10000: continue
    p=float(cd["_profit"].sum())
    ka_d=cd[cd["_tier"].str.contains("KA",na=False)];ka_r=float(ka_d["_rev"].sum());ka_p=float(ka_d["_profit"].sum())
    aa_d=cd[cd["_tier"].str.contains("AA",na=False)&~cd["_tier"].str.contains("KA",na=False)];aa_r=float(aa_d["_rev"].sum());aa_p=float(aa_d["_profit"].sum())
    cat_margins.append({"name":cat_name,"rev":round(r/1e4,1),"profit":round(p/1e4,1),"mg":round(p/r*100,1)if r>0 else 0,"ka_mg":round(ka_p/ka_r*100,1)if ka_r>0 else 0,"aa_mg":round(aa_p/aa_r*100,1)if aa_r>0 else 0})
cat_margins.sort(key=lambda x:-x["rev"])
cat_margins=cat_margins[:20]


first_imports = []
all_cust_item_history = set()  # 累积历史：已出现过的(客户, 存货名称)
for m in all_months:
    dm = _REX_BY_YM[m]  # [批次⑤ P1] 预分组，等价于 rex[rex["_ym"] == m]
    big = dm[dm["_qty"] >= 6000]
    for (cid, item), grp in big.groupby(["_cust", "_item"]):
        key = (str(cid), str(item))
        if key not in all_cust_item_history:
            # 首次大量导入！
            sales_list = grp["_sales"].unique()
            cat_new = grp["_cat_new"].iloc[0] if "_cat_new" in grp.columns else ""
            pline = grp["_pline_new"].iloc[0] if "_pline_new" in grp.columns else ""
            rev = float(grp["_rev"].sum()); profit = float(grp["_profit"].sum())
            cust_name = str(cid)
            if cust_name.strip() in ("nan","None","") or "未知" in cust_name: continue
            first_imports.append({
                "month": m, "cust": cust_name, "item": str(item),
                "cat": str(cat_new) if cat_new and cat_new != "nan" else "",
                "pline": str(pline),
                "rev": round(rev/1e4, 2), "profit": round(profit/1e4, 2),
                "mg": round(profit/rev*100, 1) if rev > 0 else 0,
                "qty": round(float(grp["_qty"].sum())/1e4, 2),
                "sales": ", ".join(sorted(set(sales_list))),
            })
        all_cust_item_history.add(key)

print(f"  月度KPI: {len(e_monthly_kpi)}月  客户月度: {len(e_cust_monthly)}客户  首次导入: {len(first_imports)}条")

# 7d. 销售员月度贡献（增强：新品+TOP1+异动）
e_sales_monthly = {}
for m in all_months:
    dm = _REX_BY_YM[m]  # [批次⑤ P1] 预分组，等价于 rex[rex["_ym"] == m]
    sdm = dm[dm["_sales"].isin(sales_2026_set)]
    sagg = sdm.groupby("_sales").agg(
        rev=("_rev","sum"), profit=("_profit","sum"), qty=("_qty","sum"),
        custs=("_cust","nunique"), new_rev=("_is_new","sum"),  # _is_new True=1
    ).reset_index()
    # 新品收入(仅新品标记=是)
    new_rev_real = sdm[sdm["_is_new"]].groupby("_sales")["_rev"].sum().reset_index()
    new_rev_real.columns = ["_sales", "new_rev_amt"]
    sagg = sagg.merge(new_rev_real, on="_sales", how="left")
    sagg["new_rev_amt"] = sagg["new_rev_amt"].fillna(0)
    # 每个销售员TOP1客户+异动
    for _, r in sagg.iterrows():
        name = str(r["_sales"])
        if name not in e_sales_monthly: e_sales_monthly[name] = {}
        rev = float(r["rev"]); profit = float(r["profit"])
        new_r = float(r["new_rev_amt"])/1e4
        new_pct = round(new_r/(rev/1e4)*100, 1) if rev > 0 else 0
        # TOP1客户(按收入)
        # [批次⑤ P1] 预分组替代 sdm[sdm["_sales"]==name]：name 来自 sagg ⊆ sdm（isin 过滤集合），
        # 该销售员当月行集与 sdm 内过滤结果完全一致
        _sd = _BY_YM_SALES_ALL[m].get(name, sdm.iloc[0:0])
        sd_cust = _sd.groupby("_cust").agg(cr=("_rev","sum"),cp=("_profit","sum")).reset_index()
        top1 = sd_cust.sort_values("cr",ascending=False).head(1)
        top1_cust = str(top1["_cust"].iloc[0]) if len(top1)>0 else ""
        top1_rev = round(float(top1["cr"].iloc[0])/1e4,2) if len(top1)>0 else 0
        top1_rev_pct = round(top1_rev/(rev/1e4)*100,1) if rev>0 else 0
        # TOP1客户(按利润)
        top1p = sd_cust.sort_values("cp",ascending=False).head(1)
        top1p_cust = str(top1p["_cust"].iloc[0]) if len(top1p)>0 else ""
        top1p_profit = round(float(top1p["cp"].iloc[0])/1e4,2) if len(top1p)>0 else 0
        top1p_pct = round(top1p_profit/(profit/1e4)*100,1) if profit>0 else 0
        # 异动客户 (>50%环比变化)
        prev_m = (pd.Timestamp(m[:4]+"-"+m[5:]+"-01") - pd.DateOffset(months=1)).strftime("%Y-%m")
        anomalies = []
        if prev_m in all_months:
            # [批次⑤ P1] 预分组替代 rex[(rex["_ym"]==prev_m)&(rex["_sales"]==name)]（键不存在→空帧，与原布尔过滤一致）
            prev_dm = _BY_YM_SALES_ALL.get(prev_m, {}).get(name, rex.iloc[0:0])
            prev_cust = prev_dm.groupby("_cust")["_rev"].sum().to_dict()
            for cid, cr in dict(sd_cust[["_cust","cr"]].values).items():
                prev_r = prev_cust.get(cid, 0)
                cr_w = cr/1e4; prev_r_w = prev_r/1e4
                if prev_r > 0:
                    chg = (cr - prev_r) / prev_r * 100
                    if abs(chg) > 50:
                        anomalies.append({"cust": str(cid), "chg": round(chg, 1), "dir": "↑" if chg > 0 else "↓", "rev_chg": round(cr_w - prev_r_w, 1), "prev_rev": round(prev_r_w, 1), "is_new": False})
                elif cr > 0:
                    anomalies.append({"cust": str(cid), "chg": 0, "dir": "↑", "rev_chg": round(cr_w, 1), "prev_rev": 0, "is_new": True})
        anomalies.sort(key=lambda x: -abs(x["chg"]))
        e_sales_monthly[name][m] = {
            "r": round(rev/1e4, 2), "p": round(profit/1e4, 2),
            "q": round(float(r["qty"])/1e4, 2),
            "mg": round(profit/rev*100, 1) if rev > 0 else 0,
            "custs": int(r["custs"]),
            "new_r": round(new_r, 2), "new_pct": new_pct,
            "top1_cust": top1_cust, "top1_rev": top1_rev, "top1_rev_pct": top1_rev_pct,
            "top1p_cust": top1p_cust, "top1p_profit": top1p_profit, "top1p_pct": top1p_pct,
            "anomalies": anomalies[:3],
        }
# 为每个销售员补导入统计
for fi in first_imports:
    for sn in fi["sales"].split(", "):
        if sn and sn in e_sales_monthly:
            m = fi["month"]
            if m not in e_sales_monthly[sn]: e_sales_monthly[sn][m] = {"r":0,"p":0,"mg":0,"custs":0,"items":0,"imports":0,"import_rev":0,"import_profit":0}
            e_sales_monthly[sn][m].setdefault("imports", 0)
            e_sales_monthly[sn][m].setdefault("import_rev", 0)
            e_sales_monthly[sn][m].setdefault("import_profit", 0)
            e_sales_monthly[sn][m]["imports"] += 1
            e_sales_monthly[sn][m]["import_rev"] = round(e_sales_monthly[sn][m]["import_rev"] + fi["rev"], 2)
            e_sales_monthly[sn][m]["import_profit"] = round(e_sales_monthly[sn][m]["import_profit"] + fi["profit"], 2)

# 客户层级映射
e_cust_tier = {}
for cid in rex_valid_sales["_cust"].unique():
    cid_str = str(cid)
    if cid_str in ("nan","None",""): continue
    tier_row = rex_valid_sales[rex_valid_sales["_cust"] == cid]["_tier"].iloc[0]
    e_cust_tier[cid_str] = str(tier_row)

# 客户名称映射（用于显示）
e_cust_names = {str(cid): str(cid) for cid in rex["_cust"].unique()}

print(f"  销售员月度: {len(e_sales_monthly)}人  首次导入检测完成")

# 7g. §3量利拆解数据（四维度：产品线/KA客户/AA客户/Top10品类）
# Top10品类按全时段收入预计算（避免每月独立取Top10导致历史月缺数据）
top_cat_names = list(rex.groupby("_cat")["_rev"].sum().sort_values(ascending=False).head(10).index)
e_decomp = {}
for dim_key, dim_label, dim_col, dim_filter in [
    ("pline", "产品线", "_pline_new", None),
    ("ka_cust", "KA客户", "_cust", lambda d: d["_tier"].str.contains("KA", na=False)),
    ("aa_cust", "AA客户", "_cust", lambda d: d["_tier"].str.contains("AA", na=False) & ~d["_tier"].str.contains("KA", na=False)),
    ("top_cat", "Top10品类", "_cat", None),
]:
    items = {}
    for m in all_months:
        dm = _REX_BY_YM[m]  # [批次⑤ P1] 预分组，等价于 rex[rex["_ym"]==m]
        if dim_filter: dm = dm[dim_filter(dm)]
        if dim_key == "top_cat":
            dm = dm[dm[dim_col].isin(top_cat_names)]
        agg = dm.groupby(dim_col).agg(r=("_rev","sum"),p=("_profit","sum"),q=("_qty","sum")).reset_index()
        for _, r in agg.iterrows():
            nm = str(r[dim_col])
            if nm in ("nan","None","","未知","未知客户"): continue
            if nm not in items: items[nm] = {}
            items[nm][m] = {"r":float(r["r"]),"p":float(r["p"]),"q":float(r["q"])}
    e_decomp[dim_key] = {"label": dim_label, "items": items}
print(f"  §3量利拆解: { {k:len(v['items']) for k,v in e_decomp.items()} }")

# 7e. KA型号变化（直接从产品变迁数据汇总，数据源统一）
ka_changes = [p for p in product_change_detail if p["tier"] == "KA"]
ka_kpi["added"] = sum(p["gained_count"] for p in ka_changes)
ka_kpi["removed"] = sum(p["lost_count"] for p in ka_changes)
print(f"  KA型号变化: +{ka_kpi['added']}/-{ka_kpi['removed']} (从变迁数据汇总)")

# AA型号变化 + AA KPI（AA卡片数据）
aa_changes = [p for p in product_change_detail if p["tier"] == "AA"]
aa_added = sum(p["gained_count"] for p in aa_changes)
aa_removed = sum(p["lost_count"] for p in aa_changes)
aa_rex = r26[r26["_tier"].str.contains("AA",na=False)&~r26["_tier"].str.contains("KA",na=False)]
aa_qty = round(float(aa_rex["_qty"].sum())/1e4, 0)
aa_rev = float(aa_rex["_rev"].sum())
aa_asp = round(aa_rev/float(aa_rex["_qty"].sum()), 4) if float(aa_rex["_qty"].sum())>0 else 0
aa_apr_rex = rex[(rex["_d"]>=prev_month_start)&(rex["_d"]<=prev_month_end)&(rex["_tier"].str.contains("AA",na=False)&~rex["_tier"].str.contains("KA",na=False))]
aa_apr_asp = round(float(aa_apr_rex["_rev"].sum())/float(aa_apr_rex["_qty"].sum()),4) if float(aa_apr_rex["_qty"].sum())>0 else 0
aa_asp_mom = round((aa_asp-aa_apr_asp)/aa_apr_asp*100,1) if aa_apr_asp>0 else 0
print(f"  AA型号变化: +{aa_added}/-{aa_removed}")

# 7f. E面首次导入汇总数（当月）
e_import_summary = {}
latest_month = latest
fi_latest = [fi for fi in first_imports if fi["month"]==latest_month]
e_import_summary["count"] = len(fi_latest)
e_import_summary["custs"] = len(set(fi["cust"] for fi in fi_latest))
e_import_summary["rev"] = round(sum(fi["rev"] for fi in fi_latest), 2)
e_import_summary["month"] = latest_month

# ========== 8. F面 H1半年度汇总 + D面部门级次 + 新品分析 ==========
_timed("E面月度作战雷达(含量利拆解)", _t_seg0); _t_seg0 = _time_mod.time()
print("[8/8] F面H1汇总 + 部门级次 + 新品分析...")

# ---- 8a. 部门映射 ----
import re as _re
_personnel_path = os.path.join(PROJECT, "data", "部门-人员-职务对应.md")
sales_dept_map = {}
if os.path.exists(_personnel_path):
    with open(_personnel_path, 'r', encoding='utf-8') as f:
        _md = f.read()
    _cur_dept = None
    for _line in _md.split('\n'):
        _m = _re.match(r'###\s+\d+\.\d+\s+(.+?)（\d+\s*人', _line)
        if _m:
            _cur_dept = _m.group(1).strip()
        if _line.startswith('|') and not _line.startswith('|--') and not _line.startswith('| 工号') and not _line.startswith('| 字段') and _cur_dept:
            _parts = [p.strip() for p in _line.split('|')]
            if len(_parts) >= 5:
                _nm = _parts[2]  # 姓名 column (工号=1, 姓名=2)
                if _nm and _nm != '姓名' and len(_nm) <= 4:
                    sales_dept_map[_nm] = _cur_dept

# Mark unmatched as 已离职
for _sn in rex_valid_sales["_sales"].unique():
    if _sn not in sales_dept_map and _sn not in ("", "nan", "None", "未知"):
        sales_dept_map[_sn] = "已离职"

# Add dept to d_sales_list
for _s in d_sales_list:
    _s["dept"] = sales_dept_map.get(_s["name"], "已离职")

# ---- 8b. 部门级聚合 ----
dept_list = []
for _dn in sorted(set(sales_dept_map.values())):
    _ds = [s for s in d_sales_list if s["dept"] == _dn]
    if not _ds:
        continue
    _dr = sum(s["ytd_rev"] for s in _ds)
    _dp = sum(s["ytd_profit"] for s in _ds)
    _df = {}
    for _fk in force_keys:
        _vals = [s["forces"].get(_fk, 50) for s in _ds if s["forces"].get(_fk, 0) > 0]
        _df[_fk] = round(sum(_vals) / len(_vals), 1) if _vals else 50
    dept_list.append({
        "name": _dn, "headcount": len(_ds),
        "rev": round(_dr, 1), "profit": round(_dp, 1),
        "mg": round(_dp / _dr * 100, 1) if _dr > 0 else 0,
        "custs": sum(s["cust_count"] for s in _ds),
        "kaaa": sum(s["ka_aa_count"] for s in _ds),
        "score": round(sum(s["score"] for s in _ds) / len(_ds), 1) if _ds else 0,
        "forces": _df,
        "members": [{"name": s["name"], "rev": s["ytd_rev"], "mg": s["ytd_mg"], "score": s["score"]} for s in _ds],
    })
dept_list.sort(key=lambda x: -x["rev"])

# ---- 插拔（W4 拍板）：F面平时关闭（faces.yaml visible=false）时跳过 8c-8h 全部 H1 计算，注入空值 ----
if _face_visible("F"):
    # ---- 8c. H1数据 ----
    h1_data = rex[(rex["_d"] >= f"{_latest_y}-01-01") & (rex["_d"] <= f"{_latest_y}-06-30")]
    ph1_data = rex[(rex["_d"] >= f"{_latest_y-1}-01-01") & (rex["_d"] <= f"{_latest_y-1}-06-30")]
    h1_r = float(h1_data["_rev"].sum()); h1_p = float(h1_data["_profit"].sum())
    h1_q = float(h1_data["_qty"].sum())
    h1_mg = round(h1_p / h1_r * 100, 1) if h1_r > 0 else 0
    ph1_r = float(ph1_data["_rev"].sum()); ph1_p = float(ph1_data["_profit"].sum())
    ph1_mg = round(ph1_p / ph1_r * 100, 1) if ph1_r > 0 else 0
    h1_rev_yoy = round((h1_r - ph1_r) / ph1_r * 100, 1) if ph1_r > 0 else 0
    h1_mg_yoy = round(h1_mg - ph1_mg, 1)
    h1_asp = round(h1_r / h1_q, 4) if h1_q > 0 else 0
    ph1_q = float(ph1_data["_qty"].sum())
    h1_asp_yoy = round((h1_asp - (ph1_r / ph1_q if ph1_q > 0 else 0)) / (ph1_r / ph1_q if ph1_q > 0 else 1) * 100, 1) if ph1_q > 0 else 0
    # KA+AA H1
    h1_kaaa_d = h1_data[h1_data["_tier"].str.contains("KA|AA", na=False)]
    h1_kaaa_r = float(h1_kaaa_d["_rev"].sum()); h1_kaaa_p = float(h1_kaaa_d["_profit"].sum())
    h1_kaaa_sc = h1_kaaa_d["_cust"].nunique()

    f_h1_kpi = {
        "rev": round(h1_r / 1e4, 0), "profit": round(h1_p / 1e4, 0), "mg": h1_mg,
        "mg_yoy": h1_mg_yoy, "rev_yoy": h1_rev_yoy, "asp": h1_asp, "asp_yoy": h1_asp_yoy,
        "prev_mg": ph1_mg, "period": f"{_latest_y} H1 (1-6月)",
        "kaaa_rev": round(h1_kaaa_r / 1e4, 0), "kaaa_mg": round(h1_kaaa_p / h1_kaaa_r * 100, 1) if h1_kaaa_r > 0 else 0,
        "kaaa_pct": round(h1_kaaa_r / h1_r * 100, 1) if h1_r > 0 else 0, "kaaa_count": h1_kaaa_sc,
    }

    # H1 产品线毛利率
    # [批次⑥] H1/去年H1 按产品线/品类预分组，替代循环内等值全表过滤（组内行序一致，等价）
    _H1_BY_PLINE = {k: g for k, g in h1_data.groupby("_pline_new", sort=False)}
    _PH1_BY_PLINE = {k: g for k, g in ph1_data.groupby("_pline_new", sort=False)}
    _H1_BY_CAT = {k: g for k, g in h1_data.groupby("_cat", sort=False)}
    _PH1_BY_CAT = {k: g for k, g in ph1_data.groupby("_cat", sort=False)}
    _H1_E0, _PH1_E0 = h1_data.iloc[0:0], ph1_data.iloc[0:0]
    h1_pline_margins = []
    for _pn in sorted(h1_data["_pline_new"].dropna().unique()):
        if _pn in ("nan", "None", "", "未知"):
            continue
        _pd = _H1_BY_PLINE[_pn]  # [批次⑥] 预分组
        _r = float(_pd["_rev"].sum()); _p = float(_pd["_profit"].sum())
        _ppd = _PH1_BY_PLINE.get(_pn, _PH1_E0)  # [批次⑥] 预分组（键缺→空帧，与原过滤一致）
        _pr = float(_ppd["_rev"].sum()); _pp = float(_ppd["_profit"].sum())
        h1_pline_margins.append({
            "name": _pn, "rev": round(_r / 1e4, 1), "profit": round(_p / 1e4, 1),
            "mg": round(_p / _r * 100, 1) if _r > 0 else 0,
            "prev_mg": round(_pp / _pr * 100, 1) if _pr > 0 else 0,
            "mg_yoy": round(_p / _r * 100 - (_pp / _pr * 100 if _pr > 0 else 0), 1) if _r > 0 else 0,
            "rev_yoy": round((_r - _pr) / _pr * 100, 1) if _pr > 0 else 0,
        })
    h1_pline_margins.sort(key=lambda x: -x["rev"])

    # H1 品类毛利率
    h1_cat_margins = []
    for _cn in sorted(h1_data["_cat"].dropna().unique()):
        if _cn in ("nan", "None", ""):
            continue
        _cd = _H1_BY_CAT[_cn]  # [批次⑥] 预分组
        _r = float(_cd["_rev"].sum())
        if _r < 10000:
            continue
        _p = float(_cd["_profit"].sum())
        _kad = _cd[_cd["_tier"].str.contains("KA", na=False)]
        _aar = _cd[_cd["_tier"].str.contains("AA", na=False) & ~_cd["_tier"].str.contains("KA", na=False)]
        _pcd = _PH1_BY_CAT.get(_cn, _PH1_E0)  # [批次⑥] 预分组
        _pr = float(_pcd["_rev"].sum()); _pp = float(_pcd["_profit"].sum())
        h1_cat_margins.append({
            "name": _cn, "rev": round(_r / 1e4, 1), "profit": round(_p / 1e4, 1),
            "mg": round(_p / _r * 100, 1) if _r > 0 else 0,
            "ka_mg": round(float(_kad["_profit"].sum()) / float(_kad["_rev"].sum()) * 100, 1) if float(_kad["_rev"].sum()) > 0 else 0,
            "aa_mg": round(float(_aar["_profit"].sum()) / float(_aar["_rev"].sum()) * 100, 1) if float(_aar["_rev"].sum()) > 0 else 0,
            "prev_mg": round(_pp / _pr * 100, 1) if _pr > 0 else 0,
            "mg_yoy": round(_p / _r * 100 - (_pp / _pr * 100 if _pr > 0 else 0), 1) if _r > 0 else 0,
        })
    h1_cat_margins.sort(key=lambda x: -x["rev"])

    # H1 销售部毛利率
    h1_dept_margins = []
    for _dn in sorted(set(sales_dept_map.values())):
        _names = [n for n, d in sales_dept_map.items() if d == _dn]
        _dd = h1_data[h1_data["_sales"].isin(_names)]
        _r = float(_dd["_rev"].sum()); _p = float(_dd["_profit"].sum())
        if _r < 10000:
            continue
        _pdd = ph1_data[ph1_data["_sales"].isin(_names)]
        _pr = float(_pdd["_rev"].sum()); _pp = float(_pdd["_profit"].sum())
        _dq = float(_dd["_qty"].sum()); _pdq = float(_pdd["_qty"].sum())
        _asp = round(_r / _dq, 4) if _dq > 0 else 0
        _pasp = round(_pr / _pdq, 4) if _pdq > 0 else 0
        _asp_yoy = round((_asp - _pasp) / _pasp * 100, 1) if _pasp > 0 else 0
        _dm = h1_data[(h1_data["_d"].dt.month == _latest_m) & (h1_data["_d"].dt.year == _latest_y) & h1_data["_sales"].isin(_names)]
        _pm = h1_data[(h1_data["_d"].dt.month == _prev_m) & (h1_data["_d"].dt.year == _prev_y) & h1_data["_sales"].isin(_names)]
        _dm_r = float(_dm["_rev"].sum()); _pm_r = float(_pm["_rev"].sum())
        _asp_mom = round((_dm_r / float(_dm["_qty"].sum()) - _pm_r / float(_pm["_qty"].sum())) / (_pm_r / float(_pm["_qty"].sum()) if float(_pm["_qty"].sum()) > 0 else 1) * 100, 1) if float(_dm["_qty"].sum()) > 0 and float(_pm["_qty"].sum()) > 0 and _pm_r > 0 else 0
        _inds = []
        for _sn in _names:
            _sd = _dd[_dd["_sales"] == _sn]
            _sr = float(_sd["_rev"].sum())
            if _sr > 0:
                _sq = float(_sd["_qty"].sum())
                _inds.append({"name": _sn, "rev": round(_sr / 1e4, 1), "mg": round(float(_sd["_profit"].sum()) / _sr * 100, 1), "asp": round(_sr / _sq, 4) if _sq > 0 else 0})
        _inds.sort(key=lambda x: -x["rev"])
        h1_dept_margins.append({
            "name": _dn, "rev": round(_r / 1e4, 1), "profit": round(_p / 1e4, 1),
            "mg": round(_p / _r * 100, 1) if _r > 0 else 0,
            "prev_mg": round(_pp / _pr * 100, 1) if _pr > 0 else 0,
            "mg_yoy": round(_p / _r * 100 - (_pp / _pr * 100 if _pr > 0 else 0), 1) if _r > 0 else 0,
            "asp": _asp, "asp_yoy": _asp_yoy, "asp_mom": _asp_mom,
            "headcount": len(_names), "individuals": _inds,
        })
    h1_dept_margins.sort(key=lambda x: -x["rev"])

    # [批次⑤ P1] H1/去年H1 按客户预分组，替代循环内逐客户全表布尔过滤（组内行序一致，等价）
    _H1_BY_CUST = {k: g for k, g in h1_data.groupby("_cust", sort=False)}
    _PH1_BY_CUST = {k: g for k, g in ph1_data.groupby("_cust", sort=False)}
    _H1_EMPTY = h1_data.iloc[0:0]
    _PH1_EMPTY = ph1_data.iloc[0:0]

    # H1 KA/AA客户毛利率（全量，含ASP/环比/新品渗透）
    h1_kaaa_cust = h1_kaaa_d.groupby("_cust").agg(rev=("_rev", "sum"), profit=("_profit", "sum"), qty=("_qty", "sum")).reset_index()
    h1_kaaa_margins = []
    for _, _row in h1_kaaa_cust.sort_values("rev", ascending=False).iterrows():
        _nm = str(_row["_cust"]); _r = float(_row["rev"]); _p = float(_row["profit"]); _q = float(_row["qty"])
        _hg = _H1_BY_CUST.get(_nm, _H1_EMPTY)    # [批次⑤ P1] 等价于 h1_data[h1_data["_cust"] == _nm]
        _pg = _PH1_BY_CUST.get(_nm, _PH1_EMPTY)  # [批次⑤ P1] 等价于 ph1_data[ph1_data["_cust"] == _nm]
        _prev = _pg[_pg["_tier"].str.contains("KA|AA", na=False)]
        _pr = float(_prev["_rev"].sum()); _pp = float(_prev["_profit"].sum()); _pq = float(_prev["_qty"].sum())
        _tr = _hg["_tier"]  # [批次⑤ P1] 预分组取数
        _tier = "KA" if any("KA" in str(t) for t in _tr) else ("AA" if any("AA" in str(t) for t in _tr) else "")
        # ASP
        _asp = round(_r / _q, 4) if _q > 0 else 0
        _pasp = round(_pr / _pq, 4) if _pq > 0 else 0
        _asp_yoy = round((_asp - _pasp) / _pasp * 100, 1) if _pasp > 0 else 0
        # 环比（最新月vs上月）
        _cm = _hg[(_hg["_d"].dt.month == _latest_m) & (_hg["_d"].dt.year == _latest_y)]  # [批次⑤ P1]
        _pm = _hg[(_hg["_d"].dt.month == _prev_m) & (_hg["_d"].dt.year == _prev_y)]      # [批次⑤ P1]
        _cm_r = float(_cm["_rev"].sum()); _pm_r = float(_pm["_rev"].sum())
        _mom = round((_cm_r - _pm_r) / _pm_r * 100, 1) if _pm_r > 0 else 0
        # 新品渗透
        _cn = _hg[_hg["_is_new"]]  # [批次⑤ P1]
        _new_r = float(_cn["_rev"].sum())
        _new_pct = round(_new_r / _r * 100, 1) if _r > 0 else 0
        h1_kaaa_margins.append({
            "name": _nm, "tier": _tier, "rev": round(_r / 1e4, 1), "profit": round(_p / 1e4, 1),
            "mg": round(_p / _r * 100, 1) if _r > 0 else 0,
            "prev_mg": round(_pp / _pr * 100, 1) if _pr > 0 else 0,
            "mg_yoy": round(_p / _r * 100 - (_pp / _pr * 100 if _pr > 0 else 0), 1) if _r > 0 else 0,
            "rev_yoy": round((_r - _pr) / _pr * 100, 1) if _pr > 0 else 0,
            "asp": _asp, "asp_yoy": _asp_yoy, "mom": _mom, "new_pct": _new_pct,
        })

    # ---- 8d. 新品分析（12个月存活口径）----
    # [批次⑤ P1] 按存货名称/产品品种一次性预分组（8d 新品、8g 趋势/Top5/品类映射复用），
    # 替代循环内 rex[rex["_prod"|"_item"]==x] 全表布尔扫描（组内行序一致，等价）
    _REX_BY_PROD = {k: g for k, g in rex.groupby("_prod", sort=False)}
    _REX_BY_ITEM = {k: g for k, g in rex.groupby("_item", sort=False)}
    _rex_new = rex[rex["_is_new"]]  # 本块多次复用，提升一次
    _new_prods = _rex_new["_prod"].unique()
    np_analysis = []
    for _prod in _new_prods:
        _pdata = _REX_BY_PROD[_prod]  # [批次⑤ P1] 预分组，等价于 rex[rex["_prod"] == _prod]
        _fd = _pdata["_d"].min()
        _we = _fd + pd.DateOffset(months=12)
        _wdata = _pdata[(_pdata["_d"] >= _fd) & (_pdata["_d"] <= _we)]
        _pm = _wdata["_ym"].nunique()
        _r = float(_wdata["_rev"].sum()); _p = float(_wdata["_profit"].sum())
        np_analysis.append({
            "name": _prod, "first": _fd.strftime("%Y-%m-%d"),
            "survival": round(_pm / 12 * 100, 1),
            "rev": round(_r / 1e4, 1), "mg": round(_p / _r * 100, 1) if _r > 0 else 0,
            "custs": int(_wdata["_cust"].nunique()),
            "sales": int(_wdata["_sales"].nunique()) if "_sales" in _wdata.columns else 0,
        })
    np_analysis.sort(key=lambda x: -x["rev"])
    _np_total_rev = sum(p["rev"] for p in np_analysis)
    _np_total_profit = sum(p["mg"] * p["rev"] / 100 for p in np_analysis)
    np_summary = {
        "count": len(np_analysis),
        "survival_rate": round(sum(1 for p in np_analysis if p["survival"] > 0) / len(np_analysis) * 100, 1) if np_analysis else 0,
        "mg": round(_np_total_profit / _np_total_rev * 100, 1) if _np_total_rev > 0 else 0,
        "penetration": round(len(set(_rex_new["_cust"])) / rex["_cust"].nunique() * 100, 1) if rex["_cust"].nunique() > 0 else 0,
        "promotion": round(len(set(_rex_new["_sales"]) & sales_2026_set) / len(sales_2026_set) * 100, 1) if sales_2026_set else 0,
        "total_rev": round(_np_total_rev, 1),
        "customers": len(set(_rex_new["_cust"])),
        "sales_people": len(set(_rex_new["_sales"]) & sales_2026_set) if "_sales" in rex.columns else 0,
    }

    # ---- 8e. H1关键问题与解决方案 ----
    h1_issues = []
    for _pl in h1_pline_margins:
        if _pl["mg_yoy"] < -2 and _pl["rev"] > 100:
            h1_issues.append({"type": "产品线毛利率下滑", "target": _pl["name"],
                "metric": f"毛利率{_pl['mg']}%(同比{_pl['mg_yoy']:+.1f}pp)",
                "solution": f"排查{_pl['name']}成本结构，关注ASP下降是否由价格战引起，评估是否调整产品组合"})
    for _dept in h1_dept_margins:
        if _dept["mg"] < h1_mg - 3 and _dept["rev"] > 100:
            h1_issues.append({"type": "销售部毛利率偏低", "target": _dept["name"],
                "metric": f"毛利率{_dept['mg']}%(低于整体{h1_mg - _dept['mg']:.1f}pp)",
                "solution": f"检查{_dept['name']}客户结构，关注低毛利客户占比，加强定价博弈力培训"})
    for _cust in h1_kaaa_margins:
        if _cust["mg_yoy"] < -3 and _cust["rev"] > 100:
            # 客户产品级归因：按存货名称拆解毛利率变化
            _cn = _cust["name"]
            _hg2 = _H1_BY_CUST.get(_cn, _H1_EMPTY)    # [批次⑤ P1] 等价于 h1_data[h1_data["_cust"] == _cn]
            _pg2 = _PH1_BY_CUST.get(_cn, _PH1_EMPTY)  # [批次⑤ P1] 等价于 ph1_data[ph1_data["_cust"] == _cn]
            _cust_26h1 = _hg2[(_hg2["_d"] >= f"{_latest_y}-01-01") & (_hg2["_d"] <= f"{_latest_y}-06-30")]
            _cust_25h1 = _pg2[(_pg2["_d"] >= f"{_prev_year}-01-01") & (_pg2["_d"] <= f"{_prev_year}-06-30")]
            _cust_attr = []
            for _pn in _cust_26h1["_item"].unique():
                _pd26 = _cust_26h1[_cust_26h1["_item"] == _pn]
                _r26 = float(_pd26["_rev"].sum()); _p26 = float(_pd26["_profit"].sum())
                if _r26 < 5000:
                    continue
                _pd25 = _cust_25h1[_cust_25h1["_item"] == _pn]
                _r25 = float(_pd25["_rev"].sum()); _p25 = float(_pd25["_profit"].sum())
                _mg26 = _p26 / _r26 * 100 if _r26 > 0 else 0
                _mg25 = _p25 / _r25 * 100 if _r25 > 0 else 0
                _cat_val = str(_pd26["_cat"].iloc[0]) if len(_pd26) > 0 else ""
                _cust_attr.append({
                    "name": _pn, "cat": _cat_val,
                    f"rev_{_yy_latest}h1": round(_r26 / 1e4, 1), f"mg_{_yy_latest}h1": round(_mg26, 1),
                    f"rev_{_yy_prev}h1": round(_r25 / 1e4, 1), f"mg_{_yy_prev}h1": round(_mg25, 1),
                    "mg_change": round(_mg26 - _mg25, 1),
                    "is_new": _r25 < 1000,
                })
            _cust_attr.sort(key=lambda x: x["mg_change"])
            # 判断原因类型
            _price_drop = [p for p in _cust_attr if p["mg_change"] < -3 and not p["is_new"]]
            _new_low = [p for p in _cust_attr if p["is_new"] and p[f"mg_{_yy_latest}h1"] < _cust["mg"]]
            _reason = "价格原因" if len(_price_drop) >= len(_new_low) else "结构原因" if _new_low else "综合原因"
            h1_issues.append({"type": "KA/AA客户毛利率下滑", "target": _cn,
                "metric": f"毛利率{_cust['mg']}%(同比{_cust['mg_yoy']:+.1f}pp) → {_reason}",
                "solution": f"{'价格原因：以下产品毛利率同比下降，建议核查定价' if _reason=='价格原因' else '结构原因：低毛利新品/新品类占比上升拉低整体' if _reason=='结构原因' else '价格+结构综合影响'}",
                "cust_attr": _cust_attr[:10],
                "reason": _reason,
            })

    # ---- 8f. 品类毛利下降归因分析 ----
    h1_cat_attribution = []
    for _cat in h1_cat_margins:
        if _cat["mg_yoy"] >= -2 or _cat["rev"] < 100:
            continue
        _cd = _H1_BY_CAT[_cat["name"]]  # [批次⑥] 预分组
        _pcd = _PH1_BY_CAT.get(_cat["name"], _PH1_E0)  # [批次⑥] 预分组
        _prod_attr = []
        for _pn in _cd["_item"].unique():
            _pd = _cd[_cd["_item"] == _pn]
            _r = float(_pd["_rev"].sum()); _p = float(_pd["_profit"].sum()); _q = float(_pd["_qty"].sum())
            if _r < 10000:
                continue
            _ppd = _pcd[_pcd["_item"] == _pn]
            _pr = float(_ppd["_rev"].sum()); _pp = float(_ppd["_profit"].sum())
            _mg = _p / _r * 100 if _r > 0 else 0
            _pmg = _pp / _pr * 100 if _pr > 0 else 0
            _mg_chg = _mg - _pmg
            _impact = _r * _mg_chg / 100
            _rm = _pd[(_pd["_d"].dt.month == _latest_m) & (_pd["_d"].dt.year == _latest_y)]
            _rm_r = float(_rm["_rev"].sum()); _rm_q = float(_rm["_qty"].sum())
            _rm_asp = _rm_r / _rm_q if _rm_q > 0 else 0
            _prod_attr.append({
                "name": _pn, "rev": round(_r / 1e4, 1), "mg": round(_mg, 1),
                "prev_mg": round(_pmg, 1), "mg_change": round(_mg_chg, 1),
                "impact": round(_impact / 1e4, 1),
                "recent_rev": round(_rm_r / 1e4, 1), "recent_qty": round(_rm_q / 1e4, 2),
                "recent_asp": round(_rm_asp, 4),
            })
        _prod_attr.sort(key=lambda x: x["impact"])
        h1_cat_attribution.append({
            "category": _cat["name"], "mg_yoy": _cat["mg_yoy"],
            "rev": _cat["rev"], "mg": _cat["mg"],
            "products": _prod_attr[:8],
        })

    # 产品线归因分析（与品类归因合并到同一列表）
    for _pl in h1_pline_margins:
        if _pl["mg_yoy"] >= -2 or _pl["rev"] < 100:
            continue
        _pd_data = _H1_BY_PLINE[_pl["name"]]  # [批次⑥] 预分组
        _ppd_data = _PH1_BY_PLINE.get(_pl["name"], _PH1_E0)  # [批次⑥] 预分组
        _pline_attr = []
        for _pn in _pd_data["_item"].unique():
            _pd = _pd_data[_pd_data["_item"] == _pn]
            _r = float(_pd["_rev"].sum()); _p = float(_pd["_profit"].sum()); _q = float(_pd["_qty"].sum())
            if _r < 10000:
                continue
            _ppd = _ppd_data[_ppd_data["_item"] == _pn]
            _pr = float(_ppd["_rev"].sum()); _pp = float(_ppd["_profit"].sum())
            _mg = _p / _r * 100 if _r > 0 else 0
            _pmg = _pp / _pr * 100 if _pr > 0 else 0
            _mg_chg = _mg - _pmg
            _impact = _r * _mg_chg / 100
            _rm = _pd[(_pd["_d"].dt.month == _latest_m) & (_pd["_d"].dt.year == _latest_y)]
            _rm_r = float(_rm["_rev"].sum()); _rm_q = float(_rm["_qty"].sum())
            _rm_asp = _rm_r / _rm_q if _rm_q > 0 else 0
            _pline_attr.append({
                "name": _pn, "rev": round(_r / 1e4, 1), "mg": round(_mg, 1),
                "prev_mg": round(_pmg, 1), "mg_change": round(_mg_chg, 1),
                "impact": round(_impact / 1e4, 1),
                "recent_rev": round(_rm_r / 1e4, 1), "recent_qty": round(_rm_q / 1e4, 2),
                "recent_asp": round(_rm_asp, 4),
            })
        _pline_attr.sort(key=lambda x: x["impact"])
        h1_cat_attribution.append({
            "category": _pl["name"], "mg_yoy": _pl["mg_yoy"],
            "rev": _pl["rev"], "mg": _pl["mg"],
            "products": _pline_attr[:8],
        })

    print(f"  H1: 收入{h1_r/1e4:.0f}万 毛利率{h1_mg}% 同比{h1_mg_yoy:+.1f}pp")
    print(f"  部门: {len(dept_list)}部 新品: {len(np_analysis)}个 存活率{np_summary['survival_rate']}% H1问题: {len(h1_issues)}条")

    # ---- 8g. F面产品维度H1对比 ----
    print("  产品维度H1对比...")
    # 定义半年区间（批次②：由 _latest_period 动态推导 前年H1/H2 + 当年H1）
    _h1_periods = _PD["h1_periods"]
    # 按存货名称聚合每个半年的收入/利润/成本
    _prod_h1 = {}
    for _pk, (_ps, _pe) in _h1_periods.items():
        _pd = rex[(rex["_d"] >= _ps) & (rex["_d"] <= _pe)]
        _agg = _pd.groupby("_item").agg(rev=("_rev", "sum"), profit=("_profit", "sum"), cost=("_rev", lambda x: float(x.sum()) - float(_pd.loc[x.index, "_profit"].sum())), qty=("_qty", "sum")).reset_index()
        for _, _r in _agg.iterrows():
            _nm = str(_r["_item"])
            if _nm not in _prod_h1:
                _prod_h1[_nm] = {}
            _prod_h1[_nm][_pk] = {
                "rev": round(float(_r["rev"]) / 1e4, 1),
                "profit": round(float(_r["profit"]) / 1e4, 1),
                "cost": round(float(_r["cost"]) / 1e4, 1),
                "qty": round(float(_r["qty"]) / 1e4, 2),
                "mg": round(float(_r["profit"]) / float(_r["rev"]) * 100, 1) if float(_r["rev"]) > 0 else 0,
            }

    # 近12月收入>10万的主要产品
    _near12 = rex[rex["_d"] >= pd.Timestamp(latest) - pd.DateOffset(months=11)]
    _near12_rev = _near12.groupby("_item")["_rev"].sum()
    _major_items = set(_near12_rev[_near12_rev > 100000].index)

    # 首次出现日期 + 新品标记
    _first_dates = rex.groupby("_item")["_d"].min()
    _is_new_tag = rex.groupby("_item")["_is_new"].any()

    # Gold画像映射
    _portrait_map = {}
    if "产品名称" in prod_df.columns and "当前画像" in prod_df.columns:
        _portrait_map = dict(zip(prod_df["产品名称"].astype(str), prod_df["当前画像"].astype(str)))
    _risk_map = {}
    if "产品名称" in prod_df.columns and "综合风险等级" in prod_df.columns:
        _risk_map = dict(zip(prod_df["产品名称"].astype(str), prod_df["综合风险等级"].astype(str)))

    # 月度趋势数据（24个月，起始月动态）
    _all_months = sorted(rex["_ym"].unique())
    _trend_months = [m for m in _all_months if m >= _trend_months_start][-24:]
    _prod_trend = {}
    for _item in _major_items:
        _td = _REX_BY_ITEM[_item]  # [批次⑤ P1] 预分组，等价于 rex[rex["_item"] == _item]
        _monthly = _td.groupby("_ym").agg(r=("_rev", "sum"), p=("_profit", "sum"), c=("_rev", lambda x: float(x.sum()) - float(_td.loc[x.index, "_profit"].sum())), q=("_qty", "sum")).reindex(_trend_months, fill_value=0)
        _prod_trend[_item] = {
            "months": _trend_months,
            "rev": [round(float(v) / 1e4, 2) for v in _monthly["r"]],
            "profit": [round(float(v) / 1e4, 2) for v in _monthly["p"]],
            "cost": [round(float(v) / 1e4, 2) for v in _monthly["c"]],
            "asp": [round(float(_monthly["r"].iloc[i]) / float(_monthly["q"].iloc[i]), 4) if float(_monthly["q"].iloc[i]) > 0 else 0 for i in range(len(_trend_months))],
        }

    # 展示层截断：ASP 轴边界（F面产品月度ASP趋势；从 fingerprinted 的 rex 数据派生，可入缓存）
    _asp_bounds = _asp_axis_bounds(_prod_trend)
    print(f"  [截断] ASP轴: raw[{_asp_bounds['raw_abs_min']:.2f}, {_asp_bounds['raw_abs_max']:.2f}] "
          f"-> p{DASHBOARD_AXIS_CLIP.get('asp_pct', [1,99])[0]}~p{DASHBOARD_AXIS_CLIP.get('asp_pct', [1,99])[1]}[{_asp_bounds['min']}, {_asp_bounds['max']}]")
    _asp_axis_cache = {"min": _asp_bounds["raw_min"], "max": _asp_bounds["raw_max"]}

    # Top5客户
    _prod_top5 = {}
    for _item in _major_items:
        _td = _REX_BY_ITEM[_item]  # [批次⑤ P1] 预分组，等价于 rex[rex["_item"] == _item]
        _cust_agg = _td.groupby("_cust")["_rev"].sum().sort_values(ascending=False).head(5)
        _prod_top5[_item] = [{"name": k, "rev": round(float(v) / 1e4, 1)} for k, v in _cust_agg.items()]

    # 构建产品列表
    f_product_list = []
    for _item in sorted(_major_items, key=lambda x: (-(_prod_h1.get(x, {}).get(f"{_yy_latest}h1", {}).get("rev", 0)), str(x))):
        _d = _prod_h1.get(_item, {})
        _fd = _first_dates.get(_item, pd.Timestamp(f"{_y0}-01-01"))
        _days_since = (pd.Timestamp(latest) - _fd).days
        _is_new = _is_new_tag.get(_item, False)
        # 新品代次
        if _is_new and _days_since <= 365:
            _gen = "新品"
        elif _days_since <= 365:
            _gen = "1年+"
        elif str(_item).endswith("Q1") or _days_since <= 730:
            _gen = "2年+"
        else:
            _gen = ""
        f_product_list.append({
            "name": _item,
            "portrait": _portrait_map.get(_item, ""),
            "risk": _risk_map.get(_item, ""),
            "gen": _gen,
            "is_new": bool(_is_new and _days_since <= 365),
            "first_date": _fd.strftime("%Y-%m-%d") if hasattr(_fd, 'strftime') else str(_fd)[:10],
            "top_cust": _prod_top5.get(_item, [{}])[0].get("name", "") if _prod_top5.get(_item) else "",
            f"h1_{_yy_prev}": _d.get(f"{_yy_prev}h1", {"rev": 0, "profit": 0, "mg": 0}),
            f"h2_{_yy_prev}": _d.get(f"{_yy_prev}h2", {"rev": 0, "profit": 0, "mg": 0}),
            f"h1_{_yy_latest}": _d.get(f"{_yy_latest}h1", {"rev": 0, "profit": 0, "mg": 0}),
            "trend": _prod_trend.get(_item, {}),
            "top5": _prod_top5.get(_item, []),
        })

    print(f"  主要产品(近12月>10万): {len(f_product_list)}个")

    # ---- 8h. F面品类维度H1对比 ----
    print("  品类维度H1对比...")
    # 先给产品列表补充品类字段（品类统计需要）
    _cat_map = {}
    for _item_name in _major_items:
        _tg = _REX_BY_ITEM.get(_item_name)  # [批次⑤ P1] 预分组，等价于 rex[rex["_item"] == _item_name]
        _cat_val = _tg["_cat"].iloc[0] if _tg is not None and len(_tg) > 0 else ""
        _cat_map[_item_name] = str(_cat_val)
    for p in f_product_list:
        p["cat"] = _cat_map.get(p["name"], "")

    f_cat_h1 = []
    for _cat_name in sorted(h1_data["_cat"].dropna().unique()):
        if _cat_name in ("nan", "None", ""):
            continue
        # 按品类聚合半年数据
        _cat_data = {}
        for _pk, (_ps, _pe) in _h1_periods.items():
            _cd = rex[(rex["_d"] >= _ps) & (rex["_d"] <= _pe) & (rex["_cat"] == _cat_name)]
            _r = float(_cd["_rev"].sum()); _p = float(_cd["_profit"].sum())
            if _r < 10000 and _pk == f"{_yy_latest}h1":
                continue
            _cat_data[_pk] = {"rev": round(_r / 1e4, 1), "profit": round(_p / 1e4, 1), "mg": round(_p / _r * 100, 1) if _r > 0 else 0}
        if not _cat_data.get(f"{_yy_latest}h1"):
            continue
        _r25h1 = _cat_data.get(f"{_yy_prev}h1", {}).get("rev", 0)
        _r25h2 = _cat_data.get(f"{_yy_prev}h2", {}).get("rev", 0)
        _r26h1 = _cat_data.get(f"{_yy_latest}h1", {}).get("rev", 0)
        _mg25h1 = _cat_data.get(f"{_yy_prev}h1", {}).get("mg", 0)
        _mg25h2 = _cat_data.get(f"{_yy_prev}h2", {}).get("mg", 0)
        _mg26h1 = _cat_data.get(f"{_yy_latest}h1", {}).get("mg", 0)
        f_cat_h1.append({
            "name": _cat_name,
            f"rev_{_yy_latest}h1": _r26h1, f"mg_{_yy_latest}h1": _mg26h1,
            f"rev_{_yy_prev}h1": _r25h1, f"mg_{_yy_prev}h1": _mg25h1,
            f"rev_{_yy_prev}h2": _r25h2, f"mg_{_yy_prev}h2": _mg25h2,
            "rev_yoy": round((_r26h1 - _r25h1) / _r25h1 * 100, 1) if _r25h1 > 0 else 0,
            "rev_mom": round((_r26h1 - _r25h2) / _r25h2 * 100, 1) if _r25h2 > 0 else 0,
            "mg_yoy": round(_mg26h1 - _mg25h1, 1),
            "mg_mom": round(_mg26h1 - _mg25h2, 1),
            "prod_count": len([p for p in f_product_list if p.get("cat") == _cat_name]),
        })
    f_cat_h1.sort(key=lambda x: -x[f"rev_{_yy_latest}h1"])

    print(f"  品类: {len(f_cat_h1)}个")

else:
    f_h1_kpi = {}; h1_pline_margins = []; h1_cat_margins = []; h1_dept_margins = []
    h1_kaaa_margins = []; np_analysis = {}; np_summary = {}; h1_issues = []
    h1_cat_attribution = {}; f_product_list = []; f_cat_h1 = {}
    _asp_bounds = {"min": "0", "max": "0"}  # ASP 轴边界只服务 F 面图表；F 隐藏时无人消费（须为 str，replace 不接受 float）
    _asp_axis_cache = {"min": 0.0, "max": 0.0}  # 缓存写入处引用（原始浮点）；F 跳过时给空，否则 NameError 静默阻断缓存重盖戳
    print("  [F面] 平时关闭（visible=false），跳过 H1 计算。半年度复盘期在 dashboard\\faces.yaml 改 visible=true")

# ========== 保存 JSON ==========
with open(os.path.join(DATA_DIR,"b_custs.json"),"w",encoding="utf-8") as f: json.dump(call,f,ensure_ascii=False)
with open(os.path.join(DATA_DIR,"b_trend.json"),"w",encoding="utf-8") as f: json.dump(ctr,f,ensure_ascii=False)
with open(os.path.join(DATA_DIR,"b_data.js"),"w",encoding="utf-8") as f:
    f.write("var B_CUSTS="+json.dumps(call,ensure_ascii=False)+";\nvar B_TREND="+json.dumps(ctr,ensure_ascii=False)+";\n")

# ========== JS数据 ==========
js_data = []
js_data.append("var TREND = "+json.dumps(trend,ensure_ascii=False)+";")
js_data.append("var SA = "+json.dumps(csa,ensure_ascii=False)+";")
js_data.append("var PIE = "+json.dumps(pie,ensure_ascii=False)+";")
js_data.append("var SCAT = "+json.dumps(scat,ensure_ascii=False)+";")
js_data.append("var KAA_REV = "+json.dumps(kaa_rev,ensure_ascii=False)+";")
js_data.append("var PLINE_MARGINS = "+json.dumps(pline_margins,ensure_ascii=False)+";")
js_data.append("var CAT_MARGINS = "+json.dumps(cat_margins,ensure_ascii=False)+";")
js_data.append("var TREND_TIERS = "+json.dumps(trend_tiers,ensure_ascii=False)+";")
js_data.append("var PROD_CHANGE = "+json.dumps(product_change_detail,ensure_ascii=False)+";")
js_data.append("var PROD_LIST = "+json.dumps([],ensure_ascii=False)+";")
js_data.append("var B_CUSTS = "+json.dumps(call,ensure_ascii=False)+";")
js_data.append("var B_TREND = "+json.dumps(ctr,ensure_ascii=False)+";")
js_data.append("var D_SALES_LIST = "+json.dumps(d_sales_list,ensure_ascii=False)+";")
js_data.append("var D_SALES_TREND = "+json.dumps(sales_trend_map,ensure_ascii=False)+";")
js_data.append("var D_KPI = "+json.dumps(d_kpi,ensure_ascii=False)+";")
js_data.append("var D_HEATMAP = "+json.dumps(d_heatmap,ensure_ascii=False)+";")
js_data.append("var D_CUST_HEATMAP = "+json.dumps(d_cust_heatmap,ensure_ascii=False)+";")
js_data.append("var D_WATERFALL = "+json.dumps(d_waterfall,ensure_ascii=False)+";")
js_data.append("var D_TEAM_PROFILE = "+json.dumps(D_TEAM_PROFILE,ensure_ascii=False)+";")
js_data.append("var E_MONTHLY_KPI = "+json.dumps(e_monthly_kpi,ensure_ascii=False)+";")
js_data.append("var E_CUST_MONTHLY = "+json.dumps(e_cust_monthly,ensure_ascii=False)+";")
js_data.append("var E_FIRST_IMPORT = "+json.dumps(first_imports,ensure_ascii=False)+";")
js_data.append("var E_SALES_MONTHLY = "+json.dumps(e_sales_monthly,ensure_ascii=False)+";")
js_data.append("var E_CUST_TIER = "+json.dumps(e_cust_tier,ensure_ascii=False)+";")
js_data.append("var E_IMPORT_SUMMARY = "+json.dumps(e_import_summary,ensure_ascii=False)+";")
js_data.append("var E_DECOMP = "+json.dumps(e_decomp,ensure_ascii=False)+";")
js_data.append("var F_H1_KPI = "+json.dumps(f_h1_kpi,ensure_ascii=False)+";")
js_data.append("var F_PLINE_MARGINS = "+json.dumps(h1_pline_margins,ensure_ascii=False)+";")
js_data.append("var F_CAT_MARGINS = "+json.dumps(h1_cat_margins,ensure_ascii=False)+";")
js_data.append("var F_DEPT_MARGINS = "+json.dumps(h1_dept_margins,ensure_ascii=False)+";")
js_data.append("var F_KAAA_MARGINS = "+json.dumps(h1_kaaa_margins,ensure_ascii=False)+";")
js_data.append("var F_NP_ANALYSIS = "+json.dumps(np_analysis,ensure_ascii=False)+";")
js_data.append("var F_NP_SUMMARY = "+json.dumps(np_summary,ensure_ascii=False)+";")
js_data.append("var F_ISSUES = "+json.dumps(h1_issues,ensure_ascii=False)+";")
js_data.append("var F_CAT_ATTRIBUTION = "+json.dumps(h1_cat_attribution,ensure_ascii=False)+";")
js_data.append("var F_PRODUCT_LIST = "+json.dumps(f_product_list,ensure_ascii=False)+";")
js_data.append("var F_CAT_H1 = "+json.dumps(f_cat_h1,ensure_ascii=False)+";")
js_data.append("var D_DEPT_LIST = "+json.dumps(dept_list,ensure_ascii=False)+";")
data_block = "// ===== DATA LAYER =====\n" + "\n".join(js_data)

# C面数据
prod_stage = prod_df["当前画像"].value_counts().to_dict()
prod_risk = prod_df["综合风险等级"].value_counts().to_dict() if "综合风险等级" in prod_df.columns else {}
prod_gm = round(float(prod_df["近12月毛利率%"].mean()),1) if "近12月毛利率%" in prod_df.columns else 0
prod_growth = round(float(prod_df["近12月增长率%"].mean()),1) if "近12月增长率%" in prod_df.columns else 0
prod_high_risk = int((prod_df["综合风险等级"]=="高风险").sum()) if "综合风险等级" in prod_df.columns else 0
prod_list = []
for _,r in prod_df.iterrows():
    prod_list.append({"n":str(r.get("产品名称","")),"stage":str(r.get("当前画像","")),"risk":str(r.get("综合风险等级","")),
        "gm":j(r.get("近12月毛利率%",0)),"growth":j(r.get("近12月增长率%",0)),
        "rev":round(j(r.get("近12月收入",0))/1e4,1),"asp":j(r.get("ASP趋势%/月",0)),
        "ref_group":str(r.get("所属参照组","")),"summary":str(r.get("画像摘要",""))[:40]})
cat_data = rex.groupby("_cat").agg(cat_rev=("_rev","sum"),cat_count=("_prod","nunique")).reset_index().sort_values("cat_rev",ascending=False)
cat_list=[{"n":str(r["_cat"]),"rev":round(float(r["cat_rev"])/1e4,1),"count":int(r["cat_count"])} for _,r in cat_data.iterrows()]

# ========== C面集成（统一数据源版本 - 内联模式） ==========
# V10: C面DATA直接注入到模板中，不再使用iframe
# template.html中已包含TABS框架+C面渲染JS，只需注入DATA对象
print("[C面] 统一数据源集成模式（内联）")
import pathlib

# 构建C面DATA对象：优先用产品生命周期报告（快照+历史+月份，内部自洽，与GOOD一致）；
# 报告缺失时回退 gold_product_portrait.csv（无历史/桑基/月份）
_snap_df, _hist_df, _data_month, _insuff = load_product_report()
_c_src = _snap_df if _snap_df is not None else prod_df
c_data = build_c_data(_c_src, hist_df=_hist_df, data_month=_data_month, insuff_count=_insuff)
c_data_json = json.dumps(c_data, ensure_ascii=False, separators=(",", ":"))
print(f"  C_DATA JSON大小: {len(c_data_json):,} 字符")

# 展示层截断：毛利率轴边界（始终由当前 C面 scatter 现算，保证缓存/全算两路径一致）
_margin_bounds = _margin_axis_bounds(c_data)
print(f"  [截断] 毛利率轴: raw[{_margin_bounds['raw_abs_min']:.2f}, {_margin_bounds['raw_abs_max']:.2f}] "
      f"-> p{DASHBOARD_AXIS_CLIP.get('margin_pct', [1,99])[0]}~p{DASHBOARD_AXIS_CLIP.get('margin_pct', [1,99])[1]}[{_margin_bounds['min']}, {_margin_bounds['max']}]")

# ========== R面（风险与行动 · W4 并入）：读取人工审定总体文档 ==========
# 内容来自 dashboard\risk_action_YYYYMM.md（跑批生成初稿 → 人工审定 → 本处渲染）。
# 该 md 已纳入指纹（fingerprint.py risk_doc 键），审定编辑后缓存自动失效。
try:
    import generate_risk_face as _rface
    r_face_html = _rface.build_r_face_inner_html(latest.replace("-", ""))
    print(f"[R面] 风险与行动内容已并入（数据月份 {latest}）")
except Exception as _e:
    r_face_html = ('<div class="cb"><h3>风险与行动</h3><div class="note">'
                   '总体文档读取失败，请先运行 python dashboard\\generate_risk_face.py'
                   f'（{type(_e).__name__}: {_e}）</div></div>')
    print(f"  [R面] 读取失败: {_e}")

# ========== W4：三层口径说明体系（faces.yaml → HTML 占位符） ==========
def _build_face_meta_html(face_id, cfg):
    """根据 faces.yaml 配置生成面级口径条 HTML（默认收起）。"""
    if not cfg:
        return ""
    theme = cfg.get("theme", "")
    desc = cfg.get("description", "")
    sections = cfg.get("sections", []) or []
    parts = []
    parts.append(f'<div class="face-meta" id="faceMeta{face_id}">')
    parts.append(f'  <div class="face-meta-summary" id="faceMetaSummary{face_id}" onclick="TABS.toggleFaceMeta(\'{face_id}\')">')
    parts.append(f'    <i class="fa-solid fa-circle-info"></i> 本面口径与用法')
    parts.append('  </div>')
    parts.append(f'  <div class="face-meta-body" id="faceMetaBody{face_id}" style="display:none">')
    if theme:
        parts.append(f'    <div class="face-meta-theme"><strong>主题：</strong>{theme}</div>')
    if desc:
        parts.append(f'    <div class="face-meta-desc">{desc}</div>')
    if sections:
        parts.append('    <div class="face-meta-sections">')
        for sec in sections:
            title = sec.get("title", "")
            definition = sec.get("definition", "")
            koujing = sec.get("koujing", "")
            usage = sec.get("usage", "")
            update_note = sec.get("update_note", "")
            if not any((definition, koujing, usage, update_note)):
                continue
            parts.append('      <div class="face-meta-section">')
            if title:
                parts.append(f'        <div class="face-meta-title">{title}</div>')
            if definition:
                parts.append(f'        <div class="face-meta-row"><span>定义：</span>{definition}</div>')
            if koujing:
                parts.append(f'        <div class="face-meta-row"><span>口径：</span>{koujing}</div>')
            if usage:
                parts.append(f'        <div class="face-meta-row"><span>用法：</span>{usage}</div>')
            if update_note:
                parts.append(f'        <div class="face-meta-row"><span>更新：</span>{update_note}</div>')
            parts.append('      </div>')
        parts.append('    </div>')
    glossary = cfg.get("glossary", []) or []
    if glossary:
        parts.append('    <div class="face-meta-sections">')
        parts.append('      <div class="face-meta-title">术语表</div>')
        for item in glossary:
            term = item.get("term", "")
            definition = item.get("definition", "")
            if not term:
                continue
            parts.append(f'      <div class="face-meta-row"><span>{term}：</span>{definition}</div>')
        parts.append('    </div>')
        parts.append('  </div>')
    parts.append('</div>')
    return "\n".join(parts)


def _build_guide_replacements(face_id, cfg):
    """生成图表级导读占位符，未配置的图表返回空字符串。"""
    reps = {}
    guides = (cfg or {}).get("chart_guides", {}) or {}
    for chart_id, guide in guides.items():
        reps[f"%%GUIDE_{face_id}_{chart_id}%%"] = guide or ""
    return reps


# 确保 faces.yaml 已加载
_face_visible("A")
_FACE_META_CACHE = {fid: _FACES_CFG.get(fid, {}) for fid in ("A", "B", "C", "D", "E", "F")}

# ========== HTML ==========
_timed("F面H1汇总+C面DATA构建", _t_seg0); _t_seg0 = _time_mod.time()
print("[HTML] 生成...")
import pathlib
template_path = pathlib.Path(__file__).parent / "template.html"
template = template_path.read_text(encoding="utf-8")

replacements = {
    "%%KPI_R%%":f"{kpi_r:,.0f}","%%KPI_P%%":f"{kpi_p:,.0f}","%%KPI_C%%":f"{kpi_c:,.0f}",
    "%%KPI_MG%%":str(kpi_mg),"%%KPI_RY%%":f"{kpi_ry:+.1f}","%%KPI_PY%%":f"{kpi_py:+.1f}",
    "%%KPI_MG_YOY%%":f"{kpi_mg_yoy:+.1f}","%%KPI_SR%%":f"{kpi_sr:,.0f}","%%KPI_SP%%":f"{kpi_sp:,.0f}",
    "%%KPI_SM%%":str(kpi_sm),"%%KPI_SPT%%":str(kpi_spt),"%%KPI_SC%%":str(kpi_sc),
    "%%KPCT%%":str(kpct),"%%LATEST%%":latest,"%%YTD_PERIOD%%":f"{_latest_y}-01~{latest[-2:]}","%%D_HEADCOUNT%%":str(len(d_sales_list)),"%%KA_REV%%":f"{ka_kpi['rev']:,.0f}",
    "%%KA_PROFIT%%":f"{ka_kpi['profit']:,.0f}","%%KA_QTY%%":f"{ka_kpi['qty']:,.0f}",
    "%%KA_MARGIN%%":str(ka_kpi['margin']),"%%NEW_PCT%%":str(new_pct),
    "%%NEW_PCT_PURE%%":str(new_flag_pct),
    "%%KA_REV_MOM%%":f"{ka_kpi['rev_mom']:+.1f}","%%KA_PROFIT_MOM%%":f"{ka_kpi['profit_mom']:+.1f}",
    "%%KA_ADDED%%":str(ka_kpi['added']),"%%KA_REMOVED%%":str(ka_kpi['removed']),
    "%%AA_ADDED%%":str(aa_added),"%%AA_REMOVED%%":str(aa_removed),

    "%%AA_REV%%":f"{aa_kpi['rev']:,.0f}","%%AA_PROFIT%%":f"{aa_kpi['profit']:,.0f}",
    "%%AA_QTY%%":f"{aa_kpi['qty']:,.0f}","%%AA_MARGIN%%":str(aa_kpi['margin']),
    "%%AA_REV_MOM%%":f"{aa_kpi['rev_mom']:+.1f}","%%AA_ASP%%":f"{aa_kpi['asp']:.4f}",
    "%%AA_ASP_MOM%%":f"{aa_kpi['asp_mom']:+.1f}",
    "%%KA_ASP%%":f"{ka_kpi['asp']:.4f}","%%KA_ASP_MOM%%":f"{ka_kpi['asp_mom']:+.1f}",
    "%%ASP%%":f"{asp_ytd:.4f}","%%ASP_YOY%%":f"{asp_yoy:+.1f}","%%ASP_MOM%%":f"{asp_mom:+.1f}",
    "%%DATA_BLOCK%%":data_block,
    "%%C_DATA_JSON%%":c_data_json,
    # ---- 年份/周期动态化占位符（批次②：由 _latest_period 推导，当前数据下与硬编码完全一致）----
    "%%DATA_AS_OF%%":latest,                                  # 2026-06
    "%%YTD_START_END%%":f"{_latest_y}-01-01 ~ {latest}",      # 2026-01-01 ~ 2026-06
    "%%YTD_SHORT%%":f"{_latest_y}-01~{latest[-2:]}",          # 2026-01~06
    "%%LATEST_YEAR%%":str(_latest_y),                         # 2026
    "%%PREV_YEAR%%":str(_latest_y-1),                         # 2025
    "%%Y0%%":str(_y0),"%%Y1%%":str(_y1),"%%Y2%%":str(_y2),    # 2024/2025/2026
    "%%YY_LATEST%%":str(_yy_latest),                           # 26（F面 JSON key 用 2 位年份）
    "%%YY_PREV%%":str(_yy_prev),                               # 25（F面 JSON key 用 2 位年份）
    "%%YY_Y0%%":str(_y0 % 100),                                # 24（趋势图 JSON key 用 2 位年份）
    "%%YY_Y1%%":str(_y1 % 100),                                # 25
    "%%YY_Y2%%":str(_y2 % 100),                                # 26
    # 与基线一致：E_SEL_MONTHS 用单引号字面量（golden_diff 的 JSON 解析器不识别单引号，
    # 基线同样不收录该变量；若用 json.dumps 双引号会在对拍中出现"新增变量"假漂移）
    "%%E_SEL_MONTHS_JSON%%":"['" + latest + "']",              # ['2026-06']
    # ---- 批次③ D-1：展示层分位截断轴边界（内嵌 JSON 数据不变，仅可视范围截断）----
    "%%MARGIN_AXIS_MIN%%":_margin_bounds["min"],
    "%%MARGIN_AXIS_MAX%%":_margin_bounds["max"],
    "%%ASP_AXIS_MIN%%":_asp_bounds["min"],
    "%%ASP_AXIS_MAX%%":_asp_bounds["max"],
    # ---- W4：风险与行动面（人工审定总体文档渲染，服务端 HTML 注入）----
    "%%R_FACE_HTML%%": r_face_html,
    # ---- W4：面级口径条（A/B/C/D/E，R 面已有自己的口径节）----
    "%%FACE_META_A%%": _build_face_meta_html("A", _FACE_META_CACHE.get("A", {})),
    "%%FACE_META_B%%": _build_face_meta_html("B", _FACE_META_CACHE.get("B", {})),
    "%%FACE_META_C%%": _build_face_meta_html("C", _FACE_META_CACHE.get("C", {})),
    "%%FACE_META_D%%": _build_face_meta_html("D", _FACE_META_CACHE.get("D", {})),
    "%%FACE_META_E%%": _build_face_meta_html("E", _FACE_META_CACHE.get("E", {})),
    "%%FACE_META_F%%": _build_face_meta_html("F", _FACE_META_CACHE.get("F", {})),
}

# 图表级导读占位符
for _fid in ("A", "B", "C", "D", "E"):
    replacements.update(_build_guide_replacements(_fid, _FACE_META_CACHE.get(_fid, {})))

html = template
for k,v in replacements.items():
    html = html.replace(k,v)
html = _hide_invisible_faces(html)

with open(OUT,"w",encoding="utf-8") as f: f.write(html)
sz=os.path.getsize(OUT)/(1024*1024)
print(f"\n[OK] {OUT} {sz:.1f}MB | YTD:{kpi_r/10000:.1f}亿 毛利率:{kpi_mg}%")

# ========== 审计 ==========
print("\n[审计] 数据检查...")
# 批次②修复：旧检查项检测的是 V9/V10 之前 HTML 里的字面量 `ytd_rev=...万`（早已不存在，恒 FAIL）。
# 改为真实校验：直接比较生成时的 ytd_rev 数值变量（raw 口径 ytd_r）与 Silver 侧口径
# （silver_cleaned_rows.csv 的 YTD 金额合计），相对容差 1e-6。
try:
    _sd_audit = pd.to_datetime(raw_rows["发货日期"], errors="coerce")
    _sr_audit = pd.to_numeric(raw_rows["金额"], errors="coerce").fillna(0)
    _silver_ytd_rev = float(_sr_audit[(_sd_audit >= ytd_start) & (_sd_audit <= ytd_end)].sum())
    _rel_diff = abs(ytd_r - _silver_ytd_rev) / max(abs(ytd_r), abs(_silver_ytd_rev), 1e-9)
    raw_silver_ok = _rel_diff <= 1e-6
    print(f"  [Raw=Silver] raw YTD={ytd_r:.2f}  silver YTD={_silver_ytd_rev:.2f}  相对差={_rel_diff:.2e}")
except Exception as _e:
    raw_silver_ok = None
    print(f"  [Raw=Silver] 无法校验: {_e}")

checks = [
    ("KPI占位符","%%KPI_R%%" not in html),
    ("TREND数据","var TREND = {" in html),
    ("SA列表","var SA = [" in html),
    ("PIE饼图","var PIE = [" in html),
    ("SCAT散点","var SCAT = [" in html),
    ("B_CUSTS","var B_CUSTS = [" in html),
    ("C面DATA","const DATA = {" in html and "TABS" in html),
]
if raw_silver_ok is not None:
    checks.append(("Raw=Silver验证", raw_silver_ok))
all_ok = True
for name,ok in checks:
    s="OK" if ok else "FAIL"
    if not ok: all_ok=False
    print(f"  [{s}] {name}")

# 关键数据一致性
print(f"\n[数据一致性]")
print(f"  Raw YTD: rev={ytd_r/1e4:.1f}万 profit={ytd_p/1e4:.1f}万 mg={ytd_p/ytd_r*100:.2f}%")
print(f"  KPI: rev={kpi_r}万 profit={kpi_p}万 mg={kpi_mg}%")
print(f"  KA YTD: rev={ka_rev_ytd/1e4:.1f}万 profit={ka_profit_ytd/1e4:.1f}万")
print(f"  SA客户: {len(csa)}个 B面客户: {len(call)}个 趋势: {len(ctr)}个 品类: {len(cid_12m_data)}个")
print(f"{'全部通过' if all_ok else '有检查失败'}")

# ========== 批次③ 车道D：写 preagg.json 缓存 ==========
_timed("HTML渲染+审计", _t_seg0)
print(f"\n[缓存] 全算路径总耗时: {_time_mod.time() - _PROG_START:.1f}s")
if not _NO_CACHE and _fp is not None and _fp_cur is not None:
    try:
        os.makedirs(PREAGG_DIR, exist_ok=True)
        _cache_payload = {
            "data_block": data_block,
            # 缓存除 DATA_BLOCK / C_DATA_JSON / 毛利率轴（现算）/ R面HTML（现算，审定 md 毫秒级解析）外的全部占位符值
            "replacements": {k: v for k, v in replacements.items()
                             if k not in ("%%DATA_BLOCK%%", "%%C_DATA_JSON%%",
                                          "%%MARGIN_AXIS_MIN%%", "%%MARGIN_AXIS_MAX%%",
                                          "%%R_FACE_HTML%%")},
            # ASP 轴边界源自 fingerprinted 的 rex 数据，缓存原始浮点值
            "asp_axis": _asp_axis_cache,
        }
        _cache_obj = {"fingerprint": _fp_cur, "payload": _cache_payload}
        with open(PREAGG_PATH, "w", encoding="utf-8") as _f:
            json.dump(_cache_obj, _f, ensure_ascii=False)
        print(f"  [缓存] 已写入 {PREAGG_PATH}")
    except Exception as _e:
        print(f"  [缓存] 写入失败: {_e}")
else:
    if _NO_CACHE:
        print("  [缓存] 已通过 --no-cache 跳过（不读不写）")
    elif _fp is None:
        print("  [缓存] fingerprint 模块不可用，跳过缓存")
