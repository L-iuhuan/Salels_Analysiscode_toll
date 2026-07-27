"""
产品画像核心引擎 — 从v2.8的run_profiling解耦重写。

使用共享Silver层作为输入，输出与原始v2.8完全一致的产品快照表。
"""

import time
import pandas as pd
import numpy as np

from shared.calc_utils import calc_slope, calc_age_months
from shared.classifiers import classify_slope_level, classify_momentum, classify_health
from shared.risk_scoring import risk_slope, risk_cv, risk_decay, risk_self_health, risk_asp
from shared.pricing import calc_asp_trend, calc_price_elasticity, calc_order_frequency_trend
from shared.forecasting import ets_forecast, weighted_ma_forecast, prepare_holiday_adjustment
from shared.customer_analysis import rfm_customer_segmentation, product_association_analysis
from product_lifecycle.nine_grid import classify_9grid_full
from product_lifecycle.notes import generate_specific_note


def run_profiling(df, latest_month, thr, name_col, date_col, qty_col, rev_col, profit_col, cust_col, order_col, cat_col, ref_priority, wgt, mode='full', prod_month=None):
    """核心画像引擎。
    
    参数:
        df: 清洗后的行级数据（已做负销量过滤、Winsorization）
        latest_month: 最新月份（Period对象）
        thr: 阈值字典
        name_col, date_col, qty_col, rev_col, profit_col, cust_col, order_col, cat_col: 列名
        ref_priority: 参照组优先级列表
        wgt: 风险因子权重
        mode: 'full'=完整计算, 'portrait_only'=仅画像+风险评分
        prod_month: 可选，预聚合的产品月度数据。为None时从df实时聚合。
    
    返回:
        (result_df, data_insufficient_list, out, ratio_cols, pp_cols, _t4)
    """
    _t_func_start = time.time()
    
    # Winsorization统计
    _winsor_low = float(thr.get("winsor_lower", -0.50))
    _winsor_high = float(thr.get("winsor_upper", 0.75))
    n_total_rows = len(df)
    n_winsor_low = int((df['_毛利率'] == _winsor_low).sum())
    n_winsor_high = int((df['_毛利率'] == _winsor_high).sum())
    n_winsor_total = n_winsor_low + n_winsor_high
    print(f"  Winsorization 钳制: {n_winsor_total}/{n_total_rows}行 "
          f"({n_winsor_total/n_total_rows*100:.1f}%) "
          f"[下限{n_winsor_low}行/{n_winsor_low/n_total_rows*100:.1f}%, "
          f"上限{n_winsor_high}行/{n_winsor_high/n_total_rows*100:.1f}%]")
    
    recent_mask = df['_月'] > (latest_month - 12)
    prior_mask = (df['_月'] <= (latest_month - 12)) & (df['_月'] > (latest_month - 24))
    
    df_recent = df[recent_mask].copy()
    df_prior = df[prior_mask].copy()
    
    # 配置参数读取
    new_product_mode = str(thr.get("new_product_mode", "月数")).strip()
    min_history_months = int(thr.get("new_product_months", 6))
    min_record_months = int(thr.get("min_record_months", 3))
    min_volume = float(thr.get("new_product_min_volume", 100))
    min_products_ref = int(thr.get("参照组最低产品数", 3))
    
    print(f"新品判定模式: {new_product_mode}")
    if new_product_mode == "月数":
        print(f"  日历月龄 < {min_history_months} 个月 → 新品观察")
        print(f"  日历月龄 < {min_record_months} 个月 → 仅记录（不入快照表）")
    elif new_product_mode == "销量":
        print(f"  近12月总销量 < {min_volume} → 新品观察")
    print(f"参照组最低产品数: {min_products_ref}")
    
    # 预聚合（如有缓存则跳过实时聚合）
    products = df[name_col].unique()
    
    if prod_month is not None:
        # 使用缓存的聚合数据，过滤到当前时间点
        prod_month = prod_month[prod_month['_月'] <= latest_month].copy()
        prod_info = prod_month.groupby(name_col).agg(
            first_month=('_月', 'min'), last_month=('_月', 'max'),
            active_months=('_月', 'nunique')
        ).reset_index()
        prod_info['calendar_age'] = prod_info.apply(
            lambda r: calc_age_months(r['first_month'], r['last_month']), axis=1
        )
    else:
        if order_col and order_col in df.columns:
            prod_month = df.groupby([name_col, '_月']).agg(
                qty_sum=(qty_col, 'sum'),
                rev_pos=(rev_col, lambda x: x[x > 0].sum()),
                profit_clip_sum=('_利润_裁剪', 'sum'),
                _order_count=(order_col, 'nunique')
            ).reset_index().sort_values([name_col, '_月'])
        else:
            prod_month = df.groupby([name_col, '_月']).agg(
                qty_sum=(qty_col, 'sum'),
                rev_pos=(rev_col, lambda x: x[x > 0].sum()),
                profit_clip_sum=('_利润_裁剪', 'sum'),
                _order_count=(qty_col, lambda x: 1)
            ).reset_index().sort_values([name_col, '_月'])
        
        prod_month['_avg_price'] = prod_month['rev_pos'] / prod_month['qty_sum'].replace(0, float('nan'))
        
        prod_info = df.groupby(name_col).agg(
            first_month=('_月', 'min'), last_month=('_月', 'max'),
            active_months=('_月', 'nunique')
        ).reset_index()
        prod_info['calendar_age'] = prod_info.apply(
            lambda r: calc_age_months(r['first_month'], r['last_month']), axis=1
        )
    
    # 参照组归属
    if cat_col and cat_col in df.columns:
        cm = df.groupby(name_col)[cat_col].apply(
            lambda x: x.mode().iloc[0] if not x.mode().empty else "未分类"
        ).reset_index()
        cm.columns = [name_col, '_ref_group']
    else:
        cm = pd.DataFrame({name_col: prod_info[name_col], '_ref_group': '未分类'})
    prod_info = prod_info.merge(cm, on=name_col, how='left')
    prod_info['_ref_group'] = prod_info['_ref_group'].fillna('未分类')
    
    # 近12月销量
    rq = df_recent.groupby(name_col)[qty_col].sum().reset_index()
    rq.columns = [name_col, 'recent_qty']
    prod_info = prod_info.merge(rq, on=name_col, how='left')
    prod_info['recent_qty'] = prod_info['recent_qty'].fillna(0)
    
    # 近12月营收
    rr = df_recent.groupby(name_col)[rev_col].sum().reset_index()
    rr.columns = [name_col, 'recent_rev']
    prod_info = prod_info.merge(rr, on=name_col, how='left')
    prod_info['recent_rev'] = prod_info['recent_rev'].fillna(0)
    
    # 首次单笔销量>=6K的日期
    first_6k_threshold = int(thr.get("first_6k_threshold", 6000))
    f6k = df[df[qty_col] >= first_6k_threshold].groupby(name_col)[date_col].min().reset_index()
    f6k.columns = [name_col, 'first_6k_date']
    prod_info = prod_info.merge(f6k, on=name_col, how='left')
    
    # 客户集中度
    if cust_col and cust_col in df.columns:
        cr = df_recent.groupby([name_col, cust_col])[rev_col].sum().reset_index()
        def conc_top(g):
            tot = g[rev_col].sum()
            if tot == 0:
                return pd.Series({'top1_ratio': 0.0, 'top3_ratio': 0.0})
            s = g[rev_col].sort_values(ascending=False)
            return pd.Series({
                'top1_ratio': s.iloc[0] / tot,
                'top3_ratio': s.iloc[:3].sum() / tot if len(s) >= 3 else 1.0
            })
        cc = cr.groupby(name_col).apply(conc_top).reset_index()
        prod_info = prod_info.merge(cc, on=name_col, how='left')
        prod_info['top1_ratio'] = prod_info['top1_ratio'].fillna(0)
        prod_info['top3_ratio'] = prod_info['top3_ratio'].fillna(0)
    else:
        prod_info['top1_ratio'] = 0
        prod_info['top3_ratio'] = 0
    
    # 新品判定标记（优先级：ERP标记 > 自动计算）
    if "新品标记" in df.columns:
        # 使用ERP"是否新品"标记：近12个月中有任意行标记为"是"即为新品
        _prod_new_flag = df_recent.groupby(name_col)["新品标记"].apply(
            lambda s: (s == "是").any()
        ).reset_index()
        _prod_new_flag.columns = [name_col, "is_new"]
        prod_info = prod_info.merge(_prod_new_flag, on=name_col, how="left")
        prod_info["is_new"] = prod_info["is_new"].fillna(False)
        print(f"  [新品判定] 使用ERP标记（新品标记列），新品数: {prod_info['is_new'].sum()}")
    else:
        # 回退模式：自动计算（月龄或销量）
        prod_info['is_new'] = prod_info['calendar_age'] < min_history_months if new_product_mode == '月数' else prod_info['recent_qty'] < min_volume
        print(f"  [新品判定] 无ERP标记，使用自动计算（{new_product_mode}），新品数: {prod_info['is_new'].sum()}")
    
    # 数据不足产品清单
    data_insufficient_mask = prod_info['calendar_age'] < min_record_months
    data_insufficient_df = prod_info[data_insufficient_mask][
        [name_col, 'calendar_age', 'active_months', 'first_month', 'last_month', 'recent_qty']
    ].copy()
    data_insufficient_df.columns = ['产品名称', '日历月龄', '活跃月数', '首次发货月', '最后发货月', '近12月销量']
    data_insufficient_df['首次发货月'] = data_insufficient_df['首次发货月'].apply(lambda x: str(x) if pd.notna(x) else '')
    data_insufficient_df['最后发货月'] = data_insufficient_df['最后发货月'].apply(lambda x: str(x) if pd.notna(x) else '')
    data_insufficient_list = data_insufficient_df.to_dict('records')
    valid_prods = prod_info[~data_insufficient_mask].copy()
    
    # 逐个产品计算指标
    print(f"产品总数: {len(products)}")
    _t_preloop = time.time()
    print(f"  [计时] 窗口划分+预聚合: {_t_preloop - _t_func_start:.1f}s")
    
    results = []
    pm_dict = {k: v.set_index('_月').sort_index() for k, v in prod_month.groupby(name_col)}
    
    for _, pinfo in valid_prods.iterrows():
        prod = pinfo[name_col]
        row_out = {"产品名称": prod}
        first_month = pinfo['first_month']
        last_month = pinfo['last_month']
        calendar_age = pinfo['calendar_age']
        active_months = pinfo['active_months']
        
        row_out["日历月龄"] = calendar_age
        row_out["活跃月数"] = active_months
        row_out["最新数据月份"] = str(latest_month)
        
        pm = pm_dict.get(prod, pd.DataFrame())
        
        # 僵尸产品复活/清仓偶发判定
        recent_24m_mask = (pm.index > (latest_month - 24))
        active_in_24m = pm.loc[recent_24m_mask, 'qty_sum'].apply(lambda x: x > 0).sum()
        
        if calendar_age >= 24 and active_in_24m <= 2:
            row_out["当前画像"] = "清仓/偶发"
            row_out["管理层摘要"] = "退出区"
            row_out["通用策略建议"] = "僵尸产品偶发销售，不作为正常周期分析"
            row_out["近12月销量"] = pinfo['recent_qty']
            row_out["近12月毛利率%"] = None
            row_out["当月毛利率%"] = None
            row_out["自比健康度%"] = None
            row_out["他比健康度(pp)"] = None
            row_out["_ref_group"] = pinfo['_ref_group']
            row_out["所属参照组"] = pinfo['_ref_group']
            row_out["客户集中度-前1大%"] = pinfo['top1_ratio']
            row_out["客户集中度-前3大%"] = pinfo['top3_ratio']
            row_out["衰退风险得分"] = None
            row_out["衰退风险等级"] = "暂无评分"
            row_out["_margin"] = np.nan
            row_out["_rev"] = 0
            row_out["近12月销售额"] = pinfo.get('recent_rev', 0)
            row_out["前12月销售额"] = None
            row_out["_首次发货月"] = first_month
            row_out["_最后发货月"] = last_month
            results.append(row_out)
            continue
        
        # 新品判定
        if pinfo['is_new']:
            recent_mask_pm = pm.index > (latest_month - 12)
            recent_qty_val = pinfo['recent_qty']
            recent_rev_val = pm.loc[recent_mask_pm, 'rev_pos'].sum()
            recent_profit_clipped = pm.loc[recent_mask_pm, 'profit_clip_sum'].sum()
            recent_margin_val = recent_profit_clipped / recent_rev_val if recent_rev_val > 0 else 0
            
            row_out["当前画像"] = "新品观察"
            row_out["管理层摘要"] = "待观察"
            row_out["通用策略建议"] = "持续跟踪，暂不参与周期判断"
            curr_mask = pm.index == latest_month
            curr_profit = pm.loc[curr_mask, 'profit_clip_sum'].sum() if curr_mask.any() else 0
            curr_rev = pm.loc[curr_mask, 'rev_pos'].sum() if curr_mask.any() else 0
            curr_margin = curr_profit / curr_rev if curr_rev > 0 else None
            
            row_out["近12月销量"] = recent_qty_val
            row_out["近12月毛利率%"] = recent_margin_val
            row_out["当月毛利率%"] = curr_margin
            row_out["自比健康度%"] = None
            row_out["历史参照毛利率%"] = None
            row_out["参照组加权均值%"] = None
            row_out["参照组均值来源"] = ""
            row_out["他比健康度(pp)"] = None
            row_out["公司加权均值%"] = None
            row_out["vs公司均值(pp)"] = None
            row_out["客户集中度-前1大%"] = pinfo['top1_ratio']
            row_out["客户集中度-前3大%"] = pinfo['top3_ratio']
            row_out["所属参照组"] = pinfo['_ref_group']
            row_out["_ref_group"] = pinfo['_ref_group']
            row_out["_margin"] = recent_margin_val
            row_out["_rev"] = recent_rev_val
            results.append(row_out)
            continue
        
        # 正常产品完整计算
        recent_mask_pm = pm.index > (latest_month - 12)
        prior_mask_pm = (pm.index <= (latest_month - 12)) & (pm.index > (latest_month - 24))
        
        recent_qty_val = pm.loc[recent_mask_pm, 'qty_sum'].sum()
        prior_qty_val = pm.loc[prior_mask_pm, 'qty_sum'].sum()
        recent_rev_val = pm.loc[recent_mask_pm, 'rev_pos'].sum()
        prior_rev_val = pm.loc[prior_mask_pm, 'rev_pos'].sum()
        recent_profit_clipped = pm.loc[recent_mask_pm, 'profit_clip_sum'].sum()
        prior_profit_clipped = pm.loc[prior_mask_pm, 'profit_clip_sum'].sum()
        recent_months = pm.loc[recent_mask_pm].shape[0]
        prior_months = pm.loc[prior_mask_pm].shape[0]
        
        row_out["近12月销量"] = recent_qty_val
        row_out["前12月销量"] = prior_qty_val
        row_out["近12月销售额"] = recent_rev_val
        row_out["前12月销售额"] = prior_rev_val
        
        # 增长率（月均法），自动缩窗
        growth_window_label = "12月"
        MIN_MONTHS = 2
        if prior_months >= MIN_MONTHS and prior_qty_val > 0:
            recent_avg = recent_qty_val / recent_months if recent_months > 0 else 0
            prior_avg = prior_qty_val / prior_months
            growth = (recent_avg - prior_avg) / prior_avg
        else:
            prior6_mask = (pm.index <= (latest_month - 6)) & (pm.index > (latest_month - 12))
            prior6_qty = pm.loc[prior6_mask, 'qty_sum'].sum()
            prior6_months = pm.loc[prior6_mask].shape[0]
            if prior6_months >= MIN_MONTHS and prior6_qty > 0:
                recent6_mask = pm.index > (latest_month - 6)
                recent6_qty = pm.loc[recent6_mask, 'qty_sum'].sum()
                recent6_months = pm.loc[recent6_mask].shape[0]
                recent6_avg = recent6_qty / recent6_months if recent6_months > 0 else 0
                prior6_avg = prior6_qty / prior6_months
                growth = (recent6_avg - prior6_avg) / prior6_avg
                growth_window_label = "6月"
            else:
                prior3_mask = (pm.index <= (latest_month - 3)) & (pm.index > (latest_month - 6))
                prior3_qty = pm.loc[prior3_mask, 'qty_sum'].sum()
                prior3_months = pm.loc[prior3_mask].shape[0]
                if prior3_months >= MIN_MONTHS and prior3_qty > 0:
                    recent3_mask = pm.index > (latest_month - 3)
                    recent3_qty = pm.loc[recent3_mask, 'qty_sum'].sum()
                    recent3_months = pm.loc[recent3_mask].shape[0]
                    recent3_avg = recent3_qty / recent3_months if recent3_months > 0 else 0
                    prior3_avg = prior3_qty / prior3_months
                    growth = (recent3_avg - prior3_avg) / prior3_avg
                    growth_window_label = "3月"
                else:
                    growth = 0.0
                    growth_window_label = "无参照"
        
        growth_raw = growth
        growth = max(-1.0, min(growth, 5.0))
        row_out["近12月增长率%"] = growth
        row_out["_growth_window"] = growth_window_label
        row_out["_growth_clamped"] = (growth_raw != growth)
        
        # 毛利率
        recent_margin_val = recent_profit_clipped / recent_rev_val if recent_rev_val > 0 else 0
        prior_margin_val = prior_profit_clipped / prior_rev_val if prior_rev_val > 0 else 0
        curr_mask = pm.index == latest_month
        curr_profit = pm.loc[curr_mask, 'profit_clip_sum'].sum() if curr_mask.any() else 0
        curr_rev = pm.loc[curr_mask, 'rev_pos'].sum() if curr_mask.any() else 0
        curr_margin = curr_profit / curr_rev if curr_rev > 0 else None
        
        row_out["近12月毛利率%"] = recent_margin_val
        row_out["当月毛利率%"] = curr_margin
        row_out["前12月毛利率%"] = prior_margin_val
        row_out["毛利率同比变化(pp)"] = (recent_margin_val - prior_margin_val) * 100
        
        # 营收增长率 + 营收-毛利综合判断
        growth_lower = float(thr.get("rev_growth_lower", -1.0))
        growth_upper = float(thr.get("rev_growth_upper", 5.0))
        rev_growth = 0.0
        if prior_rev_val > 0 and prior_months >= 2:
            recent_rev_avg = recent_rev_val / recent_months if recent_months > 0 else 0
            prior_rev_avg = prior_rev_val / prior_months
            rev_growth = (recent_rev_avg - prior_rev_avg) / prior_rev_avg
        rev_growth = max(growth_lower, min(rev_growth, growth_upper))
        row_out["营收增长率%"] = rev_growth
        if rev_growth > 0 and recent_margin_val > prior_margin_val:
            row_out["营收-毛利综合判断"] = "双增"
        elif rev_growth > 0 and recent_margin_val <= prior_margin_val:
            row_out["营收-毛利综合判断"] = "增收不增利"
        elif rev_growth <= 0 and recent_margin_val > prior_margin_val:
            row_out["营收-毛利综合判断"] = "减收增利"
        else:
            row_out["营收-毛利综合判断"] = "双降"
        
        # 帕累托分类
        para_key = float(thr.get("pareto_key_revenue", 100)) * 10000
        para_reg = float(thr.get("pareto_regular_revenue", 10)) * 10000
        if recent_rev_val >= para_key:
            row_out["帕累托分类"] = "重点产品"
        elif recent_rev_val >= para_reg:
            row_out["帕累托分类"] = "常规产品"
        else:
            row_out["帕累托分类"] = "潜力产品"
        
        # 首次6K日期
        f6k_date = pinfo.get('first_6k_date')
        if pd.notna(f6k_date):
            row_out["首次6K日期"] = f6k_date.strftime('%Y-%m-%d')
            row_out["是否已达6K"] = "是"
            f6k_period = pd.Period(f6k_date, freq='M')
            if pd.notna(first_month):
                row_out["首次6K用时(月)"] = (f6k_period - first_month).n + 1
            else:
                row_out["首次6K用时(月)"] = None
        else:
            row_out["首次6K日期"] = None
            row_out["是否已达6K"] = "否"
            row_out["首次6K用时(月)"] = None
        
        # 历史参照毛利率
        monthly_margins = (pm['profit_clip_sum'] / pm['rev_pos'].replace(0, np.nan)).dropna()
        monthly_margins = monthly_margins[monthly_margins > 0]
        hist_pct = float(thr.get("ref_percentile", 0.95))
        short_age_threshold = int(thr.get("ref_short_age_months", 12))
        short_age_pct = float(thr.get("ref_short_percentile", 0.50))
        min_effective_months = int(thr.get("ref_p95_min_months", 20))
        long_ref_months = int(thr.get("ref_long_months", 24))
        long_ref_pct = float(thr.get("ref_long_percentile", 0.80))
        min_data_for_robust_pct = int(thr.get("ref_robust_min_points", 6))
        
        if len(monthly_margins) == 0:
            hist_ref_margin = 0
        elif calendar_age < short_age_threshold:
            if len(monthly_margins) < min_data_for_robust_pct:
                robust_pct = short_age_pct * 0.6
                hist_ref_margin = monthly_margins.quantile(robust_pct)
            else:
                hist_ref_margin = monthly_margins.quantile(short_age_pct)
        else:
            n_effective = len(monthly_margins)
            if n_effective >= min_effective_months:
                hist_ref_margin = monthly_margins.quantile(hist_pct)
            else:
                fallback_pct = max(0.90, short_age_pct + 0.10)
                hist_ref_margin = monthly_margins.quantile(fallback_pct)
        row_out["历史参照毛利率%"] = hist_ref_margin
        
        if calendar_age >= 36:
            recent_n = min(long_ref_months, len(monthly_margins))
            recent_margins = monthly_margins.iloc[-recent_n:]
            long_ref_margin = recent_margins.quantile(long_ref_pct)
            row_out["长期参照毛利率%"] = long_ref_margin
        else:
            row_out["长期参照毛利率%"] = None
        
        # 自比健康度
        if len(monthly_margins) == 0:
            self_health = 0.0
            row_out["_no_valid_hist_margin"] = True
        elif recent_margin_val < 0:
            self_health = 0.0
            row_out["_no_valid_hist_margin"] = False
            row_out["_negative_margin"] = True
        else:
            self_health = recent_margin_val / hist_ref_margin if hist_ref_margin > 0 else 1.0
            row_out["_no_valid_hist_margin"] = False
            row_out["_negative_margin"] = False
        row_out["自比健康度%"] = self_health
        
        row_out["所属参照组"] = pinfo['_ref_group']
        row_out["_ref_group"] = pinfo['_ref_group']
        row_out["_margin"] = recent_margin_val
        row_out["_rev"] = recent_rev_val
        
        # 趋势斜率
        all_months = pd.period_range(latest_month - 11, latest_month, freq='M')
        margin_series = pd.Series(index=all_months, dtype=float)
        for m in all_months:
            if m in pm.index:
                sub = pm.loc[[m]]
                pos_rev = sub['rev_pos'].sum()
                if pos_rev > 0:
                    margin_series[m] = sub['profit_clip_sum'].sum() / pos_rev
                else:
                    margin_series[m] = np.nan
            else:
                margin_series[m] = np.nan
        
        slope_ratio = calc_slope(margin_series.values)
        row_out["_slope_ratio"] = slope_ratio
        row_out["毛利率趋势斜率%/月"] = slope_ratio * 100
        
        recent_margin_vals = margin_series.values
        recent_valid = recent_margin_vals[~np.isnan(recent_margin_vals)]
        zero_profit = (len(recent_valid) > 0 and np.max(recent_valid) <= 0.001)
        
        valid_margin_count = len(recent_valid)
        min_slope_pts = int(thr.get("slope_min_data_points", 3))
        if zero_profit:
            row_out["_zero_profit"] = True
            row_out["斜率等级"] = classify_slope_level(slope_ratio, thr, zero_profit=True)
            row_out["_slope_data_insufficient"] = False
        elif valid_margin_count < min_slope_pts:
            row_out["_zero_profit"] = False
            row_out["斜率等级"] = "数据不足"
            row_out["_slope_data_insufficient"] = True
        else:
            row_out["_zero_profit"] = False
            row_out["斜率等级"] = classify_slope_level(slope_ratio, thr)
            row_out["_slope_data_insufficient"] = False
        
        # 增速变化
        if calendar_age >= 24:
            prior_12_mask = (pm.index <= (latest_month - 12)) & (pm.index > (latest_month - 24))
            prior_12_qty = pm.loc[prior_12_mask, 'qty_sum'].sum()
            prior_12_months = pm.loc[prior_12_mask].shape[0]
            prior_12_prior_mask = (pm.index <= (latest_month - 24)) & (pm.index > (latest_month - 36))
            prior_12_prior_qty = pm.loc[prior_12_prior_mask, 'qty_sum'].sum()
            prior_12_prior_months = pm.loc[prior_12_prior_mask].shape[0]
            prior_12_avg = prior_12_qty / prior_12_months if prior_12_months > 0 else 0
            prior_12_prior_avg = prior_12_prior_qty / prior_12_prior_months if prior_12_prior_months > 0 else 0
            prior_12_growth = (prior_12_avg - prior_12_prior_avg) / prior_12_prior_avg if prior_12_prior_avg > 0 else 0
            growth_change = growth - prior_12_growth
            row_out["前12月增长率%"] = prior_12_growth
            row_out["增速变化(pp)"] = growth_change * 100
            row_out["增速方向"] = "加速" if growth_change > 0 else "减速"
        else:
            row_out["前12月增长率%"] = None
            row_out["增速变化(pp)"] = None
            row_out["增速方向"] = ""
        
        row_out["客户集中度-前1大%"] = pinfo['top1_ratio']
        row_out["客户集中度-前3大%"] = pinfo['top3_ratio']
        
        # 订货波动性CV
        monthly_qty_series = pm.loc[recent_mask_pm, 'qty_sum']
        if recent_qty_val <= 0 or monthly_qty_series.sum() <= 0:
            row_out["订货波动性CV"] = None
            row_out["_cv_invalid"] = True
            row_out["低量品标记"] = "是"
        else:
            low_vol_threshold = float(thr.get("长尾销量阈值", 1000))
            active_recent_months = (monthly_qty_series > 0).sum()
            is_pulse_demand = (active_recent_months <= 4) and (recent_qty_val > low_vol_threshold)
            
            if monthly_qty_series.mean() < low_vol_threshold and len(monthly_qty_series) >= 6:
                median_qty = monthly_qty_series.median()
                mad = (monthly_qty_series - monthly_qty_series.median()).abs().median()
                cv = mad / median_qty if median_qty > 0 else 0
                row_out["低量品标记"] = "是"
            elif is_pulse_demand:
                cv = 0.5
                row_out["低量品标记"] = "脉冲发货"
            else:
                cv = monthly_qty_series.std() / monthly_qty_series.mean() if monthly_qty_series.mean() > 0 else 0
                row_out["低量品标记"] = "否"
            
            row_out["订货波动性CV"] = cv
            row_out["_cv_invalid"] = False
        
        # 增速衰减
        last3_mask = pm.index > (latest_month - 3)
        prior3_mask = (pm.index <= (latest_month - 3)) & (pm.index > (latest_month - 6))
        last3_qty = pm.loc[last3_mask, 'qty_sum'].sum()
        prior3_qty = pm.loc[prior3_mask, 'qty_sum'].sum()
        last3_months = pm.loc[last3_mask].shape[0]
        prior3_months = pm.loc[prior3_mask].shape[0]
        last3_avg = last3_qty / last3_months if last3_months > 0 else 0
        prior3_avg = prior3_qty / prior3_months if prior3_months > 0 else 0
        last3_growth = (last3_avg - prior3_avg) / prior3_avg if prior3_avg > 0 else 0
        decay = (last3_growth - growth) * 100
        row_out["增速衰减(pp)"] = decay
        
        # 近3月同比下降
        yoy_change = None
        if calendar_age >= 15:
            yoy_last3_mask = (pm.index > (latest_month - 15)) & (pm.index <= (latest_month - 12))
            yoy_last3_qty = pm.loc[yoy_last3_mask, 'qty_sum'].sum()
            yoy_last3_months = pm.loc[yoy_last3_mask].shape[0]
            yoy_last3_avg = yoy_last3_qty / yoy_last3_months if yoy_last3_months > 0 else 0
            if yoy_last3_avg > 0:
                yoy_change = (last3_avg - yoy_last3_avg) / yoy_last3_avg
        row_out["_yoy_change"] = yoy_change
        
        row_out["_首次发货月"] = first_month
        row_out["_最后发货月"] = last_month
        
        # ASP趋势
        monthly_qty_arr = pm.loc[recent_mask_pm, 'qty_sum'].values
        monthly_prices = pm.loc[recent_mask_pm, '_avg_price'].values
        asp_slope, asp_reliable_flag = calc_asp_trend(monthly_prices, thr)
        row_out["ASP趋势%/月"] = asp_slope * 100 if asp_reliable_flag else None
        row_out["_asp_insufficient"] = not asp_reliable_flag
        asp_up_threshold = float(thr.get("asp_rising_pct", 0.5)) / 100
        asp_down_threshold = float(thr.get("asp_falling_pct", -0.5)) / 100
        if asp_slope > asp_up_threshold:
            row_out["ASP趋势方向"] = "上升"
        elif asp_slope < asp_down_threshold:
            row_out["ASP趋势方向"] = "下降"
        else:
            row_out["ASP趋势方向"] = "平稳"
        
        slope_ratio_check = row_out.get("_slope_ratio", 0)
        asp_diag_t = float(thr.get("joint_asp_pct", -0.5)) / 100
        margin_diag_t = float(thr.get("joint_margin_pct", -0.3)) / 100
        if asp_slope < asp_diag_t and slope_ratio_check < margin_diag_t:
            row_out["ASP-毛利率联合诊断"] = "价格战风险"
        elif asp_slope > asp_diag_t and slope_ratio_check < margin_diag_t:
            row_out["ASP-毛利率联合诊断"] = "成本问题"
        elif asp_slope < asp_diag_t and slope_ratio_check > margin_diag_t:
            row_out["ASP-毛利率联合诊断"] = "规模效应"
        else:
            row_out["ASP-毛利率联合诊断"] = "正常"
        
        # 全量模式：ETS预测 + 价格弹性 + 订单频次
        if mode == 'full':
            monthly_periods = pm.loc[recent_mask_pm].index
            pred_months = int(thr.get("forecast_months", 3))
            seasonal_p = int(thr.get("ets_seasonal_periods", 0))
            ma_window = int(thr.get("forecast_ma_window", 3))
            
            ets_result = ets_forecast(monthly_qty_arr, periods=pred_months, seasonal_periods=seasonal_p)
            if ets_result and ets_result[0] is not None:
                forecast_vals, direction, pred_intervals, model_info = ets_result
                forecast_periods = [latest_month + i + 1 for i in range(pred_months)]
                holiday_adjs = prepare_holiday_adjustment(monthly_qty_arr, monthly_periods, forecast_periods, thr)
                adjusted_forecast = [max(0, round(v * adj, 0)) for v, adj in zip(forecast_vals, holiday_adjs)]
                
                row_out["预测算法"] = "ETS+节假日调整"
                row_out["预测模型类型"] = model_info.get('model_type', '')
                row_out["预测_AIC"] = model_info.get('aic')
                for i in range(pred_months):
                    row_out[f"预测第{i+1}月销量"] = adjusted_forecast[i] if i < len(adjusted_forecast) else None
                row_out["销量趋势预测"] = direction
                
                output_ci = int(thr.get("ets_output_ci", 1))
                if output_ci and pred_intervals:
                    for ci_label in [80, 95]:
                        lower, upper = pred_intervals.get(ci_label, (None, None))
                        if lower and upper:
                            adj_lower = [max(0, round(l * a, 0)) for l, a in zip(lower, holiday_adjs)]
                            adj_upper = [max(0, round(u * a, 0)) for u, a in zip(upper, holiday_adjs)]
                            for m_idx in range(pred_months):
                                row_out[f"预测_第{m_idx+1}月_置信下限{ci_label}%"] = adj_lower[m_idx] if m_idx < len(adj_lower) else None
                                row_out[f"预测_第{m_idx+1}月_置信上限{ci_label}%"] = adj_upper[m_idx] if m_idx < len(adj_upper) else None
                        else:
                            for m_idx in range(pred_months):
                                row_out[f"预测_第{m_idx+1}月_置信下限{ci_label}%"] = None
                                row_out[f"预测_第{m_idx+1}月_置信上限{ci_label}%"] = None
                if any(adj != 1.0 for adj in holiday_adjs):
                    row_out["节假日调整系数"] = ",".join([f"{a:.2f}" for a in holiday_adjs])
                else:
                    row_out["节假日调整系数"] = "无"
            else:
                ma_forecast_vals, ma_direction = weighted_ma_forecast(monthly_qty_arr, periods=pred_months, window=ma_window)
                row_out["预测算法"] = "WMA兜底"
                row_out["预测模型类型"] = ""
                row_out["预测_AIC"] = None
                for i in range(pred_months):
                    row_out[f"预测第{i+1}月销量"] = round(ma_forecast_vals[i], 0) if ma_forecast_vals else None
                row_out["销量趋势预测"] = ma_direction if ma_forecast_vals else "无数据"
                row_out["节假日调整系数"] = "无"
                for ci_label in [80, 95]:
                    for m_idx in range(pred_months):
                        row_out[f"预测_第{m_idx+1}月_置信下限{ci_label}%"] = None
                        row_out[f"预测_第{m_idx+1}月_置信上限{ci_label}%"] = None
            
            elasticity, sensitivity = calc_price_elasticity(monthly_prices, monthly_qty_arr, thr)
            row_out["价格弹性系数"] = round(elasticity, 2) if elasticity is not None else None
            row_out["价格敏感度"] = sensitivity if elasticity is not None else "数据不足"
            
            if order_col and '_order_count' in pm.columns:
                freq_change, freq_label = calc_order_frequency_trend(pm, latest_month, thr)
                row_out["近3月月均订单数"] = round(pm.loc[last3_mask, '_order_count'].sum() / 3, 1)
                row_out["订单频次变化%"] = round(freq_change * 100, 1) if freq_change != 0 else 0
                row_out["采购意愿"] = freq_label
            else:
                row_out["近3月月均订单数"] = None
                row_out["订单频次变化%"] = None
                row_out["采购意愿"] = "无订单数据"
        
        results.append(row_out)
    
    result_df = pd.DataFrame(results)
    _t3 = time.time()
    print(f"  [计时] 逐个产品指标计算: {_t3 - _t_preloop:.1f}s ({len(valid_prods)}个有效产品)")
    
    if len(result_df) == 0:
        print("无有效产品数据，退出")
        return result_df, [], result_df, [], [], time.time()
    
    # 参照组加权均值（多级兜底）
    exit_cutoff_pre = latest_month - int(thr.get("exit_months", 12))
    exit_min_hist_pre = int(thr.get("exit_min_age_months", 3))
    not_new = result_df.copy()
    if "当前画像" in result_df.columns:
        not_new = result_df[~result_df["当前画像"].isin(["新品观察", "清仓/偶发"])].copy()
    not_new = not_new[
        ~((not_new["_最后发货月"] <= exit_cutoff_pre) & 
          (not_new["日历月龄"] >= exit_min_hist_pre))
    ].copy()
    
    if len(not_new) == 0:
        print("[警告] 所有产品均为新品观察，无足够产品计算参照组均值。")
        for i in result_df.index:
            result_df.at[i, "参照组加权均值%"] = 0
            result_df.at[i, "参照组均值来源"] = "无足够产品（全部为新品观察）"
            result_df.at[i, "他比健康度(pp)"] = 0
            result_df.at[i, "公司加权均值%"] = 0
            result_df.at[i, "vs公司均值(pp)"] = 0
    else:
        all_margins = [r["_margin"] for _, r in not_new.iterrows() 
                       if pd.notna(r["_margin"]) and r["_rev"] > 0]
        all_revs = [r["_rev"] for _, r in not_new.iterrows() 
                    if pd.notna(r["_margin"]) and r["_rev"] > 0]
        company_avg = sum(m * r for m, r in zip(all_margins, all_revs)) / sum(all_revs) if sum(all_revs) > 0 else 0
        
        all_ref_cols = set()
        for ref_col_name, _ in ref_priority:
            if ref_col_name != "（全公司均值）" and ref_col_name in df.columns:
                all_ref_cols.add(ref_col_name)
        
        product_groups = {}
        for ref_col in all_ref_cols:
            if ref_col in df.columns:
                mode_series = df.groupby(name_col)[ref_col].apply(
                    lambda x: x.mode().iloc[0] if not x.mode().empty else "未分类"
                )
                prod_group_map = mode_series.to_dict()
                for p in products:
                    if p not in prod_group_map:
                        prod_group_map[p] = "未分类"
            else:
                prod_group_map = {p: "未分类" for p in products}
            product_groups[ref_col] = prod_group_map
        
        group_stats = {}
        for ref_col in all_ref_cols:
            grp_map = product_groups[ref_col]
            valid = not_new[pd.notna(not_new["_margin"]) & (not_new["_rev"] > 0)].copy()
            if len(valid) == 0:
                continue
            valid["_grp"] = valid["产品名称"].map(grp_map).fillna("未分类")
            valid["_w_product"] = valid["_margin"] * valid["_rev"]
            grp_agg = valid.groupby("_grp").agg(
                count=("_w_product", "count"),
                rev_sum=("_rev", "sum"),
                weighted_sum=("_w_product", "sum")
            )
            for grp_val, r in grp_agg.iterrows():
                wavg = r["weighted_sum"] / r["rev_sum"] if r["rev_sum"] > 0 else 0
                group_stats[(ref_col, grp_val)] = {
                    "count": int(r["count"]),
                    "weighted_avg": wavg
                }
        
        # 列名显示映射：保持与原始v2.8输出一致
        _ref_col_display = {
            "产品二级分类": "产品系列",
        }
        
        for i, row in result_df.iterrows():
            if row.get("当前画像") in ["新品观察", "清仓/偶发"]:
                continue
            prod_name = row["产品名称"]
            ref_assigned = False
            for ref_col_name, min_n in ref_priority:
                if ref_col_name == "（全公司均值）":
                    result_df.at[i, "参照组加权均值%"] = company_avg
                    result_df.at[i, "参照组均值来源"] = "全公司均值（兜底）"
                    ref_assigned = True
                    break
                if ref_col_name not in df.columns:
                    continue
                grp_val = product_groups.get(ref_col_name, {}).get(prod_name, "未分类")
                stats = group_stats.get((ref_col_name, grp_val))
                if stats and stats["count"] >= min_n:
                    result_df.at[i, "参照组加权均值%"] = stats["weighted_avg"]
                    display_name = _ref_col_display.get(ref_col_name, ref_col_name)
                    result_df.at[i, "参照组均值来源"] = f"{display_name}: {grp_val} (n={stats['count']})"
                    ref_assigned = True
                    break
            if not ref_assigned:
                result_df.at[i, "参照组加权均值%"] = company_avg
                result_df.at[i, "参照组均值来源"] = "全公司均值（各级参照组均不满足条件）"
        
        for i, row in result_df.iterrows():
            if row.get("当前画像") in ["新品观察", "清仓/偶发"]:
                continue
            margin = row["_margin"]
            cat_avg_val = result_df.at[i, "参照组加权均值%"]
            if pd.notna(margin) and pd.notna(cat_avg_val) and cat_avg_val > 0:
                rel_health = (margin - cat_avg_val) * 100
            else:
                rel_health = 0
            result_df.at[i, "他比健康度(pp)"] = rel_health
            result_df.at[i, "公司加权均值%"] = company_avg
            result_df.at[i, "vs公司均值(pp)"] = (margin - company_avg) * 100
    
    # 退市产品检测 + 品类寿命中位数
    exit_months_val = int(thr.get("exit_months", 12))
    exit_min_hist = int(thr.get("exit_min_age_months", 3))
    exit_cutoff = latest_month - exit_months_val
    
    for i, row in result_df.iterrows():
        last_m = row.get("_最后发货月")
        first_m = row.get("_首次发货月")
        age = calc_age_months(first_m, last_m)
        if pd.notna(last_m) and pd.notna(first_m):
            is_exited = (last_m <= exit_cutoff) and (age >= exit_min_hist)
            result_df.at[i, "_退市"] = is_exited
            if is_exited:
                result_df.at[i, "_产品寿命月"] = age
        else:
            result_df.at[i, "_退市"] = False
            result_df.at[i, "_产品寿命月"] = None
    
    exited_df = result_df[result_df["_退市"] == True]
    group_lifespan = {}
    if len(exited_df) > 0:
        for grp, grp_data in exited_df.groupby("_ref_group"):
            lifespans = grp_data["_产品寿命月"].dropna()
            if len(lifespans) >= min_products_ref:
                group_lifespan[grp] = lifespans.median()
    
    # （v2.9: 因子5历史对照已移除 — 49%产品标记HL，默认分50无区分度）

    # 九宫格画像 + 风险评分
    _t4 = time.time()
    print(f"  [计时] 参照组+退市计算: {_t4 - _t3:.1f}s")
    
    tg = float(thr.get("growth_accelerate", 0.15))
    tf = float(thr.get("growth_flat_lower", -0.10))
    th_h = float(thr.get("health_healthy", 0.70))
    th_s = float(thr.get("health_severe", 0.50))
    th_r = float(thr.get("health_relative", -10))
    
    for i, row in result_df.iterrows():
        if row.get("当前画像") in ["新品观察", "清仓/偶发"]:
            continue
        
        g = row["近12月增长率%"]
        if g > tg:
            m_full, m_short = "加速增长", "量增"
        elif g > 0:
            m_full, m_short = "稳定扩张", "量增"
        elif g > tf:
            m_full, m_short = "持平", "量稳"
        else:
            m_full, m_short = "萎缩", "量跌"
        
        sh = row["自比健康度%"]
        rh = row["他比健康度(pp)"]
        is_severe = sh < th_s or rh < th_r
        if is_severe:
            h_full, h_short = "严重侵蚀", "利跌"
        elif sh >= th_h and rh >= 0:
            h_full, h_short = "健康", "利稳"
        else:
            h_full, h_short = "轻度侵蚀", "利稳"
        
        result_df.at[i, "销量动能"] = m_full
        result_df.at[i, "盈利健康"] = h_full
        
        portrait, summary, strategy = classify_9grid_full(m_full, h_full, row=result_df.iloc[i])
        result_df.at[i, "当前画像"] = portrait
        result_df.at[i, "管理层摘要"] = summary
        result_df.at[i, "通用策略建议"] = strategy
        
        # 5因子风险评分（v2.9: 移除F2客户集中度+F5历史对照，新增F5自比健康度）
        if row.get("_slope_data_insufficient"):
            s1 = int(thr.get("slope_insufficient_score", 50))
        elif row.get("斜率等级") == "无利润/异常":
            s1 = 80
        else:
            s1 = risk_slope(row["_slope_ratio"], thr, zero_profit=row.get("_zero_profit", False))

        s3 = risk_cv(row["订货波动性CV"], thr)
        s4 = risk_decay(row["增速衰减(pp)"], row.get("_yoy_change"), thr)
        s_sh = risk_self_health(row.get("自比健康度%"), thr)

        asp_val = row.get("ASP趋势%/月")
        asp_ratio = asp_val / 100 if pd.notna(asp_val) and asp_val is not None else 0
        s6 = risk_asp(asp_ratio, row.get("_slope_ratio", 0), thr)

        # 增速衰减上限保护
        growth_cap = float(thr.get("decay_explosive_cap", 1.0))
        decay_thresh = float(thr.get("decay_explosive_threshold", -100))
        s4_cap = int(thr.get("decay_explosive_s4_cap", 50))
        if row["近12月增长率%"] > growth_cap and row["增速衰减(pp)"] < decay_thresh:
            last3_growth_ratio = row.get("_yoy_change")
            if last3_growth_ratio is not None and pd.notna(last3_growth_ratio) and last3_growth_ratio <= 0:
                result_df.at[i, "_decay_cap_removed"] = True
            else:
                s4 = min(s4, s4_cap)
                result_df.at[i, "_decay_cap_removed"] = False

        result_df.at[i, "因子1得分(斜率)"] = round(s1)
        result_df.at[i, "因子3得分(波动)"] = round(s3)
        result_df.at[i, "因子4得分(衰减)"] = round(s4)
        result_df.at[i, "因子5得分(自比健康度)"] = round(s_sh)
        result_df.at[i, "因子6得分(ASP)"] = round(s6)

        # 原始权重（5因子）
        w1 = wgt.get("毛利率趋势斜率", 0.20)
        w3 = wgt.get("订货波动性(CV)", 0.10)
        w4 = wgt.get("增速衰减", 0.20)
        w_sh = wgt.get("自比健康度", 0.35)
        w6 = wgt.get("ASP趋势", 0.15)

        # 可靠标记
        slope_reliable = not row.get("_slope_data_insufficient", False) and not row.get("_zero_profit", False)
        cv_reliable = not row.get("_cv_invalid", False)
        decay_reliable = True
        sh_reliable = not row.get("_no_valid_hist_margin", False)
        asp6_reliable = not row.get("_asp_insufficient", True)

        w = [w1, w3, w4, w_sh, w6]
        reliable = [slope_reliable, cv_reliable, decay_reliable, sh_reliable, asp6_reliable]
        for idx in range(5):
            if not reliable[idx]:
                w[idx] = 0.0

        sum_w = sum(w)
        if sum_w > 0:
            w = [wi / sum_w for wi in w]

        result_df.at[i, "_w_斜率"] = round(w[0], 4)
        result_df.at[i, "_w_波动"] = round(w[1], 4)
        result_df.at[i, "_w_衰减"] = round(w[2], 4)
        result_df.at[i, "_w_自比健康度"] = round(w[3], 4)
        result_df.at[i, "_w_ASP"] = round(w[4], 4)
        result_df.at[i, "_w_sum"] = round(sum_w, 4)

        total = s1 * w[0] + s3 * w[1] + s4 * w[2] + s_sh * w[3] + s6 * w[4]
        result_df.at[i, "衰退风险得分"] = round(total, 1)

        # 衰退期最低分保护（仅对非SH部分施加）
        if result_df.at[i, "当前画像"] == "衰退期":
            margin_val = row.get("近12月毛利率%", 0) or 0
            qty_val = row.get("近12月销量", 0) or 0
            exit_min_risk = int(thr.get("decay_portrait_min_risk", 50))
            if margin_val <= 0 or qty_val <= 0:
                non_sh_weight = w[0] + w[1] + w[2] + w[4]
                if non_sh_weight > 0:
                    non_sh_score = (s1 * w[0] + s3 * w[1] + s4 * w[2] + s6 * w[4]) / non_sh_weight
                    if non_sh_score < exit_min_risk:
                        total = (exit_min_risk * non_sh_weight + s_sh * w[3]) / sum_w
                        result_df.at[i, "衰退风险得分"] = round(total, 1)

        contributions = {
            "毛利率斜率": s1 * w[0],
            "订货波动":   s3 * w[1],
            "增速衰减":   s4 * w[2],
            "自比健康度": s_sh * w[3],
            "ASP趋势":    s6 * w[4],
        }
        dominant = max(contributions, key=contributions.get)
        result_df.at[i, "风险主导因子"] = dominant

        t_low = float(thr.get("risk_low_max", 25))
        t_mid = float(thr.get("risk_mid_max", 50))
        t_high = float(thr.get("risk_high_max", 75))
        if total <= t_low:
            result_df.at[i, "衰退风险等级"] = "低风险"
        elif total <= t_mid:
            result_df.at[i, "衰退风险等级"] = "中风险"
        elif total <= t_high:
            result_df.at[i, "衰退风险等级"] = "高风险"
        else:
            result_df.at[i, "衰退风险等级"] = "极高风险"

        result_df.at[i, "特情说明"] = generate_specific_note(result_df.iloc[i], thr)

        # 数据质量标记（v2.9 移除CM/HL）
        quality_flags = []
        if row.get("_zero_profit"):
            quality_flags.append("ZP")
        if row.get("_negative_margin"):
            quality_flags.append("NM")
        if row.get("_slope_data_insufficient"):
            quality_flags.append("SL")
        if row.get("_cv_invalid"):
            quality_flags.append("CV")
        if row.get("_asp_insufficient"):
            quality_flags.append("AS")
        if row.get("_growth_clamped"):
            quality_flags.append("GC")
        if row.get("近12月销量", 0) == 0 and row.get("当前画像") not in ["新品观察", "清仓/偶发"]:
            quality_flags.append("ZS")
        if row.get("_no_valid_hist_margin"):
            quality_flags.append("NH")
        result_df.at[i, "数据质量标记"] = ",".join(quality_flags) if quality_flags else "全部可靠"
    
    # 整理输出列
    output_cols = [
        "产品名称", "所属参照组", "帕累托分类",
        "最新数据月份", "日历月龄", "活跃月数",
        "首次6K日期", "首次6K用时(月)", "是否已达6K",
        "当前画像", "管理层摘要", "销量动能", "盈利健康",
        "近12月销量", "前12月销量",
        "近12月增长率%", "前12月增长率%", "增速方向", "增速变化(pp)", "增速衰减(pp)", "低量品标记",
        "近12月销售额", "前12月销售额", "营收增长率%", "营收-毛利综合判断",
        "当月毛利率%", "近12月毛利率%",
        "前12月毛利率%", "毛利率同比变化(pp)",
        "历史参照毛利率%", "长期参照毛利率%",
        "自比健康度%", "他比健康度(pp)",
        "参照组加权均值%", "参照组均值来源",
        "公司加权均值%", "vs公司均值(pp)",
        "毛利率趋势斜率%/月", "斜率等级",
        "ASP趋势%/月",
        "ASP趋势方向", "ASP-毛利率联合诊断",
        "客户集中度-前1大%", "客户集中度-前3大%",
        "订货波动性CV",
        "近3月月均订单数", "订单频次变化%", "采购意愿",
        "价格弹性系数", "价格敏感度",
        "衰退风险得分", "衰退风险等级", "风险主导因子",
        "因子1得分(斜率)", "因子3得分(波动)", "因子4得分(衰减)",
        "因子5得分(自比健康度)", "因子6得分(ASP)",
        "通用策略建议", "特情说明",
        "数据质量标记",
    ]
    
    output_cols = [c for c in output_cols if c in result_df.columns]
    out = result_df[output_cols].copy()
    
    ratio_cols = [
        "近12月增长率%", "前12月增长率%",
        "营收增长率%",
        "自比健康度%",
        "当月毛利率%", "近12月毛利率%", "前12月毛利率%",
        "历史参照毛利率%", "长期参照毛利率%",
        "参照组加权均值%", "公司加权均值%",
        "客户集中度-前1大%", "客户集中度-前3大%",
    ]
    
    pp_cols = [
        "增速变化(pp)", "增速衰减(pp)",
        "他比健康度(pp)", "vs公司均值(pp)",
        "毛利率同比变化(pp)",
        "毛利率趋势斜率%/月",
        "ASP趋势%/月",
    ]
    
    for c in ratio_cols:
        if c in out.columns:
            out[c] = out[c].apply(lambda x: round(x * 100, 2) if pd.notna(x) else x)
    
    for c in pp_cols:
        if c in out.columns:
            out[c] = out[c].apply(lambda x: round(x, 2) if pd.notna(x) else x)
    
    if "订货波动性CV" in out.columns:
        out["订货波动性CV"] = out["订货波动性CV"].apply(
            lambda x: round(x, 3) if pd.notna(x) else x
        )
    
    return result_df, data_insufficient_list, out, ratio_cols, pp_cols, _t4
