"""
库龄数据层 — 加载、BOM拆分、估算降级、客户维度映射。

数据流:
  库龄.xlsx (物料维度) + BOM映射表.xlsx (物料→产成品)
    → explode_inventory_to_finished() → 产成品维度库龄
    → calc_customer_inventory_risk() → 客户维度库龄风险

无真实数据时降级到 estimate_inventory_aging()。
"""

import os
import sys
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.settings import INVENTORY_AGING


# ── Column alias resolution ──────────────────────────────────

def _resolve_column(col_name: str, target_key: str) -> str | None:
    """Match a column name against configured aliases. Returns the standard key if matched."""
    aliases = INVENTORY_AGING.get("aging_bucket_aliases", {}).get(target_key, [])
    if col_name in aliases:
        return target_key
    # Fuzzy: strip whitespace and try again
    col_clean = col_name.strip()
    for alias in aliases:
        if col_clean == alias.strip():
            return target_key
    return None


def _detect_aging_columns(columns: list[str]) -> dict[str, str]:
    """Auto-detect which DataFrame columns map to which aging buckets.

    Returns dict: {standard_key: actual_column_name}
    """
    mapping = {}
    buckets = INVENTORY_AGING.get("aging_buckets", ["180天以内", "180天-1年", "1年以上"])
    for bucket in buckets:
        for col in columns:
            if _resolve_column(col, bucket):
                mapping[bucket] = col
                break
    return mapping


def _detect_material_code_column(columns: list[str]) -> str:
    """Auto-detect the material code column."""
    for candidate in ["物料编码", "材料编码", "存货编码", "物料号", "产品编码", "产成品编码"]:
        if candidate in columns:
            return candidate
    if columns:
        return columns[0]
    return "物料编码"


def _detect_material_name_column(columns: list[str]) -> str | None:
    for candidate in ["物料名称", "材料名称", "存货名称", "产品名称"]:
        if candidate in columns:
            return candidate
    return None


# ── 1.1 Raw inventory loading ────────────────────────────────

def load_inventory_aging(inv_path: str) -> pd.DataFrame:
    """加载原始库龄数据，自动识别列名。

    预期输入列: 物料编码, 物料名称, ≤180天数量, 180天-1年数量, >1年数量

    返回:
        DataFrame: 物料编码, 物料名称, 库龄_180天以内, 库龄_180天到1年, 库龄_1年以上,
                   库龄_库存总量, 库龄_超180天占比, 库龄_超1年占比
    """
    if inv_path.endswith(".csv"):
        raw = pd.read_csv(inv_path, encoding="utf-8-sig")
    else:
        raw = pd.read_excel(inv_path)

    col_map = _detect_aging_columns(list(raw.columns))
    mat_col = _detect_material_code_column(list(raw.columns))
    name_col = _detect_material_name_column(list(raw.columns))

    result = pd.DataFrame()
    if mat_col and mat_col in raw.columns:
        result["物料编码"] = raw[mat_col].astype(str).str.strip()
    else:
        result["物料编码"] = ""

    if name_col and name_col in raw.columns:
        result["物料名称"] = raw[name_col].astype(str).str.strip()
    else:
        result["物料名称"] = ""

    for bucket in INVENTORY_AGING.get("aging_buckets", ["180天以内", "180天-1年", "1年以上"]):
        std_name = f"库龄_{bucket}"
        actual_col = col_map.get(bucket)
        if actual_col and actual_col in raw.columns:
            result[std_name] = pd.to_numeric(raw[actual_col], errors="coerce").fillna(0).astype(float)
        else:
            print(f"  [库龄] 警告: 未找到列 '{bucket}' (检测到的映射: {col_map})")
            result[std_name] = 0.0

    total = result["库龄_180天以内"] + result["库龄_180天到1年"] + result["库龄_1年以上"]
    result["库龄_库存总量"] = total
    result["库龄_超180天占比"] = (
        (result["库龄_180天到1年"] + result["库龄_1年以上"]) / total.replace(0, float("nan"))
    ).fillna(0)
    result["库龄_超1年占比"] = (
        result["库龄_1年以上"] / total.replace(0, float("nan"))
    ).fillna(0)

    print(f"  [库龄] 加载: {len(result)} 行物料, "
          f"库存总量={total.sum():.0f}, "
          f"超180天占比={(result['库龄_180天到1年'].sum() + result['库龄_1年以上'].sum()) / max(total.sum(), 1) * 100:.1f}%")

    return result


# ── 1.2 BOM mapping ──────────────────────────────────────────

def load_bom_mapping(bom_path: str) -> pd.DataFrame:
    """加载BOM映射表。

    预期列: 物料编码, 产成品编码
    """
    if bom_path.endswith(".csv"):
        bom = pd.read_csv(bom_path, encoding="utf-8-sig")
    else:
        bom = pd.read_excel(bom_path)

    mat_col = _detect_material_code_column(list(bom.columns))
    # Detect finished-product code column
    prod_candidates = ["产成品编码", "成品编码", "产品编码", "产品品种", "存货名称", "产成品名称"]
    prod_col = None
    for c in prod_candidates:
        if c in bom.columns:
            prod_col = c
            break
    if prod_col is None:
        # Fall back to the second column
        cols = [c for c in bom.columns if c != mat_col]
        prod_col = cols[0] if cols else "产成品编码"

    result = pd.DataFrame({
        "物料编码": bom[mat_col].astype(str).str.strip(),
        "产成品编码": bom[prod_col].astype(str).str.strip(),
    })

    dupes = result.duplicated(subset=["物料编码", "产成品编码"]).sum()
    if dupes > 0:
        result = result.drop_duplicates(subset=["物料编码", "产成品编码"])
        print(f"  [BOM] 移除 {dupes} 行重复的(物料,产成品)组合")

    print(f"  [BOM] 加载: {len(result)} 行映射, "
          f"{result['物料编码'].nunique()} 物料 → {result['产成品编码'].nunique()} 产成品")

    return result


def explode_inventory_to_finished(
    inv_df: pd.DataFrame,
    bom_df: pd.DataFrame,
    silver: dict,
) -> pd.DataFrame:
    """将物料级库龄按BOM + 历史销量分摊到产成品。

    分摊逻辑:
      1. JOIN 库龄 × BOM → 每个物料行展开为N行
      2. 查询各产成品的近12月历史销量（从 product_monthly）
      3. 分摊权重 = 该产成品近12月销量 / SUM(该物料所有产成品近12月销量)
      4. 各库龄桶数量 × 分摊权重 → 产成品维度的库龄

    参数:
        inv_df: load_inventory_aging() 返回的物料级库龄
        bom_df: load_bom_mapping() 返回的BOM映射表
        silver: Silver层数据字典 (需要 product_monthly)

    返回:
        产成品维度的库龄 DataFrame
    """
    # JOIN inventory × BOM
    merged = inv_df.merge(bom_df, on="物料编码", how="inner")
    if len(merged) == 0:
        print("  [BOM拆分] 警告: 库龄数据与BOM表无交集，尝试直接映射")
        return _direct_map_inventory(inv_df)

    # Get historical sales (last 12 months) from product_monthly
    prod_monthly = silver.get("product_monthly")
    hist_sales = pd.Series(dtype=float)
    if prod_monthly is not None and len(prod_monthly) > 0:
        pm = prod_monthly.copy()
        if not isinstance(pm["_月"].dtype, pd.PeriodDtype):
            pm["_月"] = pd.to_datetime(pm["_月"]).dt.to_period("M")
        latest = pm["_月"].max()
        recent = pm[pm["_月"] > (latest - 12)]
        if "qty_sum" in recent.columns:
            hist_sales = recent.groupby("产品品种")["qty_sum"].sum()
        elif "数量" in recent.columns:
            hist_sales = recent.groupby("产品品种")["数量"].sum()

    # Calculate allocation weights
    aging_cols = ["库龄_180天以内", "库龄_180天到1年", "库龄_1年以上"]

    # Attach historical sales to each row
    merged["_hist_qty"] = merged["产成品编码"].map(
        lambda x: hist_sales.get(x, 0) if x is not None else 0
    ).astype(float)

    # Per material: sum of historical sales across all finished products
    mat_total = merged.groupby("物料编码")["_hist_qty"].transform("sum")

    # Allocation weight
    merged["_weight"] = np.where(
        mat_total > 0,
        merged["_hist_qty"] / mat_total,
        1.0 / merged.groupby("物料编码")["_hist_qty"].transform("count"),
    )

    # Flag fallback cases
    merged["_bom_fallback"] = "none"
    merged.loc[mat_total == 0, "_bom_fallback"] = "equal_split"

    # Apply weights to aging columns
    for col in aging_cols:
        merged[col] = merged[col] * merged["_weight"]

    # Aggregate to finished-product level
    result = merged.groupby("产成品编码").agg({
        "库龄_180天以内": "sum",
        "库龄_180天到1年": "sum",
        "库龄_1年以上": "sum",
    }).reset_index()

    result = result.rename(columns={"产成品编码": "产品品种"})

    total = result["库龄_180天以内"] + result["库龄_180天到1年"] + result["库龄_1年以上"]
    result["库龄_库存总量"] = total
    result["库龄_超180天占比"] = (
        (result["库龄_180天到1年"] + result["库龄_1年以上"]) / total.replace(0, float("nan"))
    ).fillna(0)
    result["库龄_超1年占比"] = (
        result["库龄_1年以上"] / total.replace(0, float("nan"))
    ).fillna(0)
    result["库龄_数据来源"] = "real"

    # Report fallbacks
    n_fallback = (merged["_bom_fallback"] == "equal_split").sum()
    if n_fallback > 0:
        n_affected = merged.loc[merged["_bom_fallback"] == "equal_split", "产成品编码"].nunique()
        print(f"  [BOM拆分] {n_affected} 个产成品无历史销量，使用均分 (涉及 {n_fallback} 行)")

    print(f"  [BOM拆分] {len(inv_df)} 物料 → {len(result)} 产成品, "
          f"总库存={total.sum():.0f}")

    return result


def _direct_map_inventory(inv_df: pd.DataFrame) -> pd.DataFrame:
    """BOM映射失败时的直接映射降级: 物料编码即产成品编码。"""
    result = inv_df.rename(columns={"物料编码": "产品品种"})
    result["库龄_数据来源"] = "real"
    result["_bom_inferred"] = "direct"
    print(f"  [BOM拆分] 降级: 直接映射 {len(result)} 行 (物料编码=产成品编码)")
    return result


# ── 1.3 Estimation fallback ──────────────────────────────────

def estimate_inventory_aging(
    silver: dict,
    product_portrait: pd.DataFrame = None,
) -> pd.DataFrame:
    """无真实库龄数据时，从交易数据估算库存周转。

    估算逻辑:
      - 近3月月均销量 → 出库速度
      - 假设安全库存 ≈ 月均销量 × 2
      - 库龄分布: 近期有交易 → 大部分在180天内; 3月无交易 → 大部分超180天

    返回:
        DataFrame: 产品品种, 库龄_180天以内, 库龄_180天到1年, 库龄_1年以上,
                   库龄_库存总量, 库龄_超180天占比, 库龄_超1年占比,
                   库龄_数据来源='estimated'
    """
    prod_monthly = silver.get("product_monthly")
    if prod_monthly is None or len(prod_monthly) == 0:
        return pd.DataFrame(columns=[
            "产品品种", "库龄_180天以内", "库龄_180天到1年", "库龄_1年以上",
            "库龄_库存总量", "库龄_超180天占比", "库龄_超1年占比",
            "库龄_数据来源",
        ])

    pm = prod_monthly.copy()
    if not isinstance(pm["_月"].dtype, pd.PeriodDtype):
        pm["_月"] = pd.to_datetime(pm["_月"]).dt.to_period("M")

    latest = pm["_月"].max()
    last3 = pm[pm["_月"] > (latest - 3)]
    last6 = pm[pm["_月"] > (latest - 6)]

    qty_col = "qty_sum" if "qty_sum" in pm.columns else "数量"

    # Monthly average sales (last 3 months)
    avg_sales_3m = last3.groupby("产品品种")[qty_col].sum() / 3
    # How many of the last 6 months had sales?
    active_months = last6.groupby("产品品种")["_月"].nunique()

    # Estimated total inventory = avg monthly sales × 2
    est_inventory = avg_sales_3m * 2

    result = pd.DataFrame({"产品品种": est_inventory.index, "库龄_库存总量": est_inventory.values})
    result["库龄_库存总量"] = result["库龄_库存总量"].fillna(0)

    # Aging distribution heuristic:
    #   active in all 6 months → 80% ≤180d, 15% 180d-1y, 5% >1y
    #   active in 3-5 months   → 50% ≤180d, 30% 180d-1y, 20% >1y
    #   active in 1-2 months   → 20% ≤180d, 40% 180d-1y, 40% >1y
    #   no recent activity      → 10% ≤180d, 30% 180d-1y, 60% >1y
    active = active_months.reindex(result["产品品种"]).fillna(0).values

    conditions = [
        active >= 6,
        (active >= 3) & (active < 6),
        (active >= 1) & (active < 3),
        active < 1,
    ]
    ratios = [
        (0.80, 0.15, 0.05),
        (0.50, 0.30, 0.20),
        (0.20, 0.40, 0.40),
        (0.10, 0.30, 0.60),
    ]

    r180 = np.select(conditions, [r[0] for r in ratios], default=0.50)
    r180_1y = np.select(conditions, [r[1] for r in ratios], default=0.30)
    r1y = np.select(conditions, [r[2] for r in ratios], default=0.20)

    result["库龄_180天以内"] = result["库龄_库存总量"] * r180
    result["库龄_180天到1年"] = result["库龄_库存总量"] * r180_1y
    result["库龄_1年以上"] = result["库龄_库存总量"] * r1y
    result["库龄_超180天占比"] = r180_1y + r1y
    result["库龄_超1年占比"] = r1y
    result["库龄_数据来源"] = "estimated"

    print(f"  [库龄估算] {len(result)} 个产品, 估算总库存={result['库龄_库存总量'].sum():.0f}")
    return result


# ── 1.4 Unified entry ────────────────────────────────────────

def get_inventory_aging(
    inv_path: str = None,
    bom_path: str = None,
    silver: dict = None,
    product_portrait: pd.DataFrame = None,
) -> pd.DataFrame:
    """获取产成品维度库龄表 — 优先真实数据(含BOM拆分)，降级估算。

    参数:
        inv_path: 库龄文件路径 (None → 降级估算)
        bom_path: BOM映射表路径 (None → 直接映射)
        silver: Silver层数据 (BOM拆分需要 product_monthly; 估算也需要)
        product_portrait: 产品画像 (估算可选)

    返回:
        产成品维度库龄 DataFrame
    """
    if inv_path is not None and os.path.exists(inv_path):
        inv_df = load_inventory_aging(inv_path)

        if bom_path is not None and os.path.exists(bom_path):
            bom_df = load_bom_mapping(bom_path)
            result = explode_inventory_to_finished(inv_df, bom_df, silver or {})
        else:
            print("  [库龄] 未提供BOM映射表，尝试直接映射")
            result = _direct_map_inventory(inv_df)

        result["_estimated"] = False
        return result

    print("  [库龄] 无真实库龄数据，启用估算降级")
    result = estimate_inventory_aging(silver or {}, product_portrait)
    result["_estimated"] = True
    return result


# ── 1.5 Customer-dimension inventory risk ────────────────────

def calc_customer_inventory_risk(
    customer_x_product: pd.DataFrame,
    inv_aging: pd.DataFrame,
) -> pd.DataFrame:
    """将产成品维度的库龄风险映射到客户维度。

    参数:
        customer_x_product: Silver层客户×产品聚合表 (需含 客户编号, 产品品种, rev_sum)
        inv_aging: get_inventory_aging() 返回的产成品维度库龄

    返回:
        DataFrame keyed by 客户编号:
          呆滞品种数, 呆滞金额占比, 超1年品种数, 超1年金额占比, 加权平均超180天占比
    """
    if len(inv_aging) == 0 or len(customer_x_product) == 0:
        return pd.DataFrame(columns=["客户编号"])

    cxp = customer_x_product.copy()
    cxp["产品品种"] = cxp["产品品种"].astype(str).str.strip()
    inv = inv_aging.copy()
    inv["产品品种"] = inv["产品品种"].astype(str).str.strip()

    # Merge customer products with inventory aging
    rev_col = "rev_sum" if "rev_sum" in cxp.columns else "金额"
    if rev_col not in cxp.columns:
        rev_col = [c for c in cxp.columns if "金额" in c or "rev" in c.lower()]
        rev_col = rev_col[0] if rev_col else cxp.columns[-1]

    merged = cxp.merge(
        inv[["产品品种", "库龄_超180天占比", "库龄_超1年占比"]],
        on="产品品种", how="left",
    )
    merged["库龄_超180天占比"] = merged["库龄_超180天占比"].fillna(0)
    merged["库龄_超1年占比"] = merged["库龄_超1年占比"].fillna(0)

    # Customer-level aggregation
    result = merged.groupby("客户编号").apply(_agg_customer_inv_risk, rev_col=rev_col, include_groups=False).reset_index()
    result.columns = [
        "客户编号", "呆滞品种数", "超1年品种数",
        "呆滞金额占比", "超1年金额占比", "加权平均超180天占比",
    ]

    # derived columns use _estimated from inv_aging if available
    if "_estimated" in inv_aging.columns:
        result["_estimated"] = inv_aging["_estimated"].iloc[0] if len(inv_aging) > 0 else True

    print(f"  [客户库龄风险] {len(result)} 客户, "
          f"呆滞品种>0的客户={(result['呆滞品种数'] > 0).sum()}, "
          f"超1年品种>0的客户={(result['超1年品种数'] > 0).sum()}")

    return result


def _agg_customer_inv_risk(group, rev_col):
    total_rev = group[rev_col].sum()
    stagnant_mask = group["库龄_超180天占比"] > 0.30
    dead_mask = group["库龄_超1年占比"] > 0.10
    stagnant_rev = group.loc[stagnant_mask, rev_col].sum() if any(stagnant_mask) else 0
    dead_rev = group.loc[dead_mask, rev_col].sum() if any(dead_mask) else 0
    weighted_avg = (
        (group["库龄_超180天占比"] * group[rev_col]).sum() / total_rev
        if total_rev > 0 else 0
    )
    return pd.Series([
        int(stagnant_mask.sum()),
        int(dead_mask.sum()),
        stagnant_rev / total_rev if total_rev > 0 else 0,
        dead_rev / total_rev if total_rev > 0 else 0,
        weighted_avg,
    ])
