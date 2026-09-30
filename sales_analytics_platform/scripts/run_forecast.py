#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
预测流水线生产入口 · 月度滚动预测（run_forecast.py）
=====================================================================
职责：读平台银层 silver_cleaned_rows.parquet → 滚动生成月度预测交付 CSV，
供 generate_dashboard.py 的「月度滚动预测」面（tabP）消费。

数据源：
  - output/silver/silver_cleaned_rows.parquet        （平台银层，run_chain 每月产出）
  - data_warehouse/**/zongbiao_frozen*.parquet       （冻结历史总表，长序列拼接用）
  - OUT/E12b_量价集成_对比.csv                       （区间比率池，静态标定产物）
  - OUT/R3_方向准确率_公司口径.csv                   （方向准确率回算，静态标定产物）

产出（与历史交付保持一致，位置不变）：
  OUT = E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910\
  - 交付_公司分月.csv        月,预测,规则,无偏
  - 交付_产品线.csv          行=产品线，列=选优方法+未来12个月（已锚定公司口径）
  - 交付_品类.csv            行=品类（Top15+其他），同上
  - 看板数据_线级置信分层.csv  产品线,实际合计万,金额占比%,WAPE%,置信档（近20月窗口）
  - 公司月度长序列80月.csv / 线级月度长序列80月.csv（data_warehouse 同步副本）

滚动化规则（方法与 2026-09-10 交付版等价，仅日期相对化）：
  - 未来 12 个月 = silver 最新完整月 + 1 起
  - 春节月（正月初一所在月）= 低谷月：预测 = 前月 × 0.53（E22c 低谷桶中位）
  - 春节前一月 = 冲量月：三法中枢 A(相位YoY)/B(近6月均×1.17)/C(两年同月 CAGR³) 取中位；
    基准年数据缺失时退化为 A/B 双法中枢
  - 其余月 = ma6（近6月均值，递归）
  - 无偏口径 = 基准 × 1.040（E20 中位因子）
  - 线/品类 = 8 方法近20月回测选优 + 递归外推 + 锚定公司口径
  - 回测/置信分层窗口 = 最近 20 个月

用法：
  python scripts/run_forecast.py             # 生成全部交付 CSV
  python scripts/run_forecast.py --verify    # 生成后与既有 交付_公司分月.csv 对拍（等价性验收）

等价性说明：用 2026-08 截止的 silver 运行，本脚本输出应与
《预测交付_2026收官与6-12个月_20260910》的交付 CSV 在 月/预测/无偏 三列上逐值一致
（规则列 tag 文案已通用化，不参与对拍）。
"""
import argparse
import glob
import io
import json
import os
import sys
import time

import numpy as np
import pandas as pd

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer,
                                  encoding=sys.stdout.encoding or "utf-8",
                                  errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer,
                                  encoding=sys.stderr.encoding or "utf-8",
                                  errors="replace")
except (AttributeError, OSError, ValueError):
    pass

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/ 的上级 = 包根
SILVER = os.path.join(PKG, "output", "silver", "silver_cleaned_rows.parquet")

# 交付目录：与历史交付保持一致（用户拍板）。目录缺失时回退平台内并告警（可移植性兜底）。
OUT_PRIMARY = r"E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910"
OUT_FALLBACK = os.path.join(PKG, "output", "forecast")

LINE_COL = "型号_产品线（新）"
CAT_COL = "型号_产品品类"
F_UNBIAS = 1.040            # E20 无偏中位因子
CNY_LOW_RATIO = 0.53        # E22c 春节低谷桶中位
CNY_SURGE_K = 1.17          # E22c 节前冲量系数（B 法）
TOPN_CAT = 15               # 品类展示 Top N
GRADE_A_MAX = 15.0          # 置信分档：A ≤15% / B 15~25% / C >25%
GRADE_B_MAX = 25.0

# 春节所在月（正月初一所落月份）。来源：build_long_series.py 春节表 + 公历万年历。
CNY_MONTHS = {
    "2020": "2020-01", "2021": "2021-02", "2022": "2022-02", "2023": "2023-01",
    "2024": "2024-02", "2025": "2025-01", "2026": "2026-02", "2027": "2027-02",
    "2028": "2028-01", "2029": "2029-02", "2030": "2030-02",
}

METHODS = ["naive", "ma3", "ma6", "ma12", "snaive", "yoy_adj", "trend6", "trend12"]


# ---------------------------------------------------------------- 基础工具
def predict_one(v, method):
    n = len(v)
    if method == "naive":
        return float(v[-1])
    if method.startswith("ma"):
        k = int(method[2:])
        return float(v[-k:].mean()) if n >= k else float(v.mean())
    if method == "snaive":
        return float(v[-12]) if n >= 12 else float(v.mean())
    if method == "yoy_adj":
        base = float(v[-12]) if n >= 12 else float(v.mean())
        den = float(v[-24:-12].sum())
        g = (float(v[-12:].sum()) / den) if (n >= 24 and den > 1e5) else 1.0
        return base * g
    if method.startswith("trend"):
        k = int(method[5:])
        y = np.asarray(v[-k:], dtype=float)
        x = np.arange(len(y))
        if len(y) >= 3 and y.std() > 0:
            sl, ic = np.polyfit(x, y, 1)
            return max(0.0, float(ic + sl * len(y)))
        return float(y.mean())
    raise ValueError(method)


def forecast_steps(hist, method, steps):
    h = list(hist)
    out = []
    for _ in range(steps):
        p = predict_one(np.array(h), method)
        out.append(p)
        h.append(p)
    return out


def wape_series(v, method, targets, months_all):
    errs = acts = 0.0
    for t in targets:
        i = months_all.index(t)
        if i < 12:
            continue
        p = predict_one(v[:i], method)
        errs += abs(p - v[i])
        acts += v[i]
    return errs / acts if acts > 0 else np.inf


def select_method(v, targets, months_all):
    scores = {m: wape_series(v, m, targets, months_all) for m in METHODS}
    return min(scores, key=lambda m: (scores[m], METHODS.index(m)))


def month_add(ym, k=1):
    y, m = int(ym[:4]), int(ym[5:7])
    tot = y * 12 + (m - 1) + k
    return "%04d-%02d" % (tot // 12, tot % 12 + 1)


def cny_month_of(ym):
    """该月是否为春节月；返回 (is_cny, is_pre_cny)"""
    y = ym[:4]
    cny = CNY_MONTHS.get(y)
    nxt = CNY_MONTHS.get(month_add(ym, 1)[:4])
    is_cny = (cny == ym)
    is_pre = (nxt == month_add(ym, 1))
    return is_cny, is_pre


# ---------------------------------------------------------------- 主流程
def load_silver():
    if not os.path.exists(SILVER):
        print("[错误] 未找到银层 %s —— 请先运行数据处理（run_chain 步骤1）。" % SILVER)
        sys.exit(1)
    df = pd.read_parquet(SILVER, columns=["发货日期", LINE_COL, "金额", CAT_COL, "客户编号", "新品标记"])
    df["月"] = pd.to_datetime(df["发货日期"], errors="coerce").dt.strftime("%Y-%m")
    df = df.dropna(subset=["月"])
    df = df[df[LINE_COL].astype(str).str.strip() != ""]
    df["金额"] = pd.to_numeric(df["金额"], errors="coerce").fillna(0.0)
    return df


def company_forecast(ts, months_all):
    """公司口径：滚动未来 12 个月。返回 DataFrame(月,预测,规则)。"""
    hist = list(ts.values.astype(float))
    hist_months = list(months_all)
    n_actual = len(hist)                      # 实际月数（递归追加的预测不计入）
    actual_months = list(months_all)
    last_month = months_all[-1]

    future = []

    def actual_same_pos(target_ym):
        """最近一个实际同位月（月份相同）的值；无则 None。"""
        mm = target_ym[5:7]
        for i in range(n_actual - 1, -1, -1):
            if actual_months[i][5:7] == mm:
                return float(hist[i]), actual_months[i]
        return None, None

    def base_same_pos(target_ym, years_back):
        """years_back 年前同位月的实际值；无则 None。"""
        y0 = int(target_ym[:4]) - years_back
        want = "%04d-%s" % (y0, target_ym[5:7])
        if want in actual_months:
            return float(hist[actual_months.index(want)])
        return None

    for k in range(1, 13):
        month = month_add(last_month, k)
        mm = month[5:7]
        is_cny, is_pre = cny_month_of(month)
        if is_cny:
            pred = float(hist[-1]) * CNY_LOW_RATIO
            tag = "cny低谷(前月×%.2f)" % CNY_LOW_RATIO
        elif is_pre:
            # 三法中枢（E22c）：A=相位YoY，B=近6月均×冲量系数，C=两年同月 CAGR³
            g = float(sum(hist[-12:])) / max(float(sum(hist[-24:-12])), 1.0)
            v_recent, jan_name = actual_same_pos(month)
            A = (v_recent * g) if v_recent is not None else None
            B = float(np.mean(hist[-6:])) * CNY_SURGE_K
            v_base = base_same_pos(month, 3)
            if v_recent is not None and v_base is not None and v_base > 0:
                cagr = (v_recent / v_base) ** 0.5
                C = v_base * cagr ** 3
                cands = [x for x in (A, B, C) if x is not None]
                tag = "phase中枢(A=%s%.0f/B=%.0f/C=%.0f万)" % (
                    "" if A is not None else "—/", A / 1e4 if A is not None else 0,
                    B / 1e4, C / 1e4)
            else:
                cands = [x for x in (A, B) if x is not None]
                tag = "phase中枢(A/B 双法，C 缺基准)"
            pred = float(np.median(cands))
        else:
            pred = float(np.mean(hist[-6:]))
            tag = "ma6"
        future.append({"月": month, "预测": pred, "规则": tag})
        hist.append(pred)
        hist_months.append(month)

    return pd.DataFrame(future)


def detail_forecast(pivot, anchor_map, months_all, targets):
    """线/品类：逐线选优 + 递归外推 12 步 + 锚定公司口径。"""
    sel, rows = {}, {}
    for k in pivot.columns:
        v = pivot[k].values.astype(float)
        sel[k] = select_method(v, targets, months_all)
        rows[k] = forecast_steps(v, sel[k], 12)
    det = pd.DataFrame(rows, index=list(anchor_map.keys())).T
    out = {}
    for t in det.columns:
        raw_sum = float(det[t].sum())
        out[t] = det[t] * (anchor_map[t] / raw_sum) if raw_sum > 0 else det[t]
    out = pd.DataFrame(out)
    out.insert(0, "选优方法", pd.Series(sel))
    return out, sel


def build_conf_tier(pv, sel, months_all, targets):
    """置信分层：近20月实际合计 + 选优方法 WAPE + A/B/C 分档。"""
    win = months_all[-20:]
    rows = []
    total_win = float(pv.loc[win].sum().sum())
    for k in pivot_cols(pv):
        v = pv[k].values.astype(float)
        w = wape_series(v, sel[k], targets, months_all) * 100.0
        amt = float(pv.loc[win, k].sum()) / 1e4
        share = (amt * 1e4 / total_win * 100.0) if total_win > 0 else 0.0
        grade = "A" if w <= GRADE_A_MAX else ("B" if w <= GRADE_B_MAX else "C")
        rows.append({"产品线": k, "实际合计万": round(amt, 6),
                     "金额占比%": round(share, 1), "WAPE%": round(w, 1), "置信档": grade})
    conf = pd.DataFrame(rows).sort_values("实际合计万", ascending=False).reset_index(drop=True)
    return conf


def pivot_cols(pv):
    return list(pv.columns)


def build_long_series(df):
    """拼接长序列：历史总表(<2024-01) + silver 全月。写 data_warehouse 并同步 OUT。"""
    wh_hits = glob.glob(os.path.join(PKG, "data_warehouse", "**", "zongbiao_frozen*.parquet"),
                        recursive=True)
    comp_parts, line_parts = [], []
    if wh_hits:
        zb = pd.read_parquet(max(wh_hits, key=os.path.getmtime))
        zb["_ym"] = pd.to_datetime(zb["发货日期"], errors="coerce").dt.strftime("%Y-%m")
        zb["_amt"] = pd.to_numeric(zb["RMB 未税金额小计"], errors="coerce").fillna(0)
        zb = zb[zb["_ym"] < "2024-01"]
        comp_parts.append(zb.groupby("_ym")["_amt"].sum())
        if LINE_COL in zb.columns:
            line_parts.append(zb.groupby([LINE_COL, "_ym"])["_amt"].sum()
                              .rename("金额").reset_index()
                              .rename(columns={LINE_COL: "产品线", "_ym": "月"}))
        else:
            print("[警告] 历史总表无 %s 列，线级长序列仅含 silver 段。" % LINE_COL)
    else:
        print("[警告] 未找到 zongbiao_frozen*.parquet，长序列仅含 silver 段（2024-01 起）。")

    sv = df.copy()
    comp_parts.append(sv.groupby("月")["金额"].sum())
    line_parts.append(sv.groupby([LINE_COL, "月"])["金额"].sum()
                      .rename("金额").reset_index()
                      .rename(columns={LINE_COL: "产品线"}))

    comp = pd.concat(comp_parts).sort_index()
    comp_df = pd.DataFrame({"月": comp.index, "金额": comp.values})
    line_df = (pd.concat(line_parts)
               .groupby(["产品线", "月"])["金额"].sum().reset_index())

    wh_dir = os.path.dirname(max(wh_hits, key=os.path.getmtime)) if wh_hits else \
        os.path.join(PKG, "data_warehouse")
    comp_df.to_parquet(os.path.join(wh_dir, "company_monthly_rmb_long.parquet"), index=False)
    line_df.to_parquet(os.path.join(wh_dir, "line_monthly_rmb_long.parquet"), index=False)
    return comp_df, line_df


def verify_against_existing(fut, old_fut):
    """等价性验收：与既有交付（内存中已预读，避免被本次写盘覆盖）对拍 月/预测/无偏。"""
    if old_fut is None:
        print("[verify] 无既有交付 CSV，跳过对拍。")
        return True
    old = old_fut
    if list(old["月"]) != list(fut["月"]):
        print("[verify] 预测起点与旧交付不一致（数据月已滚动），不做逐值对拍。"
              "（旧首月=%s，新首月=%s）" % (old["月"].iloc[0], fut["月"].iloc[0]))
        return True
    ok = True
    for col, tol in (("预测", 1e-6), ("无偏", 1e-6)):
        diff = (pd.to_numeric(old[col]) - pd.to_numeric(fut[col])).abs()
        rel = diff / pd.to_numeric(old[col]).abs().clip(lower=1.0)
        bad = int((rel > tol).sum())
        if bad:
            ok = False
            print("[verify] %s 列 %d/%d 个月超差（最大相对误差 %.2e）"
                  % (col, bad, len(old), float(rel.max())))
        else:
            print("[verify] %s 列 %d/%d 月全部一致（最大相对误差 %.2e）"
                  % (col, len(old) - bad, len(old), float(rel.max())))
    print("[verify] %s" % ("✓ 等价性通过" if ok else "✗ 等价性未通过——请检查滚动化改造！"))
    return ok


def main():
    ap = argparse.ArgumentParser(description="月度滚动预测 · 生产入口")
    ap.add_argument("--verify", action="store_true", help="生成后与既有交付 CSV 对拍")
    args = ap.parse_args()

    t0 = time.perf_counter()
    out_dir = OUT_PRIMARY if os.path.isdir(OUT_PRIMARY) else OUT_FALLBACK
    if out_dir == OUT_FALLBACK:
        print("[警告] 交付目录 %s 不存在，回退 %s（预测面数据源以实际生成路径为准）"
              % (OUT_PRIMARY, OUT_FALLBACK))
    os.makedirs(out_dir, exist_ok=True)

    e12_path = os.path.join(out_dir, "E12b_量价集成_对比.csv")
    if not os.path.exists(e12_path):
        print("[错误] 区间比率池缺失：%s（静态标定产物，需从实验目录恢复）" % e12_path)
        sys.exit(1)

    # ---- 1. 银层 ----
    df = load_silver()
    ts = df.groupby("月")["金额"].sum().sort_index()
    months_all = list(ts.index)
    last_month = months_all[-1]
    pv = df.groupby(["月", LINE_COL])["金额"].sum().unstack(fill_value=0.0).sort_index()
    cat = df.groupby(["月", CAT_COL])["金额"].sum().unstack(fill_value=0.0).sort_index()
    targets = months_all[-20:]
    print("[数据] silver %s ~ %s（%d 月，%d 条产品线）"
          % (months_all[0], last_month, len(months_all), pv.shape[1]))

    # ---- 2. 公司口径滚动预测 ----
    fut = company_forecast(ts, months_all)
    fut["无偏"] = fut["预测"] * F_UNBIAS
    anchor_map = dict(zip(fut["月"], fut["预测"]))
    fut_months = list(fut["月"])
    print("[公司] 未来 12 个月：%s ~ %s" % (fut_months[0], fut_months[-1]))

    # ---- 3. 区间（E12b 比率池 + Bootstrap）----
    e12 = pd.read_csv(e12_path, encoding="utf-8-sig")
    pool = (e12["实际"] / e12["combo_volxasp"]).dropna().values
    q10, q90 = np.percentile(pool, [10, 90])

    def interval(preds):
        S = float(np.sum(preds))
        rng = np.random.default_rng(42)
        sims = np.array([sum(p * rng.choice(pool) for p in preds) for _ in range(4000)])
        lo_i, hi_i = np.percentile(sims, [10, 90])
        return S, S * q10, S * q90, lo_i, hi_i

    S4 = interval(fut.loc[fut["月"] <= "%s-12" % last_month[:4], "预测"].values)
    S6 = interval(fut["预测"].values[:6])
    S12 = interval(fut["预测"].values)

    # ---- 4. 线 / 品类（选优 + 锚定）----
    line_fc, sel = detail_forecast(pv, anchor_map, months_all, targets)
    cat_fc_all, _ = detail_forecast(cat, anchor_map, months_all, targets)
    year_start = "%s-01" % last_month[:4]
    cat_rank = cat.loc[year_start:last_month].sum().sort_values(ascending=False)
    keep = list(cat_rank.head(TOPN_CAT).index)
    cat_fc = cat_fc_all.loc[[c for c in cat_fc_all.index if c in keep]]
    cat_other = cat_fc_all.loc[[c for c in cat_fc_all.index if c not in keep]].sum()
    cat_other.name = "其他(%d类)" % (len(cat_fc_all) - TOPN_CAT)

    # ---- 5. 置信分层（近20月窗口）----
    conf = build_conf_tier(pv, sel, months_all, targets)

    # ---- 6. 长序列拼接 + 同步 ----
    comp_df, line_df = build_long_series(df)

    # ---- 7. 写盘（全部覆盖式，与历史交付同名同格式）----
    # 等价性对拍基准必须在写盘前预读（否则会被本次输出覆盖，对拍失效）。
    _old_path = os.path.join(out_dir, "交付_公司分月.csv")
    old_fut = pd.read_csv(_old_path, encoding="utf-8-sig") if os.path.exists(_old_path) else None
    fut_out = fut[["月", "预测", "规则", "无偏"]]
    fut_out.to_csv(os.path.join(out_dir, "交付_公司分月.csv"),
                   index=False, encoding="utf-8-sig")
    line_fc.to_csv(os.path.join(out_dir, "交付_产品线.csv"), encoding="utf-8-sig")
    cat_out = pd.concat([cat_fc, cat_other.to_frame().T])
    cat_out.to_csv(os.path.join(out_dir, "交付_品类.csv"), encoding="utf-8-sig")
    conf.to_csv(os.path.join(out_dir, "看板数据_线级置信分层.csv"),
                index=False, encoding="utf-8-sig")
    comp_df.to_csv(os.path.join(out_dir, "公司月度长序列80月.csv"),
                   index=False, encoding="utf-8-sig")
    line_df.to_csv(os.path.join(out_dir, "线级月度长序列80月.csv"),
                   index=False, encoding="utf-8-sig")

    # ---- 7.5 预测面展示元数据（供 generate_dashboard.py 注入 tabP 消费）----
    ytd = float(ts.loc[year_start:last_month].sum())
    s4_base = float(fut.loc[fut["月"] <= "%s-12" % last_month[:4], "预测"].sum()) + ytd
    s4_unb = (s4_base - ytd) * F_UNBIAS + ytd
    s6_base = float(fut["预测"].values[:6].sum())
    s12_base = float(fut["预测"].values.sum())

    def _rng_txt(lo, hi, add=0.0):
        return "{:,.0f}~{:,.0f}".format((lo + add) / 1e4, (hi + add) / 1e4)

    cover_pct = {g: round(float(conf.loc[conf["置信档"] == g, "金额占比%"].sum()), 1)
                 for g in ("A", "B", "C")}
    # 春节月标注：近一年历史 + 未来窗口内的春节月（主图春节带 & 月历橙格共用）
    cny_marks = []
    for k in range(24):
        ym = month_add(last_month, -11 + k)
        if CNY_MONTHS.get(ym[:4]) == ym:
            cny_marks.append(ym)
    fut_cny = [m for m in cny_marks if m > last_month]
    cny_note = ""
    if fut_cny:
        cny_note = "春节在 %s：%s 为低谷月，已按 6 个春节年份规律标定" % (
            fut_cny[0], fut_cny[0])
    # 季度聚合（未来 4 个自然季；区间=合计×比率池 q10/q90，全相关口径）
    _qs = {}
    for _, r in fut.iterrows():
        _y, _m = int(r["月"][:4]), int(r["月"][5:7])
        _q = "%dQ%d" % (_y, (_m - 1) // 3 + 1)
        _qs.setdefault(_q, [0.0, 0.0])
        _qs[_q][0] += float(r["预测"])
        _qs[_q][1] += float(r["无偏"])
    quarters = []
    for _q in sorted(_qs):
        _b = _qs[_q][0]
        quarters.append({"q": _q, "base": round(_b / 1e4),
                         "unbiased": round(_qs[_q][1] / 1e4),
                         "lo": round(_b * q10 / 1e4), "hi": round(_b * q90 / 1e4)})

    # ---- 7.6 预测追踪回填：过去月"当时预测 vs 实际"（无状态回演，规则与生产同源）----
    _hist_f = ts.values.astype(float)
    tr_months, tr_pred, tr_act, tr_err, tr_err_unb = [], [], [], [], []
    _dir_hit = _dir_n = 0
    for t in months_all[-20:]:
        i = months_all.index(t)
        if i < 13:
            continue
        h = list(_hist_f[:i]); hm = months_all[:i]
        is_cny_t, is_pre_t = cny_month_of(t)
        if is_cny_t:
            p = h[-1] * CNY_LOW_RATIO
        elif is_pre_t:
            g = float(sum(h[-12:])) / max(float(sum(h[-24:-12])), 1.0)
            mm = t[5:7]
            v_recent = None
            for k2 in range(len(h) - 1, -1, -1):
                if hm[k2][5:7] == mm:
                    v_recent = float(h[k2]); break
            A = (v_recent * g) if v_recent is not None else None
            B = float(np.mean(h[-6:])) * CNY_SURGE_K
            _want = "%04d-%s" % (int(t[:4]) - 3, mm)
            v_base = float(h[hm.index(_want)]) if _want in hm else None
            if A is not None and v_base is not None and v_base > 0 and v_recent is not None:
                C = v_base * (v_recent / v_base) ** 1.5
                cands = [x for x in (A, B, C) if x is not None]
            else:
                cands = [x for x in (A, B) if x is not None]
            p = float(np.median(cands))
        else:
            p = float(np.mean(h[-6:]))
        act = float(_hist_f[i])
        tr_months.append(t)
        tr_pred.append(round(p / 1e4))
        tr_act.append(round(act / 1e4))
        tr_err.append(round((p - act) / act * 100, 1) if act > 0 else None)
        tr_err_unb.append(round((p * F_UNBIAS - act) / act * 100, 1) if act > 0 else None)
        _prev = float(_hist_f[i - 1])
        if _prev > 0 and act > 0:
            _dir_n += 1
            if (p - _prev) * (act - _prev) > 0:
                _dir_hit += 1
    _abs_errs = [abs(e) for e in tr_err if e is not None]
    _abs_errs_unb = [abs(e) for e in tr_err_unb if e is not None]
    track = {
        "months": tr_months, "pred": tr_pred, "act": tr_act, "errPct": tr_err,
        "errPctUnb": tr_err_unb,
        "avgAbsErr": round(float(np.mean(_abs_errs)), 1) if _abs_errs else None,
        "avgAbsErrUnb": round(float(np.mean(_abs_errs_unb)), 1) if _abs_errs_unb else None,
        "dirHit": _dir_hit, "dirN": _dir_n,
    }

    # ---- 7.7 季节性指纹 / 大客户依赖 / 新品占比 / 年度目标 ----
    # 季节指纹：各自然月相对当年月均的指数（中位，剔 2020 起步年），基于 80 月长序列
    _seas = {}
    for _, _r in comp_df.iterrows():
        _ym = str(_r["月"])
        if _ym[:4] == "2020":
            continue
        _yr_mean = float(comp_df[comp_df["月"].str.startswith(_ym[:4])]["金额"].mean())
        if _yr_mean > 0:
            _seas.setdefault(int(_ym[5:7]), []).append(float(_r["金额"]) / _yr_mean)
    seasonal = [round(float(np.median(_seas.get(m, [1.0]))), 2) for m in range(1, 13)]

    # 大客户依赖：近 12 月 Top5 客户收入占比（及 vs 前 12 月变化、Top1 占比）
    _m12 = months_all[-12:]
    _d12 = df[df["月"].isin(_m12)]
    _c12 = _d12.groupby("客户编号")["金额"].sum().sort_values(ascending=False)
    _tot12 = float(_c12.sum())
    cust_conc = {"top5Share": None, "top1Share": None, "names": [], "deltaPp": None}
    if _tot12 > 0 and len(_c12):
        _top5 = _c12.head(5)
        cust_conc["top5Share"] = round(float(_top5.sum()) / _tot12 * 100, 1)
        cust_conc["top1Share"] = round(float(_top5.iloc[0]) / _tot12 * 100, 1)
        cust_conc["names"] = [str(x) for x in _top5.index[:5]]
        if len(months_all) >= 24:
            _dprev = df[df["月"].isin([m for m in months_all[-24:-12]])]
            _cprev = _dprev.groupby("客户编号")["金额"].sum().sort_values(ascending=False)
            _totprev = float(_cprev.sum())
            if _totprev > 0:
                cust_conc["deltaPp"] = round(cust_conc["top5Share"]
                                             - float(_cprev.head(5).sum()) / _totprev * 100, 1)

    # 新品占比（近 12 月新品标记收入占比）
    _isnew = _d12["新品标记"].astype(str).isin(["是", "True", "true", "Y"])
    new_share = round(float(_d12.loc[_isnew, "金额"].sum()) / _tot12 * 100, 1) if _tot12 > 0 else None

    # 年度目标（chain_config.json forecast_target: {"year":2026,"value":万元}；缺省不显示）
    _target = None
    try:
        with open(os.path.join(PKG, "chain_config.json"), encoding="utf-8") as _tf:
            _tgt = (json.load(_tf) or {}).get("forecast_target") or {}
        if _tgt.get("value"):
            _target = {"year": int(_tgt.get("year") or int(last_month[:4])),
                       "value": float(_tgt["value"])}
    except Exception:
        pass

    meta = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "lastMonth": last_month,
        "futureStart": fut_months[0],
        "cnyMarks": cny_marks,
        "cnyNote": cny_note,
        # kpis 数值统一存万元（修复单位错位：此前存元级与区间串万元级混用）
        "kpis": {
            "fy": [round(s4_base / 1e4), round(s4_unb / 1e4), _rng_txt(S4[3], S4[4], ytd)],
            "m6": [round(s6_base / 1e4), round(s6_base * F_UNBIAS / 1e4), _rng_txt(S6[3], S6[4])],
            "m12": [round(s12_base / 1e4), round(s12_base * F_UNBIAS / 1e4), _rng_txt(S12[3], S12[4])],
        },
        "quarters": quarters,
        "track": track,
        "seasonal": seasonal,
        "custConc": cust_conc,
        "newShare": new_share,
        "target": _target,
        "conclusion": {
            "lead": "未来 12 个月预计出货 %.1f 亿，八成把握落在 %.1f ~ %.1f 亿" % (
                s12_base / 1e8, S12[3] / 1e8, S12[4] / 1e8),
            "note": cny_note or "未来窗口无春节月",
        },
        "cover": cover_pct,
    }
    with open(os.path.join(out_dir, "看板数据_预测面.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    # ---- 8. 汇总打印 ----
    ytd = float(ts.loc[year_start:last_month].sum())
    print()
    print("=== 公司口径（万元）===")
    for _, r in fut_out.iterrows():
        print("  %s 基准 %8.0f | 无偏 %8.0f | %s"
              % (r["月"], r["预测"] / 1e4, r["无偏"] / 1e4, r["规则"]))
    print("今年YTD实际 %.0f万 + 年内预测 %.0f万；未来6个月 %.0f万；12个月 %.0f万"
          % (ytd / 1e4, S4[0] / 1e4, S6[0] / 1e4, S12[0] / 1e4))
    print("80%%区间(独立) 6个月 [%.0f, %.0f]万 | 12个月 [%.0f, %.0f]万"
          % (S6[3] / 1e4, S6[4] / 1e4, S12[3] / 1e4, S12[4] / 1e4))
    print("置信分档 A %d 线 / B %d 线 / C %d 线"
          % ((conf["置信档"] == "A").sum(), (conf["置信档"] == "B").sum(),
             (conf["置信档"] == "C").sum()))
    print("产物目录: %s" % out_dir)

    # ---- 9. 等价性验收 ----
    if args.verify:
        verify_against_existing(fut_out, old_fut)

    print("[完成] 预测流水线耗时 %.1fs" % (time.perf_counter() - t0))


if __name__ == "__main__":
    main()
