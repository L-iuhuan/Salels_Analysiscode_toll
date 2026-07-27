# P2-B: Dependency Injection Pipeline Class

## Goal

Replace `run_all.py`'s function-based orchestration with a DI container using Protocol interfaces, enabling mocking in tests and isolating stage dependencies.

## Architecture

### `core/interfaces.py` — 9 Protocol Interfaces

| Protocol | Method | Wraps |
|----------|--------|-------|
| `IDataLoader` | `load(path, **kwargs)`, `find_source(data_dir)` | `read_excel_auto`, `find_source_data` |
| `IDataCleaner` | `clean(df)`, `validate(df)` | `rename_erp_columns`, `filter_negative_qty`, `winsorize_margins` |
| `IDataAggregator` | `aggregate(df)` | `monthly_aggregate_double_pass` |
| `ISilverBuilder` | `build(source_path)` | `stage_silver()` |
| `IAnalyzer` | `analyze(data, config)` | `run_analysis()`, `run_pipeline()` |
| `IScorer` | `score(portrait)` | scoring modules |
| `IGoldGenerator` | `generate(portrait, silver, **deps)` | `generate_gold_tables()` |
| `IReporter` | `generate(gold)` | `save_gold_tables()`, `write_excel_report()` |
| `IValidator` | `validate(df, stage)` | `SimpleValidator` |

### `core/config.py` — AppConfig

Nested dataclass config:

```
AppConfig
├── paths: PathConfig
├── clean: CleanConfig
├── pricing: PricingConfig
├── customer_window: CustomerAnalysisWindow
├── product: ProductLifecycleConfig
├── skip_silver_if_exists: bool
├── report_retention_count: int
└── run_stages: list[str]
```

Loads defaults from `config/settings.py` via `from_defaults()`. Supports `from_dict()` for future YAML/JSON config.

### `core/pipeline.py` — Pipeline DI Container

- `@dataclass` with 10 injectable dependencies
- `__post_init__` auto-wires defaults (lazy imports)
- `run(stages, source_path)` orchestrates pipeline

### `data_pipeline/loader.py`, `cleaner.py`, `aggregator.py`

Lightweight wrappers around existing `shared/data_cleaning.py` functions.

### Integration

`run_all.py` main loop becomes:
```python
pipeline = Pipeline(config=AppConfig.from_defaults())
pipeline.run(stages=stages, source_path=source_path)
```

Existing stage functions are preserved as concrete implementations.
Backward compatible — all existing entry points unchanged.

### Test Strategy

`test/test_pipeline.py` — 8-10 tests:
- Pipeline with default auto-wiring runs
- Mock data_loader can inject test data
- Mock validator captures calls
- Stage filtering works
- Config from_defaults() populates correctly
- Empty stages list handled
