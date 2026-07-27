# Pipeline Node Map — Data Lineage & Row Count Traceability

> Generated from code analysis. Row counts marked with `?` are unknown at code-read time.
> Known counts use actual `print()` outputs from code.

---

## Legend

```
[Node Name]
  Input:  <source>   ← what feeds this node
  Output: <dest>     ← what this node produces
  Filter: <logic>    ← operations that change row count
  Rows:   <N> → <M>  ← row count transformation (if known)
```

---

## STAGE 0: Source Data

```
[Source Excel]
  File:  data/*.xlsx  (auto-detected, alphabetically first)
  Sheets:
    - Sheet 0: Transaction data (row-level: date × customer × product)
    - "客户信息表": Customer master data (客户编号, 渠道类型, 客户等级, 所属区域)
  Rows:  ? (unknown, depends on data volume)
```

---

## STAGE 1: Silver Layer

### Node 1a: Read & Rename

```
[read_excel_auto]
  Input:  data/*.xlsx  sheet=0
  Output: raw DataFrame (with ERP raw column names)
  Rows:   ?

  ↓

[rename_erp_columns]
  Input:  raw with ERP names
  Output: raw with standard column names (数量, 金额, 利润, 成本, 客户编号, 产品品种, 发货日期)
  Filter: NO row removal — only column renaming
  Rows:   ? → ? (unchanged)
  Print:  "原始行数: {len(raw)}"
```

### Node 1b: Negative Quantity Filter

```
[filter_negative_qty]
  Input:  raw (standard column names)
  Output: raw filtered (qty > 0)
  Filter: result[result[qty_col] > 0]
  Rows:   ? → ? - removed_neg
  Print:  "负销量过滤: 剔除 {removed} 条记录 ({pct}%)"
```

### Node 1c: Winsorization (no row removal)

```
[winsorize_margins]
  Input:  filtered raw
  Output: raw + columns [_毛利率, _利润_裁剪]
  Filter: NO row removal — clips extreme margin ratios to [-50%, +75%]
  Rows:   unchanged
```

### Node 1d: Customer Info Merge

```
[merge with 客户信息表]
  Input:  cleaned raw + read_excel_auto(sheet="客户信息表")
  Output: raw with joined columns (渠道类型, 客户等级, 所属区域)
  Filter: LEFT JOIN — customer rows without info get "未知"
  Rows:   unchanged (left join preserves all rows)
  Print:  "已合并客户信息 ({len(cust_info)} 条)" [product_lifecycle path]
```

### Node 1e: Monthly Aggregation (KEY TRANSFORMATION — massive compression)

```
[monthly_aggregate_double_pass]
  Input:  cleaned row-level DataFrame
  Output: dict of 3 aggregate tables

  Transformations:
    df["_月"] = df[date_col].dt.to_period("M")   ← extract year-month period

    ┌─ customer_monthly: groupby([_月, 客户编号])
    │     agg: qty_sum, rev_sum, cost_sum, profit_raw_sum, profit_clip_sum, order_count
    │     Then: 毛利率% = profit_clip_sum / rev_sum * 100
    │
    ├─ product_monthly: groupby([_月, 产品品种])
    │     agg: qty_sum, rev_sum, cost_sum, profit_raw_sum, profit_clip_sum, avg_price
    │     Then: 毛利率% = profit_clip_sum / rev_sum * 100
    │
    └─ customer_x_product: groupby([_月, 客户编号, 产品品种])
          agg: qty_sum, rev_sum, profit_clip_sum
          Then: 毛利率% = profit_clip_sum / rev_sum * 100

  Rows compression:
    Raw N rows  →  customer_monthly:  M_cust rows  (M_cust ≈ #customers × #active_months)
    Raw N rows  →  product_monthly:   M_prod rows  (M_prod ≈ #products × #active_months)
    Raw N rows  →  customer_x_product: M_cxp rows  (M_cxp ≈ #cxp_combos × #active_months)
    (M_cust + M_prod + M_cxp << N)

  Print:  "输出: silver_{key}.csv ({len(df)} 行)" [×3 tables]
          "清洗行级数据: {len(raw)} 行"
```

### Silver Output Files

```
output/silver/
├── silver_customer_monthly.csv       ← customer aggregation
├── silver_product_monthly.csv        ← product aggregation
├── silver_customer_x_product.csv     ← bridge aggregation
└── silver_cleaned_rows.csv           ← row-level cleaned data (for product lifecycle reuse)
```

### Additional Silver-Node: Product Category Line Propagation

```
[product category merge into customer_x_product]
  Input: raw columns [产品品种, 产品一级分类].drop_duplicates()
  Output: silver["customer_x_product"] + 产品一级分类 column
  Filter: LEFT JOIN (preserves all cxp rows)
  Rows:   unchanged
```

---

## STAGE 2: Product Lifecycle Analysis

### Node 2a: Data Loading (two modes)

```
── Mode A: From Silver CSV (skip_silver=True) ──

[read silver_cleaned_rows.csv]
  Input:  output/silver/silver_cleaned_rows.csv
  Output: cleaned_df (pre-cleaned row-level data)
  Filter: NO additional filtering (already cleaned)
  Rows:   = same as stage_silver output

── Mode B: From Source Excel (skip_silver=False) ──

  Same as Stage 1a-1c: read_excel_auto → rename_erp_columns
```

### Node 2b: Data Preparation (`_prepare_data`)

```
[_prepare_data]  [in product_lifecycle/run.py:191-279]
  Input:  cleaned_df (from Mode A or Mode B)
  Output: df ready for profiling

  Sub-nodes:

  [Type conversion]
    df[name_col] = df[name_col].astype(str).str.strip()
    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
    df[qty_col] = pd.to_numeric(...).fillna(0)
    Filter: NO row removal

  [Negative qty filter]
    df = df[df[qty_col] > 0]
    Rows: ? → ? - neg_before
    Print: "已剔除 {neg_qty_before} 行负销量/零销量"

  [Date filter]
    df = df[df[date_col] >= pd.Timestamp(start_date)]
    df = df.dropna(subset=[date_col])
    Rows: ? → ? (removes rows before start_date + null dates)
    Print: "过滤后行数（起始日期>={start_date}）: {len(df)}"

  [Incomplete month check]
    if latest_max_day < incomplete_month_threshold_day:
        df = df[df['_月'] < latest_month]
        Print: "已自动剔除 {latest_month} 的数据"

  [Winsorization]
    df['_毛利率'] = clip(...)
    df['_利润_裁剪'] = ...
    Filter: NO row removal

  Rows:  Source N → after filtering N'

  Print: "行数: {len(df)}, 列数: {len(df.columns)}"
         "数据范围: {min} ~ {max}"
         "最新月份: {latest_month}"
```

### Node 2c: Product Profiling (`run_profiling`)

```
[run_profiling]  [in product_lifecycle/profiling.py]
  Input:  cleaned + filtered df
  Output: (result_df, data_insufficient, out, ratio_cols, pp_cols, timing)

  Key filtering inside:
    - Products with < min_record_months of data → moved to data_insufficient list
    - Only products with enough data go into result_df/out

  Rows:  N' rows (time-series) → len(out) products (1 row per product)
         + len(data_insufficient) products excluded

  Print:  "产品总数: {len(products)}"
          "[计时] 逐个产品指标计算: ... ({len(valid_prods)}个有效产品)"

  Output 'out' has columns:
    当前画像, 综合风险等级, 综合评分, 近12月毛利率%, 近12月增长率%,
    近12月销量, ASP趋势, 毛利率趋势斜率%/月, 策略建议, 产品名称, ...
```

### Node 2d: RFM + Association Analysis

```
[RFM Customer Segmentation]
  Input:  cleaned df (row-level)
  Output: rfm_result (DataFrame or None)
  Filter: handled inside function
  Print:  "RFM分群完成: {len(rfm_result)} 个客户"

[Product Association Analysis]
  Input:  cleaned df
  Output: assoc_result (DataFrame or None)
  Filter: handled inside function
  Print:  "关联分析完成: {len(assoc_result)} 条规则"
```

### Node 2e: Customer Analysis Bridge (called from product lifecycle)

```
[calc_customer_portrait + generate_customer_gold]
  Input:  silver dict built from product's df
  Output: customer_gold tables (same as Stage 3)
  (Reuses customer_analysis modules)
```

### Node 2f: Historical Portrait Tracking

```
[Historical Portrait — multi-process]
  Input:  df, latest_month, hist_intervals (e.g., [1,2,...,12])
  Output: hist_sheet_df (result_df + _t-1, _t-2, ... _t-12 columns)

  Per time point:
    Filter df to months ≤ tp
    Run run_profiling(mode='portrait_only')
    Merge results onto main result_df

  Print:  "[历史画像] t-{offset}月: {len(hist_result)}个产品"
```

### Node 2g: Excel Report Output

```
[_write_excel_output]
  Input:  out (product data), result_df, data_insufficient, rfm, assoc, hist
  Output: output/report/产品生命周期报告_v4.0_{timestamp}.xlsx

  Sheets:
    1. 产品快照表       — all products (out DataFrame)
    2. 预警清单         — filtered: 综合风险等级=="高" OR 当前画像 contains "预警|衰退"
    3. 画像分布         — value_counts of 当前画像
    4. 数据不足产品清单 — data_insufficient products
    5. 客户RFM分群      — rfm_result
    6. 产品关联分析     — assoc_result
    7. 趋势预测汇总     — forecast columns
    8. 历史画像追踪     — hist_sheet_df
    9. 使用说明         — static text

  Filter within sheets:
    预警清单: out[out["综合风险等级"].str.contains("高") | out["当前画像"].str.contains("预警|衰退")]
    Rows: total → warned_count

  Summary Print:
    "产品总数: {total + insuf_count}"
    "数据不足(<3月): {insuf_count}"
    "进入快照表: {total}"
    "新品观察: {new_count}"
    "清仓/偶发: {zombie_count}"
    "参与分析: {active_count}"
    "预警/衰退: {warned}"
    "高风险(>{threshold}分): {high_risk}"
```

### Product Lifecycle Gold Output

```
output/gold/
└── gold_product_portrait.csv          ← "out" DataFrame (1 row per product)
```

---

## STAGE 3: Customer Analysis

### Node 3a: Silver Loading (two modes)

```
── Mode A: From CSV (skip_silver=True) ──

  Input files:
    output/silver/silver_customer_monthly.csv
    output/silver/silver_customer_x_product.csv
    output/silver/silver_product_monthly.csv
  Output: silver dict (3 DataFrames)
  Print:  "Silver层从CSV加载 ({len(silver['customer_monthly'])} 客户月记录)"

  Additional: Load raw channel columns from source Excel for _derive_channel
  Print:  "渠道推导数据从源文件加载 ({len(raw_data)} 行)"

── Mode B: Build from Source (skip_silver=False) ──

  Same as Stage 1 but with ADDITIONAL date window filter:

  [Window filter — customer_analysis specific]
    raw = raw[raw[date_col] >= CUSTOMER_ANALYSIS_WINDOW.start_date]
    Print:  "窗口过滤({start_date}): {before} → {len(raw)} 行"

  Then: filter_negative_qty → winsorize_margins → merge customer info → monthly_aggregate_double_pass
```

### Node 3b: Customer Portrait Calculation

```
[calc_customer_portrait]  [in customer_analysis/portrait.py]
  Input:  silver dict, source_path, latest_month, raw_data, cust_info_df
  Output: customer_df (1 row per customer, 60+ columns)

  Algorithm:
    1. Unique customers from cust_monthly["客户编号"]
    2. For each customer, compute 10 dimensions:
       - 基本信息 (channel, tier, region)
       - 经营势能 (revenue, margin, growth rate, streaks)
       - 产品覆盖 (top3 concentration, variety count)
       - 产品线分布 (categories, HHI)
       - 采购健康度 (intervals, churn warning)
       - 价格治理 (price bands)
       - 品类接受度 (dominant category)
       - SKU生命周期 (dominant SKU stage)
       - 新品渗透 (new product adoption)
       - ASP/毛利率对比

  Rows transformation:  M_cust (customer-months) → #customers (1 row per customer)
  
  Filtering within (NO global row removal, but per-customer window filters):
    - recent = c_data[c_data["_月"] > (latest_month - value_window)]
    - prior = c_data[... window filter ...]
    - recent_months = recent[recent["rev_sum"] > 0]
  
  Print:  "[时间] 客户全景画像: ... ({len(customer_df)}个客户)"
```

### Node 3c: Customer Master Enrichment (optional)

```
[enrich_customer_portrait]  [in customer_analysis/customer_master.py]
  Input:  customer_df + load_customer_master("data/所有的终端客户.xlsx")
  Output: customer_df with "终端{字段}" columns merged

  Match strategy:
    1. Exact match on 公司工商全称
    2. Exact match on 公司简称
    3. Fuzzy match (rapidfuzz, threshold 85)

  Filter: LEFT JOIN — preserves all customer rows
  Rows:   unchanged

  Print:  "终端客户主数据整合: 新增 {n_cols} 列"
          "匹配结果: {n_matched}/{n_total} ({pct}%)"
          "渠道类型(CRM): {n} 客户来自CRM映射"
          "渠道类型(交易): {n} 客户来自交易数据推导"
```

### Node 3d: Gold Table Generation

```
[generate_gold_tables]  [in customer_analysis/gold.py]
  Input:  customer_df, silver dict, product_portrait_path
  Output: gold dict (8+ DataFrames)

  Sub-nodes (chained merges onto customer_df):

  [RFM-π Scoring]
    score_rfm_pi(df, channel_col, weights)
    Add: RFMπ_得分, RFMπ_层级

  [Old Action Suggestions]
    generate_action_suggestions(df)
    Add: 行动建议数, 行动建议

  [B2B v2: Customer Journey Stage]
    classify_customer_journey_stage(cust_monthly, thresholds)
    Merge onto df on 客户编号 (LEFT JOIN)
    Print: (handled inside)

  [B2B v2: Purchase Volatility]
    batch_calc_volatility(cust_monthly, VOLATILITY_METRICS)
    Merge onto df on 客户编号 (LEFT JOIN)

  [B2B v2: True Profit Estimation]
    batch_estimate_true_profit(df, ESTIMATED_COST)
    Merge onto df on 客户编号 (LEFT JOIN)

  [Customer Tier + Composite Scoring]
    calc_customer_tier(df)
    calc_composite_scores(df)

  [Inventory Aging + Anomaly Detection]
    get_inventory_aging(silver, product_portrait)
    calc_customer_inventory_risk(customer_x_product, inv_aging)
    Merge inv_risk onto df on 客户编号 (LEFT JOIN)
    run_anomaly_detection(df, silver, inv_aging)
      → gold["异常日志"]

  [V2 Action Suggestions]
    run_action_suggestions(df, anomaly_log, silver)
      → Override old action columns
      → gold["交叉销售建议"] (if any)

  [Customer-Product Bridge]
    _build_customer_product_bridge(silver, product_portrait_path)
      → gold["客户产品桥接"]
      = customer_x_product + product lifecycle portrait columns (LEFT JOIN)

  [Portfolio Health]
    _build_portfolio_health(customer_x_product + portrait)
      → gold["客户组合健康度"]
      = groupby 客户编号: 总品种数, 总金额 + portrait breakdown

  [Group Aggregation]
    run_group_aggregation(df, cust_x_prod, cat_col)
      → df + _集团名称 field
      → gold["集团聚合"]

  [Derived Tables — independent from customer_df]
    gold["价格离散度"]   = calc_cross_customer_price_dispersion(cxp)
    gold["SKU生命周期"]  = calc_sku_lifecycle_stage(prod_monthly)
    gold["品类接受度"]   = calc_category_acceptance(cxp) [if cat_col exists]
    gold["提价机会"]     = calc_markup_opportunity(cxp)
    gold["降价策略试算"] = calc_markdown_recommendation(cxp)
    gold["跨客户价格差异"] = calc_cross_customer_price_variation(cxp, df)
    gold["渠道价格对比"]  = calc_channel_price_comparison(cxp, df)
    gold["业务员定价偏离"] = calc_sales_owner_price_deviation(cxp, df)
    gold["市场细分价格"]  = calc_segment_price_analysis(cxp, df)
    gold["客户月度趋势"]  = calc_monthly_revenue_trend(cust_monthly, latest_month)
    gold["品类迁移"]      = calc_category_migration(cxp)
    gold["客户预测"]      = calc_customer_forecast(cust_monthly, latest_month)

  Print:  "[时间] Gold表生成: ..."
```

### Customer Gold Output Files

```
output/gold/
├── 客户全景.csv                    ← customer_df (1 row per customer, 60+ columns)
├── 客户产品桥接.csv               ← customer_x_product + portrait
├── 集团聚合.csv                    ← group aggregation
├── 客户组合健康度.csv             ← portfolio health
├── 价格离散度.csv                  ← price dispersion
├── SKU生命周期.csv                ← SKU lifecycle stages
├── 品类接受度.csv                 ← category acceptance (conditional)
├── 提价机会.csv                    ← markup opportunity
├── 降价策略试算.csv               ← markdown recommendation
├── 跨客户价格差异.csv             ← cross-customer price variation
├── 渠道价格对比.csv               ← channel price comparison
├── 业务员定价偏离.csv             ← sales owner price deviation
├── 市场细分价格.csv               ← segment price analysis
├── 异常日志.csv                    ← anomaly detection log
├── 交叉销售建议.csv               ← cross-sell suggestions (conditional)
├── 客户月度趋势.csv               ← monthly revenue trend
├── 品类迁移.csv                    ← category migration
└── 客户预测.csv                    ← customer ETS forecast

output/report/
└── 客户分析报告_v1.1_{timestamp}.xlsx  ← formatted Excel report
```

---

## STAGE 4: KPI Daily (Independent Pipeline)

```
[build_kpi]  [in customer_analysis/run_kpi_daily.py]
  Input:  source Excel (SAME raw file, INDEPENDENT read)
          OR pre-loaded raw_df

  Flow:
    read_excel_auto → rename_erp_columns → filter_negative_qty → groupby DATE

  [Negative qty filter]
    filter_negative_qty(raw, qty_col="数量")
    Rows: ? → ? (same as main pipeline)

  [Daily aggregation]
    groupby date: 销售额(sum), 数量(sum), 订单数(nunique), 客户数(nunique), 品种数(nunique)
    Rows: N (row-level) → #unique_dates

  Additional:
    - 本月累计销售额 (cumulative within latest month)
    - Top5客户 (当日, 金额排序)
    - Top5产品 (当日, 金额排序)

  Output: output/gold/gold_kpi_daily.csv
  Print:  "[KPI] 已输出: ... ({len(daily)} 行)"
          "[KPI] 数据范围: {min} ~ {max}"
```

---

## STAGE 5: Cross Reference

```
[run_cross_ref]  [in cross_reference/run_cross_ref.py]
  Input files (from Gold layer):
    output/gold/gold_product_portrait.csv    ← product lifecycle output
    output/gold/客户全景.csv                   ← customer analysis output
    output/gold/客户产品桥接.csv              ← customer analysis output

  [load_gold_tables]
    Print:  "加载: gold_product_portrait.csv ({len} 行)"
            "加载: gold_customer_profile.csv ({len} 行)"
            "加载: gold_customer_x_product.csv ({len} 行)"

  Calc 1: Customer Portfolio Health
    Input: 客户产品桥接.csv + gold_product_portrait.csv
    Merge: LEFT JOIN on product name
    Groupby: 客户编号 × 当前画像 → pivot → 风险品金额占比
    Output: output/gold/cross_customer_portfolio_health.csv

  Calc 2: Product Customer Health
    Input: 客户产品桥接.csv + 客户全景.csv
    Merge: on 客户编号
    Groupby: 产品品种 → 客户总数, 总金额, 高风险客户数
    Output: output/gold/cross_product_customer_health.csv
```

---

## COMPLETE FILE INVENTORY

### Silver Layer (output/silver/)
| File | Source | Description |
|------|--------|-------------|
| `silver_customer_monthly.csv` | Stage 1e | Customer × month aggregates |
| `silver_product_monthly.csv` | Stage 1e | Product × month aggregates |
| `silver_customer_x_product.csv` | Stage 1e | Customer × product × month bridge |
| `silver_cleaned_rows.csv` | Stage 1b-1c | Row-level cleaned data (for product lifecycle reuse) |

### Gold Layer (output/gold/)
| File | Source | Description |
|------|--------|-------------|
| `gold_product_portrait.csv` | Stage 2g | 1 row per product, lifecycle portrait |
| `gold_kpi_daily.csv` | Stage 4 | Daily KPI (independent pipeline) |
| `客户全景.csv` | Stage 3d | 1 row per customer, 60+ columns |
| `客户产品桥接.csv` | Stage 3d | Customer × product + portrait bridge |
| `集团聚合.csv` | Stage 3d | Group-level aggregation |
| `客户组合健康度.csv` | Stage 3d | Portfolio health by customer |
| `价格离散度.csv` | Stage 3d | Price dispersion across customers |
| `SKU生命周期.csv` | Stage 3d | SKU lifecycle stages |
| `品类接受度.csv` | Stage 3d (cond.) | Category acceptance |
| `提价机会.csv` | Stage 3d | Markup opportunity analysis |
| `降价策略试算.csv` | Stage 3d | Markdown recommendation |
| `跨客户价格差异.csv` | Stage 3d (cond.) | Cross-customer price variation |
| `渠道价格对比.csv` | Stage 3d (cond.) | Channel price comparison |
| `业务员定价偏离.csv` | Stage 3d (cond.) | Sales owner price deviation |
| `市场细分价格.csv` | Stage 3d (cond.) | Segment price analysis |
| `异常日志.csv` | Stage 3d | Anomaly detection results |
| `交叉销售建议.csv` | Stage 3d (cond.) | Cross-sell suggestions |
| `客户月度趋势.csv` | Stage 3d (cond.) | Monthly revenue trends |
| `品类迁移.csv` | Stage 3d (cond.) | Category migration |
| `客户预测.csv` | Stage 3d (cond.) | Customer ETS forecast |
| `cross_customer_portfolio_health.csv` | Stage 5 | Cross-ref: portfolio health |
| `cross_product_customer_health.csv` | Stage 5 | Cross-ref: product customer health |

### Reports (output/report/)
| File | Source | Description |
|------|--------|-------------|
| `产品生命周期报告_v3.0_{ts}.xlsx` | Stage 2g | 8+ sheets |
| `客户分析报告_v1.1_{ts}.xlsx` | Stage 3d | Formatted with warnings |

---

## FILTERING SUMMARY — All Row Reduction Points

| # | Location | Filter Logic | What's Removed |
|---|----------|-------------|----------------|
| 1 | `filter_negative_qty` | `df[df[qty_col] > 0]` | Rows with qty ≤ 0 (returns/credits) |
| 2 | `_prepare_data` [product] | `df[df[date_col] >= start_date]` | Rows before configurable start date |
| 3 | `_prepare_data` [product] | `dropna(subset=[date_col])` | Rows with unparseable dates |
| 4 | `_prepare_data` [product] | `df[df['_月'] < latest_month]` | Incomplete latest month (conditional) |
| 5 | `silver.py` [customer] | `df[df[date_col] >= start_date]` | Rows before CUSTOMER_ANALYSIS_WINDOW start |
| 6 | `run_pipeline.py` [customer] | `dropna(subset=[date_col])` | Unparseable dates (non-skip_silver path) |
| 7 | `monthly_aggregate_double_pass` | GroupBy aggregation | Row-level → monthly (massive compression) |
| 8 | `run_profiling` | `min_record_months` check | Products with < N months data → data_insufficient |
| 9 | `run_profiling` | Portrait type filters | Only valid/mature products into scoring |
| 10 | Excel 预警清单 sheet | `综合风险等级=="高"` or 画像==预警/衰退 | Subset of out DataFrame for warning sheet |
| 11 | Excel 趋势预测汇总 | `forecast_out[forecast_out["近12月销量"].notna()]` | Products without recent sales |
| 12 | `calc_customer_portrait` | Window filters per customer | Only recent N months considered per customer |
| 13 | Customer master matching | Join logic (exact/fuzzy) | Unmatched customers get defaults (no removal) |
| 14 | `build_kpi` | `filter_negative_qty` + daily groupby | Same as #1, then row→daily compression |
