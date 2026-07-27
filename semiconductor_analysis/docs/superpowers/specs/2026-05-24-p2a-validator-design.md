# P2-A: Data Validation Layer (SimpleValidator)

## Goal

Insert a lightweight data validation layer at 4 pipeline nodes to catch data quality issues early, without introducing new dependencies.

## Design

### SimpleValidator Class

Location: `data_pipeline/validator.py`

Pure pandas static methods, no external dependencies:

| Method | Purpose |
|--------|---------|
| `check_required_columns(df, required)` | Returns missing column names |
| `check_null_constraint(df, cols, max_null_pct)` | Columns exceeding null threshold |
| `check_value_range(df, col, lo, hi)` | Values outside [lo, hi] |
| `check_category_values(df, col, allowed)` | Unexpected category values |
| `validate(df, stage)` | Dispatches to stage-specific checks |

### 4 Validation Stages

| Stage | Where | Checks |
|-------|-------|--------|
| V1: raw | `run_all.py:stage_silver` after `read_excel_auto` | Required cols exist, null rates on key cols, revenue >= 0 |
| V2: clean | `run_all.py:stage_silver` after `winsorize_margins` | Margin in [-0.50, 0.75], qty > 0, dates parsed |
| V3: silver | `run_all.py:stage_silver` after `monthly_aggregate_double_pass` | Silver tables have `_月`, `rev_sum` >= 0, `qty_sum` >= 0 |
| V4: gold | Called from both product/customer gold output | Score ranges [0,100], category labels valid |

### Error Handling

Warn + continue: validation failures print warnings but don't stop the pipeline.

### Tests

`test/test_validator.py` — 8-10 unit tests covering valid/invalid data, edge cases.

### Files Changed

- `data_pipeline/__init__.py` — new
- `data_pipeline/validator.py` — new
- `test/test_validator.py` — new
- `run_all.py` — integrate V1/V2/V3 in `stage_silver`
