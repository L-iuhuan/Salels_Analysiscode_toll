"""
Batch A end-to-end test: 新品标记传播 + 爬坡期配置验证
Saves intermediate files for fast re-run.
"""
import sys, os, time, json, warnings, pickle
warnings.filterwarnings('ignore')

# 支持从 test/ 目录下直接运行
_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_TEST_DIR)
sys.path.insert(0, PROJECT_ROOT)
import pandas as pd, numpy as np

DATA_FILE = os.path.join(PROJECT_ROOT, 'data', '所有的出货明细5.9.xlsx')
DIAG_DIR = os.path.join(PROJECT_ROOT, 'output', 'test_diag')
os.makedirs(DIAG_DIR, exist_ok=True)
PKL = os.path.join(DIAG_DIR, '_intermediate.pkl')

# ---- Phase 1: Load & process to Silver (E/S heavy, ~200s) ----
if not os.path.exists(PKL):
    print("=" * 70)
    print("Phase 1: Load + Silver build")
    print("=" * 70)
    df_full = pd.read_excel(DATA_FILE, sheet_name=0, engine='openpyxl')
    print("  Loaded: {} rows x {} cols".format(len(df_full), len(df_full.columns)))

    has_new_flag = '是否新品' in df_full.columns
    vc_new = df_full['是否新品'].value_counts(dropna=False) if has_new_flag else None
    new_pct = (df_full['是否新品'] == '是').mean() * 100 if has_new_flag else 0
    print("  has_new_flag: {}, new_row_pct: {:.2f}%".format(has_new_flag, new_pct))

    from shared.data_cleaning import rename_erp_columns, monthly_aggregate_double_pass, filter_negative_qty, winsorize_margins
    df = rename_erp_columns(df_full.copy())
    df_clean = filter_negative_qty(df.copy())
    df_clean = winsorize_margins(df_clean)
    silver = monthly_aggregate_double_pass(df_clean)
    prod_monthly = silver['product_monthly']
    cxp = silver['customer_x_product']
    cust_monthly = silver['customer_monthly']
    has_in_silver = '新品标记' in prod_monthly.columns
    erp_new_ct = (prod_monthly['新品标记'] == '是').sum() if has_in_silver else 0
    print("  product_monthly: {}, has_new: {}, erp_new_rows: {}".format(prod_monthly.shape, has_in_silver, erp_new_ct))

    # Compare ERP vs auto-calc
    if has_new_flag:
        latest_month = prod_monthly['_月'].max()
        ps = prod_monthly.groupby('产品品种')['_月'].min().reset_index()
        ps.columns = ['产品品种', '首次销售月']
        ps['auto_new'] = (latest_month - ps['首次销售月']).apply(lambda x: x.n) <= 12
        erp_new_set = set(prod_monthly[prod_monthly['新品标记']=='是']['产品品种'].unique())
        auto_new_set = set(ps[ps['auto_new']]['产品品种'].unique())

    # Save intermediates
    to_save = {
        'df_full_shape': df_full.shape,
        'has_new_flag': has_new_flag,
        'new_pct': new_pct,
        'df_clean': df_clean,
        'prod_monthly': prod_monthly,
        'cxp': cxp,
        'cust_monthly': cust_monthly,
        'has_in_silver': has_in_silver,
        'erp_new_ct': erp_new_ct,
        'date_range': (str(df_full['发货日期'].min()), str(df_full['发货日期'].max())),
        'product_count': df_full['存货名称'].nunique(),
        'customer_count': df_full['代理商/直供名称'].nunique(),
        'vc_new': vc_new,
    }
    if has_new_flag:
        to_save['erp_new_count'] = len(erp_new_set)
        to_save['auto_new_count'] = len(auto_new_set)
        to_save['overlap_count'] = len(erp_new_set & auto_new_set)
        to_save['erp_unique'] = len(erp_new_set - auto_new_set)
        to_save['auto_unique'] = len(auto_new_set - erp_new_set)
    with open(PKL, 'wb') as f:
        pickle.dump(to_save, f)
    print("  Intermediates saved to {}".format(PKL))
else:
    print("=" * 70)
    print("Phase 1: Loading intermediates (skip data reload)")
    print("=" * 70)
    with open(PKL, 'rb') as f:
        to_save = pickle.load(f)
    df_clean = to_save['df_clean']
    prod_monthly = to_save['prod_monthly']
    cxp = to_save['cxp']
    cust_monthly = to_save['cust_monthly']
    has_new_flag = to_save['has_new_flag']
    has_in_silver = to_save['has_in_silver']
    erp_new_ct = to_save['erp_new_ct']
    print("  Loaded intermediates OK")

# ---- Phase 2: Tests ----
print("=" * 70)

# Test rename_erp_columns status
print("\n[TEST A] rename_erp_columns -> 新品标记列验证")
print("  has_new_flag: {}".format(has_new_flag))
if has_new_flag:
    print("  新增行占比: {:.2f}%".format(to_save['new_pct']))

print("\n[TEST B] Silver层新品标记传播验证")
print("  新品标记在 product_monthly: {}".format(has_in_silver))
if has_in_silver:
    print("  ERP标记=是的行数: {} / {}".format(erp_new_ct, len(prod_monthly)))

print("\n[TEST C] 新品判定 (仅ERP标记)")
if has_new_flag:
    print("  ERP标记新品品种: {}".format(to_save['erp_new_count']))
    print("  (自动计算逻辑保留作为回退, 输出仅使用ERP标记)")

# Test calc_new_product_cohort
print("\n[TEST D] 新品Cohort (calc_new_product_cohort)")
from shared.pricing import calc_new_product_cohort
cohort_result = calc_new_product_cohort(prod_monthly, cxp)
has_new_buyers = (cohort_result['是否采购新品']>0).sum()
print("  Cohort结果: {} customers".format(len(cohort_result)))
print("  有新品采购客户: {} / {} ({:.1f}%)".format(has_new_buyers, len(cohort_result), has_new_buyers/len(cohort_result)*100))
print("  新品渗透率: {:.2f}%".format(cohort_result['新品渗透率'].iloc[0]*100))
print("  新品采购占比均值: {:.2f}%".format(cohort_result['新品采购占比'].mean()*100))
# Save cohort
cohort_result.to_csv(os.path.join(DIAG_DIR, 'diag_cohort.csv'), index=False, encoding='utf-8-sig')

# Test product lifecycle profiling
print("\n[TEST E] 产品生命周期 profiling (ERP标记->is_new)")
from product_lifecycle.profiling import run_profiling
from config.settings import PRODUCT_LIFECYCLE

col_map_pl = PRODUCT_LIFECYCLE.get('col_map', {})
thr_pl = {k: v for k, v in PRODUCT_LIFECYCLE.items() if k != 'col_map'}
wgt_pl = thr_pl.pop('risk_weights', {})
ref_priority_pl = thr_pl.pop('ref_priority', [])
name_col = col_map_pl.get('产品名称列', '产品品种')
date_col = col_map_pl.get('发货日期列', '发货日期')
qty_col = col_map_pl.get('销量列', '数量')
rev_col = col_map_pl.get('营收列', '金额')
profit_col = col_map_pl.get('利润列', '利润')
cust_col_pl = col_map_pl.get('客户列', '客户编号')
order_col = col_map_pl.get('订单号列', '订单编号')
cat_col = col_map_pl.get('分类参照列', '产品一级分类')

# Ensure _月 column
if '_月' not in df_clean.columns:
    df_clean['_月'] = df_clean[date_col].dt.to_period('M')
latest_month = df_clean['_月'].max()
print("  latest_month: {}, products: {}".format(latest_month, df_clean[name_col].nunique()))

t0 = time.time()
result_df, data_insufficient, out, ratio_cols, pp_cols, _t4 = run_profiling(
    df_clean, latest_month, thr_pl, name_col, date_col, qty_col, rev_col,
    profit_col, cust_col_pl, order_col, cat_col, ref_priority_pl, wgt_pl, mode='full'
)
prof_t = time.time() - t0
print("  Profiling time: {:.0f}s".format(prof_t))
print("  Result: {} products".format(len(result_df)))

new_obs = (result_df['当前画像'] == '新品观察').sum()
print("  新品观察: {} / {} ({:.1f}%)".format(new_obs, len(result_df), new_obs/len(result_df)*100))
for img, cnt in result_df['当前画像'].value_counts().items():
    print("    {}: {}".format(img, cnt))
result_df.to_csv(os.path.join(DIAG_DIR, 'diag_product_portrait.csv'), index=False, encoding='utf-8-sig')

# Test customer lifecycle stages
print("\n[TEST F] 客户生命周期阶段 (爬坡期参数验证)")
from shared.pricing import calc_customer_lifecycle_stage
stages_thr = calc_customer_lifecycle_stage(cust_monthly, latest_month=latest_month, thr={
    '爬坡期环比阈值': 0.15,
    '爬坡期_环比增长前N月均值': 3,
})
print("  Stages: {} customers".format(len(stages_thr)))
for stage, cnt in stages_thr['客户生命周期'].value_counts().items():
    print("    {}: {}".format(stage, cnt))
stages_thr.to_csv(os.path.join(DIAG_DIR, 'diag_customer_stages.csv'), index=False, encoding='utf-8-sig')

# Save summary JSON
summary = {
    'data_rows': to_save.get('df_full_shape', [0,0])[0],
    'data_cols': to_save.get('df_full_shape', [0,0])[1],
    'date_range': to_save.get('date_range', ('','')),
    'product_count': to_save.get('product_count', 0),
    'customer_count': to_save.get('customer_count', 0),
    'has_is_new_column': bool(has_new_flag),
    'new_row_pct': float(to_save.get('new_pct', 0)),
    'product_monthly_has_new_flag': bool(has_in_silver),
    'erp_new_row_count': int(erp_new_ct),
    'profile_new_obs_count': int(new_obs),
    'profile_total_products': int(len(result_df)),
    'cohort_new_buyers': int(has_new_buyers),
    'cohort_total_customers': int(len(cohort_result)),
    'cohort_new_penetration': float(cohort_result['新品渗透率'].iloc[0]),
    'cohort_new_ratio_avg': float(cohort_result['新品采购占比'].mean()),
    'product_portraits': {str(k): int(v) for k, v in result_df['当前画像'].value_counts().items()},
    'customer_stages': {str(k): int(v) for k, v in stages_thr['客户生命周期'].value_counts().items()},
    'profiling_time_s': round(prof_t, 1),
}
if has_new_flag:
    summary['erp_new_products'] = int(to_save.get('erp_new_count', 0))
    summary['auto_new_products'] = int(to_save.get('auto_new_count', 0))
    summary['erp_auto_overlap'] = int(to_save.get('overlap_count', 0))
    summary['erp_unique'] = int(to_save.get('erp_unique', 0))
    summary['auto_unique'] = int(to_save.get('auto_unique', 0))

with open(os.path.join(DIAG_DIR, 'test_summary.json'), 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print("\n[OK] Summary saved. All tests complete.")
print("Diagnostics in: {}".format(DIAG_DIR))
