"""
数据预聚合脚本：读取 Gold 层 CSV → 生成 6 个轻量 JSON 供看板使用。

用法:  python dashboard/build_data.py
输出:  dashboard/data/*.json
"""

import pandas as pd
import numpy as np
import os, json, sys

PROJECT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GOLD_DIR = os.path.join(PROJECT, "output", "gold")
OUT_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(OUT_DIR, exist_ok=True)

def safe_json(obj):
    """递归转换 numpy 类型为 Python 原生类型。"""
    if isinstance(obj, (np.integer,)): return int(obj)
    if isinstance(obj, (np.floating,)): return round(float(obj), 2)
    if isinstance(obj, np.ndarray): return obj.tolist()
    if isinstance(obj, pd.Period): return str(obj)
    if isinstance(obj, dict): return {k: safe_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)): return [safe_json(v) for v in obj]
    if pd.isna(obj): return None
    return obj

def write_json(data, name):
    path = os.path.join(OUT_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(safe_json(data), f, ensure_ascii=False)
    size_kb = os.path.getsize(path) / 1024
    print(f"  [OK] {name} ({size_kb:.1f} KB)")

# ═══════════════════════════════════════════════════════════
# 1. 加载核心数据
# ═══════════════════════════════════════════════════════════

print("[1/6] 加载客户全景...")
df = pd.read_csv(os.path.join(GOLD_DIR, "客户全景.csv"))
print(f"      客户数: {len(df)}, 列数: {len(df.columns)}")

print("[2/6] 加载异常日志...")
alerts = pd.read_csv(os.path.join(GOLD_DIR, "异常日志.csv"))
print(f"      异常数: {len(alerts)}")

print("[3/6] 加载 Silver 月度数据...")
try:
    scm = pd.read_csv(os.path.join(PROJECT, "output", "silver", "silver_customer_monthly.csv"))
    print(f"      行数: {len(scm)}, 列数: {len(scm.columns)}")
except Exception as e:
    print(f"      ⚠ 加载失败: {e}")
    scm = pd.DataFrame()

print("[4/6] 加载价格数据...")
try:
    pricing = pd.read_csv(os.path.join(GOLD_DIR, "跨客户价格差异.csv"))
    fairness = pd.read_csv(os.path.join(GOLD_DIR, "定价合理性分析.csv"))
    print(f"      跨客户价格差异: {len(pricing)} 行, 定价合理性: {len(fairness)} 行")
except Exception as e:
    print(f"      ⚠ 加载失败: {e}")
    pricing = pd.DataFrame()
    fairness = pd.DataFrame()

print("[5/6] 加载销售画像...")
try:
    sales = pd.read_csv(os.path.join(GOLD_DIR, "销售画像.csv"))
    print(f"      销售人数: {len(sales)}")
except:
    sales = pd.DataFrame()

# ═══════════════════════════════════════════════════════════
# 2. KPI 汇总
# ═══════════════════════════════════════════════════════════

print("\n生成 KPI 汇总...")

total_rev = float(df["近12月收入"].sum())
prior_rev = float(df.get("前12月收入", pd.Series(0, index=df.index)).sum())
total_profit = float(df["近12月毛利"].sum())
total_margin = round(total_profit / total_rev * 100, 2) if total_rev > 0 else 0
prior_margin = round(float(df.get("前12月毛利", pd.Series(0, index=df.index)).sum()) / prior_rev * 100, 2) if prior_rev > 0 else 0

active = df[df["活跃状态"].isin(["活跃", "微量活跃"])]
ka_aa = len(active[active["综合价值层级"].isin(["S", "A"])])
high_risk = len(active[active["风险评级"].isin(["极高", "高"])])
high_risk_rev = float(active[active["风险评级"].isin(["极高", "高"])]["近12月收入"].sum())
avg_score = round(float(df["综合价值分"].mean()), 1)

# 计算增速
rev_growth = round((total_rev - prior_rev) / prior_rev * 100, 1) if prior_rev > 0 else 0

# 上月 vs 前月（从 Silver 客户月度数据获取）
if len(scm) > 0 and "_月" in scm.columns:
    try:
        scm["_月_p"] = pd.PeriodIndex(scm["_月"].astype(str), freq="M")
    except:
        scm["_月_p"] = None
    months = sorted(scm["_月_p"].dropna().unique())
    if len(months) >= 2:
        latest_m = months[-1]; prior_m = months[-2]
        latest_rev = float(scm[scm["_月_p"] == latest_m]["rev_sum"].sum())
        prior_m_rev = float(scm[scm["_月_p"] == prior_m]["rev_sum"].sum())
        mom_rev = round((latest_rev - prior_m_rev) / prior_m_rev * 100, 1) if prior_m_rev > 0 else 0
    else:
        latest_m = months[-1]; prior_m = None; latest_rev = total_rev; mom_rev = 0
else:
    latest_m = None; prior_m = None; latest_rev = total_rev; mom_rev = 0

kpi = {
    "总营收": {"value": round(total_rev / 1e4, 0), "unit": "万元", "yoy": rev_growth},
    "毛利率": {"value": total_margin, "unit": "%", "yoy": round(total_margin - prior_margin, 1)},
    "KA_AA客户数": {"value": ka_aa, "unit": "个", "yoy": None},
    "衰退风险客户": {"value": high_risk, "unit": "个", "sub": f"涉及{round(high_risk_rev/1e4,0)}万元", "yoy": None},
    "综合价值分均值": {"value": avg_score, "unit": "分", "yoy": None},
}
write_json(kpi, "kpi_summary.json")

# ═══════════════════════════════════════════════════════════
# 3. 客户价值矩阵（仅 S/A 级活跃客户）
# ═══════════════════════════════════════════════════════════

print("\n生成客户价值矩阵...")
sa = active[active["综合价值层级"].isin(["S", "A"])].copy()
matrix = []
for _, row in sa.iterrows():
    matrix.append({
        "name": str(row.get("客户名称", "")),
        "value_score": float(row.get("综合价值分", 0)),
        "growth_score": float(row.get("增长动能分", 0)),
        "revenue": float(row.get("近12月收入", 0)),
        "risk": str(row.get("风险评级", "低")),
        "tier": str(row.get("客户层级", "未知")),
        "lifecycle": str(row.get("客户生命周期", "")),
        "owner": str(row.get("业务负责人", "")),
    })
write_json(matrix, "customer_matrix.json")

# ═══════════════════════════════════════════════════════════
# 4. 异常日志（关联客户名称和业务负责人）
# ═══════════════════════════════════════════════════════════

print("\n生成异常日志...")
cid_to_name = dict(zip(df["客户编号"].astype(str), df["客户名称"].astype(str)))
cid_to_owner = dict(zip(df["客户编号"].astype(str), df.get("业务负责人", pd.Series("")).astype(str)))

alert_list = []
for _, row in alerts.iterrows():
    cid = str(row.get("客户编号", ""))
    alert_list.append({
        "customer_id": cid,
        "customer_name": cid_to_name.get(cid, cid),
        "owner": cid_to_owner.get(cid, ""),
        "type": str(row.get("异常类型", "")),
        "level": str(row.get("异常等级", "")),
        "detail": str(row.get("异常详情", ""))[:150],
    })
# 按等级排序：高 → 中 → 低
level_order = {"高": 0, "中": 1, "低": 2}
alert_list.sort(key=lambda x: level_order.get(x["level"], 3))
write_json(alert_list, "alerts.json")

# ═══════════════════════════════════════════════════════════
# 5. 生命周期分布（双层环形图数据）
# ═══════════════════════════════════════════════════════════

print("\n生成生命周期分布...")
lifecycle_stages = ["导入期", "成长期", "成熟期", "衰退期", "流失期", "激活期", "稳定期"]
tier_order = ["KA", "AA", "KM", "MM"]

inner = []
outer = []
for stage in lifecycle_stages:
    stage_df = active[active["客户生命周期"] == stage]
    inner.append({"name": stage, "value": len(stage_df)})
    for t in tier_order:
        n = len(stage_df[stage_df["客户层级"] == t])
        if n > 0:
            outer.append({"name": t, "value": n, "stage": stage})

write_json({"inner": inner, "outer": outer, "stages": lifecycle_stages, "tiers": tier_order},
           "lifecycle_distribution.json")

# ═══════════════════════════════════════════════════════════
# 6. 月度收入趋势
# ═══════════════════════════════════════════════════════════

print("\n生成月度趋势...")
trend_data = []
if len(scm) > 0 and "_月" in scm.columns:
    scm["_月_str"] = scm["_月"].astype(str)
    monthly = scm.groupby("_月_str").agg(
        rev=("rev_sum", "sum"),
        profit=("profit_clip_sum", "sum"),
        qty=("qty_sum", "sum"),
    ).reset_index().sort_values("_月_str")
    for _, row in monthly.iterrows():
        trend_data.append({
            "month": str(row["_月_str"]),
            "revenue": round(float(row["rev"]) / 1e4, 2),
            "profit": round(float(row["profit"]) / 1e4, 2),
            "quantity": round(float(row["qty"]) / 1e4, 2),
        })
    print(f"      月度数据: {len(trend_data)} 个月")
else:
    print(f"      ⚠ 无 Silver 月度数据")
write_json(trend_data, "revenue_trend.json")

# ═══════════════════════════════════════════════════════════
# 7. 价格差异数据（Top 30 产品 × Top 100 客户）
# ═══════════════════════════════════════════════════════════

print("\n生成价格差异数据...")
price_data = {}
if len(pricing) > 0:
    cols = pricing.columns.tolist()
    cust_col = next((c for c in cols if "客户" in c and "编号" in c), cols[0] if len(cols) > 0 else None)
    prod_col = next((c for c in cols if "产品" in c), cols[1] if len(cols) > 1 else None)
    price_col = next((c for c in cols if "单价" in c or "均价" in c or "价格" in c), cols[2] if len(cols) > 2 else None)

    if cust_col and prod_col:
        # Top 30 products by customer count
        top_prods = pricing[prod_col].value_counts().head(30).index.tolist()
        subset = pricing[pricing[prod_col].isin(top_prods)]
        for prod in top_prods:
            pp = subset[subset[prod_col] == prod]
            prices = []
            for _, row in pp.iterrows():
                prices.append({
                    "customer": str(row.get(cust_col, "")),
                    "price": float(row.get(price_col, 0)) if price_col else 0,
                })
            if prices:
                price_data[prod] = prices[:100]  # max 100 per product

write_json(price_data, "product_pricing.json")

# ═══════════════════════════════════════════════════════════
# 8. 客户明细（用于抽屉）
# ═══════════════════════════════════════════════════════════

print("\n生成客户明细...")
detail_cols = [
    "客户名称", "业务负责人", "渠道类型", "客户层级", "活跃状态",
    "综合价值层级", "双轴分类", "增长潜力", "风险评级", "客户生命周期",
    "利润率情况", "利润贡献等级",
    "近12月收入", "前12月收入", "收入增长率", "YoY同比增速",
    "近12月毛利", "近12月毛利率", "毛利率跌幅%",
    "连续增长月数", "连续下滑月数",
    "品种总数", "在采品种数", "实际品类数", "产品线数",
    "主导产品线", "主导产品线占比", "品种集中度Top3",
    "主导品类", "主导品类占比",
    "ASP_加权", "ASP_跌幅%", "低价品种收入占比", "中价品种收入占比", "高价品种收入占比",
    "策略详细建议", "策略触发原因", "异常告警汇总",
    "价值贡献分", "增长动能分", "稳定关系分", "战略潜力分", "效率运营分", "综合价值分",
    "新品采购占比", "是否采购新品", "新品采购额", "新品品种数",
    "R_得分", "F_得分", "M_得分", "P_得分", "RFMπ_综合分",
    "常规平均采购间隔", "距上次采购天数", "采购中断预警",
    "收入CV", "增长动量", "近6月交易额环比增长率",
    "阶段持续月数", "阶段转换次数",
    "预警增长_金额", "隐性衰退_金额", "衰退期_金额", "衰退风险品金额占比",
]
available = [c for c in detail_cols if c in df.columns]
detail_subset = df[df["活跃状态"].isin(["活跃", "微量活跃"])]
print(f"      筛选后: {len(detail_subset)} 个活跃客户")
detail = {}
for _, row in detail_subset.iterrows():
    name = str(row.get("客户名称", ""))
    item = {}
    for c in available:
        val = row[c]
        if pd.isna(val):
            item[c] = None
        elif isinstance(val, (np.floating,)):
            item[c] = round(float(val), 2)
        elif isinstance(val, (np.integer,)):
            item[c] = int(val)
        elif isinstance(val, np.bool_):
            item[c] = bool(val)
        else:
            item[c] = str(val)
    detail[str(row.get("客户编号", name))] = item
write_json(detail, "customer_detail.json")

# ═══════════════════════════════════════════════════════════
print(f"\n[OK] 完成！JSON 输出目录: {OUT_DIR}")
total_size = sum(os.path.getsize(os.path.join(OUT_DIR, f)) for f in os.listdir(OUT_DIR) if f.endswith(".json"))
print(f"   总大小: {total_size/1024:.0f} KB")
