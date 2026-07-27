# Dashboard 开发会话总结

## 项目路径
`C:\Users\45091\Desktop\工作文件\semiconductor_analysis\`

## 核心架构

### 数据管道（单管道双用途）
```
Raw Excel (24-26 sheet)
  ↓ run_all.py (修复后)
Silver 层 (3个CSV)
  ├── product_lifecycle/ → 产品生命周期报告 → generate_v4.py → product_lifecycle.html
  └── customer_analysis/ → Gold 层 (32 CSV) → generate_dashboard.py → dashboard_a.html
```

### 数据源切换：总表 → 24-26
- Sheet: `config/settings.py` `DATA_SHEET_NAME = "24-26"`
- 收入列: `RMB 未税金额小计` (未税)
- 利润列: `利润`
- 客户: 3,059 (vs 原来 3,849)
- 产品: 806 (vs 原来 964)

## 已创建的 Dashboard 文件

```
dashboard/
├── generate_dashboard.py   ← V8: 全量 Raw Excel 数据源，零 Silver 依赖
├── template.html           ← 看板 HTML 模板
├── dashboard_a.html        ← 生成的看板文件 (5.3MB)
├── product_lifecycle.html  ← C面产品生命周期
├── data/
│   ├── b_custs.json        ← B面客户数据
│   ├── b_trend.json        ← B面趋势数据
│   └── b_data.js           ← B面 JS 变量
```

## 看板结构 (A/B/C面，标签切换)

### A面 - 总览决策
**顶部 6 KPI 卡片 (6列)**:
- 本年度收入 35,711万 (同比 +30.6%)
- 本年度毛利 12,359万 (毛利率 34.6% · 同比 -0.5pp)
- 本年度成本 23,352万
- 新品渗透率 XX%
- KA+AA YTD收入 14,092万 (39个客户)
- KA+AA YTD毛利 4,196万 (毛利率 29.8%)

**KA YTD 卡片行 (客户列表上方，4卡片)**:
- KA YTD销售额 / KA YTD利润 / KA YTD销量 / KA YTD品种变化

**图表区**:
- 月度柱状图 (成本+毛利堆叠，毛利率折线，双Y轴) — 可多选年份/层级筛选
- K类客户分布饼图
- KA+AA月度收入折线
- KA客户散点图

**客户列表**: YTD口径，收入保留2位小数，红涨绿跌

**产品变迁窗口**: 折叠式客户卡片，红涨绿跌，按净变化排序

### B面 - 客户360
- 左侧: 客户列表 (搜索+筛选+排序)，YTD口径，6列含毛利率/新品%
- 右侧: 采购节律、近12月毛利趋势、评分、价格诊断、品类结构(饼图+Top5)、新品明细(滚动条)、毛利诊断(双层卡片)、策略
- 品类数据来自 `产品品类（新）` 列(24-26 sheet)

### C面 - 产品生命周期
- iframe 嵌入 `product_lifecycle.html` (由 generate_v4.py 生成)

## Pipeline 修改记录

### 1. 清洗关闭 (`shared/data_cleaning.py`)
- `filter_negative_qty()` → 不退负销量行（保留退货）
- `winsorize_margins()` → `_利润_裁剪 = 利润`（不钳制毛利率）

### 2. 空客户编号填充 (`run_all.py`)
- 1,830 行客户编号为空 → fillna("未知客户")
- **这是 547万缺口的根因**

### 3. 日期有效性检查 (`data_cleaning.py`)
- `monthly_aggregate_double_pass` 增加 `pd.to_datetime` + `dropna`

### 4. 列传播 (`run_all.py`)
- 新增 `产品品类` 到桥接表传播列表

### 5. 营收断崖修复 (`b2b_v2/anomaly/rules.py`)
- 原用不存在的 `近3月收入` 字段 → 改用 `收入增长率 + 连续下滑月数`

## 关键设计决策

1. **KPI 数据源**: Raw Excel 直读（零差异）
2. **全量数据源**: V8 全改为 Raw Excel，不再依赖 Silver
3. **颜色规范**: 红涨绿跌（中国市场习惯）
4. **口径统一**: 全部 YTD(2026-01~05)
5. **产品粒度**: 24-26 sheet 只有 `产品线`列，无 `产品品种`列
6. **新品定义**: 本年度标记=是 AND 全量首次交易≥12个月前

## 运行命令

```powershell
# 全量 Pipeline
python run_all.py --force-silver

# 产品生命周期 HTML
python generate_v4.py "output/report/产品生命周期报告_v4.0_XXXX.xlsx" -o dashboard/product_lifecycle.html

# Dashboard 生成
python dashboard/generate_dashboard.py

# 查看看板
# 双击 dashboard/dashboard_a.html
```

## D面 - 销售能力 (2026-06-22 新增)

### 核心逻辑
- **数据源**: Raw Excel `实际业务员`列（index 4）→ YTD聚合，零差异对标A面KPI
- **在职过滤**: YTD(2026-01~05)收入>0 → 26人在职，自动剔除11名离职/无交易人员
- **客户归属**: 按交易行归属（各自算各自的交易额）

### 数据结构
```
generate_dashboard.py [6/6]
  ├── Raw Excel 实际业务员 → 按销售员聚合YTD（收入/毛利/数量/订单/客户数/品种数）
  ├── 同比2025增长
  ├── Gold 销售画像.csv → 9力模型 + 能力等级 + 亚组
  ├── Gold 品类擅长.csv → 每人×产品线擅长Top8
  ├── Gold 销售人员周期表现.csv → 月度趋势（近13月）
  ├── Gold 交叉销售建议.csv → 按客户→销售员汇总
  └── Gold 客户预测.csv → 下月预测汇总
  
→ D_SALES_LIST (26人) + D_SALES_TREND + D_KPI
```

### 前端布局（D面Tab）
- **6 KPI卡片**: 团队营收 / 团队毛利 / 人均营收 / A级占比 / KA+AA覆盖 / 能力均分
- **左侧**: 销售员列表（搜索+等级/亚组筛选+排序，7列含能力分和等级）
- **右侧**: 点击查看详情
  - 九力雷达图（叠加团队均值虚线）
  - 月度业绩趋势（成本+毛利堆叠柱状 + 毛利率折线双Y轴）
  - 品类擅长卡片（Top8，颜色区分利润型/增长型/流量型，含5维子分）
  - 客户组合 & 交叉销售机会
  - 下月业绩预测

### 数据一致性
- D面团队营收 = A面YTD收入 = 35,711万（零差异）
- D面团队毛利 = A面YTD毛利 = 12,359万
- 26名销售员100%匹配Gold画像

## 待开发
- E面: 价格诊断（客户层面，待讨论方案）
- F面: 研发项目投产比 (数据不足)
- G面: 库存存货 (数据不足)
