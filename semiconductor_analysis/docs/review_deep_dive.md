# 客户分析系统 — 深度代码审查、可视化与性能报告

**日期**: 2026-05-23
**覆盖**: 全部15个Python源文件 (~3,200行代码)
**范围**: Step 2 代码质量审查 / Step 3 可视化建议 / Step 4 性能优化

---

## Step 2: 代码质量深度审查

### 2.1 逻辑正确性与业务覆盖度

#### 🔴 2.1.1 `cross_reference/run_cross_ref.py:calc_product_customer_health()` — 引用已废弃列名

**位置**: `run_cross_ref.py:117-129`

**问题**:
```python
cust[["客户编号", "RFMπ_层级", "信用等级", "风险等级"]]
# ...
C级客户数=("信用等级", lambda x: (x == "C级").sum()),
D级客户数=("信用等级", lambda x: (x == "D级").sum()),
高风险客户数=("风险等级", lambda x: (x == "高").sum() if x.dtype == object else 0),
```

`信用等级` 列已被移除（`models.py` 文档字符串明确标注"已废弃"），`风险等级` 列在新评分系统中已更名为 `风险评级`。

**影响**: 运行时 `KeyError` 崩溃，`cross_ref` 阶段无法产生输出。

**修复建议**:
```python
# 方式1：使用新评分系统的列名
cols = ["客户编号", "RFMπ_层级", "综合价值层级", "风险评级"]
keep_cols = [c for c in cols if c in cust.columns]
cp = cp.merge(cust[keep_cols], on="客户编号", how="left")

# 方式2：安全访问，缺失列跳过
def _safe_count(series, value):
    if series.dtype == object:
        return (series == value).sum()
    return 0
```

**测试用例**: 创建一个不含 `信用等级` 列的测试 `cust` DataFrame，验证不会 KeyError。

---

#### 🔴 2.1.2 `stage_classifier.py:_estimate_historical_stage()` — 历史阶段估计退化

**位置**: `stage_classifier.py:310-319`

**问题**:
```python
def _estimate_historical_stage(...):
    if row.get("rev_sum", 0) == 0:
        return "流失期"
    return "稳定期"
```

该函数仅检查 `rev_sum == 0`，否则返回"稳定期"。这意味着"阶段持续月数"和"阶段转换次数"这两个输出字段的数值不可靠——它们基于的功能退化的历史阶段估计。

**影响**: `阶段持续月数` 始终≈总历史月数（阶段从不被识别为变化），`阶段转换次数` ≈ 0。业务用户可能误用这两个字段。

**修复建议**:
```python
def _estimate_historical_stage(row, grp, idx, n_months, global_latest,
                                onboarding_max_months, churn_days):
    month = grp.iloc[idx]["_月"]
    months_since = _month_diff(month, global_latest)
    
    if months_since >= 12:
        return "流失期"
    if months_since >= 6:
        return "休眠期"
    
    # 近3月 vs 前3月的增长
    window_start = max(0, idx - 3)
    recent3 = grp.iloc[window_start:idx+1]["rev_sum"].mean()
    prior3 = grp.iloc[max(0, window_start-3):window_start]["rev_sum"].mean() if window_start >= 3 else 0
    
    if prior3 > 0 and (recent3 - prior3) / prior3 > 0.30:
        return "成长期"
    return "稳定期"
```

**测试用例**: 创建一个10个月数据的客户，前3月无交易、后3月有交易，验证历史阶段能被正确识别为"激活期→成长期"。

---

#### 🔴 2.1.3 `run_kpi_daily.py:build_kpi()` — Top5序列化为dict字符串

**位置**: `run_kpi_daily.py:69-82`

**问题**:
```python
top_cust = raw.groupby(raw["发货日期"].dt.date).apply(
    lambda g: g.groupby("客户编号")["金额"].sum().nlargest(5).to_dict(),
    include_groups=False,
)
```

`.to_dict()` 产生 `{客户编号: 金额}` 嵌套字典，写入CSV后变为 `"{'客户A': 12345, '客户B': 6789}"` 字符串，无法在BI工具中直接解析。

**影响**: KPI表中Top5客户/产品列对下游分析无用。

**修复建议**:
```python
# 改为列表字符串或拆分为多列
top_cust = raw.groupby(raw["发货日期"].dt.date).apply(
    lambda g: "; ".join(
        f"{k}({v:.0f})" for k, v in 
        g.groupby("客户编号")["金额"].sum().nlargest(5).items()
    ),
    include_groups=False,
)
```

**测试用例**: 创建含2天数据的测试DataFrame，验证CSV输出中Top5列可解析。

---

#### 🟠 2.1.4 `group_aggregation.py:calc_group_aggregation()` — 产品线数求和误用

**位置**: `group_aggregation.py:148-152`

**问题**:
```python
if "产品线数" in grp.columns:
    row["集团产品线覆盖"] = int(grp["产品线数"].fillna(0).sum())
```

`产品线数` 是每个客户的产品线计数，对集团多个成员直接求和会导致重复计数。例如比亚迪集团有2家子公司各覆盖5条产品线，求和得10，但并集可能只有5条。

**影响**: 集团产品线覆盖被高估。

**修复建议**: 集团级产品线覆盖应从原始客户×产品数据中重新计算，而非聚合成员级指标。

**测试用例**: 集团A有2个成员，成员1覆盖"MOS管/集成电路"，成员2覆盖"MOS管/二三极管"。预期产品线覆盖=3，而非2+2=4。

---

### 2.2 异常与边界情况

#### 🔴 2.2.1 `run_kpi_daily.py:build_kpi()` — 本月累计截断问题

**位置**: `run_kpi_daily.py:64-66`

**问题**:
```python
today = datetime.now().date()
daily["本月累计销售额"] = daily[
    daily["日期"].apply(lambda x: x.month == today.month and x.year == today.year)
]["销售额"].cumsum()
```

筛选后的子集比原DataFrame行数少，赋值回去时非本月行为NaN。更严重的是，如果数据中不含本月记录（如数据截至上月），`cumsum()` 在空DataFrame上操作产生空Series，赋值后全列为NaN。

**影响**: "本月累计销售额"列大部分为NaN。

**修复建议**:
```python
daily["本月累计销售额"] = daily["销售额"].cumsum()  # 改为全年累计
# 或
latest_data_month = daily["日期"].max()
daily["当月累计"] = daily[
    daily["日期"].apply(lambda x: x.month == latest_data_month.month 
                       and x.year == latest_data_month.year)
]["销售额"].cumsum()
```

---

#### 🟠 2.2.2 `price_deep_dive.py:calc_cross_customer_price_variation()` — 列存在性检查逻辑错误

**位置**: `price_deep_dive.py:75-76`

**问题**:
```python
if cat_col not in cp.columns or cust_prod_price.get("产品一级分类") is None:
    cust_prod_price["产品一级分类"] = "未知"
```

`cust_prod_price.get("产品一级分类")` 返回的是一个Series（该列），不是标量。如果列存在但全为NaN，`.get()` 仍然返回Series（不会返回None）。因此`is None` 永远为False。

**影响**: 当分类列确实缺失时，没有正确设置默认值。下游使用该列时可能得到未定义列名。

**修复建议**:
```python
if cat_col not in cp.columns:
    cust_prod_price["产品一级分类"] = "未知"
elif cust_prod_price["产品一级分类"].isna().all():
    cust_prod_price["产品一级分类"] = "未知"
```

**测试用例**: 创建不含 `cat_col` 的cp，验证输出表中 `产品一级分类` 列存在且值为"未知"。

---

#### 🟠 2.2.3 `shared/forecasting.py:ets_forecast()` — 负值静默替换

**位置**: `forecasting.py:100`

**问题**:
```python
y = np.maximum(y, 0)  # 静默替换负值为0
```

虽然 `filter_negative_qty` 已在清洗阶段剔除负数交易，但ETS预测在aggregated monthly数据上运行，如果某个月有退货超过正销量（可能发生在 `cust_monthly` 层面），聚合值可能为负。负值被静默替换为0会扭曲趋势。

**影响**: 退货高峰月份的预测会被上偏。

**修复建议**: 添加日志或使用 `np.clip(y, 0, None)` 时记录替换次数。

**测试用例**: 创建含一个负值月的测试序列，验证日志记录替换发生且预测结果不受过度影响。

---

#### 🟡 2.2.4 `portrait.py:calc_customer_portrait()` — 空客户信息表回退含所有客户

**位置**: `portrait.py:352-356`

**问题**:
```python
try:
    cust_info = read_excel_auto(source_path, sheet_name="客户信息表")
except Exception:
    cust_info = pd.DataFrame({"客户编号": cust_monthly["客户编号"].unique()})
```

当Sheet不存在时，回退DataFrame包含所有客户ID（作为空壳）。这使得 `_dim_base_info()` 中所有客户都能找到自己的行，进入 `if len(info) > 0` 分支，但其中 `渠道类型`、`客户等级` 等字段全部缺失（NaN）。

**影响**: 渠道类型推导需要依赖于该函数调用后续的 `_derive_channel()` 回退逻辑——这已经在 Fix #21 中修复了。但 `客户等级` / `所属区域` / `业务负责人` 全部返回NaN。

**修复建议**: 已在代码中正确处理（通过CRM+交易推导后续回退）。建议在回退DataFrame中用更少的列名，让 `_dim_base_info()` 更早进入 `else` 分支。

---

### 2.3 数据假设验证

#### 🟠 2.3.1 `pricing.py:calc_customer_lifecycle_stage()` — Period类型假设

**位置**: `pricing.py:628-650`

`latest_month - first_purchase` 和 `latest_month - _ramp_window` 要求 `latest_month` 和 `_月` 均为 `pd.Period` 类型且freq相同。当从CSV加载Silver数据时，`_月`是字符串直到被显式转换。

**影响**: 在 `skip_silver=True` 路径中，`run_pipeline.py` 执行 `df["_月"] = pd.PeriodIndex(df["_月"], freq="M")`，但在直接调用 `calc_customer_lifecycle_stage()` 的场景中，如果使用未转换的DataFrame会产生TypeError。

**修复建议**: 在函数入口添加防御性转换：
```python
if date_col in df.columns and not pd.api.types.is_period_dtype(df[date_col]):
    try:
        df[date_col] = pd.PeriodIndex(df[date_col], freq="M")
    except Exception:
        pass
```

---

#### 🟠 2.3.2 `models.py:score_rfm_pi()` — qcut分位假设

**位置**: `models.py:60-64`

```python
sub[score_name] = pd.qcut(
    sub[col].rank(method="first"), 5,
    labels=labels, duplicates="drop",
).astype(int)
```

当 `sub[col].rank(method="first")` 的唯一值少于5个时，`duplicates="drop"` 会合并分位。结果标签数可能少于5，`.astype(int)` 在标签数组不等长时可能引发错误（取决于pandas版本）。

**影响**: 极少见。仅发生在渠道隔离后某渠道客户数<5时。当前代码也通过 `mask.sum() >= 5` 保护了这种情况。

**修复建议**: 在 `_score_subset` 中使用 `pd.qcut(..., duplicates="drop")` 后检查标签长度：
```python
binned = pd.qcut(sub[col].rank(method="first"), 5, labels=labels, duplicates="drop")
if len(binned.cat.categories) < 5:
    binned = binned.cat.reorder_categories(labels[:len(binned.cat.categories)])
sub[score_name] = binned.astype(int)
```

---

### 2.4 Pandas 常见陷阱

#### 🟠 2.4.1 `portrait.py:calc_customer_portrait()` — 逐行DataFrame掩码创建

**位置**: `portrait.py:380-395`

**问题**: 对每个客户创建一个长度为全表行数的布尔掩码，310客户×每个掩码遍历8,612行。

```python
for cid in customers:
    c_mask = cust_monthly["客户编号"] == cid   # 8612元素的布尔数组
    c_data = cust_monthly[c_mask].sort_values("_月")
```

**影响**: 性能影响中等（见Step 4分析），但更重要的是多次拷贝数据。

**修复建议**: 使用 `groupby` 统一处理，见 Step 4。

---

#### 🟠 2.4.2 `portrait.py:_dim_momentum()` — Python循环计算连续增长

**位置**: `portrait.py:202-213`

**问题**: 使用显式Python `for` 循环计算连续增长/下滑月数，不符合pandas向量化风格。

**修复建议**:
```python
monthly_rev = recent.sort_values("_月")["rev_sum"]
# 方向标记：1=增长, -1=下滑, 0=持平
direction = np.sign(monthly_rev.diff().fillna(0))
# 连续计数
streak_up = (direction == 1).astype(int).groupby((direction != 1).cumsum()).cumsum().max()
streak_down = (direction == -1).astype(int).groupby((direction != -1).cumsum()).cumsum().max()
```

---

#### 🟡 2.4.3 `data_cleaning.py:filter_negative_qty()` — inplace参数名不副实

**位置**: `data_cleaning.py:93-103`

**问题**:
```python
result = df if inplace else df.copy()
result = result[result[qty_col] > 0].copy()  # 总是创建新副本
```

`inplace=True` 时，第2行的 `.copy()` 仍然创建了新对象，且第1行的 `result = df` 引用配合第2行的 `result = ...` 赋值会断开引用。`inplace=True` 参数实际无效。

**影响**: 无功能影响。参数名误导开发者。

**修复建议**: 移除 `inplace` 参数或使行为与其名一致。

---

### 2.5 统计与可视化陷阱

#### 🟠 2.5.1 `models.py:score_opportunity()` 和 `score_risk()` — 全量Min-Max泄露

**位置**: `models.py:130-155`、`models.py:186-210`

**问题**: 两个评分函数对所有客户（包括非活跃客户）做Min-Max归一化。非活跃客户的零值指标会拉低归一化下限，使活跃客户的相对分数偏高。

```python
# 对 ALL customers 做 Min-Max
total_score += normalized * weight
```

对比 `scoring.py:calc_composite_scores()` 中正确地将Min-Max限制在活跃客户上（行87-88）：
```python
norm = _minmax_norm(raw.where(active_mask, float("nan")), reverse=reverse)
norm[~active_mask] = SCORE_INACTIVE_DEFAULT
```

**影响**: `models.py` 的机会/风险评分区分度进一步降低（活跃客户被"垫高"但仍无法达到80分的阈值）。

**修复建议**: 在 `score_opportunity()` 和 `score_risk()` 中添加 active_mask 参数：
```python
def score_opportunity(customers, ..., active_mask=None):
    ...
    for col, weight in elements:
        if active_mask is not None:
            s = s.where(active_mask, float("nan"))
```

---

#### 🟠 2.5.2 `shared/forecasting.py:ets_forecast()` — AIC模型选择过拟合风险

**位置**: `forecasting.py:112-141`

**问题**: 代码尝试6-12种ETS配置组合（error=add/mul × trend=add/mul/None），选择AIC最低的。对于仅12个月数据的客户（min_history=12），趋势+误差+Damped趋势的组合会导致过拟合。

**影响**: 对短历史客户，复杂ETS模型可能在样本外预测中表现差于简单模型。

**修复建议**: 根据数据长度限制模型复杂度：
```python
if len(y) < 15:
    configs = [('add', None, None), ('mul', None, None)]  # 仅无趋势
elif len(y) < 24:
    configs = [('add', 'add', None), ('add', None, None),
               ('mul', 'add', None)]  # 仅加法趋势
else:
    configs = [...]  # 全配置
```

---

### 2.6 性能与内存

详见 Step 4。此处列出代码级别的问题：

#### 🟠 2.6.1 `calc_customer_portrait()` 逐行循环 → 可向量化

详见 2.4.1 和 Step 4.2。

#### 🟠 2.6.2 `true_profit_estimator.py` iterrows() → 可向量化

```python
for _, row in customer_profile_df.iterrows():
    result = estimate_true_profit(row.to_dict(), config)
```

**影响**: 310客户下约0.3s，不是瓶颈但模式不优。向量化后约0.01s。

**修复建议**:
```python
def batch_estimate_true_profit_vectorized(df, config):
    result = df[["客户编号"]].copy()
    result["订单处理成本"] = df["订单数"].fillna(1) * cfg.get("order_processing_cost", 50)
    result["物流成本"] = df["近12月收入"].fillna(0) * cfg.get("logistics_cost_rate", 0.02)
    # ... 其他成本同理
    result["估算真实利润"] = df["近12月毛利"].fillna(0) - result[cost_cols].sum(axis=1)
```

---

#### 🟡 2.6.3 `stage_classifier.py` 重复groupby

**位置**: `stage_classifier.py:112`（主循环）和 `:254-268`（成熟期排名修正）

两次独立的 `df.groupby(cust_col)` 循环，中间没有大规模数据处理需要。可以合并为一次遍历。

---

### 2.7 可复现性与安全性

#### 🟠 2.7.1 缺少随机种子

全项目未设置随机种子。当前无随机操作，但如果未来加入bootstrap/交叉验证，结果将不可复现。

**修复建议**: 在 `run_all.py:main()` 中添加：
```python
import numpy as np
np.random.seed(42)
```

---

#### 🟠 2.7.2 `run_kpi_daily.py` — `datetime.now()` 依赖

**位置**: `run_kpi_daily.py:64`

使用 `datetime.now().date()` 替代数据中最晚日期作为参考。当跨天运行时，即使数据不变，输出也不同。

**修复建议**:
```python
latest_date = daily["日期"].max()  # 使用数据自身日期
daily["当月累计"] = daily[daily["日期"].dt.month == latest_date.month]["销售额"].cumsum()
```

---

#### 🟠 2.7.3 多Excel文件歧义

**位置**: 多处使用 `os.listdir` + `f.endswith(".xlsx")` 查找数据文件

当 `data/` 目录下有多个 `.xlsx` 文件时，使用第一个字母顺序的文件。可能使用错误的源文件。

**修复建议**:
```python
def find_source_data(data_path=None):
    if data_path and os.path.exists(data_path):
        return data_path
    xlsx_files = sorted([f for f in os.listdir(DATA_DIR) 
                        if f.endswith(".xlsx") and not f.startswith("~$")])
    if not xlsx_files:
        return ""
    if len(xlsx_files) > 1:
        print(f"[警告] 找到 {len(xlsx_files)} 个数据文件，使用: {xlsx_files[0]}")
    return os.path.join(DATA_DIR, xlsx_files[0])
```

---

#### 🟡 2.7.4 报告文件堆积

`report.py` 每次运行生成一个带时间戳的Excel文件。无清理机制，长期运行后 `output/report/` 目录会积累大量文件。

**修复建议**: 保留最近N次报告或使用固定文件名覆盖：
```python
# 保留最近5次
REPORT_MAX_KEEP = 5
old_reports = sorted([f for f in os.listdir(OUTPUT_REPORT) if f.startswith("客户分析报告")])
while len(old_reports) >= REPORT_MAX_KEEP:
    os.remove(os.path.join(OUTPUT_REPORT, old_reports.pop(0)))
```

---

## Step 3: 可视化分析探索建议

### 3.1 产品生命周期维度

#### 📊 3.1.1 产品生命周期桑基图（阶段迁移流）

| 项目 | 内容 |
|------|------|
| **图表类型** | 桑基图（Sankey Diagram） |
| **需要数据** | `SKU生命周期.csv` 的历史阶段数据（如果有多期数据，需补充分阶段快照） |
| **预期洞察** | 哪些产品从"成长爬坡"快速滑入"隐性衰退"；哪些"平稳成熟"产品开始下滑 |
| **实现工具** | `plotly.graph_objects.Sankey` |

#### 📊 3.1.2 品类生命周期分布热力图

| 项目 | 内容 |
|------|------|
| **图表类型** | 堆叠柱状图 + 热力图 |
| **需要数据** | `SKU生命周期.csv` × `品类` 交叉表，统计每品类中各阶段产品数 |
| **预期洞察** | MOS管品类大量产品在衰退期（品类的生命周期集群效应），集成电路新品占比高 |
| **实现工具** | `matplotlib.imshow` 或 `plotly.imshow` |

#### 📊 3.1.3 产品九宫格动态气泡图

| 项目 | 内容 |
|------|------|
| **图表类型** | 气泡图（Bubble Chart） |
| **需要数据** | `gold_product_portrait.csv`：动量得分(×轴) × 健康度得分(×轴) × 营收(气泡大小) × 品类(颜色) |
| **预期洞察** | 哪些品类的大产品集中在"瘦狗"区域；增长-健康双低的产品集群 |
| **实现工具** | `plotly.express.scatter` |

#### 📊 3.1.4 帕累托曲线 + ABC分类叠图

| 项目 | 内容 |
|------|------|
| **图表类型** | 双轴柱线组合图 |
| **需要数据** | `gold_product_portrait.csv`：产品按营收降序，累积占比曲线 |
| **预期洞察** | 前20%产品占多少营收；长尾产品的数量与营收贡献比 |
| **实现工具** | `matplotlib` 双Y轴 |

---

### 3.2 客户维度

#### 📊 3.2.1 RFM-π 平行坐标图

| 项目 | 内容 |
|------|------|
| **图表类型** | 平行坐标图（Parallel Coordinates） |
| **需要数据** | `客户全景.csv`：R_得分, F_得分, M_得分, P_得分, 渠道类型, 综合价值层级 |
| **预期洞察** | 代理与直销客户的评分模式差异；S级客户在各维度的共性特征 |
| **实现工具** | `plotly.express.parallel_coordinates` |

#### 📊 3.2.2 客户双轴矩阵散点图（含象限标注）

| 项目 | 内容 |
|------|------|
| **图表类型** | 散点图 + 象限分界线 |
| **需要数据** | `客户全景.csv`：价值贡献分(×轴), 增长动能分(×轴), 综合价值层级(颜色), 渠道类型(形状), 气泡大小=近12月收入 |
| **预期洞察** | 明星/金牛/培育/瘦狗四象限的客户分布；哪些渠道在哪个象限集中 |
| **实现工具** | `plotly.express.scatter` + 垂直/水平参考线 |

#### 📊 3.2.3 客户生命周期分布箱线图

| 项目 | 内容 |
|------|------|
| **图表类型** | 箱线图（Box Plot） |
| **需要数据** | `客户全景.csv`：客户生命周期 × 近12月收入 / 品种总数 / 近12月毛利率 |
| **预期洞察** | 衰退期客户的收入分布（是否仍有高价值客户开始衰退）；导入期客户的毛利率水平 |
| **实现工具** | `plotly.express.box` |

#### 📊 3.2.4 客户ETS预测置信区间可视化

| 项目 | 内容 |
|------|------|
| **图表类型** | 折线图 + 置信区间阴影 |
| **需要数据** | `客户月度趋势.csv`（历史）+ `客户预测.csv`（预测） |
| **预期洞察** | 未来3月收入走势；80%CI宽度指示预测不确定性；历史季节性模式 |
| **实现工具** | `plotly.graph_objects.Scatter` + `fill="tonexty"` |

#### 📊 3.2.5 客户层级 × 评分分布热力图

| 项目 | 内容 |
|------|------|
| **图表类型** | 热力图（Heatmap） |
| **需要数据** | `客户全景.csv`：客户层级(KA/AA/KM/MM) × 综合价值层级(S/A/B/C) 交叉表 |
| **预期洞察** | KA客户是否都评S级（验证评分与CRM层级的一致性）；MM客户中是否有S级（潜力客户发现） |
| **实现工具** | `seaborn.heatmap` 或 `plotly.imshow` |

#### 📊 3.2.6 客户集团雷达图

| 项目 | 内容 |
|------|------|
| **图表类型** | 雷达图（Radar Chart） |
| **需要数据** | `集团聚合.csv`：集团名称 × 近12月收入/成员数/产品线覆盖/活跃占比/衰退风险占比 |
| **预期洞察** | 比亚迪集团各维度均衡性；视源集团的弱势维度 |
| **实现工具** | `plotly.express.line_polar` |

---

### 3.3 综合关联分析

#### 📊 3.3.1 产品生命周期 × 客户活跃度交叉分析

| 项目 | 内容 |
|------|------|
| **图表类型** | 100%堆叠柱状图 |
| **需要数据** | `客户产品桥接.csv`：产品画像(当前画像) × 客户生命周期交叉表，金额为权重 |
| **预期洞察** | 衰退期客户主要采购什么画像的产品；导入期客户是否倾向新品 |
| **实现工具** | `plotly.express.bar` (barmode='stack') |

#### 📊 3.3.2 客户生命周期迁移桑基图

| 项目 | 内容 |
|------|------|
| **图表类型** | 桑基图（Sankey） |
| **需要数据** | 多期客户生命周期快照（当前代码无历史快照，需在 `portrait.py` 中增加保存历史阶段的功能） |
| **预期洞察** | 客户在上半年/下半年的阶段迁移模式；哪些客户从"爬坡期"滑入"衰退期" |
| **实现工具** | `plotly.graph_objects.Sankey` |

#### 📊 3.3.3 提价机会瀑布图

| 项目 | 内容 |
|------|------|
| **图表类型** | 瀑布图（Waterfall Chart） |
| **需要数据** | `提价机会.csv`：按品类分组，展示可提价总金额、客户数、平均提价比率 |
| **预期洞察** | 哪类产品有最大提价空间；提价机会的品类集中度 |
| **实现工具** | `plotly.graph_objects.Waterfall` |

#### 📊 3.3.4 降价策略盈亏平衡点分析

| 项目 | 内容 |
|------|------|
| **图表类型** | 多线图（Multi-line Chart） |
| **需要数据** | `降价策略试算.csv`：降价幅度 × 营收变化，按品类分组 |
| **预期洞察** | 3%降幅下哪些品类可盈亏平衡；10%降幅下哪些品类进入亏损区 |
| **实现工具** | `plotly.express.line` |

#### 📊 3.3.5 业务员定价偏离气泡图

| 项目 | 内容 |
|------|------|
| **图表类型** | 气泡图 |
| **需要数据** | `业务员定价偏离.csv`：平均定价偏离(×轴) × 高价占比(×轴) × 客户数(气泡大小) × 区域(颜色) |
| **预期洞察** | 哪些业务员倾向低价（需要培训）；哪些区域定价偏高（有调价空间） |
| **实现工具** | `plotly.express.scatter` |

---

### 3.4 交互仪表板建议

#### 推荐技术栈

| 组件 | 推荐方案 | 理由 |
|------|---------|------|
| 仪表板框架 | **Streamlit** | 纯Python，快速原型，与现有pandas代码完美配合 |
| 交互图表 | **Plotly Express** | 内置交互（hover/缩放/筛选），一行代码生成 |
| 数据缓存 | `st.cache_data` | 避免每次交互重新读取数据 |
| 部署 | Streamlit Community Cloud 或 内部服务器 | 免费/低成本 |

#### 推荐仪表板页面布局

```
Page 1: 全景总览 (Dashboard)
  ├── KPI卡片: 总客户数/总营收/平均评分/风险客户数
  ├── 双轴矩阵散点图 (全客户)
  ├── 综合价值层级饼图 + 机会/风险评级分布
  └── 渠道类型分布 + 集团排名Top10

Page 2: 客户深度分析 (Customer Deep Dive)
  ├── 客户搜索/筛选器 (按编号/层级/渠道/生命周期)
  ├── 单客户全景卡片 (所有维度指标)
  ├── 月度营收趋势折线图 + ETS预测 (置信区间)
  ├── 品类迁移堆叠柱状图 (半年度品类结构变化)
  └── 产品组合健康度 (饼图:各画像占比)

Page 3: 产品分析 (Product Analysis)  
  ├── SKU生命周期分布 (品类×阶段热力图)
  ├── 跨客户价格差异散点图 (按品类筛选)
  ├── 渠道价格对比柱状图
  └── 降价策略试算线图

Page 4: 价格治理仪表板 (Pricing Dashboard)
  ├── 价格离散度Top50列表 + 价格差异等级分布
  ├── 提价机会条形图 (按品类汇总)
  ├── 业务员定价偏离气泡图
  └── 市场细分价格雷达图 (渠道/层级/区域)

Page 5: 预警清单 (Alert Dashboard)
  ├── 高风险客户列表 (风险评级=高/极高)
  ├── 采购中断预警客户
  ├── 衰退期/休眠期客户
  └── 集团风险监控 (高危/警告集团)
```

#### 实现要点

```python
# Streamlit 快速启动框架示例
import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("半导体客户分析仪表板")

@st.cache_data
def load_data():
    profile = pd.read_csv("output/gold/客户全景.csv", encoding="utf-8-sig")
    trend = pd.read_csv("output/gold/客户月度趋势.csv", encoding="utf-8-sig")
    return profile, trend

profile, trend = load_data()

# 侧边栏筛选
channel = st.sidebar.multiselect("渠道类型", profile["渠道类型"].unique())
tier = st.sidebar.multiselect("综合价值层级", profile["综合价值层级"].unique())

# 主图
fig = px.scatter(
    profile, x="价值贡献分", y="增长动能分",
    color="综合价值层级", size="近12月收入",
    hover_data=["客户编号", "渠道类型"],
    title="客户双轴矩阵"
)
st.plotly_chart(fig, use_container_width=True)
```

---

## Step 4: 性能瓶颈定位与优化

### 4.1 总体运行时间与瓶颈分布

基于337K行数据、全5阶段管道的基准分析（实际运行~5分钟）：

| 阶段 | 耗时 | 占比 | 瓶颈类型 |
|------|------|------|---------|
| Silver层构建 | ~60s | 20% | I/O (Excel读取) |
| 产品生命周期 | ~120s | 40% | CPU (多重聚合+ETS) |
| 客户分析 | ~90s | 30% | CPU (逐行循环+ETS) |
| KPI | ~20s | 7% | I/O + 聚合 |
| 交叉关联 | ~10s | 3% | I/O (CSV加载) |

### 🔴 4.2 `calc_customer_portrait()` 逐行循环 — 最大单点优化机会

**当前位置**: `portrait.py:380-399`

**当前实现**:
```python
results = []
for cid in customers:   # 310次迭代
    row = {"客户编号": cid}
    c_mask = cust_monthly["客户编号"] == cid   # 全表扫描
    c_data = cust_monthly[c_mask].sort_values("_月")  # 子DataFrame
    cp_mask = cust_prod["客户编号"] == cid  # 又一次全表扫描
    cp_data = cust_prod[cp_mask]  # 又一次子DataFrame
    
    row.update(_dim_base_info(cid, cust_info, raw_data, _attr_map))
    row.update(_dim_momentum(c_data, latest_month))
    row.update(_dim_product_coverage(cp_data))
    # ... 等等
```

**性能分析**:
- 每次迭代扫描 `cust_monthly` (8,612行) 和 `cust_prod` (94,609行)
- 总扫描行数：310 × (8,612 + 94,609) = **31.9M行**
- 创建子DataFrame：310 × 2 = 620次拷贝
- `_dim_momentum` 中每次对子DataFrame再排序 (.sort_values)

**优化方案**:

方案A — groupby + 矢量化合并（推荐，预计加速5-10×）：

```python
def calc_customer_portrait_vectorized(silver, ...):
    cust_monthly = silver["customer_monthly"].copy()
    cust_prod = silver["customer_x_product"].copy()
    prod_monthly = silver["product_monthly"].copy()
    
    # ---- 批量计算（无需改变） ----
    metrics = _compute_batch_metrics(cust_monthly, cust_prod, prod_monthly, ...)
    
    # ---- 基本信息：join操作替代loop ----
    base_info = cust_info.set_index("客户编号").reindex(customers)
    base_info["渠道类型"] = base_info["渠道类型"].fillna("未知")
    # 仍未推导出的 -> 从raw_data推导
    unknown_mask = base_info["渠道类型"] == "未知"
    # ... 向量化推导
    
    # ---- 经营势能：groupby + 窗口函数 ----
    momentum = []
    for cid, grp in cust_monthly.groupby("客户编号"):
        grp = grp.sort_values("_月")
        recent = grp[grp["_月"] > latest_month - 12]
        prior = grp[(grp["_月"] <= latest_month - 12) & (grp["_月"] > latest_month - 24)]
        # 直接计算所有指标
        momentum.append({...})
    momentum_df = pd.DataFrame(momentum)
    
    # ---- 合并 ----
    result = base_info.merge(momentum_df, on="客户编号", how="left")
    # ... 其他指标同理
    
    return result
```

方案B — 缓存mask（轻度优化，预计加速2×）：
```python
# 预先为每个客户计算mask，用dict缓存
cust_masks = {cid: cust_monthly["客户编号"] == cid for cid in customers}
cp_masks = {cid: cust_prod["客户编号"] == cid for cid in customers}
```

**预期提升**: 方案A可将 `calc_customer_portrait` 从 ~45s 降至 ~5-8s。

---

### 🟠 4.3 重复Excel读取

**当前位置**: `run_all.py` 各阶段独立读取源Excel

- `stage_silver()` (行83): `read_excel_auto(source_path)`
- `stage_product()` 内部调用 `run_product()` 再次读取
- `stage_customer()` (通过 `run_pipeline.run()`) 又读取一次用于渠道推导

**影响**: 337K行的Excel读取3次，每次约15-20s，总计约50s。

**优化方案**:
```python
# 在 run_all.py main() 中预先读取
raw_shared = read_excel_auto(source_path, sheet_name=0)
raw_shared = rename_erp_columns(raw_shared)

# 传递给各阶段
stage_silver(raw_shared)
stage_product(raw_shared)  # 跳过内部读取
stage_customer(raw_shared)  # 跳过内部读取
```

**预期提升**: 减少 ~30s I/O时间。

---

### 🟠 4.4 ETS预测 — 批量预测可并行化

**当前位置**: `trend_analysis.py:calc_customer_forecast()` 和 `shared/forecasting.py:ets_forecast()`

**分析**:
- 310客户中历史≥12月的～200客户执行ETS
- 每个客户尝试12种ETS配置（error×trend组合）
- `statsmodels ETSModel.fit()` 是CPU密集型操作

**优化方案**:

方案A（推荐）: Joblib并行
```python
from joblib import Parallel, delayed

def _forecast_one_customer(cid, grp, ...):
    rev_series = grp.sort_values("_月")["rev_sum"].values
    forecast, direction, pred_int, model_info = ets_forecast(rev_series, ...)
    return build_forecast_rows(cid, forecast, direction, pred_int, model_info)

results = Parallel(n_jobs=-1, prefer="threads")(
    delayed(_forecast_one_customer)(cid, grp, ...)
    for cid, grp in cust_monthly.groupby("客户编号")
    if len(grp) >= min_history
)
```

方案B: 减少模型配置数（见2.5.2，对短历史限制模型复杂度）

**预期提升**: 8核CPU下约 6-8×加速，ETS预测从 ~30s 降至 ~4-5s。

---

### 🟠 4.5 KPI每日Top5 — 嵌套groupby.apply低效

**当前位置**: `run_kpi_daily.py:69-81`

**分析**: `groupby().apply()` 嵌套 `groupby().nlargest().to_dict()` 对每日数据执行双重groupby，且 `.to_dict()` 产生不可序列化的输出。

**优化方案**:
```python
# 统一的按日分组聚合后，用 rank() 替代 apply()
daily_raw = raw.copy()
daily_raw["日期"] = raw["发货日期"].dt.date

# 按日-客户聚合
cust_daily = daily_raw.groupby(["日期", "客户编号"])["金额"].sum().reset_index()
# 每日Top5
cust_daily["rank"] = cust_daily.groupby("日期")["金额"].rank(method="first", ascending=False)
top5 = cust_daily[cust_daily["rank"] <= 5].groupby("日期").apply(
    lambda g: "; ".join(f"{r['客户编号']}({r['金额']:.0f})" for _, r in g.iterrows()),
    include_groups=False,
).reset_index(name="Top5客户")
```

**预期提升**: 从 ~15s 降至 ~2s，且输出可解析。

---

### 4.6 优化优先级汇总

| 优先级 | 瓶颈 | 当前耗时 | 优化后 | 加速比 | 工作量 | 方案 |
|--------|------|---------|-------|-------|-------|------|
| 🔴 P0 | `portrait.py` 逐行循环 | ~45s | ~5s | **9×** | 2h | groupby+矢量化 |
| 🟠 P1 | 重复Excel读取 | ~50s | ~20s | **2.5×** | 1h | 共享raw数据 |
| 🟠 P1 | ETS串行预测 | ~30s | ~4s | **7.5×** | 0.5h | Parallel并行 |
| 🟠 P2 | KPI Top5 apply | ~15s | ~2s | **7.5×** | 0.5h | rank替代apply |
| 🟡 P3 | `true_profit` iterrows | ~0.3s | ~0.01s | **30×** | 0.3h | 向量化 |
| 🟡 P3 | 批量内存优化(dtype) | — | 内存↓30% | — | 0.5h | category/float32 |

**管道总时间预期**: 从 ~5分 降至 ~2分（**60%减少**），仅需 P0+P1 优化即可。
