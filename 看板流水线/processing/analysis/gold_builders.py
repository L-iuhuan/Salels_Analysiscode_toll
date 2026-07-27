"""
Gold 层辅助表构建器。

P2-D: 从 customer_analysis/gold.py 提取的 3 个独立构建函数。
不再依赖 customer_analysis 内部模块，可在 Pipeline DI 中直接调用。

函数:
    build_customer_product_bridge(silver, product_portrait_path) -> DataFrame
    build_portfolio_health(cp) -> DataFrame
    build_product_association(silver, assoc_thresholds=None) -> DataFrame
"""

import os
import sys
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.customer_analysis import product_association_analysis
from config.settings import PRODUCT_LIFECYCLE


def build_customer_product_bridge(
    silver: dict,
    product_portrait_path: str = None,
) -> pd.DataFrame:
    """构建客户×产品桥接表（合并产品生命周期画像引用）。

    参数:
        silver: Silver 层数据字典（需含 customer_x_product）
        product_portrait_path: 产品画像 CSV 路径（可选）

    返回:
        DataFrame: 桥接表
    """
    cp = silver["customer_x_product"].copy()
    if product_portrait_path and os.path.exists(product_portrait_path):
        pp = pd.read_csv(product_portrait_path, encoding="utf-8-sig")
        if "产品名称" in pp.columns and "产品品种" in cp.columns:
            cp["产品品种"] = cp["产品品种"].astype(str)
            pp["产品名称"] = pp["产品名称"].astype(str)
            cp = cp.merge(
                pp[[
                    "产品名称", "当前画像", "管理层摘要",
                    "综合评分", "综合风险等级", "帕累托分类",
                ]],
                left_on="产品品种", right_on="产品名称", how="left",
            ).drop(columns=["产品名称"], errors="ignore")
    return cp


def build_portfolio_health(cp: pd.DataFrame) -> pd.DataFrame:
    """构建客户组合健康度表。

    参数:
        cp: 客户×产品桥接 DataFrame

    返回:
        DataFrame: 含总品种数、总金额、各画像金额、衰退风险占比
    """
    if "当前画像" not in cp.columns:
        return pd.DataFrame()

    portfolio = cp.groupby("客户编号").agg(
        总品种数=("产品品种", "nunique"),
        总金额=("rev_sum", "sum"),
    ).reset_index()

    portrait_groups = cp.groupby(["客户编号", "当前画像"]).agg(
        品种数=("产品品种", "nunique"),
        金额=("rev_sum", "sum"),
    ).reset_index()

    for img in ["成长期", "现金牛", "预警增长", "隐性衰退", "衰退期", "新品观察"]:
        sub = portrait_groups[portrait_groups["当前画像"] == img][["客户编号", "金额"]]
        sub = sub.rename(columns={"金额": f"{img}_金额"})
        portfolio = portfolio.merge(sub, on="客户编号", how="left")

    for img in ["预警增长", "隐性衰退", "衰退期"]:
        col = f"{img}_金额"
        if col in portfolio.columns:
            portfolio[col] = portfolio[col].fillna(0)
        else:
            portfolio[col] = 0

    portfolio["衰退风险品金额占比"] = (
        (portfolio.get("预警增长_金额", 0)
         + portfolio.get("隐性衰退_金额", 0)
         + portfolio.get("衰退期_金额", 0))
        / portfolio["总金额"].replace(0, float("nan"))
    )

    return portfolio


def build_product_association(
    silver: dict,
    assoc_thresholds: dict = None,
) -> pd.DataFrame:
    """从 Silver 客户×产品交易数据计算产品关联规则（购物篮分析）。

    方法: 按客户×月份构建"购物篮"，统计产品对共现频次，
    计算支持度、置信度、提升度等关联指标。

    质量说明:
        - 基础实现(3/5) — 使用共现计数，非完整 Apriori/F-P Growth
        - 适合中小规模数据集（<500 个 SKU，<10000 个客户-月篮子）
        - 大规模数据建议换用 mlxtend.frequent_patterns.apriori
        - 不区分方向，置信度仅反映共现强度

    参数:
        silver: Silver 层数据字典（需含 customer_x_product）
        assoc_thresholds: 关联阈值字典（可选，默认从 settings 读取）

    返回:
        DataFrame: 含 产品A, 产品B, 支持度, 置信度, 提升度, ...
    """
    cxp = silver.get("customer_x_product")
    if cxp is None or len(cxp) < 100:
        print("  [产品关联分析] customer_x_product 数据不足（<100行），跳过")
        return pd.DataFrame()

    thr = assoc_thresholds or {
        "assoc_min_support": PRODUCT_LIFECYCLE.get("assoc_min_support", 0.02),
        "assoc_min_confidence": PRODUCT_LIFECYCLE.get("assoc_min_confidence", 0.15),
    }

    df = cxp.copy()
    df["_assoc_date"] = df["_月"].dt.start_time  # Period → Timestamp

    result = product_association_analysis(
        df,
        name_col="产品品种",
        date_col="_assoc_date",
        cust_col="客户编号",
        thr=thr,
    )

    if result is None or len(result) == 0:
        print("  [产品关联分析] 未找到满足阈值的关联规则")
        return pd.DataFrame()

    print(f"  [产品关联分析] 生成 {len(result)} 条规则"
          f"（min_support={thr['assoc_min_support']}, "
          f"min_confidence={thr['assoc_min_confidence']}）")
    return result
