# run_0.3_v3.py — 实验 0.3: 产品生命周期数据提取与对齐 (修正版v3)
# 从原始Excel建立 产品名称->产品线 映射
# 创建: 2026-06-12

import pandas as pd
import os
import random
import numpy as np
from pathlib import Path

np.random.seed(42)
random.seed(42)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BASE = str(PROJECT_ROOT)
OUTPUT_DIR = os.path.join(BASE, "output", "test")
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=" * 80)
print("EXPERIMENT 0.3 v3: Lifecycle Data Extraction & Alignment")
print("=" * 80)

# ── 1. Read raw Excel to build product->product_line mapping ──
print("\n[1] Reading raw Excel for product->product_line mapping...")
raw_path = os.path.join(BASE, "data", "财务分析-5月（6.3）.xlsx")
if not os.path.exists(raw_path):
    raise FileNotFoundError(f"Required file not found: {raw_path}")

# Read only needed columns
raw_sample = pd.read_excel(raw_path, sheet_name="总表", nrows=5)
print(f"  Raw columns ({len(raw_sample.columns)}):")
for i, c in enumerate(raw_sample.columns):
    print(f"    [{i}] {c}")

# Find name column (product SKU name) and product line column
name_col = None
pline_col = None
for c in raw_sample.columns:
    if c == '存货名称':
        name_col = c
    if c == '型号_产品线（新）':
        pline_col = c

if not name_col:
    # Try alternatives
    for c in raw_sample.columns:
        if '存货' in str(c) and '名称' in str(c):
            name_col = c
            break
    if not name_col:
        for c in raw_sample.columns:
            if '产品' in str(c) and ('名' in str(c) or '型号' in str(c)):
                name_col = c
                break

if not pline_col:
    for c in raw_sample.columns:
        if '产品线' in str(c):
            pline_col = c
            break

print(f"\n  Product name column: '{name_col}'")
print(f"  Product line column: '{pline_col}'")

if name_col and pline_col:
    # Read only these 2 columns to build mapping
    raw_mapping = pd.read_excel(raw_path, sheet_name="总表", usecols=[name_col, pline_col])
    raw_mapping = raw_mapping.dropna(subset=[name_col, pline_col])
    raw_mapping = raw_mapping.drop_duplicates(subset=[name_col])
    print(f"  Unique product->pline mappings: {len(raw_mapping)}")
    print(f"  Product lines in raw data: {raw_mapping[pline_col].nunique()}")
    print(f"  Product lines: {sorted(raw_mapping[pline_col].unique())}")
else:
    print(f"  ERROR: Cannot find required columns")

# ── 2. Load gold product portrait and join ───────────────────
print(f"\n[2] Loading gold_product_portrait and joining product line...")
gold_path = os.path.join(BASE, "output", "gold", "gold_product_portrait.csv")
if not os.path.exists(gold_path):
    raise FileNotFoundError(f"Required file not found: {gold_path}")
gold = pd.read_csv(gold_path)
print(f"  Products in gold: {len(gold)}")
print(f"  Gold product name column: 产品名称")
print(f"  Sample product names: {gold['产品名称'].head(3).tolist()}")

if name_col and pline_col:
    # Join on product name
    gold_merged = gold.merge(raw_mapping, left_on='产品名称', right_on=name_col, how='left')
    mapped = gold_merged[pline_col].notna().sum()
    unmapped = gold_merged[pline_col].isna().sum()
    print(f"  Products mapped to product line: {mapped}/{len(gold)} ({mapped/len(gold)*100:.1f}%)")
    print(f"  Products unmapped: {unmapped}")

    if unmapped > 0:
        # Show some unmapped products
        unmapped_products = gold_merged[gold_merged[pline_col].isna()]['产品名称'].head(10).tolist()
        print(f"  Sample unmapped products: {unmapped_products}")
else:
    gold_merged = gold.copy()
    gold_merged['_pline'] = None
    pline_col = '_pline'

# ── 3. Aggregate lifecycle features by product line ───────────
print(f"\n[3] Aggregating lifecycle features by product line...")

# Use the joined product line column
agg_col = pline_col if pline_col else '_pline'

# Count-based features
portrait_counts = gold_merged.groupby([agg_col, '当前画像']).size().unstack(fill_value=0)
risk_counts = gold_merged.groupby([agg_col, '综合风险等级']).size().unstack(fill_value=0)
mgmt_counts = gold_merged.groupby([agg_col, '管理层摘要']).size().unstack(fill_value=0)
rev_counts = gold_merged.groupby([agg_col, '营收-毛利综合判断']).size().unstack(fill_value=0)
dir_counts = gold_merged.groupby([agg_col, '增速方向']).size().unstack(fill_value=0)
k6_counts = gold_merged.groupby([agg_col, '是否已达6K']).size().unstack(fill_value=0)

# Continuous features
cont_agg = gold_merged.groupby(agg_col).agg(
    产品数=('产品名称', 'nunique'),
    近12月总销售额=('近12月销售额', 'sum'),
    近12月总销量=('近12月销量', 'sum'),
    加权平均风险评分=('综合评分', lambda x: np.average(x.dropna()) if len(x.dropna()) > 0 else np.nan),
    加权平均毛利率=('近12月毛利率%', lambda x: np.average(x.dropna()) if len(x.dropna()) > 0 else np.nan),
    加权平均毛利率趋势=('毛利率趋势斜率%/月', lambda x: np.average(x.dropna()) if len(x.dropna()) > 0 else np.nan),
    平均客户集中度=('客户集中度-前1大%', lambda x: x.dropna().mean() if len(x.dropna()) > 0 else np.nan),
    平均增长率=('近12月增长率%', lambda x: np.average(x.dropna()) if len(x.dropna()) > 0 else np.nan),
).reset_index()
cont_agg.columns = ['产品线', '产品数', '近12月总销售额', '近12月总销量',
                     '加权平均风险评分', '加权平均毛利率', '加权平均毛利率趋势',
                     '平均客户集中度', '平均增长率']

# Merge all features
pline_features = cont_agg.copy()
pline_features = pline_features[pline_features['产品线'].notna()]

# Add portrait distribution
for col in portrait_counts.columns:
    pline_features = pline_features.merge(
        portrait_counts[col].reset_index().rename(columns={col: f'画像_{col}', agg_col: '产品线'}),
        on='产品线', how='left'
    )

# Add risk distribution
for col in risk_counts.columns:
    if pd.notna(col):
        pline_features = pline_features.merge(
            risk_counts[col].reset_index().rename(columns={col: f'风险_{col}', agg_col: '产品线'}),
            on='产品线', how='left'
        )

# Compute derived metrics
n = pline_features['产品数']
pline_features['健康扩张占比'] = pline_features.get('画像_健康扩张', 0) / n
pline_features['衰退+夕阳占比'] = (pline_features.get('画像_衰退期', 0) + pline_features.get('画像_夕阳产品', 0)) / n
pline_features['新品占比'] = pline_features.get('画像_新品观察', 0) / n
pline_features['成长型占比'] = pline_features.get('画像_成长型', 0) / n
pline_features['现金牛占比'] = pline_features.get('画像_现金牛', 0) / n

high_risk = pline_features.get('风险_高风险', 0).fillna(0) + pline_features.get('风险_极高风险', 0).fillna(0)
pline_features['高风险+极高风险占比'] = high_risk / n
pline_features['低风险占比'] = pline_features.get('风险_低风险', 0).fillna(0) / n

# Healthy index
pline_features['健康度指标'] = (
    pline_features['健康扩张占比'].fillna(0) +
    pline_features['成长型占比'].fillna(0) +
    pline_features['现金牛占比'].fillna(0) -
    pline_features['衰退+夕阳占比'].fillna(0) -
    pline_features['高风险+极高风险占比'].fillna(0)
)

# Add direction, management, revenue-profit, 6K
for prefix, cnt_df in [('方向_', dir_counts), ('管理层_', mgmt_counts), ('营收判断_', rev_counts), ('6K_', k6_counts)]:
    for col in cnt_df.columns:
        if pd.notna(col):
            col_name = f'{prefix}{col}'
            pline_features = pline_features.merge(
                cnt_df[col].reset_index().rename(columns={col: col_name, agg_col: '产品线'}),
                on='产品线', how='left'
            )

# ── 4. Coverage check against 17 product lines ───────────────
print(f"\n[4] Coverage check:")
forecast_dir = os.path.join(BASE, "quarterly_forecast_package", "output", "quarterly_forecast")
hf_path = os.path.join(forecast_dir, "产品线季度历史与预测.csv")
if not os.path.exists(hf_path):
    raise FileNotFoundError(f"Required file not found: {hf_path}")
history = pd.read_csv(hf_path)
plines_17 = sorted(history[history['数据类型'] == '历史']['产品线'].unique())

covered = set(pline_features['产品线'].unique())
uncovered = [p for p in plines_17 if p not in covered]
print(f"  Product lines with lifecycle data: {len(covered)}")
print(f"  Matched to 17 core lines: {len(covered & set(plines_17))}")
print(f"  Uncovered core lines: {uncovered if uncovered else 'None'}")

# Check which covered lines are in the 17
matched_plines = covered & set(plines_17)
print(f"  Matched: {sorted(matched_plines)}")

# ── 5. Print summary for core product lines ──────────────────
print(f"\n{'='*80}")
print(f"PRODUCT LINE LIFECYCLE HEALTH SUMMARY")
print(f"{'='*80}")

# Select core product lines only
core_features = pline_features[pline_features['产品线'].isin(plines_17)].copy()

print(f"{'产品线':<22s} {'产品':>4s} {'健康度':>7s} {'衰退%':>6s} {'新品%':>6s} {'高风险%':>7s} {'毛利率%':>8s}")
print(f"{'-'*80}")
for _, row in core_features.iterrows():
    health = row['健康度指标'] if not pd.isna(row['健康度指标']) else 0
    dec_pct = row['衰退+夕阳占比'] if not pd.isna(row.get('衰退+夕阳占比')) else 0
    new_pct = row['新品占比'] if not pd.isna(row.get('新品占比')) else 0
    risk_pct = row['高风险+极高风险占比'] if not pd.isna(row.get('高风险+极高风险占比')) else 0
    gm = row['加权平均毛利率'] if not pd.isna(row.get('加权平均毛利率')) else 0
    print(f"{row['产品线']:<22s} {int(row['产品数']):>4d} {health:>7.3f} {dec_pct:>6.1%} {new_pct:>6.1%} {risk_pct:>7.1%} {gm:>8.1f}")

for pl in uncovered:
    print(f"{pl:<22s} {'N/A':>4s} {'N/A':>7s} {'N/A':>6s} {'N/A':>6s} {'N/A':>7s} {'N/A':>8s}")

# ── 6. Save ───────────────────────────────────────────────────
output_cols_v3 = ['产品线', '产品数', '近12月总销售额', '近12月总销量',
    '加权平均风险评分', '加权平均毛利率', '加权平均毛利率趋势',
    '平均客户集中度', '平均增长率',
    '健康扩张占比', '成长型占比', '现金牛占比', '衰退+夕阳占比', '新品占比',
    '高风险+极高风险占比', '低风险占比', '健康度指标']

available_final = [c for c in output_cols_v3 if c in pline_features.columns]
final_output = pline_features[pline_features['产品线'].isin(plines_17)][available_final]

output_path = os.path.join(OUTPUT_DIR, "lifecycle_features_by_pline.csv")
final_output.to_csv(output_path, index=False, encoding='utf-8-sig')
print(f"\n  Output: {output_path}")

# ── 7. Success criteria ───────────────────────────────────────
n_covered = len(matched_plines)
print(f"\n[7] Success Criteria:")
print(f"  Cover >= 14/17: {n_covered}/17 -> {'PASS' if n_covered >= 14 else 'FAIL'}")
if n_covered < 14:
    print(f"  NOTE: {len(uncovered)} product lines have no lifecycle mapping")
    print(f"  Per risk mitigation (plan): mark these factors as 'partial availability'")

print(f"\nPHASE 0 COMPLETE.")
