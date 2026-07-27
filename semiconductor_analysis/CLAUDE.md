# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Semiconductor industry sales data analysis system. Ingests ERP export data (Excel) and produces:
- **Product lifecycle analysis**: 9-grid portfolio classification, 5-factor risk scoring, ETS forecasting, product profiling with 40+ metrics
- **Customer analysis**: 60+ metrics per customer, RFM-π scoring, opportunity/risk scoring, pricing analysis, markup/markdown recommendations
- **B2B v2 scoring system**: Customer journey stage classification (7 stages), purchase volatility metrics, estimated true profit

## Data Pipeline Architecture

```
data/*.xlsx ──→ [Shared Cleaning] ──→ Silver Layer (CSV) ──→ Gold Layer (CSV) ──→ Excel Reports
                     │                     ├── customer_monthly
                     │                     ├── product_monthly
                     │                     └── customer_x_product
```

- **Raw data**: ERP export in `data/` directory (single sheet of transactions + optional "客户信息表" sheet)
- **Silver layer**: `output/silver/` — cleaned row-level data + 3 monthly aggregation tables
- **Gold layer**: `output/gold/` — 22+ analysis tables in CSV format (BI-tool friendly)
- **Reports**: `output/report/` — formatted multi-sheet Excel workbooks
- **Test diagnostics**: `output/test_diag/` — pickle cache, diagnostic CSVs, charts

## Key Files & Modules

| File | Purpose |
|------|---------|
| `run_all.py` | Unified entry — stages: silver → product → customer → kpi → cross_ref |
| `run_product.py` / `run_customer.py` | Standalone entry points |
| `config/settings.py` | All parameters centralized (146 lines, plus 765-line settings_customer.py), no need to modify main code |
| `shared/data_cleaning.py` | Shared cleaning: ERP column rename, negative qty filter, margin winsorization, double-pass monthly aggregation |
| `shared/pricing.py` | Pricing analysis: ASP trends, elasticity, price deviation/bands/dispersion, purchase intervals, churn, SKU/customer lifecycle, cohort, markup/markdown |
| `shared/calc_utils.py` | Slope calculation, growth rate with auto window shrink, HHI, percentile cut |
| `shared/classifiers.py` | Slope level, momentum, health classification |
| `shared/risk_scoring.py` | 5-factor risk model: slope, CV, decay, self-health, ASP |
| `shared/forecasting.py` | ETS forecasting (statsmodels) with chinese_calendar holiday adjustment |
| `shared/customer_analysis.py` | RFM segmentation, product association analysis |
| `product_lifecycle/profiling.py` | Core profiling engine — 40+ metrics per product |
| `product_lifecycle/nine_grid.py` | 9-grid portrait classification + contextual strategy generation |
| `product_lifecycle/notes.py` | Automated exception notes generation |
| `product_lifecycle/run.py` | Product lifecycle v2.8 decoupled rewrite orchestration |
| `customer_analysis/models.py` | RFM-π scoring (channel-isolated), opportunity/risk scoring |
| `customer_analysis/run_pipeline.py` | Customer pipeline orchestration (Silver→Gold→Report) |
| `src/journey/stage_classifier.py` | B2B v2 — 7-stage customer journey classifier |
| `src/behavior/volatility.py` | B2B v2 — Purchase volatility (CV, max drop, zero-month ratio, R²) |
| `src/profitability/true_profit_estimator.py` | B2B v2 — Estimated true profit after service costs |

## Quick Start

```bash
# Full pipeline
python run_all.py

# Selective stages
python run_all.py --stage silver,customer
python run_all.py --skip-product
python run_all.py --force-silver

# Standalone
python run_product.py
python run_customer.py

# With custom data
python run_all.py --data path/to/data.xlsx
```

## Running Tests

```bash
# 3-phase test suite (load → validate → visualize)
python test/run_all_tests.py

# Skip specific phases
python test/run_all_tests.py --skip-load
python test/run_all_tests.py --stage 2        # validate only
python test/run_all_tests.py --stage 3        # visualize only

# Run specific test cases (A-H)
python test/run_all_tests.py --tests A,B,C

# Force reload data (ignore pickle cache)
python test/run_all_tests.py --force

# Unit tests for B2B v2 modules
python -m pytest test/test_week1_modules.py -v
python test/test_week1_modules.py             # direct run (unittest)

# Validation suite (20+ boundary tests, schema checks)
python test/validation_suite.py

# All pytest unit tests (118 tests across 6 modules)
python -m pytest test/ -v
```

## Code Architecture Notes

- **Config-driven**: All thresholds, weights, column mappings live in `config/settings.py`. No hardcoded magic numbers in analysis code.
- **Shared core**: `shared/` modules are used by both product_lifecycle and customer_analysis — avoid duplicated logic.
- **Silver layer cache**: `SKIP_SILVER_IF_EXISTS=True` in settings skips re-cleaning if CSVs exist. Use `--force-silver` to regenerate.
- **Column mapping**: `ERP_COL_MAP` in settings maps ERP column names to standard names. Modify this if your ERP uses different column names.
- **Risk model**: 4-factor (v4.0): margin slope (10%), growth decay (60%), self-health (20%), order change (10%). Thresholds: low≤55, mid≤65, high≤68, >68=extreme. growth decay≥80 + margin slope≥70 override → auto-extreme.
- **ETS forecasting**: Uses statsmodels ETSModel with AIC-based model selection and chinese_calendar holiday adjustment.
- **B2B v2 modules** in `src/` integrate into the main pipeline via `customer_analysis/run_pipeline.py:generate_gold_tables()`.
