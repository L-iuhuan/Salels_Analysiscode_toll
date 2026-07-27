"""
交叉关联层。

读取产品生命周期和客户分析两套系统的Gold层输出，计算：
  1. 客户的产品组合健康度：每个客户采购产品中各画像占比
  2. 产品的客户群健康度：每个产品客户中各分层占比
  3. 双重画像矩阵：客户层级 × 产品画像的金额分布
"""

import os
import sys
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

OUTPUT_GOLD = os.path.join(PROJECT_ROOT, "output", "gold")
OUTPUT_REPORT = os.path.join(PROJECT_ROOT, "output", "report")


def load_gold_tables() -> dict:
    """加载两套系统的Gold层输出。如果文件不存则跳过。"""
    tables = {}

    # 产品画像（来自产品生命周期系统）
    path = os.path.join(OUTPUT_GOLD, "gold_product_portrait.csv")
    if os.path.exists(path):
        tables["product_portrait"] = pd.read_csv(path, encoding="utf-8-sig")
        print(f"  加载: gold_product_portrait.csv ({len(tables['product_portrait'])} 行)")
    else:
        print("  [警告] gold_product_portrait.csv 不存在，跳过产品画像引用")

    # 客户全景（来自客户分析系统）
    path = os.path.join(OUTPUT_GOLD, "客户全景.csv")
    if os.path.exists(path):
        tables["customer_profile"] = pd.read_csv(path, encoding="utf-8-sig")
        print(f"  加载: gold_customer_profile.csv ({len(tables['customer_profile'])} 行)")
    else:
        print("  [警告] gold_customer_profile.csv 不存在，跳过客户分析引用")

    # 客户×产品桥接表
    path = os.path.join(OUTPUT_GOLD, "客户产品桥接.csv")
    if os.path.exists(path):
        tables["customer_x_product"] = pd.read_csv(path, encoding="utf-8-sig")
        print(f"  加载: gold_customer_x_product.csv ({len(tables['customer_x_product'])} 行)")
    else:
        print("  [警告] gold_customer_x_product.csv 不存在，跳过桥接关联")

    return tables


def calc_customer_portfolio_health(tables: dict) -> pd.DataFrame:
    """计算每个客户的产品组合健康度。"""
    if "customer_x_product" not in tables or "product_portrait" not in tables:
        print("  跳过客户产品组合健康度计算（缺少数据）")
        return pd.DataFrame()

    cp = tables["customer_x_product"].copy()
    pp = tables["product_portrait"].copy()

    # 确保产品名称列一致
    if "当前画像" not in cp.columns and "当前画像" in pp.columns:
        if "产品品种" in cp.columns and "产品名称" in pp.columns:
            cp["产品品种"] = cp["产品品种"].astype(str)
            pp["产品名称"] = pp["产品名称"].astype(str)
            cp = cp.merge(
                pp[["产品名称", "当前画像", "管理层摘要", "综合评分", "综合风险等级"]],
                left_on="产品品种",
                right_on="产品名称",
                how="left",
            )

    if "当前画像" not in cp.columns:
        print("  跳过：无法关联产品画像")
        return pd.DataFrame()

    # 计算每个客户各画像的金额占比
    result = cp.groupby(["客户编号", "当前画像"]).agg(
        金额=("rev_sum", "sum"),
        品种数=("产品品种", "nunique"),
    ).reset_index()

    # 透视：客户×画像
    pivot = result.pivot_table(
        index="客户编号",
        columns="当前画像",
        values="金额",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()

    pivot["总金额"] = pivot.select_dtypes(include=[np.number]).sum(axis=1)

    # 各画像占比
    img_cols = [c for c in pivot.columns if c not in ["客户编号", "总金额"]]
    for col in img_cols:
        pivot[f"{col}_占比"] = pivot[col] / pivot["总金额"].replace(0, float("nan"))

    # 风险品占比（预警增长+隐性衰退+衰退期）
    risk_cols = [c for c in img_cols if c in ["预警增长", "隐性衰退", "衰退期"]]
    pivot["风险品金额占比"] = pivot[risk_cols].sum(axis=1) / pivot["总金额"].replace(0, float("nan"))

    return pivot


def calc_product_customer_health(tables: dict) -> pd.DataFrame:
    """计算每个产品的客户群健康度。"""
    if "customer_x_product" not in tables or "customer_profile" not in tables:
        print("  跳过产品客户群健康度计算（缺少数据）")
        return pd.DataFrame()

    cp = tables["customer_x_product"].copy()
    cust = tables["customer_profile"].copy()

    merge_cols = ["客户编号"]
    if "RFMπ_层级" in cust.columns:
        merge_cols.append("RFMπ_层级")
    if "风险等级" in cust.columns:
        merge_cols.append("风险等级")

    if len(merge_cols) > 1:
        cp = cp.merge(cust[merge_cols], on="客户编号", how="left")

        agg_dict = {
            "客户总数": ("客户编号", "nunique"),
            "总金额": ("rev_sum", "sum"),
        }
        if "风险评级" in cp.columns:
            agg_dict["高风险客户数"] = (
                "风险评级",
                lambda x: int((x == "高").sum()),
            )

        result = cp.groupby("产品品种").agg(**agg_dict).reset_index()
        return result

    return pd.DataFrame()


def run():
    """执行交叉关联计算。"""
    print("=" * 60)
    print("[交叉关联] 开始")
    print("=" * 60)

    tables = load_gold_tables()
    if not tables:
        print("无可用数据，跳过")
        return {}

    results = {}

    # 计算1：客户的产品组合健康度
    portfolio = calc_customer_portfolio_health(tables)
    if len(portfolio) > 0:
        path = os.path.join(OUTPUT_GOLD, "cross_customer_portfolio_health.csv")
        portfolio.to_csv(path, index=False, encoding="utf-8-sig")
        results["customer_portfolio_health"] = path
        print(f"  客户产品组合健康度: {path}")

    # 计算2：产品的客户群健康度
    product_health = calc_product_customer_health(tables)
    if len(product_health) > 0:
        path = os.path.join(OUTPUT_GOLD, "cross_product_customer_health.csv")
        product_health.to_csv(path, index=False, encoding="utf-8-sig")
        results["product_customer_health"] = path
        print(f"  产品客户群健康度: {path}")

    print(f"\n[OK] 交叉关联完成")
    return results


if __name__ == "__main__":
    run()
