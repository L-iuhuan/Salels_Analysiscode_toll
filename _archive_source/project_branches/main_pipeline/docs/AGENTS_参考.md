# AGENTS.md

Agent guidance for this repo. See also `CLAUDE.md` for project overview, pipeline architecture, and quick-start commands. This file covers what CLAUDE.md doesn't: operational gotchas, conventions an agent would guess wrong, and dependency/environment quirks.

## Dependencies

All dependencies are listed in `requirements.txt` at the project root. Manual install: `pip install -r requirements.txt`
- `pandas`, `numpy`, `openpyxl` (Excel read/write)
- `statsmodels` (ETS forecasting)
- `chinese_calendar` (holiday adjustment)
- `rapidfuzz` (fuzzy company-name matching)
- `matplotlib` (test charts; optional for main pipeline)
- `scikit-learn` (IsolationForest anomaly detection; optional for main pipeline)
- `python-calamine` (Rust Excel engine; optional, 5-10x speedup)

## Path injection convention

Every module that runs standalone uses `sys.path.insert(0, PROJECT_ROOT)` at the top. This means:
- Always run scripts from the **project root**: `python run_all.py`, `python test/run_all_tests.py`
- Running from a subdirectory works because the script injects its own parent
- If you write new scripts, add the same pattern (see any existing file)

**Pytest exception:** The root `conftest.py` handles path injection automatically. You can run `pytest test/ -v` from the project root without manual injection.

## CSV encoding: UTF-8 with BOM

All CSV output uses `encoding="utf-8-sig"` — UTF-8 with byte-order mark. This is essential for Excel to correctly display Chinese characters. Always use this encoding for CSV output.

## Silver-layer caching: invisible skip

`SKIP_SILVER_IF_EXISTS=True` in `config/settings.py` means the pipeline silently skips all data cleaning and aggregation if the 3 Silver CSV files exist in `output/silver/`. This is fast but dangerous during development:
- Changing cleaning logic or `ERP_COL_MAP` won't take effect until you use `--force-silver`
- The test framework has its own pickle cache (`output/test_diag/_intermediate.pkl`) with the same hazard; use `--force` to regenerate

## Test framework: dual system

### 1. Custom 3-phase orchestrator (`test/run_all_tests.py`)
1. **Phase 1** (load): Reads Excel → cleans → aggregates → saves pickle cache
2. **Phase 2** (validate): Reads pickle → runs test cases A-H → outputs CSV/JSON/MD
3. **Phase 3** (visualize): Reads pickle → generates 5 diagnostic PNG charts

Phases are sequential with pickle as handoff. Phase 2 or 3 fails without Phase 1 unless `--skip-load` is used.

### 2. Standard pytest suite (118 tests across 6+ modules)
Run from project root: `pytest test/ -v`
- `test/test_week1_modules.py` — 28 unit tests for B2B v2 modules
- `test/test_validator.py` — 28 tests for data_pipeline validation layer
- `test/test_pipeline.py`, `test/test_gold_builders.py`, `test/test_gold_exporter.py`, `test/test_analysis_scoring.py`
- `test/validation_suite.py` — 20+ boundary/schema checks
- `test/batch_a_test.py` and `test/fallback.py` are excluded from pytest collection via root `conftest.py`

## Config: single source of truth, three files

All thresholds, weights, column mappings, and scoring tiers live in `config/`. **No hardcoded magic numbers in analysis code.**
- `config/settings.py` — shared config (ERP_COL_MAP, silver settings, report retention)
- `config/settings_product.py` — product lifecycle config (9-grid thresholds, risk weights, strategy text)
- `config/settings_customer.py` — customer analysis config (~760 lines: channel weights, window settings, composite scores, tier mappings)

`settings.py` re-exports both via `from config.settings_product import *` and `from config.settings_customer import *`, so `from config.settings import *` pulls in everything.

Config uses Chinese annotations with source tags: `【经验值】` (business experience), `【统计值】` (statistical tuning), `【行业参考】` (industry reference).

The legacy `config/config.xlsx` (v2.8 Excel format) no longer exists. `load_config_from_xlsx()` in `product_lifecycle/run.py` is dead code — never use this path.

## Channel type: raw column names matter

Channel type derivation (`_derive_channel` in `customer_analysis/portrait.py`) uses **raw ERP column names** (`"代理商/直供名称"`, `"实际终端客户"`), not the mapped standard names. The `stage_silver` function in `run_all.py` intentionally preserves these raw columns before the ERP column rename happens. Don't reorder these operations.

## Data file auto-detection

Both the pipeline and test framework auto-detect the first `.xlsx` found in `data/`. They pick differently:
- Pipeline: alphabetically first
- Test framework: alphabetically last (newest by name sort)
Use `--data` / `--file` to specify explicitly when multiple files exist.

## Report retention

`REPORT_RETENTION_COUNT = 10` in settings. The pipeline auto-deletes older Excel reports in `output/report/` during `run_all.py`.

## Directory migrations (completed)

The codebase has undergone structural refactoring. Be aware of the current layout:
- **`b2b_v2/`** — B2B v2 scoring modules (was `src/`). Contains `journey/` (7-stage classifier), `behavior/` (volatility), `profitability/` (true profit), `anomaly/` (IsolationForest + rules), `actions/` (cross-sell + rules engine)
- **`analysis/pricing/`** — Price analysis has been split from `shared/pricing.py` into 6 domain files (`pricing_trends.py`, `pricing_bands.py`, `pricing_customer.py`, `pricing_lifecycle.py`, `pricing_insights.py`, `pricing_actions.py`). **`shared/pricing.py` remains as a thin backward-compatible re-export layer** — existing imports still work. New code should import from `analysis/pricing/` directly.
- **`analysis/`** — Also contains `b2b_adapters.py`, `gold_builders.py`, `rfm_pi.py`, `scoring.py`
- **`data_pipeline/`** — New validation layer with `validator.py`, `aggregator.py`, `cleaner.py`, `loader.py`. Validator runs during pipeline as warn-and-continue (4 nodes: V1 schema, V2 business rules, V3 consistency, V4 aggregation correctness).

## Architecture: shared core

`shared/` modules (`calc_utils.py`, `classifiers.py`, `data_cleaning.py`, `forecasting.py`, `risk_scoring.py`, `timing.py`, `customer_analysis.py`) are used by **both** `product_lifecycle/` and `customer_analysis/`. Avoid duplicating logic — push shared behavior into `shared/`.

## B2B v2 integration

B2B v2 modules in `b2b_v2/` integrate into the main pipeline through `customer_analysis/gold.py:generate_gold_tables()`. Their outputs are merged into the customer Gold tables (LEFT JOIN on 客户编号). Configuration lives in `config/settings_customer.py` under `CUSTOMER_JOURNEY_THRESHOLDS`, `VOLATILITY_METRICS`, `ESTIMATED_COST`. Do not read individual module output CSVs — use the integrated Gold tables.
