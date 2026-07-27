"""
客户分析函数 — 从v2.8提取的RFM分群和产品关联分析。

可被产品生命周期和客户分析复用。
"""

import pandas as pd
import numpy as np
from collections import Counter


def rfm_customer_segmentation(df, date_col, cust_col, rev_col, thr=None):
    """RFM客户分群。
    
    R=最近购买天数, F=频次, M=金额。
    
    参数:
        df: 行级销售数据
        date_col: 日期列名
        cust_col: 客户列名
        rev_col: 营收列名
        thr: 阈值字典
    
    返回:
        DataFrame: RFM分群结果
    """
    if not cust_col or cust_col not in df.columns:
        return None
    
    max_date = df[date_col].max()
    last_purchase = df.groupby(cust_col)[date_col].max()
    r_days = (max_date - last_purchase).dt.days
    f_count = df.groupby(cust_col)[date_col].nunique()
    m_total = df.groupby(cust_col)[rev_col].sum()
    
    rfm = pd.DataFrame({
        'R_天数': r_days,
        'F_频次': f_count,
        'M_金额': m_total
    }).dropna()
    
    if len(rfm) < 5:
        return rfm
    
    for col, ascending in [('R_天数', True), ('F_频次', False), ('M_金额', False)]:
        try:
            score_col = col.split('_')[0] + '_得分'
            rfm[score_col] = pd.qcut(
                rfm[col], 5,
                labels=[5, 4, 3, 2, 1] if ascending else [1, 2, 3, 4, 5],
                duplicates='drop'
            ).astype(int)
        except ValueError:
            rfm[col.split('_')[0] + '_得分'] = 3
    
    for sc in ['R_得分', 'F_得分', 'M_得分']:
        if sc not in rfm.columns:
            rfm[sc] = 3
    
    rfm['RFM总分'] = rfm['R_得分'] + rfm['F_得分'] + rfm['M_得分']
    
    def classify_customer(row):
        r, f, m = row['R_得分'], row['F_得分'], row['M_得分']
        if r >= 4 and f >= 4 and m >= 4:
            return "重要价值客户"
        elif r >= 4 and f >= 4 and m < 4:
            return "重要发展客户"
        elif r < 4 and f >= 4 and m >= 4:
            return "重要保持客户"
        elif r < 4 and f < 4 and m >= 4:
            return "重要挽留客户"
        elif r >= 4 and f < 4 and m < 4:
            return "新客户"
        else:
            return "一般客户"
    
    rfm['客户类型'] = rfm.apply(classify_customer, axis=1)
    
    churn_days = 90
    if thr:
        churn_days = int(thr.get("rfm_churn_days", 90))
    rfm['流失预警'] = rfm['R_天数'] > churn_days
    
    return rfm.reset_index().rename(columns={cust_col: '客户名称'})


def product_association_analysis(df, name_col, date_col, cust_col, thr=None):
    """产品关联分析（按客户+月份聚合的购物篮分析）。
    
    返回含支持度/置信度/提升度/杠杆率/确信度的DataFrame。
    
    参数:
        df: 行级销售数据
        name_col: 产品名称列名
        date_col: 日期列名
        cust_col: 客户列名
        thr: 阈值字典
    
    返回:
        DataFrame: 关联规则结果
    """
    if not cust_col or cust_col not in df.columns:
        return None
    if not date_col or date_col not in df.columns:
        return None
    
    min_support = 0.02
    min_confidence = 0.15
    if thr:
        min_support = float(thr.get("assoc_min_support", 0.02))
        min_confidence = float(thr.get("assoc_min_confidence", 0.15))
    
    df = df.copy()
    df['_assoc_basket'] = df[cust_col].astype(str).str.strip() + '_' + df[date_col].dt.to_period('M').astype(str)
    
    baskets = df.groupby('_assoc_basket')[name_col].apply(
        lambda x: list(set(str(v) for v in x if pd.notna(v)))
    ).reset_index()
    baskets = baskets[baskets[name_col].apply(len) >= 2]
    
    if len(baskets) < 2:
        return None
    
    total_baskets = len(baskets)
    product_counts = Counter()
    for prods in baskets[name_col]:
        product_counts.update(prods)
    
    pair_counts = Counter()
    for prods in baskets[name_col]:
        unique_prods = sorted(set(prods))
        for i in range(len(unique_prods)):
            for j in range(i + 1, len(unique_prods)):
                pair = (unique_prods[i], unique_prods[j])
                pair_counts[pair] += 1
    
    results = []
    for (p1, p2), count in pair_counts.items():
        support = count / total_baskets
        if support < min_support:
            continue
        
        sup_p1 = product_counts[p1] / total_baskets
        sup_p2 = product_counts[p2] / total_baskets
        conf_1_to_2 = count / product_counts[p1]
        conf_2_to_1 = count / product_counts[p2]
        
        lift_1_to_2 = conf_1_to_2 / sup_p2 if sup_p2 > 0 else 0
        lift_2_to_1 = conf_2_to_1 / sup_p1 if sup_p1 > 0 else 0
        
        leverage_1_to_2 = support - sup_p1 * sup_p2
        conviction_1_to_2 = (1 - sup_p2) / (1 - conf_1_to_2) if conf_1_to_2 < 1 else float('inf')
        conviction_2_to_1 = (1 - sup_p1) / (1 - conf_2_to_1) if conf_2_to_1 < 1 else float('inf')
        
        if conf_1_to_2 >= min_confidence:
            results.append({
                '产品A': p1, '产品B': p2,
                '支持度': round(support, 4),
                '置信度(A->B)': round(conf_1_to_2, 4),
                '提升度(A->B)': round(lift_1_to_2, 2),
                '杠杆率(A->B)': round(leverage_1_to_2, 4),
                '确信度(A->B)': round(conviction_1_to_2, 2),
                '共现客户月数': count
            })
        if conf_2_to_1 >= min_confidence:
            results.append({
                '产品A': p2, '产品B': p1,
                '支持度': round(support, 4),
                '置信度(A->B)': round(conf_2_to_1, 4),
                '提升度(A->B)': round(lift_2_to_1, 2),
                '杠杆率(A->B)': round(leverage_1_to_2, 4),
                '确信度(A->B)': round(conviction_2_to_1, 2),
                '共现客户月数': count
            })
    
    if not results:
        return None
    
    return pd.DataFrame(results).sort_values('支持度', ascending=False).reset_index(drop=True)
