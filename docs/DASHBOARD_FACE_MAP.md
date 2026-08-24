# Dashboard 六面逆向工程迁移地图（批次④a 第一阶段）

> 目标：让 `dashboard/generate_dashboard.py` 彻底停止直读原始 Excel（当前约 13 列 + 全表 `rex` 构建，占全算 ~47.7s 加载 + 各面重算，另 D面 241.7s），改为只读 `output/` 下 silver/gold/report 产物。
> 方法：**以代码实际行为为准**（逐区段读 `generate_dashboard.py` 当前版本，行号随批次②③变更已更新）；列头来自 `output/` 实际文件（用 pandas 实读，工作目录 `sales_analytics_platform`；**当前无 parquet**，silver 为 CSV 形态，见 §2 说明）。
> 备注：批次②已做列语义化（`DASHBOARD_COL_PRIORITY`）与年份动态化（`derive_periods`）；批次③已加 `preagg.json` 自缓存与 D-1 展示层截断。本图以全算路径（缓存未命中）为基线。

---

## 0. 数据流概览与主要读取点

```
data/*.xlsx (最新) ──13列 usecols──▶ rex(行级,~19万行) ──▶ 六面全部聚合 (A/B/C/D/E/F)
                                       ▲                          │
output/silver/*.csv（仅 silver_cleaned_rows 用于新品+审计）        ▼
output/gold/*.csv（客户全景/产品画像/销售画像/销售周期/交叉销售/客户预测）└▶ preagg.json 缓存
output/report/产品生命周期报告*.xlsx（C面 DATA）
data/部门-人员-职务对应.md（D_DEPT_LIST / F_DEPT_MARGINS 部门映射）
```

代码读取点（证据）：

| 读取 | 位置 | 内容 |
|---|---|---|
| 原始 Excel 表头 + 13 列精准读取 | L657-704（`keep_cols` L674-688，`rex` L690-704） | 全看板主数据源（`rex`） |
| `output/gold/客户全景.csv` | L643（`df`） | A面客户列表/散点属性/B面 call 的客户属性 |
| `output/gold/gold_product_portrait.csv` | L645（`prod_df`） | C面回退快照、产品列表画像/风险映射 |
| `output/silver/silver_cleaned_rows.csv` | L1075（`cleaned_cols=[客户编号,产品品种,新品标记,金额,数量,发货日期]`） | B面新品明细 `new_detail`、A面新品渗透率 `new_pct`、Raw=Silver 审计 |
| `output/gold/销售画像.csv` | L1181 | D面 `portrait_map`（9力/评分/等级/亚组） |
| `output/gold/销售人员周期表现.csv` | L1248 | D面 `D_SALES_TREND` |
| `output/gold/交叉销售建议.csv` | L1266 | D面 `cross_by_sales` |
| `output/gold/客户预测.csv` | L1282 | D面 `fc_by_sales` |
| `output/report/产品生命周期报告_v4.0_*.xlsx` | L447-493（`load_product_report`）/ L2349-2358（构建） | C面 DATA |
| `data/部门-人员-职务对应.md` | L1798 | D_DEPT_LIST / F_DEPT_MARGINS 部门映射 |

---

## 1. 逐面数据源清单

> 列名括号内为 `rex` 归一列（`_xxx`）或产出变量；"过滤/聚合" 描述该区块做了什么。

### 1.1 KPI 总览（A面顶部卡片，L744-782；[2/5]）

| 产出 | Excel 直读列（rex） | silver/gold 读取 | 关键计算 |
|---|---|---|---|
| `kpi_r/kpi_p/kpi_c/kpi_mg`（YTD 收入/利润/成本/毛利率） | 发货日期`_d`、RMB未税金额小计`_rev`、利润`_profit` | — | YTD 窗口 `[ytd_start,ytd_end]` 内 `_rev/_profit` 求和、`/1e4`、相除出毛利率（L744-776） |
| `kpi_ry/kpi_py/kpi_mg_yoy`（同比） | `_d`、`_rev`、`_profit` | — | PYTD（上年同期）求和对比（L745-763） |
| `kpi_sr/kpi_sp/kpi_sm/kpi_spt/kpi_sc`（KA+AA 卡） | `_d`、`_tier`(终端客户名称_客户类别)、`_rev`、`_profit`、`_cust` | — | `_tier` 含 "KA\|AA" 过滤，YTD 求和 / 客户去重（L750-764） |
| `asp_ytd/asp_lytd/asp_yoy/asp_mom`（ASP） | `_d`、`_rev`、`_qty` | — | `_rev/_qty`；环比用最新月 vs 上月（L766-776） |

### 1.2 A面 其余区块

| 区块 | 产出 | Excel 直读列 | silver/gold 读取 | 关键计算 |
|---|---|---|---|---|
| 月度成本/毛利趋势 | `TREND`（r24..m26） | `_ym`、`_rev`、`_profit` | — | 按年分组 12 月补齐（`yd()` L783-805）；成本=收入-毛利 |
| 分层趋势 | `TREND_TIERS`（KA/AA/KM/MM） | `_tier`、`_ym`、`_rev`、`_profit` | — | 每层 `_tier.str.contains` 过滤后同 TREND（L806-829） |
| KA+AA 月度折线 | `KAA_REV` | `_tier`、`_ym`、`_rev` | — | 按月求和 `/1e4`（L830-833） |
| K类客户饼图 | `PIE` | `_tier`、`_cust` | — | YTD 内 KA/AA/KM 客户数去重（排除 nan 客户名）（L835-861） |
| KA 经营势能散点 | `SCAT` | `_tier`、`_cust`、`_rev`、`_profit` | `客户全景.csv`（客户名称→n、双轴分类→d） | YTD vs PYTD 增长%+毛利率%，过滤 `rev>0 & |g|<500`（L863-869） |
| KA/AA 客户列表 | `SA`（csa） | `_cust`、`_rev`、`_profit`、`_qty`、`_d` | `客户全景.csv`（客户名称/层级/双轴/生命周期/风险/策略/负责人/新品占比等） | YTD 聚合 + 最新月/上月环比 + YoY（来自 Gold 列 `YoY同比增速`）（L871-914） |
| KA KPI 卡 | `%%KA_*%%` | `_d`、`_tier`、`_rev`、`_profit`、`_qty` | — | YTD/环比/ASP（L916-932） |
| AA KPI 卡 | `%%AA_*%%` | 同上 | — | 同 KA（L934-948） |
| 产品线/品类毛利率明细表 | `PLINE_MARGINS`/`CAT_MARGINS` | `_pline_new`、`_cat`、`_rev`、`_profit`、`_tier` | — | YTD 按产品线/品类聚合 + KA/AA 拆解（L1605-1624） |
| 产品型号变迁 | `PROD_CHANGE` | `_cust`、`_ym_full`、`_item`、`_cat_new`、`_rev`、`_profit`、`_qty` | `客户全景.csv`（KA/AA 客户名单） | 全历史 vs 近12月 品种集合差集，`q≥6000` 阈值（L1000-1048） |
| 新品渗透率 | `%%NEW_PCT%%` | `_prod`、`_d`、`_is_new`、`_rev` | — | YTD 新品收入占比（L1094-1095） |

### 1.3 B面（客户详情/列表）

| 区块 | 产出 | Excel 直读列 | silver/gold 读取 | 关键计算 |
|---|---|---|---|---|
| B面月度趋势 | `B_TREND`（ctr） | `_cust`、`_ym_full`、`_rev`、`_profit`、`_qty` | — | 客户×月聚合，取最近 25 月（L950-957） |
| B面财务 | `cid_fin`（→call） | 同 ctr | — | YTD/PYTD/近12月/最新月/上月 收入利润毛利成本（L958-978） |
| B面品类/品种 | `cid_12m_data`/`prank`（→call） | `_cust`、`_prod`、`_cat`、`_rev`、`_ym_full` | — | 近12月 客户×品种去重数、品类收入、Top5 产品（L980-998） |
| B面客户列表 | `B_CUSTS`（call） | —（来自上述+下述） | `客户全景.csv`（~50 客户属性列）；`silver_cleaned_rows.csv`（新品明细） | 逐客户组装展示对象（L1096-1129） |

### 1.4 C面（产品画像）

| 区块 | 产出 | Excel 直读列 | 文件读取 | 关键计算 |
|---|---|---|---|---|
| C面 DATA | `DATA`（table/kpi/charts/scatter/sankey/history/filters） | **无（C面已不读 Excel）** | `output/report/产品生命周期报告_v4.0_*.xlsx`（产品快照表 / 历史画像追踪 / 数据不足产品清单）；回退 `gold_product_portrait.csv` | `load_product_report()` 找最新报告（L447-493）→ `build_c_data()`（L499-518） |

### 1.5 D面（销售能力）——见 §3 专项

### 1.6 E面（月度作战雷达）

| 区块 | 产出 | Excel 直读列 | 关键计算 |
|---|---|---|---|
| 全量月度 KPI | `E_MONTHLY_KPI` | `_ym`、`_rev`、`_profit`、`_qty`、`_cust`、`_item`、`_tier` | 逐月求和 + KA/AA/KM/MM 分层（L1561-1580） |
| 客户月度势能 | `E_CUST_MONTHLY` | `_ym`、`_cust`、`_rev`、`_profit`、`_qty` | 客户×月 聚合（L1582-1594） |
| 首次大量导入 | `E_FIRST_IMPORT`/`E_IMPORT_SUMMARY` | `_ym`、`_qty`、`_cust`、`_item`、`_sales`、`_cat_new`、`_pline_new`、`_rev`、`_profit` | 全历史 `q≥6000` 首次出现（L1627-1653, L1783-1794） |
| 销售员月度贡献 | `E_SALES_MONTHLY` | `_ym`、`_sales`、`_rev`、`_profit`、`_qty`、`_cust`、`_is_new` | 逐月逐销售员聚合 + Top1客户 + 异动>50%（L1656-1736） |
| §3 量利拆解 | `E_DECOMP` | `_ym`、`_pline_new`、`_cust`、`_cat`、`_tier`、`_rev`、`_profit`、`_qty` | 产品线/KA客户/AA客户/Top10品类 四维×月（L1742-1762） |
| 层级映射 | `E_CUST_TIER` | `_cust`、`_tier` | 客户→层级（L1729-1733） |

### 1.7 F面（H1 半年度汇总 + 部门 + 新品 + 产品对比）

| 区块 | 产出 | Excel 直读列 | 其他文件 | 关键计算 |
|---|---|---|---|---|
| H1 KPI | `F_H1_KPI` | `_d`、`_rev`、`_profit`、`_qty`、`_tier`、`_cust` | — | H1（1-6月）YTD 对比、ASP、KA+AA（L1848-1872） |
| 产品线/品类毛利率 | `F_PLINE_MARGINS`/`F_CAT_MARGINS` | `_pline_new`、`_cat`、`_rev`、`_profit`、`_tier`、`_d` | — | H1 vs 前年H1 毛利率/同比（L1875-1914） |
| 销售部毛利率 | `F_DEPT_MARGINS` | `_d`、`_sales`、`_rev`、`_profit`、`_qty` | `data/部门-人员-职务对应.md` | 按部门聚合 + ASP/环比/成员（L1917-1950） |
| KA/AA 客户 H1 毛利率 | `F_KAAA_MARGINS` | `_d`、`_cust`、`_tier`、`_rev`、`_profit`、`_qty`、`_is_new` | — | 客户×H1 毛利率/ASP/环比/新品渗透（L1953-1981） |
| 新品分析 | `F_NP_ANALYSIS`/`F_NP_SUMMARY` | `_is_new`、`_prod`、`_d`、`_ym`、`_rev`、`_profit`、`_cust`、`_sales` | — | 新品 12 个月存活口径（L1983-2012） |
| H1 问题/归因 | `F_ISSUES`/`F_CAT_ATTRIBUTION` | `_item`、`_cat`、`_pline_new`、`_rev`、`_profit`、`_qty`、`_d` | — | 毛利率下滑归因（L2014-2135） |
| 产品维度 H1 对比 | `F_PRODUCT_LIST` | `_item`、`_d`、`_ym`、`_rev`、`_profit`、`_qty`、`_cust`、`_is_new` | `gold_product_portrait.csv`（画像/风险映射） | 近12月收入>10万主要产品 + 24月趋势 + Top5客户（L2136-2233） |
| 品类维度 H1 对比 | `F_CAT_H1` | `_cat`、`_d`、`_rev`、`_profit` | — | 品类×半年 聚合（L2235-2290） |
| 部门列表 | `D_DEPT_LIST`（dept_list） | —（基于 d_sales_list） | `部门-人员-职务对应.md` | 部门聚合（L1824-1846） |

---

## 2. 缺口分析

### 2.0 说明
- 当前 `output/` **无 parquet**（批次②.5 CSV+Parquet 双写未落地/已回退），silver 为 CSV：`silver_cleaned_rows.csv`（行级，180MB，73 列）、`silver_customer_monthly.csv`（客户×月）、`silver_customer_x_product.csv`（客户×产品×月）、`silver_product_monthly.csv`（产品×月）。
- 关键结论：**`silver_cleaned_rows.csv` 几乎就是"清过洗的原始 Excel"**（73 列，含看板 13 列的全部等价列，且列名已按 `settings.ERP_COL_MAP` 归一）。看板 `rex` 所需的 13 列**全部**能在其中找到（列级"真缺口"= 0）。
- 风险提示：silver 是批次① 统一清洗入口（负数量过滤/毛利率钳制），与 raw 可能有行级差异；批次② 的 Raw=Silver 审计验证了**当前数据下 YTD 收入完全相等（430,806,283.91，相对差 0.00e+00）**，但逐面迁移仍须对拍（见 §5）。

### 2.1 Excel 直读 13 列 → silver/gold 逐列对照

| # | Excel 直读列（`keep_cols`/语义解析） | `rex` 归一 | 语义 | **silver_cleaned_rows 等价列** | **gold 某表等价/可派生** | 结论 |
|---|---|---|---|---|---|---|
| 1 | 发货日期（L674） | `_d` | 交易日期→最新月/窗口 | `发货日期`（同名） | `gold_kpi_daily.日期`（日粒度）；`客户月度趋势.月份`（月粒度） | 已在 silver ✓ |
| 2 | RMB 未税金额小计（L674） | `_rev` | 收入 | `金额`（ERP_COL_MAP：RMB未税金额小计→金额） | `经营周期总览.收入`、`客户月度趋势.月收入`、`KA_AA月度雷达.月收入` | 已在 silver ✓ / gold(聚合) |
| 3 | 利润（L674） | `_profit` | 毛利 | `利润`（同名） | `月毛利`、`月毛利润` 等 | 已在 silver ✓ / gold(聚合) |
| 4 | 发货数量（L674） | `_qty` | 数量 | `数量`（ERP_COL_MAP：发货数量→数量） | `月数量`、`qty_sum` | 已在 silver ✓ / gold(聚合) |
| 5 | 终端客户名称_客户类别（L674） | `_tier` | 客户层级 | `客户类别`（注意：非同名，需对拍验证同值） | `客户全景.客户层级`、`KA_AA月度雷达.客户层级`、`负毛利分析.客户层级` | 已在 silver ✓ / gold ✓ |
| 6 | 终端客户简称（L674） | `_cust` | 客户唯一标识 | `客户编号`（ERP_COL_MAP：终端客户简称→客户编号） | `客户全景.客户编号`、各 gold 客户表 | 已在 silver ✓ / gold ✓ |
| 7 | 客户订单号（L674） | — | 订单唯一号 | `客户订单号`（同名） | `silver_customer_monthly.order_count`（聚合）；`gold_kpi_daily.订单数` | 已在 silver ✓ / gold(聚合) |
| 8 | 产品线 或 产品品种（L663-664, 语义） | `_prod` | 产品线维度 | `产品一级分类`（ERP_COL_MAP：产品线→产品一级分类） | `gold_product_portrait.产品名称`；`跨客户价格差异.产品一级分类`；`品类擅长.产品线` | 已在 silver ✓ / gold(部分) |
| 9 | 产品品类（新）（L668, 语义 `category`） | `_cat`/`_cat_new` | 品类 | `产品品类`（ERP_COL_MAP：产品品类（新）→产品品类） | `silver_customer_x_product.产品品类`（silver）；`客户全景.主导品类`；`品类接受度.主导品类` | 已在 silver ✓ / gold(部分) |
| 10 | 存货名称（L673） | `_item` | 产品型号/存货 SKU | `产品品种`（ERP_COL_MAP：存货名称→产品品种） | `gold_product_portrait.产品名称`；`SKU生命周期.产品品种` | 已在 silver ✓ / gold ✓ |
| 11 | 型号_产品线（新）（L669, 语义 `product_line_new`） | `_pline_new` | E面产品线（新） | `型号_产品线（新）`（同名） | `silver_customer_x_product.型号_产品线（新）`（silver）；`gold_product_portrait` 无 | 已在 silver ✓ / gold ✗ |
| 12 | 是否新品（L670, 语义 `is_new`） | `_is_new` | 新品标记 | `新品标记`（ERP_COL_MAP：是否新品→新品标记） | `silver_product_monthly.新品标记`（silver）；`客户全景.是否采购新品`（客户级，非产品级） | 已在 silver ✓ / gold ✗ |
| 13 | 实际业务员（L671, 语义 `sales`） | `_sales` | D面销售员 | `实际业务员`（同名） | `销售画像.业务负责人`、`销售人员周期表现.业务负责人`、`品类擅长.业务负责人` | 已在 silver ✓ / gold ✓ |

**汇总**：已在 silver = **13/13**；已在 gold（直接等价列）= **10/13**（#11 型号_产品线（新）、#12 是否新品 gold 无产品级列；#1 发货日期 gold 仅日/月粒度）；列级**真缺口 = 0**。

### 2.2 聚合级缺口（看板需要但现成预聚表未直接提供）

| 所需聚合 | 看板位置 | silver/gold 现成 | 缺口 / 建议归宿 |
|---|---|---|---|
| 销售员 × 客户 × YTD（金额/利润/数量） | D面 `D_CUST_HEATMAP`（L1539-1558，858 次 rex 过滤） | ✗（`silver_customer_x_product` 无销售员；`silver_customer_monthly` 无销售员） | **新建 gold 预聚表** `dashboard_sales_customer_ytd`（实际业务员×客户编号×YTD 金额/利润/数量）或 silver_cleaned_rows groupby（1 次） |
| 销售员 × 品类（收入/毛利/数量） | D面 `D_HEATMAP`/6e（L1206-1237） | ✗（`silver_customer_x_product` 有品类无销售员） | 新建 gold 表或 silver_cleaned_rows groupby |
| 销售员 × 月 × 客户（异动>50%） | E面 `E_SALES_MONTHLY`（L1656-1736） | ✗（现成表无 销售员×客户×月） | 新建 gold 表或 silver_cleaned_rows groupby |
| 客户 × 月（收入/毛利/数量/订单数） | B面 `B_TREND`/`cid_fin`、E面 `E_CUST_MONTHLY`、A面月度趋势 | `silver_customer_monthly`（_月,客户编号,qty_sum,rev_sum,cost_sum,profit_raw_sum,profit_clip_sum,order_count,毛利率%）✓ | 已覆盖；注意看板 `_rev` 是"金额"、silver 用 `rev_sum`，口径需对拍 |
| 客户 × 产品 × 月（品种/品类/6000 阈值） | A面 `PROD_CHANGE`、B面 `cid_12m_data`/`prank`、E面 `E_FIRST_IMPORT` | `silver_customer_x_product`（_月,客户编号,产品品种,qty_sum,rev_sum,profit_clip_sum,毛利率%,产品一级分类,型号_产品品类,型号_产品线（新）,产品品类）✓ | 已覆盖；注意缺"利润 raw"（只有 profit_clip_sum） |
| 产品 × 月（趋势/H1/ASP） | F面 `F_PRODUCT_LIST`（trend）、`_prod_h1` | `silver_product_monthly`（_月,产品品种,qty_sum,rev_sum,cost_sum,profit_raw_sum,profit_clip_sum,avg_price,新品标记,毛利率%）✓ | 已覆盖；缺"品类"列（F面 `f_cat_h1` 需品类×半年，见下） |
| 品类 × 月（`F_CAT_H1`/`CAT_MARGINS`） | F面 `f_cat_h1`（L2235-2290）、A面 `CAT_MARGINS` | ✗（`silver_product_monthly` 无品类；`silver_customer_x_product` 有品类但带客户维） | 新建 gold 预聚表 `dashboard_cat_monthly`（品类×月）或由 silver_cleaned_rows groupby |
| 层级 × 月（`TREND_TIERS`、`E_MONTHLY_KPI` 分层） | A面 `TREND_TIERS`、E面 7a | ✗（`silver_customer_monthly` 无客户层级列） | 迁移时对 `silver_customer_monthly` join `客户全景.客户层级`（客户编号→层级），或新建带层级的月度预聚 |

> 结论：看板 6 面的聚合，**绝大部分可用 silver 3 张预聚表 + silver_cleaned_rows（行级）groupby 覆盖**；真正的"新建 gold 表"缺口集中在 **D面（销售员维度 3 个表）+ F面品类月度（1 个表）** 共约 4 张新预聚表。

---

## 3. D面专项（241.7s，占全算 61.3%，头号热点）

> D面 241.7s 中，**6n 客户热力图独占 ~215s**（26 销售员 × 33 客户 × 每次 4 条件布尔过滤 19 万行 ≈ 858 次 = ~6.5 亿行次判定）；其余 ~26s 来自 6l/6l2 的证据循环（逐客户再过滤 rex）。迁移后 6n 可改为**1 次 groupby**。

| D面子块 | 产出 | 数据需求 | 当前计算方式 | rex 依赖 | 迁移建议 |
|---|---|---|---|---|---|
| 6a-6c YTD 聚合 | （→D_SALES_LIST/D_KPI） | 销售员×YTD：收入/毛利/数量/订单数/客户数/产品数 + 同比 + 环比 | `rex` 过滤 YTD/PYTD/最新月/上月 → groupby `_sales`（L1145-1178） | `_d,_sales,_rev,_profit,_qty,客户订单号,_cust,_prod` | silver_cleaned_rows 按 `实际业务员` groupby（金额/利润/数量/客户订单号nunique/客户编号nunique/产品品种nunique） |
| 6d 销售画像 | `portrait_map`（→D_SALES_LIST forces/score/level/subgroup） | 销售员画像 | 读 `gold/销售画像.csv`（L1180-1204） | 无 | 已 gold，不动 |
| 6e 真实品类 | `cat_by_sales`/`team_cat_names`（→D_HEATMAP/D_SALES_LIST） | 销售员×品类 Top8 + 团队 Top15 品类 | `rex` YTD 过滤 → groupby `_sales,_cat`（L1206-1245） | `_d,_sales,_cat,_rev,_profit,_qty` | 新建 gold `dashboard_sales_cat_ytd` 或 silver_cleaned_rows groupby |
| 6f 销售周期表现 | `D_SALES_TREND` | 销售员×月 | 读 `gold/销售人员周期表现.csv`（L1247-1262） | 无 | 已 gold，不动 |
| 6g 交叉销售 | `cross_by_sales` | 客户→销售员映射 + 推荐 | 读 `gold/交叉销售建议.csv` + `rex` 客户→销售员（L1265-1279） | `_cust,_sales`（cust_to_sales） | `cust_to_sales` 用 silver_cleaned_rows groupby 客户编号→实际业务员 |
| 6h 客户预测 | `fc_by_sales` | 客户预测 → 销售员 | 读 `gold/客户预测.csv` + cust_to_sales（L1281-1299） | `_cust,_sales` | 同 6g |
| 6i 组装列表 | `D_SALES_LIST` | 汇总 6c/6d/6e/6g/6h | 逐销售员组装（L1301-1343） | 间接 | 迁移后仅用上述产物 |
| 6j KPI | `D_KPI` | 团队营收/毛利/评分/A级/KA+AA 数 | 对 `d_sales_list` 求和（L1337-1363） | 间接 | 不动 |
| 6k 团队热力图 | `D_HEATMAP` | 销售员×团队Top15品类矩阵 | 由 cat_by_sales 组装（L1356-1365） | 间接 | 随 6e |
| 6l 短板诊断 | `diagnosis`（→D_SALES_LIST） | 团队9力均值 + 客户同比降幅 + 客户存货下滑证据 | 逐销售员逐力；`cust_yoy_data`（逐客户 r26/r25 过滤，L1373-1382）、`cust_item_decline`（逐客户 近6/前6月 过滤，L1384-1396）、证据循环（L1398-1436） | `_cust,_d,_rev,_item,_cat_new,_ym_full,_sales` | `cust_yoy_data`=silver_cleaned_rows groupby 客户编号（YTD/PYTD）；`cust_item_decline`=silver_cleaned_rows groupby（客户×存货×品类 近6/前6）；证据循环改为基于预聚合 dict 查询 |
| 6l2 能力画像 | `profile`（→D_SALES_LIST） | 强项/弱项/排名/占比 | 逐销售员（L1438-1534） | 间接（用 r26_all/r25_all/cust_to_sales） | 随 6l 预聚合 |
| 6m 瀑布图 | `D_WATERFALL` | 团队9力均值 | 由 forces 均值（L1536-1537） | 间接 | 不动 |
| 6n **客户热力图** | `D_CUST_HEATMAP` | 销售员×Top33客户×YTD 金额/利润 | **858 次 rex 布尔过滤**（L1539-1558）：`rex[YTD & _sales==s & _cust==cn]` | `_d,_sales,_cust,_rev,_profit` | **改 1 次 silver_cleaned_rows groupby（实际业务员×客户编号）YTD 金额/利润**；Top33 客户也由同一次 groupby 出 |
| D_TEAM_PROFILE | `D_TEAM_PROFILE` | 团队总结 | 由 d_sales_list（L1530-1543 附近） | 间接 | 不动 |

**D面迁移收益估算**：6n 从 ~215s → <1s（1 次 groupby）；6l/6l2 从 ~26s → ~2s（3 次 groupby + dict 查询）。D面整体 241.7s → 预计 <10s。

---

## 4. C面专项（report 读取机制与指纹/缓存影响）

### 4.1 报告读取机制（`load_product_report()` L447-493）
1. **找最新报告**：`glob output/report/产品生命周期报告_v4.0_*.xlsx`，排除 `~$` 开头的临时文件，按 `os.path.getmtime` 降序取第一个（L452-457）。当前最新：`产品生命周期报告_v4.0_20260824_122215.xlsx`。
2. **读哪些 sheet**（用 calamine 引擎，`_sheet(frag)` 按子串匹配 sheet 名）：
   - 产品快照表：`_sheet("产品快照表")`，找不到则取第一个 sheet（L469-470）→ `df_snap`（列 = gold_product_portrait 同构，62 列，792 行）。
   - 历史画像追踪（Format B）：`_sheet("历史画像追踪")`；若快照自带 `当前画像_t-N` 列（Format A）则直接用快照（L471-478）→ `df_hist`（t-1..t-12 × 6 列）。
   - 数据不足产品清单：`_sheet("数据不足")`，取其行数作为 `insuff_count`（L487-493）。
   - 数据月份：快照的 `最新数据月份` 首值（L481-486）。
3. **C面 DATA 构建**（`build_c_data()` L499-518）：由 `df_snap`/`df_hist` 产出 `table`(792)、`history`(792)、`kpi`、`charts`、`filters`、`scatter`(645)、`sankey`(44 节点/164 边)、`data_month`。
4. **回退**：报告缺失时 `_c_src = prod_df`（gold_product_portrait.csv，L2336-2338），无历史/桑基/月份。

### 4.2 对指纹/缓存的影响（批次③已用"两路径均现算"规避）
- `output/report/*.xlsx` **不在**批次③指纹 5 键内（指纹只覆盖 `excel / settings / dashboard_code / template / outputs[silver+gold]`，见 `processing/shared/fingerprint.py`）。
- 因此报告变化**不会**触发 preagg.json 失效。批次③的设计**主动规避**了这一点：**缓存与全算两条路径都重新调用 `load_product_report()` + `build_c_data()` 现算 C面**（缓存路径 L583-593；全算路径 L2349-2358），并把 `%%C_DATA_JSON%%`/`%%MARGIN_AXIS_*%%`（源自 C面）排除在缓存 payload 之外。
- 报告读取 ~1s（792 行小文件），不影响缓存命中 0.9s 的优势；报告本身的"找最新→读 3 sheet"是安全的（若报告缺失，两路径一致回退 gold）。
- 迁移到"只读产物"后：C面已是纯 report/gold 消费方，**无需改动**；仅需确认④a 冻结 Dashboard 输入 schema 时把"产品生命周期报告_v4.0_*.xlsx 的 3 个 sheet 列结构"纳入契约（建议同时纳入指纹，消除残余风险）。

---

## 5. 迁移顺序建议（按 缺口×收益 排序）

| 优先级 | 面/区块 | 现状耗时 | 缺口大小 | 迁移方案 | 预估改动量 | 风险 | 说明 |
|---|---|---|---|---|---|---|---|
| P0 | **D面（6n 客户热力图 + 6l/6l2）** | 241.7s（61%） | 中（新建 3 张销售员维度 gold 预聚表：sales×customer×YTD、sales×cat、sales×customer×month） | 6n 改 1 次 groupby；cust_yoy/cust_item_decline 改预聚 dict | 中 | 中（Top33 客户口径、利润=金额-成本 vs profit_clip_sum 需对拍） | 收益最大（≈232s）；④a 头号目标 |
| P1 | **E面（7a/7b/7d + e_decomp）** | 48.7s（12%） | 中（层级×月 需 join 客户层级；销售员×月×客户 需新表） | silver_customer_monthly（+客户层级 join）覆盖 7a/7b；silver_customer_x_product 覆盖首次导入；新表或 groupby 覆盖 7d 异动 | 中 | 中（7d 异动逐月逐销售员逐客户，需精确等价） | 第二收益（≈45s） |
| P2 | **加载（Excel 直读→silver_cleaned_rows）** | 47.7s（12%） | 低（13 列全在 silver，列级缺口 0） | `rex = pd.read_csv(silver_cleaned_rows, usecols=<映射后13列>)` + 列名映射 + 类型转换 | 小 | **高（口径风险：负数量过滤/钳制 vs raw，须逐面 golden-diff 对拍）** | 全局收益（所有面都受益）；建议作为 D/E 迁移后的统一底座，先做 Raw=Silver 全字段对拍 |
| P3 | **A面（趋势/分层/散点/饼图/列表）** | 27.5s（7%） | 低-中（层级×月、客户×月 需预聚） | TREND/TREND_TIERS/KAA_REV 用 silver_customer_monthly（+层级 join）；PIE/SCAT 用 silver_cleaned_rows groupby | 小 | 低 | 结构简单，迁移快 |
| P4 | **B面（ctr/cid_fin/call）** | 27.4s（7%） | 低（客户×月 预聚已就绪） | B_TREND/cid_fin 用 silver_customer_monthly；cid_12m_data/prank 用 silver_customer_x_product；new_detail 已用 silver | 小 | 低 | 现成预聚表基本覆盖 |
| P5 | **F面（H1/产品/品类对比）** | 27.5s（7%） | 低-中（品类×月 需新表） | _prod_trend/_prod_h1 用 silver_product_monthly；f_cat_h1 用新 `dashboard_cat_monthly` 或 groupby；h1_kaaa 用 silver_customer_monthly+层级 | 中 | 中（半年区间、6000 阈值、ASP 口径） | 依赖 P2 底座 |
| 0 | **C面** | 27.5s 中报告部分 ~1s | 0（已只读 report/gold） | 不动；把 report sheet 结构纳入接口契约 | 0 | 低 | 无需迁移 |

**落地建议**：
1. 先做 **Raw=Silver 全字段对拍**（发货日期/金额/利润/数量/客户类别/客户编号/客户订单号/产品线/品类/存货/产品线新/新品/实际业务员 13 列的行数与合计），确认 silver 与 raw 在当前数据下逐列一致，消除 P2 口径风险——这是整个④a 的前置门禁。
2. 按 P0(P1)→P3/P4→P5→P2 实施（先把 D/E 大头用 groupby 换掉，再把 rex 底座换成 silver），每面迁移后 `golden_diff` 对拍（数值容差 1e-6、计数严格）。
3. 新增 gold 预聚表建议 4 张：`dashboard_sales_customer_ytd`、`dashboard_sales_cat_ytd`、`dashboard_sales_customer_monthly`、`dashboard_cat_monthly`；写入时同步纳入批次③指纹的 `outputs` 键（自动覆盖，无需改契约）。
4. 迁移完成标准：`generate_dashboard.py` 不再出现 `pd.read_excel` / `data/*.xlsx`，看板全算耗时目标 <60s（加载与六面聚合全部落到预聚表/groupby）。


