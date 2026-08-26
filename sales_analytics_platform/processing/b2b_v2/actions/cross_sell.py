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

    # [批次⑥ P4] 每客户 ~750 个候选的打分/排序/理由构建是主要耗时（3032×750 dict 构建+排序）。
    # 等价改写：
    #  1) 候选循环只算 (dead_stock, score, prod) 轻量元组，理由文案只为最终 top-N 重构
    #     （理由仅依赖 (cid, prod)，重构结果与原逐候选构建完全一致）；
    #  2) heapq.nlargest 替代全量 sort —— CPython 文档保证
    #     nlargest(n, it, key=k) == sorted(it, key=k, reverse=True)[:n]（含并列稳定性），
    #     候选列表按 sorted(all_products - purchased) 顺序构造，并列顺序与原实现一致。
    import heapq as _heapq

    _portrait_reason_map = {
        "成长期": "高增长潜力品种", "现金牛": "稳定贡献品种",
        "新品观察": "新品拓展机会", "预警增长": "可关注品种",
    }

    def _build_reasons(prod, portrait, my_cats, purchased_sorted):
        reasons = []
        prod_cat = prod_category.get(prod, "")
        if prod_cat and prod_cat in my_cats:
            reasons.append(f"同品类[{prod_cat}]扩展")
        for owned in purchased_sorted:
            key = (owned, prod)
            if key in assoc_map:
                reasons.append(
                    f"与已采购 [{owned}] 关联(置信度{assoc_map[key].get('conf', 0):.0%})"
                )
        if not reasons:
            reasons.append(_portrait_reason_map.get(portrait, "基于产品画像推荐"))
        return "; ".join(reasons)

    for cid, purchased in cust_products.items():
        # Products the customer hasn't purchased yet
        # 批次②.5车道B：原 set 迭代顺序随 PYTHONHASHSEED 跨进程随机（同分产品推荐漂移），
        # 改为确定性排序；同分推荐按产品名顺序稳定排序。
        candidates = sorted(all_products - purchased)

        if len(candidates) == 0:
            continue

        # Categories this customer already buys from
        my_cats = cust_categories.get(cid, set())
        purchased_sorted = sorted(purchased)  # [批次⑥ P4] 预排一次（原为每候选 sorted(purchased)）

        # Score candidates（轻量元组，理由延后到 top-N 重构）
        scored_keys = []
        for prod in candidates:
            s0 = prod_score.get(prod, {})
            score = s0.get("score", 0)

            # Bonus for category matching
            prod_cat = prod_category.get(prod, "")
            if prod_cat and prod_cat in my_cats:
                score += cat_bonus_cfg

            # Bonus for association with already-purchased products
            for owned in purchased_sorted:
                key = (owned, prod)
                if key in assoc_map:
                    score += assoc_map[key].get("bonus", 0)

            scored_keys.append((s0.get("dead_stock", False), score, prod))

        # (dead_stock, score) 降序取前 N，并列保持 candidates 原顺序（与原文档等价）
        top = _heapq.nlargest(max_recs, scored_keys, key=lambda t: (t[0], t[1]))

        if top:
            results.append({
                cust_col: cid,
                "推荐品种数": len(top),
                "推荐品种": "; ".join(
                    f"{prod}({prod_score.get(prod, {}).get('portrait', '')})"
                    for _, _, prod in top
                ),
                "推荐理由": "; ".join(
                    _build_reasons(prod, prod_score.get(prod, {}).get("portrait", ""),
                                   my_cats, purchased_sorted)
                    for _, _, prod in top
                ),
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
    # [批次⑥ P4] 产品画像/库龄的首匹配映射预构建（原实现每产品各做一次全表
    # astype(str)+等值扫描，800×N 行；映射取每个键的首行，与原 iloc[0] 语义一致）
    _portrait_map = {}
    if product_portrait is not None and len(product_portrait) > 0:
        pp = product_portrait
        prod_name_col = "产品名称" if "产品名称" in pp.columns else "产品品种"
        if "当前画像" in pp.columns:
            _pp_keys = pp[prod_name_col].astype(str)
            _pp_first = pd.DataFrame({"_k": _pp_keys, "_v": pp["当前画像"]}).drop_duplicates("_k")
            _portrait_map = dict(zip(_pp_first["_k"], _pp_first["_v"]))
    _aging_map = {}
    if inv_aging is not None and len(inv_aging) > 0:
        _ag_keys = inv_aging["产品品种"].astype(str)
        _ag_first = pd.DataFrame({
            "_k": _ag_keys,
            "_pct": inv_aging["库龄_超1年占比"],
            "_qty": inv_aging["库龄_1年以上"],
        }).drop_duplicates("_k")
        _aging_map = {r["_k"]: (r["_pct"], r["_qty"]) for r in _ag_first.to_dict("records")}

    for prod in pop_score.index:
        score = float(pop_score.get(prod, 0) * 10)

        portrait = str(_portrait_map.get(str(prod), ""))  # [批次⑥ P4] 首匹配映射
        if portrait:
            score += portrait_bonus.get(portrait, 0)

        dead_stock = False
        _am = _aging_map.get(str(prod))  # [批次⑥ P4] 首匹配映射
        if _am is not None:
            dead_pct, dead_qty = _am
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
