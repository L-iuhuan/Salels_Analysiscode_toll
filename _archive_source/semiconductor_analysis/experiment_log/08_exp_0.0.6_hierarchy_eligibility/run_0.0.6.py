# -*- coding: utf-8 -*-
# run_0.0.6.py — 实验 0.0.6: Hierarchy Eligibility by Product Line
# 评估17条产品线在各层级预测维度上的数据就绪度
# 创建: 2026-06-12

import pandas as pd
import numpy as np
import os
import random
from pathlib import Path

np.random.seed(42)
random.seed(42)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BASE = str(PROJECT_ROOT)
SILVER_DIR = os.path.join(BASE, "output", "silver")
OUTPUT_DIR = os.path.join(BASE, "output", "test")
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=" * 80)
print("EXPERIMENT 0.0.6: Hierarchy Eligibility by Product Line")
print("=" * 80)

# ── 1. Load data ──────────────────────────────────────────────
print("\n[1] Loading silver_cleaned_rows.csv...")
csv_path = os.path.join(SILVER_DIR, "silver_cleaned_rows.csv")
cols_needed = [
    '发货日期', '型号_产品线（新）', '型号_产品品类',
    '存货编码', '终端客户名称_客户类别', '出货总金额', '金额'
]
# Note: '产品系列' and '存货名称' are NOT present in silver_cleaned_rows.csv;
# use '型号_产品品类' directly as category_key; use '存货编码' as SKU key.
df = pd.read_csv(csv_path, usecols=cols_needed, encoding='utf-8-sig')
print(f"    Loaded {len(df):,} rows, {len(df.columns)} columns")

# Parse dates
df['发货日期'] = pd.to_datetime(df['发货日期'])
df['month_key'] = df['发货日期'].dt.to_period('M')
df['year'] = df['发货日期'].dt.year

print(f"    Date range: {df['发货日期'].min().date()} to {df['发货日期'].max().date()}")
print(f"    Distinct months: {df['month_key'].nunique()}")

# ── 2. Identify product lines ─────────────────────────────────
product_lines = sorted(df['型号_产品线（新）'].dropna().unique())
print(f"\n[2] Product lines found: {len(product_lines)}")
for i, pl in enumerate(product_lines):
    n_rows = (df['型号_产品线（新）'] == pl).sum()
    n_months = df[df['型号_产品线（新）'] == pl]['month_key'].nunique()
    print(f"    {i+1:2d}. {pl}: {n_rows:,} rows, {n_months} months")

# ── 3. Prepare derived keys ───────────────────────────────────
# Category key: 型号_产品品类 (产品系列 not in silver CSV)
df['category_key'] = df['型号_产品品类'].fillna('')
df['category_key'] = df['category_key'].replace('', np.nan)

# SKU key: 存货编码 (存货名称 not in silver CSV)
df['sku_key'] = df['存货编码'].fillna('')

# Customer key
df['cust_key'] = df['终端客户名称_客户类别'].fillna('')

# ── 4. Determine time window ──────────────────────────────────
all_months = sorted(df['month_key'].unique())
latest_month = all_months[-1]
cutoff_36m = latest_month - 35  # Last 36 complete months
recent_36_months = [m for m in all_months if m >= cutoff_36m]
actual_n_months = len(recent_36_months)
print(f"\n[3] Time window:")
print(f"    Latest month: {latest_month}")
print(f"    36-month window: {recent_36_months[0]} to {recent_36_months[-1]} ({actual_n_months} available)")

# ── 5. Compute eligibility per product line ───────────────────
print(f"\n[4] Computing eligibility per product line...")
print(f"    {'产品线':<28s} PL_Q  PL_M  Cat_M SKU_M  P_C   C_T")
print(f"    {'-'*28} {'-'*4} {'-'*4} {'-'*4} {'-'*4} {'-'*4} {'-'*4}")

results = []

for pline in product_lines:
    pline_mask = df['型号_产品线（新）'] == pline
    pline_df = df[pline_mask].copy()

    total_rows_pline = len(pline_df)

    row = {'产品线': pline}

    # ── 5a. product_line_quarterly: always eligible ────────────
    row['product_line_quarterly_eligible'] = True

    # ── 5b. product_line_monthly ───────────────────────────────
    # Require: last 36 months have >=18 effective months, zero-month ratio <60%
    pline_recent = pline_df[pline_df['month_key'].isin(recent_36_months)]
    effective_months_pline = pline_recent['month_key'].nunique()
    zero_months_pline = actual_n_months - effective_months_pline
    zero_month_ratio_pline = zero_months_pline / actual_n_months if actual_n_months > 0 else 1.0

    pl_monthly_eligible = (effective_months_pline >= 18) and (zero_month_ratio_pline < 0.60)
    row['product_line_monthly_eligible'] = pl_monthly_eligible

    pl_monthly_reasons = []
    if effective_months_pline < 18:
        pl_monthly_reasons.append(
            f"effective months {effective_months_pline}/{actual_n_months} < 18"
        )
    if zero_month_ratio_pline >= 0.60:
        pl_monthly_reasons.append(
            f"zero-month ratio {zero_month_ratio_pline:.1%} >= 60%"
        )
    row['product_line_monthly_reason'] = (
        '; '.join(pl_monthly_reasons) if pl_monthly_reasons else
        f'OK ({effective_months_pline}/{actual_n_months} effective months, zero={zero_month_ratio_pline:.1%})'
    )

    # ── 5c. category_monthly ──────────────────────────────────
    # Require: >=2 categories, each with >=6 effective months,
    #   category_key missing rate low (<30%), no cross-product-line categories
    cat_series = pline_df['category_key'].dropna()
    categories = sorted(cat_series.unique())
    n_categories = len(categories)

    # Check cross-product-line categories
    cross_pline_cats = []
    for cat in categories:
        global_plines = df[df['category_key'] == cat]['型号_产品线（新）'].dropna().unique()
        if len(global_plines) > 1:
            cross_pline_cats.append(cat)

    # Category effective months (in recent 36 months)
    cats_with_enough_months = 0
    for cat in categories:
        cat_recent = pline_df[
            (pline_df['category_key'] == cat) &
            (pline_df['month_key'].isin(recent_36_months))
        ]
        if cat_recent['month_key'].nunique() >= 6:
            cats_with_enough_months += 1

    # Category key missing rate (rows where category_key is null)
    cat_missing_count = pline_df['category_key'].isna().sum()
    cat_missing_rate = cat_missing_count / total_rows_pline if total_rows_pline > 0 else 1.0

    cat_monthly_reasons = []
    if n_categories < 2:
        cat_monthly_reasons.append(
            f"only {n_categories} categories (need >=2)"
        )
    if len(cross_pline_cats) > 0:
        cat_monthly_reasons.append(
            f"{len(cross_pline_cats)} categories cross product lines: "
            f"{cross_pline_cats[:3]}{'...' if len(cross_pline_cats) > 3 else ''}"
        )
    if cats_with_enough_months < 2:
        cat_monthly_reasons.append(
            f"only {cats_with_enough_months}/{n_categories} categories have >=6 effective months"
        )
    if cat_missing_rate > 0.30:
        cat_monthly_reasons.append(
            f"category_key missing rate {cat_missing_rate:.1%} > 30%"
        )

    cat_monthly_eligible = (
        n_categories >= 2
        and len(cross_pline_cats) == 0
        and cats_with_enough_months >= 2
        and cat_missing_rate <= 0.30
    )
    row['category_monthly_eligible'] = cat_monthly_eligible
    row['category_monthly_reason'] = (
        '; '.join(cat_monthly_reasons) if cat_monthly_reasons else
        f'OK ({n_categories} cats, {cats_with_enough_months} with >=6mo, missing={cat_missing_rate:.1%})'
    )

    # ── 5d. sku_monthly ───────────────────────────────────────
    # Require: enough SKUs with effective months >=6 or nonzero months >=4,
    #   head SKUs cover >=70% sales, tail pool for others
    sku_sales = pline_df.groupby('sku_key')['出货总金额'].sum().sort_values(ascending=False)
    total_pline_sales = sku_sales.sum()

    # Count eligible SKUs
    sku_eligible_set = set()
    head_skus_list = []
    cumulative_sales = 0.0
    head_covered = False

    for sku, sales in sku_sales.items():
        sku_df = pline_df[pline_df['sku_key'] == sku]
        sku_eff_months = sku_df['month_key'].nunique()
        sku_nonzero_months = sku_df[sku_df['出货总金额'] > 0]['month_key'].nunique()

        if sku_eff_months >= 6 or sku_nonzero_months >= 4:
            sku_eligible_set.add(sku)

        cumulative_sales += sales
        if not head_covered:
            head_skus_list.append(sku)
            if total_pline_sales > 0 and cumulative_sales / total_pline_sales >= 0.70:
                head_covered = True

    total_skus = len(sku_sales)
    n_eligible_skus = len(sku_eligible_set)
    n_head_skus = len(head_skus_list)
    n_head_eligible = len([s for s in head_skus_list if s in sku_eligible_set])
    n_tail_skus = total_skus - n_head_skus

    MIN_ELIGIBLE_SKUS = 3
    sku_monthly_reasons = []

    if n_eligible_skus < MIN_ELIGIBLE_SKUS:
        sku_monthly_reasons.append(
            f"only {n_eligible_skus} eligible SKUs (need >= {MIN_ELIGIBLE_SKUS})"
        )
    if not head_covered:
        sku_monthly_reasons.append(
            f"head SKUs ({n_head_skus}) do not cover 70% of sales"
        )

    sku_monthly_eligible = (n_eligible_skus >= MIN_ELIGIBLE_SKUS) and head_covered
    row['sku_monthly_eligible'] = sku_monthly_eligible
    row['sku_monthly_reason'] = (
        '; '.join(sku_monthly_reasons) if sku_monthly_reasons else
        f'OK ({n_eligible_skus} eligible of {total_skus} SKUs, '
        f'{n_head_eligible}/{n_head_skus} head eligible, {n_tail_skus} tail)'
    )

    # ── 5e. product_customer ──────────────────────────────────
    # Only for head customer/SKU combos; cell effective months >= 6
    pline_df['cust_sku_key'] = (
        pline_df['cust_key'].astype(str) + '|||' + pline_df['sku_key'].astype(str)
    )

    # Group by customer x SKU combo
    cs_eff_months = pline_df.groupby('cust_sku_key')['month_key'].nunique()
    cs_sales = pline_df.groupby('cust_sku_key')['出货总金额'].sum().sort_values(ascending=False)

    total_cs_sales = cs_sales.sum()
    cs_cumulative = 0.0
    head_cs_count = 0
    head_cs_eligible = 0

    for cs_key, cs_sales_val in cs_sales.items():
        cs_cumulative += cs_sales_val
        head_cs_count += 1

        eff = cs_eff_months.get(cs_key, 0)
        if eff >= 6:
            head_cs_eligible += 1

        if total_cs_sales > 0 and cs_cumulative / total_cs_sales >= 0.70:
            break

    total_cs_combos = len(cs_sales)

    pc_reasons = []
    pc_eligible = True

    if head_cs_count == 0:
        pc_eligible = False
        pc_reasons.append("no customer-SKU combos found")
    elif head_cs_eligible == 0:
        pc_eligible = False
        pc_reasons.append(
            f"0/{head_cs_count} head combos have >=6 effective months"
        )
    elif head_cs_eligible < max(1, head_cs_count * 0.5):
        # At least 50% of head combos should be eligible
        pc_eligible = False
        pc_reasons.append(
            f"only {head_cs_eligible}/{head_cs_count} ({head_cs_eligible/head_cs_count:.0%}) "
            f"head combos have >=6 effective months"
        )

    row['product_customer_eligible'] = pc_eligible
    row['product_customer_reason'] = (
        '; '.join(pc_reasons) if pc_reasons else
        f'OK ({head_cs_eligible}/{head_cs_count} head combos eligible '
        f'of {total_cs_combos} total combos)'
    )

    # ── 5f. customer_tier ─────────────────────────────────────
    # Use 终端客户名称_客户类别 only
    # 2024+ missing rate must be 0
    # Allow Unknown bucket for 2023+
    # Forbid customer analysis system scores (use raw column only)
    mask_2024plus = pline_df['year'] >= 2024
    recent_2024_df = pline_df[mask_2024plus]

    missing_2024 = recent_2024_df['cust_key'].isna().sum() + (recent_2024_df['cust_key'] == '').sum()
    total_2024 = len(recent_2024_df)
    missing_rate_2024 = missing_2024 / total_2024 if total_2024 > 0 else 0.0

    # Distinct customer tiers observed
    customer_tiers = pline_df['cust_key'].replace('', np.nan).dropna().unique()

    ct_reasons = []
    ct_eligible = True

    if missing_rate_2024 > 0:
        ct_eligible = False
        ct_reasons.append(
            f"2024+ missing rate {missing_rate_2024:.1%} > 0% "
            f"({missing_2024}/{total_2024} rows missing)"
        )

    row['customer_tier_eligible'] = ct_eligible
    row['customer_tier_reason'] = (
        '; '.join(ct_reasons) if ct_reasons else
        f'OK (2024+ 0% missing, {len(customer_tiers)} tiers, {total_2024:,} rows since 2024)'
    )

    # ── 5g. Recommended hierarchy candidates ───────────────────
    candidates = []
    if row['product_line_quarterly_eligible']:
        candidates.append('product_line_quarterly')
    if row['product_line_monthly_eligible']:
        candidates.append('product_line_monthly')
    if row['category_monthly_eligible']:
        candidates.append('category_monthly')
    if row['sku_monthly_eligible']:
        candidates.append('sku_monthly')
    if row['product_customer_eligible']:
        candidates.append('product_customer')
    if row['customer_tier_eligible']:
        candidates.append('customer_tier')
    row['recommended_hierarchy_candidates'] = ', '.join(candidates)

    results.append(row)

    # Per-line status
    def tick(b):
        return 'Y' if b else 'N'

    print(
        f"    {pline:<28s} {tick(row['product_line_quarterly_eligible']):>4s} "
        f"{tick(row['product_line_monthly_eligible']):>4s} "
        f"{tick(row['category_monthly_eligible']):>4s} "
        f"{tick(row['sku_monthly_eligible']):>4s} "
        f"{tick(row['product_customer_eligible']):>4s} "
        f"{tick(row['customer_tier_eligible']):>4s}"
    )

# ── 6. Build output DataFrame ─────────────────────────────────
print(f"\n[5] Building output CSV...")
out_cols = [
    '产品线',
    'product_line_quarterly_eligible',
    'product_line_monthly_eligible', 'product_line_monthly_reason',
    'category_monthly_eligible', 'category_monthly_reason',
    'sku_monthly_eligible', 'sku_monthly_reason',
    'product_customer_eligible', 'product_customer_reason',
    'customer_tier_eligible', 'customer_tier_reason',
    'recommended_hierarchy_candidates'
]
out_df = pd.DataFrame(results, columns=out_cols)

output_path = os.path.join(OUTPUT_DIR, "hierarchy_eligibility_by_pline.csv")
out_df.to_csv(output_path, index=False, encoding='utf-8-sig')
print(f"    Output: {output_path}")
print(f"    Rows: {len(out_df)}")

# ── 7. Summary ────────────────────────────────────────────────
print(f"\n{'='*80}")
print("SUMMARY: Eligible product lines per hierarchy level")
print(f"{'='*80}")
print(f"Total product lines evaluated: {len(out_df)}")
print()

summary_map = {
    'product_line_quarterly_eligible': 'Product Line Quarterly (always)',
    'product_line_monthly_eligible': 'Product Line Monthly (>=18mo, zero<60%)',
    'category_monthly_eligible': 'Category Monthly (>=2 cats, >=6mo each)',
    'sku_monthly_eligible': 'SKU Monthly (>=3 eligible, head>=70% sales)',
    'product_customer_eligible': 'Product×Customer (head combos >=6mo)',
    'customer_tier_eligible': 'Customer Tier (2024+ 0% missing)',
}

for col, desc in summary_map.items():
    eligible = out_df[col].sum()
    pct = eligible / len(out_df) * 100
    bar = '#' * int(pct / 5)
    print(f"  {desc}")
    print(f"    Eligible: {eligible}/{len(out_df)} ({pct:.0f}%) {bar}")
    if eligible < len(out_df):
        not_eligible = out_df[~out_df[col]]['产品线'].tolist()
        print(f"    Not eligible: {not_eligible}")
    print()

# Print detailed reasons for non-eligible product lines
print(f"{'='*80}")
print("DETAILED REASONS (non-eligible)")
print(f"{'='*80}")
for _, row_data in out_df.iterrows():
    pl = row_data['产品线']
    issues = []
    for col in ['product_line_monthly', 'category_monthly', 'sku_monthly',
                 'product_customer', 'customer_tier']:
        if not row_data[f'{col}_eligible']:
            reason = row_data[f'{col}_reason']
            issues.append(f"{col}: {reason}")
    if issues:
        print(f"\n  [{pl}]")
        for issue in issues:
            print(f"    {issue}")

print(f"\n{'='*80}")
print("EXPERIMENT 0.0.6 COMPLETE")
print(f"{'='*80}")
