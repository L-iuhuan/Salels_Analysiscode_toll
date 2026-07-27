# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

半导体销售数据分析系统 — a semiconductor sales data analysis system that processes ERP shipment data (Excel) through a multi-stage pipeline to produce customer portraits (60+ metrics/customer), product lifecycle analysis, pricing recommendations, anomaly detection, and formatted Excel reports. Python 3.10+, ~12,000 lines of production code.

## Commands

### Running the Pipeline

```powershell
# Full pipeline (silver → product → customer → kpi → cross_ref)
python run_all.py

# Specific stages only
python run_all.py --stage silver,customer

# Use new DI architecture (P2-B Pipeline container)
python run_all.py --pipeline

# Force rebuild Silver layer (ignore cache)
python run_all.py --force-silver

# Specify data file
python run_all.py --data "path/to/data.xlsx"

# Skip a stage
python run_all.py --skip-product

# Customer analysis only
python run_customer.py

# Product lifecycle analysis only
python run_product.py
```

### Running Tests

```powershell
# Full 3-phase test suite (load → validate → visualize)
python test/run_all_tests.py

# Single phase only
python test/run_all_tests.py --stage 2

# Specific test cases
python test/run_all_tests.py --tests A,B,C

# Use cached intermediate data (skip Phase 1 reload)
python test/run_all_tests.py --skip-load

# Force data reload
python test/run_all_tests.py --force
```

There is no `pytest` setup — the project uses a custom test framework (`test/run_all_tests.py`) with pickle-based intermediate caching. Test data is auto-detected from `data/*.xlsx`.

### Installing Dependencies

No `requirements.txt` exists yet. Both `run_all.py` and `test/run_all_tests.py` auto-install missing packages from the hardcoded `REQUIRED` list:
`pandas`, `numpy`, `openpyxl`, `statsmodels`, `chinese_calendar`, `rapidfuzz`, `matplotlib`, `sklearn` (scikit-learn).

`python-calamine` is optional but recommended (5-10x Excel read speedup). `xlsxwriter` is required for Excel report generation (imported by `reports/gold_exporter.py`).

## Architecture

### Data Flow

```
ERP Excel (.xlsx)
  → rename_erp_columns() → filter_negative_qty() → winsorize_margins()
  → monthly_aggregate_double_pass()
  → Silver layer (3 CSVs: customer_monthly, product_monthly, customer_x_product)
  → Product Lifecycle Analysis + Customer Analysis (parallel branches)
  → Gold layer (20 CSVs) → Formatted Excel Report
```

### Dual Architecture (Old + New)

The codebase is mid-refactor. Two architectures coexist:

1. **Procedural (`run_all.py`)** — the production entry point. Uses `shared/data_cleaning.py` directly, calls `product_lifecycle/run.py` and `customer_analysis/run_pipeline.py` as procedural scripts. This is stable and fully functional.

2. **DI / IoC (`core/pipeline.py`, `--pipeline` flag)** — new architecture (P2-B). Uses `Protocol` interfaces (`core/interfaces.py`) and a dependency injection container. Defaults auto-wire production implementations; all dependencies are replaceable for testing. The adapters in `analysis/b2b_adapters.py` bridge B2B v2 modules to the Protocol interfaces.

### Key Modules

| Directory | Purpose |
|-----------|---------|
| `config/` | All configuration. `settings.py` (~1074 lines) is the single source of truth; it imports from `settings_product.py` and `settings_customer.py`. |
| `core/` | New DI architecture: `interfaces.py` (Protocol definitions), `pipeline.py` (DI container), `config.py` (`AppConfig` dataclass). |
| `data_pipeline/` | New architecture's data layer: `loader.py` (ExcelDataLoader), `cleaner.py` (DefaultCleaner), `aggregator.py` (DefaultAggregator), `validator.py` (SimpleValidator with V1-V4 validation gates). |
| `shared/` | Core shared logic: `data_cleaning.py` (ERP column mapping, winsorization, dual-pass monthly aggregation), `calc_utils.py` (slope, growth rate, concentration, HHI), `classifiers.py` (slope/momentum/health classifiers shared by product and customer analysis). |
| `customer_analysis/` | Customer pipeline: `silver.py` → `portrait.py` (60+ metrics) → `gold.py` (orchestrates scoring + gold generation) → `report.py`. Also `scoring.py`, `dimensions.py`, `group_aggregation.py`, `trend_analysis.py`, `price_deep_dive.py`. |
| `product_lifecycle/` | Product lifecycle analysis with 9-grid classification (`nine_grid.py`). |
| `analysis/` | Shared analysis modules: `scoring.py` (5-dimension scorecard), `rfm_pi.py`, `pricing/` (trends, bands, actions, insights, lifecycle, customer pricing), `b2b_adapters.py` (Protocol adapters). |
| `b2b_v2/` | B2B v2 modules: `journey/` (7-stage classifier), `behavior/` (volatility), `profitability/` (true profit estimation), `anomaly/` (isolation forest + rule-based detection), `actions/` (cross-sell + rules engine). |
| `reports/` | `gold_exporter.py` — writes Gold CSVs + formatted Excel reports (xlsxwriter, blue headers, red warning rows). |
| `cross_reference/` | Cross-reference analysis between product and customer dimensions. |
| `test/` | Custom test framework. `conftest.py` provides shared paths, pickle caching, logging, and result structures. `phase1_load.py`, `phase2_validate.py`, `phase3_visualize.py` are the 3 phases. |
| `recession_risk_opt/` | Independent module for recession risk modeling and backtesting. |
| `data/` | Place ERP Excel files here. Auto-detected (first `.xlsx` found). |

### Configuration System

All tunable parameters live in `config/settings.py`. Key configuration blocks:
- `ERP_COL_MAP` — maps ERP Chinese column names to standard names (critical for new ERP exports)
- `CLEAN` — winsorization bounds, sample Z-threshold
- `RFM_PI_WEIGHTS` — per-channel R/F/M/π weights
- `SCORE_DIMENSION_WEIGHTS` — 5-dimension scorecard weights (价值贡献 35%, 增长动能 25%, 稳定关系 20%, 战略潜力 15%, 效率运营 5%)
- `PRODUCT_THRESHOLDS` — product lifecycle classification thresholds
- `INVENTORY_AGING` — inventory aging analysis config

The `AppConfig` dataclass (`core/config.py`) wraps these for the DI architecture but defaults to empty — `config/settings.py` values are still used directly in most modules.

### Important Patterns

- **Always run from project root**. All modules inject the project root into `sys.path`:
  ```python
  PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
  if PROJECT_ROOT not in sys.path:
      sys.path.insert(0, PROJECT_ROOT)
  ```
- **Silver layer caching**: Controlled by `SKIP_SILVER_IF_EXISTS`. A checksum of `config/settings.py` + `shared/data_cleaning.py` invalidates the cache when config changes.
- **Warnings are suppressed**: `FutureWarning` and numerical warnings (`divide by zero`, `invalid value`) are filtered at entry points because statsmodels generates known benign warnings.
- **Validation is non-blocking**: `SimpleValidator` prints warnings but never halts the pipeline.
- **Column names are Chinese**: All processed DataFrames use Chinese column names (客户编号, 产品品种, 金额, etc.). The `COL_MAP` dict provides English→Chinese mapping.

### Customer ID Mapping (2026-06-12 update)

- **Customer ID = "终端客户简称"** (end customer short name), mapped via `ERP_COL_MAP["终端客户简称"] = "客户编号"`.
- Previously used "代理商/直供名称" (agent names, 310 customers); now 3,850+ end customers.
- **Channel type**: derived from "销售模式" column (经销→代理, 直销→直供), configured in `CHANNEL_DERIVE`.
- **Customer tier**: from "终端客户名称_客户类别" column (KA>1亿/AA>5000万/KM>1000万/MM<1000万), mapped to KA/AA/KM/MM via `calc_customer_tier()`.
- **Customer grade**: derived from tier (KA/AA→A, KM→B, MM→C).
- **New product flag**: "是否新品" → "新品标记", authoritative from ERP.
- **Group aggregation**: disabled (`GROUP_AGGREGATION.enabled=False`).
- **Region & sales owner**: no data source → all "未知".
- The old `_derive_channel()` buyer/end-customer matching is replaced by direct "销售模式" column mapping.

### Known Issues

- Customer growth rates are not clamped (unlike product lifecycle which has `[-1.0, 5.0]` bounds) — extreme values like 3085% can appear.
- Revenue cliff detection threshold (`revenue_cliff_ratio=0.3`) is sensitive, producing many medium-severity anomalies.
- Month-to-days conversion uses `*30` hardcoded, causing slight bias for 28/31-day months.
- `config/settings.py` at ~1074 lines is large and should be split further.
- `所属区域` and `业务负责人` fields remain "未知" for all end customers — no data source available.
- `sheet_name=0` bug in `customer_analysis/run_pipeline.py` fixed — now uses `DATA_SHEET_NAME` from config.
