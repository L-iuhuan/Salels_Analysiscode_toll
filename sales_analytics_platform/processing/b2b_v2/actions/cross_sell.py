"""
L3 交叉销售推荐 — 基于产品关联 + 库龄压力，推荐可推品种。

逻辑:
  1. 找出客户未采购但高关联的产品
  2. 过滤已衰退/退市产品
  3. 优先推荐现金牛+成长期产品
  4. 如有库龄数据，优先推荐有库存压力的品种
"""

import pandas as pd
import numpy as np

from config.settings import ACTION_SUGGESTIONS


def generate_cross_sell(
    customer_x_product: pd.DataFrame,
    product_portrait: pd.DataFrame = None,
    inv_aging: pd.DataFrame = None,
    product_assoc: pd.DataFrame = None,
) -> pd.DataFrame:
    """为每个客户生成交叉销售推荐。

    参数:
        customer_x_product: Silver层客户×产品聚合表
        product_portrait: 产品画像表 (含 当前画像 列)
        inv_aging: 产成品维度库龄表
        product_assoc: 产品关联分析结果 (含 产品A, 产品B, 置信度 等列)

    返回:
        DataFrame: [客户编号, 推荐品种数, 推荐品种, 推荐理由]
    """
    max_recs = ACTION_SUGGESTIONS.get("cross_sell_max_recommendations", 5)
    cat_bonus_cfg = ACTION_SUGGESTIONS.get("cross_sell_cat_bonus", 3)

    if len(customer_x_product) == 0:
        return pd.DataFrame(columns=["客户编号", "推荐品种数", "推荐品种", "推荐理由"])

    cxp = customer_x_product.copy()

    # Determine columns
    cust_col = "客户编号"
    prod_col = "产品品种"
    rev_col = "rev_sum" if "rev_sum" in cxp.columns else "金额"
    if rev_col not in cxp.columns:
        alt_cols = [c for c in cxp.columns if "金额" in c or "rev" in c.lower()]
        rev_col = alt_cols[0] if alt_cols else cxp.columns[-1]

    # Build per-customer "purchased products" set
    cust_products = cxp.groupby(cust_col)[prod_col].apply(set).to_dict()
    cust_revenue = cxp.groupby(cust_col)[rev_col].sum().to_dict()

    # Build product→category mapping for category-matching bonus
    cat_col = None
    for c in cxp.columns:
        if c in ("产品一级分类", "产品线", "产品系列", "品类", "category", "产品二级分类"):
            cat_col = c
            break
    prod_category = {}
    cust_categories = {}
    if cat_col:
        prod_category = cxp.groupby(prod_col)[cat_col].first().to_dict()
        # Per-customer purchased categories
        for cid, grp in cxp.groupby(cust_col):
            cust_categories[cid] = set(grp[cat_col].dropna().unique())

    # Product health scores (higher = better to recommend)
    prod_score = _build_product_recommendation_scores(
        cxp, product_portrait, inv_aging
    )

    # If we have product association data, use it for targeting
    assoc_map = _build_association_map(product_assoc) if product_assoc is not None else {}

    results = []
    all_products = set(prod_score.keys())

    for cid, purchased in cust_products.items():
        # Products the customer hasn't purchased yet
        # 批次②.5车道B：原 set 迭代顺序随 PYTHONHASHSEED 跨进程随机（同分产品推荐漂移），
        # 改为确定性排序；同分推荐按产品名顺序稳定排序。
        candidates = sorted(all_products - purchased)

        if len(candidates) == 0:
            continue

        # Categories this customer already buys from
        my_cats = cust_categories.get(cid, set())

        # Score and rank candidates
        scored = []
        for prod in candidates:
            score = prod_score.get(prod, {}).get("score", 0)
            portrait = prod_score.get(prod, {}).get("portrait", "")
            reasons = []

            # Bonus for category matching: products in categories the customer already buys
            prod_cat = prod_category.get(prod, "")
            cat_bonus = 0
            if prod_cat and prod_cat in my_cats:
                cat_bonus = cat_bonus_cfg
                reasons.append(f"同品类[{prod_cat}]扩展")

            # Bonus for association with already-purchased products（purchased 亦排序，保证理由顺序确定）
            assoc_bonus = 0
            for owned in sorted(purchased):
                key = (owned, prod)
                if key in assoc_map:
                    assoc_bonus += assoc_map[key].get("bonus", 0)
                    reasons.append(
                        f"与已采购 [{owned}] 关联(置信度{assoc_map[key].get('conf', 0):.0%})"
                    )

            # Fallback reason based on product portrait
            if not reasons:
                portrait_reason = {
                    "成长期": "高增长潜力品种", "现金牛": "稳定贡献品种",
                    "新品观察": "新品拓展机会", "预警增长": "可关注品种",
                }.get(portrait, "基于产品画像推荐")
                reasons.append(portrait_reason)

            scored.append({
                "产品品种": prod,
                "score": score + cat_bonus + assoc_bonus,
                "reason": "; ".join(reasons),
                "portrait": portrait,
                "dead_stock": prod_score.get(prod, {}).get("dead_stock", False),
            })

        # Sort by score descending, prioritize dead stock products too
        scored.sort(key=lambda x: (x["dead_stock"], x["score"]), reverse=True)
        top = scored[:max_recs]

        if top:
            results.append({
                cust_col: cid,
                "推荐品种数": len(top),
                "推荐品种": "; ".join(
                    f"{r['产品品种']}({r['portrait']})" for r in top
                ),
                "推荐理由": "; ".join(r["reason"] for r in top),
            })

    df = pd.DataFrame(results)
    if len(df) > 0:
        print(f"  [交叉销售] {len(df)} 客户有推荐, "
              f"平均推荐{df['推荐品种数'].mean():.1f}个品种")
    return df


def _build_product_recommendation_scores(
    cxp: pd.DataFrame,
    product_portrait: pd.DataFrame = None,
    inv_aging: pd.DataFrame = None,
) -> dict:
    """Build product-level recommendation scores.

    Returns:
        dict: {产品品种: {"score": float, "portrait": str, "dead_stock": bool}}
    """
    prod_col = "产品品种"

    # Base score from product popularity (how many customers buy it)
    popularity = cxp.groupby(prod_col)["客户编号"].nunique()
    pop_score = popularity / popularity.max() if len(popularity) > 0 else pd.Series(dtype=float)

    # Portrait bonus from config
    portrait_bonus = ACTION_SUGGESTIONS.get("cross_sell_portrait_bonus", {
        "成长期": 5, "现金牛": 4, "新品观察": 3, "预警增长": 2,
        "隐性衰退": 0, "衰退期": -1,
    })

    scores = {}
    for prod in pop_score.index:
        score = float(pop_score.get(prod, 0) * 10)

        portrait = ""
        if product_portrait is not None and len(product_portrait) > 0:
            pp = product_portrait
            prod_name_col = "产品名称" if "产品名称" in pp.columns else "产品品种"
            match = pp[pp[prod_name_col].astype(str) == str(prod)]
            if len(match) > 0:
                if "当前画像" in match.columns:
                    portrait = str(match["当前画像"].iloc[0])
                    score += portrait_bonus.get(portrait, 0)

        dead_stock = False
        if inv_aging is not None and len(inv_aging) > 0:
            age_match = inv_aging[inv_aging["产品品种"].astype(str) == str(prod)]
            if len(age_match) > 0:
                dead_pct = age_match["库龄_超1年占比"].iloc[0]
                dead_qty = age_match["库龄_1年以上"].iloc[0]
                dead_stock_threshold = ACTION_SUGGESTIONS.get("cross_sell_dead_stock_threshold", 0.15)
                dead_stock_bonus = ACTION_SUGGESTIONS.get("cross_sell_dead_stock_bonus", 3)
                if dead_pct > dead_stock_threshold and dead_qty > 0:
                    dead_stock = True
                    score += dead_stock_bonus  # Boost products with dead stock to help clear inventory

        scores[prod] = {"score": score, "portrait": portrait, "dead_stock": dead_stock}

    return scores


def _build_association_map(product_assoc: pd.DataFrame) -> dict:
    """Build product association lookup.

    Expects columns like: 产品A, 产品B, 置信度
    Returns: {(产品A, 产品B): {"bonus": float, "conf": float}}
    """
    result = {}
    col_a = None
    col_b = None
    col_conf = None

    for c in product_assoc.columns:
        if "A" in c or "前件" in c or "产品1" in c or "antecedent" in c.lower():
            col_a = c
        elif "B" in c or "后件" in c or "产品2" in c or "consequent" in c.lower():
            col_b = c
        elif "conf" in c.lower() or "置信" in c or "lift" in c.lower():
            col_conf = c

    if col_a is None or col_b is None:
        # Assume first two columns are the product pair
        cols = list(product_assoc.columns)
        col_a = cols[0]
        col_b = cols[1]
        col_conf = cols[2] if len(cols) > 2 else None

    for _, row in product_assoc.iterrows():
        a = str(row[col_a])
        b = str(row[col_b])
        conf = float(row[col_conf]) if col_conf and col_conf in row else 0.5
        bonus = conf * 5  # Scale confidence to bonus points
        result[(a, b)] = {"bonus": bonus, "conf": conf}

    return result
