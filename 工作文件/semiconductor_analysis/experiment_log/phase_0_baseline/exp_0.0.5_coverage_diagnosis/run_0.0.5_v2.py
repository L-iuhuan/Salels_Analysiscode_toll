# run_0.0.5_v2.py — 实验 0.0.5: 产品线覆盖与字段一致性诊断
# 创建: 2026-06-12
# 数据源: data/财务分析-5月（6.3）.xlsx, output/silver/, quarterly_forecast_package/output/

import pandas as pd
import os
import json

BASE = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis"
FORECAST_DIR = os.path.join(BASE, "quarterly_forecast_package", "output", "quarterly_forecast")
FORECAST_LOCKED_DIR = os.path.join(BASE, "quarterly_forecast_package", "output", "quarterly_forecast_locked")
FORECAST_CUSTOMER_DIR = os.path.join(BASE, "quarterly_forecast_package", "output", "quarterly_forecast_customer")
OUTPUT_DIR = os.path.join(BASE, "output", "test")
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=" * 80)
print("EXPERIMENT 0.0.5: Product Line Coverage & Field Consistency Diagnosis")
print("=" * 80)

results = {}

# ── Source 1: Raw Excel data ──────────────────────────────────
print("\n[1] Raw Excel data...")
raw_path = os.path.join(BASE, "data", "财务分析-5月（6.3）.xlsx")
try:
    raw_df = pd.read_excel(raw_path, sheet_name="总表", nrows=0)
    print(f"    Columns: {len(raw_df.columns)}")
    pline_col_candidates = ['型号_产品线（新）', '产品线', '产品线（新）']
    raw_pline_col = None
    for c in pline_col_candidates:
        if c in raw_df.columns:
            raw_pline_col = c
            break
    if raw_pline_col:
        raw_plines_raw = pd.read_excel(raw_path, sheet_name="总表", usecols=[raw_pline_col])
        raw_plines = set(raw_plines_raw[raw_pline_col].dropna().unique())
        results['raw'] = {'count': len(raw_plines), 'values': raw_plines, 'column': raw_pline_col}
        print(f"    Product lines via '{raw_pline_col}': {len(raw_plines)}")
    else:
        print(f"    WARNING: No product line column found. Available: {list(raw_df.columns)[:20]}")
        results['raw'] = {'count': 0, 'values': set(), 'column': None}
except Exception as e:
    print(f"    ERROR: {e}")
    results['raw'] = {'count': 0, 'values': set(), 'column': None}

# ── Source 2: Silver cleaned data ─────────────────────────────
print("\n[2] Silver cleaned data...")
silver_path = os.path.join(BASE, "output", "silver", "silver_cleaned_rows.csv")
try:
    if os.path.exists(silver_path):
        silver_sample = pd.read_csv(silver_path, nrows=1)
        silver_pline_col = None
        for c in pline_col_candidates:
            if c in silver_sample.columns:
                silver_pline_col = c
                break
        if silver_pline_col:
            silver_plines_raw = pd.read_csv(silver_path, usecols=[silver_pline_col])
            silver_plines = set(silver_plines_raw[silver_pline_col].dropna().unique())
            results['silver'] = {'count': len(silver_plines), 'values': silver_plines, 'column': silver_pline_col}
            print(f"    Product lines via '{silver_pline_col}': {len(silver_plines)}")
        else:
            print(f"    No product line column in silver")
            results['silver'] = {'count': 0, 'values': set(), 'column': None}
    else:
        print(f"    Silver file not found")
        results['silver'] = {'count': 0, 'values': set(), 'column': None}
except Exception as e:
    print(f"    ERROR: {e}")
    results['silver'] = {'count': 0, 'values': set(), 'column': None}

# ── Source 3: History/Forecast main table ─────────────────────
print("\n[3] History/Forecast main table...")
hf = pd.read_csv(os.path.join(FORECAST_DIR, "产品线季度历史与预测.csv"))
hist_plines = set(hf[hf['数据类型'] == '历史']['产品线'].unique())
forecast_plines = set(hf[hf['数据类型'] == '预测']['产品线'].unique())
results['history'] = {'count': len(hist_plines), 'values': hist_plines}
results['forecast'] = {'count': len(forecast_plines), 'values': forecast_plines}
print(f"    History product lines: {len(hist_plines)}")
print(f"    Forecast product lines: {len(forecast_plines)}")

# ── Source 4: Method ranking ──────────────────────────────────
print("\n[4] Method ranking...")
ranking = pd.read_csv(os.path.join(FORECAST_DIR, "预测方法排行榜.csv"))
ranking_plines = set(ranking['产品线'].unique())
results['ranking'] = {'count': len(ranking_plines), 'values': ranking_plines}
print(f"    Ranking product lines: {len(ranking_plines)}")

# ── Source 5: Locked forecast ─────────────────────────────────
print("\n[5] Locked forecast...")
try:
    lf = pd.read_csv(os.path.join(FORECAST_LOCKED_DIR, "产品线季度历史与预测.csv"))
    locked_plines = set(lf[lf['数据类型'] == '历史']['产品线'].unique())
    results['locked'] = {'count': len(locked_plines), 'values': locked_plines}
    print(f"    Locked product lines: {len(locked_plines)}")
except:
    results['locked'] = {'count': 0, 'values': set()}
    print(f"    Locked: not available")

# ── Source 6: Gold product portrait ───────────────────────────
print("\n[6] Gold product portrait...")
gold = pd.read_csv(os.path.join(BASE, "output", "gold", "gold_product_portrait.csv"))
ref_groups = set(gold['所属参照组'].dropna().unique())
results['gold_ref'] = {'count': len(ref_groups), 'values': ref_groups}
print(f"    所属参照组 unique: {len(ref_groups)}")

# ── Source 7: Customer forecast ───────────────────────────────
print("\n[7] Customer forecast...")
try:
    cf = pd.read_csv(os.path.join(FORECAST_CUSTOMER_DIR, "客户季度历史与预测.csv"))
    if '产品线' in cf.columns:
        cust_plines = set(cf['产品线'].dropna().unique())
        results['customer'] = {'count': len(cust_plines), 'values': cust_plines}
        print(f"    Customer forecast product lines: {len(cust_plines)}")
    else:
        results['customer'] = {'count': 0, 'values': set()}
        print(f"    No product line column in customer forecast")
except:
    results['customer'] = {'count': 0, 'values': set()}
    print(f"    Customer forecast: not available")

# ── Compile cross-reference matrix ────────────────────────────
print("\n" + "=" * 80)
print("CROSS-REFERENCE MATRIX")
print("=" * 80)

# Union of all product lines from key sources
primary_sources = ['raw', 'silver', 'history', 'forecast', 'ranking']
all_plines_primary = set()
for src in primary_sources:
    if src in results and results[src]['count'] > 0:
        all_plines_primary.update(results[src]['values'])

print(f"\nTotal unique product lines (primary sources): {len(all_plines_primary)}")

# Build diagnosis
rows = []
for pline in sorted(all_plines_primary):
    row = {'产品线名称': pline}
    row['原始Excel'] = '是' if (results.get('raw') and pline in results['raw']['values']) else '否'
    row['Silver明细'] = '是' if (results.get('silver') and pline in results['silver']['values']) else '否'
    row['历史主表'] = '是' if pline in hist_plines else '否'
    row['预测主表'] = '是' if pline in forecast_plines else '否'
    row['方法排行榜'] = '是' if pline in ranking_plines else '否'
    row['锁定预测'] = '是' if (results.get('locked') and pline in results['locked']['values']) else '否'

    # Get WAPE
    wape = None
    if pline in ranking_plines:
        sel = ranking[(ranking['产品线'] == pline) & (ranking['是否最终选中'] == '是')]
        if len(sel) > 0:
            wape = sel['销售额WAPE'].values[0]
    row['当前最优WAPE'] = round(wape, 4) if wape else None

    # Can enter subsequent experiments?
    in_all_core = (row['历史主表'] == '是' and row['预测主表'] == '是' and row['方法排行榜'] == '是')
    row['可进入后续实验'] = '是' if in_all_core else '否'

    # Missing reason
    missing = []
    if row['历史主表'] == '否': missing.append('历史主表')
    if row['预测主表'] == '否': missing.append('预测主表')
    if row['方法排行榜'] == '否': missing.append('方法排行榜')
    row['缺失原因'] = '; '.join(missing) if missing else '无缺失'

    rows.append(row)

diag_df = pd.DataFrame(rows)

# ── Summary statistics ───────────────────────────────────────
core_plines = diag_df[diag_df['可进入后续实验'] == '是']
print(f"\nCore product lines (covered in hist+forecast+ranking): {len(core_plines)}")
print(f"Other product lines (only in raw/silver/etc): {len(diag_df) - len(core_plines)}")

# Check for mismatches
hist_only = hist_plines - ranking_plines
rank_only = ranking_plines - hist_plines
raw_only = (results.get('raw') and results['raw']['values'] - hist_plines) or set()
print(f"\nProduct lines in history but NOT ranking: {hist_only if hist_only else 'None'}")
print(f"Product lines in ranking but NOT history: {rank_only if rank_only else 'None'}")
print(f"Product lines in raw but NOT history: {len(raw_only)} lines (sub-categories, expected)")

# Check locked vs current: any missing?
if results.get('locked') and results['locked']['count'] > 0:
    missing_from_locked = hist_plines - results['locked']['values']
    extra_in_locked = results['locked']['values'] - hist_plines
    print(f"\nProduct lines missing from locked (vs current): {missing_from_locked if missing_from_locked else 'None'}")
    print(f"Product lines extra in locked (vs current): {extra_in_locked if extra_in_locked else 'None'}")

# Print core 17 product lines
print(f"\n{'='*80}")
print(f"CORE 17 PRODUCT LINES (enter subsequent experiments)")
print(f"{'='*80}")
print(f"{'产品线':<25s} {'原始Excel':>6s} {'Silver':>6s} {'历史':>4s} {'预测':>4s} {'排行':>4s} {'WAPE':>8s}")
print("-" * 75)
for _, row in core_plines.iterrows():
    print(f"{row['产品线名称']:<25s} {row['原始Excel']:>6s} {row['Silver明细']:>6s} {row['历史主表']:>4s} {row['预测主表']:>4s} {row['方法排行榜']:>4s} {str(row['当前最优WAPE']):>8s}")

# ── Save ─────────────────────────────────────────────────────
output_path = os.path.join(OUTPUT_DIR, "product_line_coverage_diagnosis.csv")
diag_df.to_csv(output_path, index=False, encoding='utf-8-sig')
print(f"\nOutput: {output_path}")
print(f"Total rows: {len(diag_df)}")

# ── Field mapping check ──────────────────────────────────────
print(f"\n{'='*80}")
print(f"FIELD MAPPING CONSISTENCY CHECK")
print(f"{'='*80}")

# Check product-portrait reference group mapping
# Do all products' 所属参照组 map to one of the 17 product lines?
gold_pline_col = None
for c in ['型号_产品线（新）', '产品线']:
    if c in gold.columns:
        gold_pline_col = c
        break

if gold_pline_col:
    gold_product_plines = set(gold[gold_pline_col].dropna().unique())
    print(f"Product portrait product lines (via '{gold_pline_col}'): {len(gold_product_plines)}")
    unmapped = gold_product_plines - hist_plines
    if unmapped:
        print(f"WARNING: {len(unmapped)} product lines in gold not in history: {unmapped}")
else:
    print(f"WARNING: No product line column in gold_product_portrait")
    print(f"  Columns with '产品线' or '参照': {[c for c in gold.columns if '产品线' in c or '参照' in c]}")

print(f"\n{'='*80}")
print(f"DIAGNOSIS COMPLETE")
print(f"{'='*80}")
