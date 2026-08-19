"""
产品生命周期分析 — v2.8解耦重写版。

使用共享Silver层和共享模块，输出与原始v2.8完全一致。
"""

import os
import sys
import time
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.settings import (
    DATA_DIR, OUTPUT_SILVER, OUTPUT_GOLD, OUTPUT_REPORT,
    PRODUCT_LIFECYCLE, COL_MAP,
)
from shared.data_cleaning import (
    winsorize_margins, filter_negative_qty, monthly_aggregate_double_pass,
    rename_erp_columns, read_excel_auto,
)
import shared.timing as timing
from product_lifecycle.profiling import run_profiling
from product_lifecycle.nine_grid import classify_9grid_full
from product_lifecycle.notes import generate_specific_note
from product_lifecycle.report import write_excel_report
# 注：客户分析功能(rfm_customer_segmentation, product_association_analysis,
# calc_customer_portrait, generate_gold_tables) 已移至客户分析管道，
# 产品分析不再直接依赖 customer_analysis 模块。


def _ensure_dirs():
    for d in [OUTPUT_SILVER, OUTPUT_GOLD, OUTPUT_REPORT]:
        os.makedirs(d, exist_ok=True)


# ============================================================
# 配置加载
# ============================================================

def load_config_from_dict():
    """从config/settings.py的PRODUCT_LIFECYCLE字典加载配置。
    
    返回:
        col_map, thresholds, weights, ref_priority
    """
    cfg = PRODUCT_LIFECYCLE.copy()
    col_map = cfg.get("col_map", {})
    thresholds = {k: v for k, v in cfg.items() if k not in ("col_map", "ref_priority", "risk_weights")}
    weights = cfg.get("risk_weights", {})
    ref_priority = cfg.get("ref_priority", [("产品一级分类", 3), ("（全公司均值）", 0)])
    return col_map, thresholds, weights, ref_priority


def load_config_from_xlsx(config_path):
    """从config.xlsx加载配置（兼容原始v2.8格式）。
    
    返回:
        col_map, thresholds, weights, ref_priority
    """
    cfg = {"col_map": {}, "thresholds": {}, "weights": {}, "ref_priority": []}
    
    try:
        df = pd.read_excel(config_path, sheet_name="列映射", header=0)
        for _, row in df.iterrows():
            key = str(row.iloc[0]).strip()
            if not key:
                continue
            val = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
            cfg["col_map"][key] = val
    except (ValueError, FileNotFoundError, KeyError):
        cfg["col_map"] = PRODUCT_LIFECYCLE.get("col_map", {})
    
    try:
        df = pd.read_excel(config_path, sheet_name="阈值参数", header=0)
        for _, row in df.iterrows():
            key = str(row.iloc[0]).strip()
            if not key:
                continue
            val = row.iloc[1]
            try:
                cfg["thresholds"][key] = float(val)
            except (ValueError, TypeError):
                cfg["thresholds"][key] = str(val).strip() if pd.notna(val) else ""
    except (ValueError, FileNotFoundError, KeyError):
        cfg["thresholds"] = {k: v for k, v in PRODUCT_LIFECYCLE.items() if k not in ("col_map", "ref_priority", "risk_weights")}
    
    try:
        df = pd.read_excel(config_path, sheet_name="风险因子权重", header=0)
        for _, row in df.iterrows():
            key = str(row.iloc[0]).strip()
            if not key:
                continue
            try:
                cfg["weights"][key] = float(row.iloc[1])
            except (ValueError, TypeError):
                cfg["weights"][key] = 0
    except (ValueError, FileNotFoundError, KeyError):
        cfg["weights"] = PRODUCT_LIFECYCLE.get("risk_weights", {})
    
    try:
        df_ref = pd.read_excel(config_path, sheet_name="参照组优先级", header=0)
        for _, row in df_ref.iterrows():
            col_name = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
            if not col_name:
                continue
            try:
                min_n = int(row.iloc[2])
            except (ValueError, TypeError):
                min_n = 3
            cfg["ref_priority"].append((col_name, min_n))
    except (ValueError, FileNotFoundError, KeyError):
        cfg["ref_priority"] = PRODUCT_LIFECYCLE.get("ref_priority", [("产品一级分类", 3), ("（全公司均值）", 0)])
    
    return cfg["col_map"], cfg["thresholds"], cfg["weights"], cfg["ref_priority"]


# ============================================================
# Silver层构建
# ============================================================

def build_silver_layer(source_path):
    """从源数据构建Silver层（代理到 shared 统一实现）。

    返回:
        dict: {'customer_monthly', 'product_monthly', 'customer_x_product'}
    """
    from shared.data_cleaning import build_silver_layer as _shared_build

    print("=" * 60)
    print("[产品·共享管道] 构建Silver层")
    print("=" * 60)

    col_map, _, _, _ = load_config_from_dict()

    return _shared_build(
        source_path,
        col_map=col_map,
        save_cleaned_rows=True,        # 产品管道保存行级数据供复用
        cat_col_propagation=False,      # 产品管道不在 customer_x_product 携带分类
    )


# ============================================================
# 主分析流程
# ============================================================

def _prepare_data(source_path, col_map, thr):
    """加载并清洗源数据，返回 (cleaned_df, latest_month, order_col)。

    所有清洗步骤与原始v2.8完全一致：负销量过滤、日期过滤、Winsorization。
    """
    name_col = col_map.get("产品名称列", "产品品种")
    date_col = col_map.get("发货日期列", "发货日期")
    qty_col = col_map.get("销量列", "数量")
    rev_col = col_map.get("营收列", "金额")
    profit_col = col_map.get("利润列", "利润")
    order_col = col_map.get("订单号列", "订单编号")

    print("=" * 60)
    print("[产品] 加载数据")
    print("=" * 60)
    print(f"  数据文件: {source_path}")

    if source_path.endswith(".csv"):
        df = pd.read_csv(source_path, encoding="utf-8-sig")
        df[date_col] = pd.to_datetime(df[date_col])
    else:
        df = read_excel_auto(source_path, sheet_name=0)
        df = rename_erp_columns(df)
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col])

    print(f"  行数: {len(df)}, 列数: {len(df.columns)}")
    
    # ---- 数据类型转换（与v2.8一致） ----
    df[name_col] = df[name_col].astype(str).str.strip()
    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
    df[qty_col] = pd.to_numeric(df[qty_col], errors='coerce').fillna(0)
    df[rev_col] = pd.to_numeric(df[rev_col], errors='coerce').fillna(0)
    df[profit_col] = pd.to_numeric(df[profit_col], errors='coerce').fillna(0)
    
    if order_col and order_col in df.columns:
        df[order_col] = df[order_col].astype(str).str.strip()
    else:
        order_col = None
    
    # ---- 负销量过滤（口径开关，默认关闭） ----
    # 批次①（T1）：默认与生产链式路径（shared.data_cleaning，保留退货/红冲行自然冲减）
    # 一致，不剔除负销量。历史 v2.8 行为（剔除负销量）由配置开关 _口径_负销量过滤 控制，
    # 待批次③业务拍板（D-2）后按需启用。
    if thr.get("_口径_负销量过滤", False):
        neg_qty_before = (df[qty_col] < 0).sum()
        if neg_qty_before > 0:
            df = df[df[qty_col] > 0].copy()
            print(f"  已剔除 {neg_qty_before} 行负销量/零销量（退货/红冲/空单）")
    
    # ---- 过滤日期范围（与v2.8一致） ----
    start_date = str(thr.get("data_start_date", "2020-01-01"))
    df = df[df[date_col] >= pd.Timestamp(start_date)]
    df = df.dropna(subset=[date_col])
    print(f"  过滤后行数（起始日期>={start_date}）: {len(df)}")
    
    # ---- 毛利率（口径开关，默认不钳制） ----
    # 批次①（T1）：默认与生产链式路径（shared.winsorize_margins，保留真实毛利率、
    # _利润_裁剪=原始利润）一致。历史 v2.8 的 clip(-0.5,0.75) 行为由配置开关
    # _口径_毛利率钳制 控制，待批次③业务拍板（D-1）后按需启用。
    if thr.get("_口径_毛利率钳制", False):
        winsor_low = float(thr.get("Winsor下限", -0.50))
        winsor_high = float(thr.get("Winsor上限", 0.75))
        df['_毛利率'] = np.where(
            df[rev_col] > 0,
            df[profit_col] / df[rev_col],
            np.nan
        )
        df['_毛利率'] = df['_毛利率'].clip(winsor_low, winsor_high)
        df['_利润_裁剪'] = np.where(
            df[rev_col] > 0,
            df['_毛利率'].fillna(0) * df[rev_col],
            df[profit_col]
        )
    else:
        df['_毛利率'] = df[profit_col] / df[rev_col].replace(0, float("nan"))
        df['_利润_裁剪'] = df[profit_col]
    
    # ---- 构建时间窗口 ----
    df['_月'] = df[date_col].dt.to_period('M')
    
    # ---- 数据完整性检查（与v2.8一致） ----
    max_date = df[date_col].max()
    latest_month = df['_月'].max()

    # 检查最新月份的最大日期，而非全局最大日期
    latest_mask = df['_月'] == latest_month
    latest_max_day = df.loc[latest_mask, date_col].max().day if latest_mask.any() else 31

    _incomplete_day = int(thr.get("incomplete_month_threshold_day", 25))
    if latest_max_day < _incomplete_day:
        print(f"  [警告] 检测到最新月份 {latest_month} 数据可能不完整（仅到{latest_max_day}号，阈值{_incomplete_day}天）。")
        print(f"   已自动剔除 {latest_month} 的数据，基准月回退至 {latest_month - 1}。")
        df = df[df['_月'] < latest_month]
        latest_month = latest_month - 1
    
    print(f"  数据范围: {df[date_col].min().date()} ~ {df[date_col].max().date()}")
    print(f"  最新月份: {latest_month}")
    return df, latest_month, order_col


def run_analysis(source_path, df=None):
    """执行完整的产品生命周期分析。

    参数:
        source_path: 源数据Excel路径
        df: 可选，预清洗的DataFrame。为None时从文件读取。

    返回:
        dict: 包含输出文件路径和分析结果
    """
    _ensure_dirs()

    # ──────────────────────────────────────────────
    # Phase 1: 数据准备
    # 加载配置（列映射、阈值、权重、参照组优先级），
    # 读取或复用清洗后的数据，获取最新月份基准。
    # ──────────────────────────────────────────────
    col_map, thr, wgt, ref_priority = load_config_from_dict()

    # 获取列名
    name_col = col_map.get("产品名称列", "产品品种")
    date_col = col_map.get("发货日期列", "发货日期")
    qty_col = col_map.get("销量列", "数量")
    rev_col = col_map.get("营收列", "金额")
    profit_col = col_map.get("利润列", "利润")
    cust_col = col_map.get("客户列", "客户编号")
    order_col = col_map.get("订单号列", "订单编号")
    cat_col = col_map.get("分类参照列", "产品一级分类")

    # 读取并清洗数据
    if df is not None:
        df = df.copy()
        print("  [复用] 使用预加载数据，跳过文件读取")
        # 确保order_col处理已应用
        if order_col and order_col not in df.columns:
            order_col = None
        latest_month = df['_月'].max()
    else:
        df, latest_month, order_col = _prepare_data(source_path, col_map, thr)

    # ──────────────────────────────────────────────
    # Phase 2~6: 核心画像分析
    # 以下5个阶段均在 run_profiling() 内部完成：
    #   Phase 2 - 新品判定：使用ERP新品标记或按月数/销量自动判定
    #   Phase 3 - 历史参考计算：参照组加权均值（优先级逐级回退至全公司均值）
    #   Phase 4 - 画像分类：九宫格（销量动能×盈利健康 → 成长/成熟/衰退等）
    #   Phase 5 - 风险评分：五因子加权（斜率/波动/衰减/自比健康度/ASP），
    #                       不可靠因子自动重加权+衰退期最低分兜底
    #   Phase 6 - ETS 预测：ETS状态空间模型（MLE参数优化），
    #                       节假日调整 + 80%/95%置信区间，WMA兜底回退
    # ──────────────────────────────────────────────
    # 执行画像分析
    print("\n" + "=" * 60)
    print("[产品] 执行画像分析")
    print("=" * 60)
    
    result_df, data_insufficient, out, ratio_cols, pp_cols, _t4 = run_profiling(
        df, latest_month, thr, name_col, date_col, qty_col, rev_col,
        profit_col, cust_col, order_col, cat_col, ref_priority, wgt, mode='full'
    )
    
    # RFM客户分群已移至客户分析RFM-π模型输出
    rfm_result = None
    # 产品关联分析已移至客户分析Gold层表
    assoc_result = None
    
    # 注：客户分析（全景画像/Gold层表/RFM分群/产品关联分析）
    # 已移至 customer_analysis/run_pipeline.py 统一处理，
    # 产品分析不再重复计算客户指标。
    
    # 输出结果
    print("\n" + "=" * 60)
    print("[产品] 输出结果")
    print("=" * 60)

    # ──────────────────────────────────────────────
    # Phase 7: 历史画像追踪
    # 在多个历史时间点（如 t-1 ~ t-12 月）重新执行画像分析，
    # 通过多进程并行加速，按时间顺序合并形成画像变迁轨迹。
    # ──────────────────────────────────────────────

    # ---- 历史画像滑动窗口追踪（兼容原始v2.8逻辑，使用 run_profiling(mode='portrait_only')） ----
    # 解析历史画像配置：支持多种格式的 hist_portrait_points
    #   - "auto_12" → 自动生成 1~12 月全部偏移
    #   - "3,6,12" → 逗号分隔的偏移月数列表
    #   - 单个数值 → 仅该偏移月数
    #   - 列表 → 直接使用
    hist_enabled = int(thr.get("hist_portrait_enabled", 0))
    if hist_enabled != 1:
        hist_intervals = []
    else:
        hist_points = thr.get("hist_portrait_points", None)
        if hist_points is None:
            hist_intervals = []
        elif isinstance(hist_points, str):
            if hist_points.strip().lower() == "auto_12":
                hist_intervals = list(range(1, 13))
            else:
                parsed = []
                for x in hist_points.split(","):
                    x = x.strip()
                    try:
                        parsed.append(int(x))
                    except ValueError:
                        pass
                hist_intervals = parsed
        elif isinstance(hist_points, (int, float)):
            hist_intervals = [int(hist_points)]
        elif not isinstance(hist_points, list):
            hist_intervals = [6, 12, 18, 24]  # 未知类型时使用默认值
        else:
            hist_intervals = hist_points

    # 预聚合产品月度数据（供历史画像复用，避免重复groupby）
    # 若存在订单号列则统计订单去重数，否则以销量行代替
    if len(hist_intervals) > 0:
        if order_col and order_col in df.columns:
            prod_month_all = df.groupby([name_col, '_月']).agg(
                qty_sum=(qty_col, 'sum'),
                rev_pos=(rev_col, lambda x: x[x > 0].sum()),
                profit_clip_sum=('_利润_裁剪', 'sum'),
                _order_count=(order_col, 'nunique')
            ).reset_index().sort_values([name_col, '_月'], kind='stable')
        else:
            prod_month_all = df.groupby([name_col, '_月']).agg(
                qty_sum=(qty_col, 'sum'),
                rev_pos=(rev_col, lambda x: x[x > 0].sum()),
                profit_clip_sum=('_利润_裁剪', 'sum'),
                _order_count=(qty_col, lambda x: 1)
            ).reset_index().sort_values([name_col, '_月'], kind='stable')
        prod_month_all['_avg_price'] = prod_month_all['rev_pos'] / prod_month_all['qty_sum'].replace(0, float('nan'))
    else:
        prod_month_all = None

    hist_track_cols = ["当前画像", "综合评分", "综合风险等级", "近12月毛利率%", "近12月增长率%", "近12月销量"]
    hist_min_months = int(thr.get("hist_portrait_min_months", 6))

    # 预收集所有有效的画像任务
    # 逐偏移量检查数据量是否充足（日历月龄 ≥ hist_min_months），
    # 不足则跳过该时间点，避免短数据导致画像偏误
    hist_tasks = []
    for offset_months in hist_intervals:
        tp = latest_month - offset_months
        if tp < df['_月'].min():
            continue
        hist_mask = df['_月'] <= tp
        if df.loc[hist_mask, '_月'].nunique() < hist_min_months:
            continue
        df_hist = df[hist_mask].copy()
        hist_tasks.append((offset_months, tp, df_hist))

    # 并行执行 (ProcessPoolExecutor: 绕过GIL，多进程真并行)
    # 每个时间点独立运行 run_profiling(mode='portrait_only')，
    # 利用 prod_month_all 预聚合数据避免重复 groupby
    _t_hist_start = time.time()
    hist_results = {}
    if len(hist_tasks) > 0:
        from concurrent.futures import ProcessPoolExecutor, as_completed
        n_workers = min(int(thr.get("hist_portrait_n_workers", 4)), len(hist_tasks))
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            fut_map = {}
            for offset_months, tp, df_hist in hist_tasks:
                future = executor.submit(
                    run_profiling, df_hist, tp, thr, name_col, date_col,
                    qty_col, rev_col, profit_col, cust_col, order_col,
                    cat_col, ref_priority, wgt,
                    mode='portrait_only', prod_month=prod_month_all)
                fut_map[future] = offset_months
            for future in as_completed(fut_map):
                om = fut_map[future]
                hist_result, _, _, _, _, _ = future.result()
                hist_results[om] = hist_result
                print(f"  [历史画像] t-{om}月: {len(hist_result)}个产品")

    # 按顺序合并 (必须按 offset 递增以保证结果列顺序一致)
    # 结果列以 _t-{offset} 后缀区分（如 "当前画像_t-3"），
    # 左连接确保只有当前快照中的产品才有历史轨迹
    for offset_months in sorted(hist_results.keys()):
        hist_result = hist_results[offset_months]
        suffix = f"_t-{offset_months}"
        merge_cols = {"产品名称": "产品名称"}
        for tc in hist_track_cols:
            if tc in hist_result.columns:
                merge_cols[tc] = tc + suffix
        hist_merge = hist_result[list(merge_cols.keys())].rename(columns=merge_cols)
        result_df = result_df.merge(hist_merge, on="产品名称", how="left")

    if len(hist_intervals) > 0:  # 保留 hist_sheet_df 构建逻辑
        hist_sheet_df = result_df[["产品名称"]].copy()
        hist_new_cols = [c for c in result_df.columns if any(c.endswith(f'_t-{off}') for off in hist_intervals)]
        for c in hist_new_cols:
            hist_sheet_df[c] = result_df[c].values
        print(f"  [计时] 历史画像: {time.time() - _t_hist_start:.1f}s")

    # ---- 趋势预测汇总列（取自result_df，因为out不含预测列） ----
    forecast_cols_check = ["预测第1月销量", "预测第2月销量", "预测第3月销量", "销量趋势预测"]
    forecast_cols_ext = ["产品名称", "帕累托分类", "近12月销量",
                         "预测第1月销量", "预测第2月销量", "预测第3月销量",
                         "预测_第1月_置信下限80%", "预测_第1月_置信上限80%",
                         "预测_第2月_置信下限80%", "预测_第2月_置信上限80%",
                         "预测_第3月_置信下限80%", "预测_第3月_置信上限80%",
                         "预测_第1月_置信下限95%", "预测_第1月_置信上限95%",
                         "预测_第2月_置信下限95%", "预测_第2月_置信上限95%",
                         "预测_第3月_置信下限95%", "预测_第3月_置信上限95%",
                         "销量趋势预测", "预测模型类型",
                         "节假日调整系数", "预测算法"]
    forecast_cols_ext = [c for c in forecast_cols_ext if c in result_df.columns]

    # ---- Excel写入（委托给 write_excel_report） ----
    output_file = write_excel_report(
        out, result_df, data_insufficient,
        ratio_cols, pp_cols, hist_sheet_df, hist_intervals, thr,
        forecast_cols_check, forecast_cols_ext,
        output_report_path=OUTPUT_REPORT
    )

    # ---- 输出统计 ----
    total = len(out)
    warned = (out["当前画像"].str.contains("预警|衰退", na=False)).sum()
    high_risk_threshold = float(thr.get("risk_mid_max", 50))
    high_risk = (out["综合评分"] > high_risk_threshold).sum()
    insuf_count = len(data_insufficient)
    zombie_count = (out['当前画像'] == '清仓/偶发').sum()

    print(f"\n{'='*50}")
    print(f"报告已生成：{output_file}")
    print(f"{'='*50}")
    n_products_total = len(out) + insuf_count
    print(f"产品总数: {n_products_total}")
    print(f"数据不足(<{int(thr.get('min_record_months', 3))}月): {insuf_count}")
    print(f"进入快照表: {total}")
    print(f"新品观察: {(out['当前画像']=='新品观察').sum()}")
    print(f"清仓/偶发: {zombie_count}")
    print(f"参与分析: {(~out['当前画像'].isin(['新品观察', '清仓/偶发'])).sum()}")
    print(f"预警/衰退: {warned}")
    print(f"高风险(>{high_risk_threshold:.0f}分): {high_risk}")
    print()
    print("输出文件包含以下 Sheet：")
    print("  产品快照表       - 所有产品完整诊断数据（含策略建议、数据质量标记）")
    print("  预警清单         - 筛选出的高风险/预警/衰退产品")
    print("  画像分布         - 各画像产品数统计")
    print("  历史画像追踪     - 各产品12个时间点的画像变迁轨迹")
    if data_insufficient:
        print("  数据不足产品清单 - 日历月龄过低无法分析的产品")
    # 客户RFM分群与产品关联分析已移至客户分析报告输出
    if any(c in result_df.columns for c in forecast_cols_check):
        print("  趋势预测汇总     - 未来3月销量预测（ETS+节假日调整，含逐月置信区间）")
    print("  使用说明         - 字段解释、名词定义与术语表")
    print()
    print("百分数列已标注 %，Excel 单元格已设百分比格式")
    print("预警行已标粉色高亮")
    print()

    # 导出Gold层
    gold_path = os.path.join(OUTPUT_GOLD, "gold_product_portrait.csv")
    out.to_csv(gold_path, index=False, encoding="utf-8-sig")
    print(f"  Gold层: {gold_path}")

    return {
        "output_file": output_file,
        "gold_path": gold_path,
        "product_count": len(out),
        "hist_trace": hist_sheet_df if len(hist_intervals) > 0 else None,
    }


# ============================================================
# 独立入口
# ============================================================

def run(source_path=None, skip_silver=False):
    """运行产品生命周期分析。

    参数:
        source_path: 源数据Excel路径
        skip_silver: 是否跳过Silver层构建

    返回:
        输出文件路径
    """
    _ensure_dirs()

    if source_path is None:
        xlsx_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".xlsx")]
        if not xlsx_files:
            print("[错误] data/ 目录下未找到源数据文件")
            return ""
        source_path = os.path.join(DATA_DIR, xlsx_files[0])

    if not skip_silver:
        build_silver_layer(source_path)

    # 统一入口：优先复用共享Silver产出的行级数据（与生产链式路径一致）
    # 批次①（T1）：独立运行入口也走与链式相同的数据来源 silver_cleaned_rows.csv
    # （或 shared.data_cleaning 的同一构建函数），不再进入 _prepare_data 的
    # 私有过滤/钳制路径（该路径已由配置开关默认关闭，见 _prepare_data）。
    silver_rows_path = os.path.join(OUTPUT_SILVER, "silver_cleaned_rows.csv")
    if os.path.exists(silver_rows_path):
        print("  [复用] 从silver_cleaned_rows.csv加载，跳过Excel文件读取")
        cleaned_df = pd.read_csv(silver_rows_path, encoding="utf-8-sig", low_memory=False)
        # 补充_prepare_data所需的列：日期类型转换+_月时间窗口
        col_map, _, _, _ = load_config_from_dict()
        date_col = col_map.get("发货日期列", "发货日期")
        if date_col in cleaned_df.columns:
            cleaned_df[date_col] = pd.to_datetime(cleaned_df[date_col], errors='coerce')
            cleaned_df['_月'] = cleaned_df[date_col].dt.to_period('M')
        result = run_analysis(source_path, df=cleaned_df)
    else:
        # 共享Silver产物缺失（罕见）时回退 _prepare_data；其负销量过滤/毛利率钳制
        # 开关默认关闭，口径与生产链式路径一致（不剔除负销量、不钳制毛利率）。
        result = run_analysis(source_path)
    
    if result and result.get("output_file"):
        print(f"\n[OK] 产品生命周期分析完成")
        print(f"  输出: {result['output_file']}")
        print(f"  产品数: {result['product_count']}")
        return result["output_file"]
    else:
        print(f"\n[ERR] 产品生命周期分析未产生输出")
        return ""


if __name__ == "__main__":
    run()
