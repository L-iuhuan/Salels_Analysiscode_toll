-- ================================================================
-- 看板流水线数据模型 · 表结构导出（只要表样，无数据）
-- 源: data_warehouse 快照仓 + output\silver + output\gold
-- 导出: 2026-08-28 | 类型为通用 SQL 写法（SQL Server/MySQL/SQLite 微调即可）
-- ================================================================

-- --------------------------------------------------------------
-- 快照仓 data_warehouse（ERP 原始明文快照）
-- --------------------------------------------------------------

-- 源文件: erp_snapshot.parquet  (行数: 191725)
CREATE TABLE [erp_snapshot] (
    [发货日期] DATETIME NULL,
    [快递单号] VARCHAR(255) NULL,
    [客户订单号] VARCHAR(255) NULL,
    [销售部门] VARCHAR(255) NULL,
    [实际业务员] VARCHAR(255) NULL,
    [代理商/直供名称] VARCHAR(255) NULL,
    [实际终端客户] VARCHAR(255) NULL,
    [终端客户简称] VARCHAR(255) NULL,
    [助理备注] VARCHAR(255) NULL,
    [存货名称] VARCHAR(255) NULL,
    [发货数量] BIGINT NULL,
    [原币含税单价] DOUBLE NULL,
    [出货总金额] DOUBLE NULL,
    [单位成本] DOUBLE NULL,
    [总成本] DOUBLE NULL,
    [RMB 未税金额小计] DOUBLE NULL,
    [利润] DOUBLE NULL,
    [丝印] VARCHAR(255) NULL,
    [批号] VARCHAR(255) NULL,
    [币种] VARCHAR(255) NULL,
    [汇率] DOUBLE NULL,
    [细分市场（新）] VARCHAR(255) NULL,
    [细分市场] VARCHAR(255) NULL,
    [产品线] VARCHAR(255) NULL,
    [型号_产品线（新）] VARCHAR(255) NULL,
    [产品系列] VARCHAR(255) NULL,
    [型号_产品品类] VARCHAR(255) NULL,
    [产品类别] VARCHAR(255) NULL,
    [是否新品] VARCHAR(255) NULL,
    [型号_产品结构名称] VARCHAR(255) NULL,
    [CRM销售] VARCHAR(255) NULL,
    [ERP业务员姓名] VARCHAR(255) NULL,
    [ERP所属公司] VARCHAR(255) NULL,
    [ERP订单号] VARCHAR(255) NULL,
    [发货单号] VARCHAR(255) NULL,
    [未税单价] DOUBLE NULL,
    [客户] VARCHAR(255) NULL,
    [终端名称] VARCHAR(255) NULL,
    [发货地址] VARCHAR(255) NULL,
    [客户存货编码] VARCHAR(255) NULL,
    [表头备注] VARCHAR(255) NULL,
    [月结条件] VARCHAR(255) NULL,
    [lot] VARCHAR(255) NULL,
    [版本] VARCHAR(255) NULL,
    [档位] VARCHAR(255) NULL,
    [行号] DOUBLE NULL,
    [PM] VARCHAR(255) NULL,
    [销售订单子表主键标识] VARCHAR(255) NULL,
    [业务类型] VARCHAR(255) NULL,
    [销售类型编码] BIGINT NULL,
    [销售类型名称] VARCHAR(255) NULL,
    [销售助理] VARCHAR(255) NULL,
    [发运方式编码] DOUBLE NULL,
    [发运方式名称] VARCHAR(255) NULL,
    [利润中心] VARCHAR(255) NULL,
    [发货退货单子表标识] VARCHAR(255) NULL,
    [业务员对应工号] VARCHAR(255) NULL,
    [存货编码] BIGINT NULL,
    [制单人] VARCHAR(255) NULL,
    [型号] BIGINT NULL,
    [终端客户名称] VARCHAR(255) NULL,
    [关联订单明细] DOUBLE NULL,
    [原币税额] DOUBLE NULL,
    [终端客户名称_客户类别] VARCHAR(255) NULL,
    [代理商系统账号] VARCHAR(255) NULL,
    [销售模式] VARCHAR(255) NULL,
    [产品品类（新）] VARCHAR(255) NULL
);

-- 源文件: erp_snapshot.parquet  (行数: 199681)
CREATE TABLE [erp_snapshot] (
    [发货日期] DATETIME NULL,
    [快递单号] VARCHAR(255) NULL,
    [客户订单号] VARCHAR(255) NULL,
    [销售部门] VARCHAR(255) NULL,
    [实际业务员] VARCHAR(255) NULL,
    [代理商/直供名称] VARCHAR(255) NULL,
    [实际终端客户] VARCHAR(255) NULL,
    [终端客户简称] VARCHAR(255) NULL,
    [助理备注] VARCHAR(255) NULL,
    [存货名称] VARCHAR(255) NULL,
    [发货数量] DOUBLE NULL,
    [原币含税单价] DOUBLE NULL,
    [出货总金额] DOUBLE NULL,
    [单位成本] VARCHAR(255) NULL,
    [总成本] DOUBLE NULL,
    [RMB 未税金额小计] DOUBLE NULL,
    [利润] DOUBLE NULL,
    [丝印] VARCHAR(255) NULL,
    [批号] VARCHAR(255) NULL,
    [币种] VARCHAR(255) NULL,
    [汇率] DOUBLE NULL,
    [细分市场（新）] VARCHAR(255) NULL,
    [细分市场] VARCHAR(255) NULL,
    [产品线] VARCHAR(255) NULL,
    [型号_产品线（新）] VARCHAR(255) NULL,
    [产品系列] VARCHAR(255) NULL,
    [型号_产品品类] VARCHAR(255) NULL,
    [产品类别] VARCHAR(255) NULL,
    [是否新品] VARCHAR(255) NULL,
    [型号_产品结构名称] VARCHAR(255) NULL,
    [CRM销售] VARCHAR(255) NULL,
    [ERP业务员姓名] VARCHAR(255) NULL,
    [ERP所属公司] VARCHAR(255) NULL,
    [ERP订单号] VARCHAR(255) NULL,
    [发货单号] VARCHAR(255) NULL,
    [未税单价] DOUBLE NULL,
    [客户] VARCHAR(255) NULL,
    [终端名称] VARCHAR(255) NULL,
    [发货地址] VARCHAR(255) NULL,
    [客户存货编码] VARCHAR(255) NULL,
    [表头备注] VARCHAR(255) NULL,
    [月结条件] VARCHAR(255) NULL,
    [lot] VARCHAR(255) NULL,
    [版本] VARCHAR(255) NULL,
    [档位] VARCHAR(255) NULL,
    [行号] VARCHAR(255) NULL,
    [PM] VARCHAR(255) NULL,
    [销售订单子表主键标识] VARCHAR(255) NULL,
    [业务类型] VARCHAR(255) NULL,
    [销售类型编码] VARCHAR(255) NULL,
    [销售类型名称] VARCHAR(255) NULL,
    [销售助理] VARCHAR(255) NULL,
    [发运方式编码] VARCHAR(255) NULL,
    [发运方式名称] VARCHAR(255) NULL,
    [利润中心] VARCHAR(255) NULL,
    [发货退货单子表标识] VARCHAR(255) NULL,
    [业务员对应工号] VARCHAR(255) NULL,
    [存货编码] VARCHAR(255) NULL,
    [制单人] VARCHAR(255) NULL,
    [型号] VARCHAR(255) NULL,
    [终端客户名称] VARCHAR(255) NULL,
    [原币税额] DOUBLE NULL,
    [终端客户名称_客户类别] VARCHAR(255) NULL,
    [代理商系统账号] VARCHAR(255) NULL,
    [销售模式] VARCHAR(255) NULL,
    [产品品类（新）] VARCHAR(255) NULL,
    [统一后BL类别] VARCHAR(255) NULL,
    [存货+简称组合键] VARCHAR(255) NULL,
    [众数细分市场] VARCHAR(255) NULL,
    [细分市场（新）_1] VARCHAR(255) NULL
);

-- --------------------------------------------------------------
-- Silver 层（清洗后明细与月度聚合，parquet 双写）
-- --------------------------------------------------------------

-- 源文件: silver_cleaned_rows.parquet  (行数: 199681)
CREATE TABLE [silver_cleaned_rows] (
    [发货日期] DATETIME NULL,
    [快递单号] VARCHAR(255) NULL,
    [客户订单号] VARCHAR(255) NULL,
    [销售部门] VARCHAR(255) NULL,
    [实际业务员] VARCHAR(255) NULL,
    [代理商/直供名称] VARCHAR(255) NULL,
    [实际终端客户] VARCHAR(255) NULL,
    [客户编号] VARCHAR(255) NULL,
    [助理备注] VARCHAR(255) NULL,
    [产品品种] VARCHAR(255) NULL,
    [数量] DOUBLE NULL,
    [原币含税单价] DOUBLE NULL,
    [出货总金额] DOUBLE NULL,
    [单位成本] VARCHAR(255) NULL,
    [成本] DOUBLE NULL,
    [金额] DOUBLE NULL,
    [利润] DOUBLE NULL,
    [丝印] VARCHAR(255) NULL,
    [批号] VARCHAR(255) NULL,
    [币种] VARCHAR(255) NULL,
    [汇率] DOUBLE NULL,
    [细分市场（新）] VARCHAR(255) NULL,
    [细分市场] VARCHAR(255) NULL,
    [产品一级分类] VARCHAR(255) NULL,
    [型号_产品线（新）] VARCHAR(255) NULL,
    [产品二级分类] VARCHAR(255) NULL,
    [型号_产品品类] VARCHAR(255) NULL,
    [产品类别] VARCHAR(255) NULL,
    [新品标记] VARCHAR(255) NULL,
    [型号_产品结构名称] VARCHAR(255) NULL,
    [CRM销售] VARCHAR(255) NULL,
    [ERP业务员姓名] VARCHAR(255) NULL,
    [ERP所属公司] VARCHAR(255) NULL,
    [订单编号] VARCHAR(255) NULL,
    [发货单号] VARCHAR(255) NULL,
    [单价] DOUBLE NULL,
    [客户] VARCHAR(255) NULL,
    [终端名称] VARCHAR(255) NULL,
    [发货地址] VARCHAR(255) NULL,
    [客户存货编码] VARCHAR(255) NULL,
    [表头备注] VARCHAR(255) NULL,
    [月结条件] VARCHAR(255) NULL,
    [lot] VARCHAR(255) NULL,
    [版本] VARCHAR(255) NULL,
    [档位] VARCHAR(255) NULL,
    [行号] VARCHAR(255) NULL,
    [PM] VARCHAR(255) NULL,
    [销售订单子表主键标识] VARCHAR(255) NULL,
    [业务类型] VARCHAR(255) NULL,
    [销售类型编码] VARCHAR(255) NULL,
    [销售类型名称] VARCHAR(255) NULL,
    [销售助理] VARCHAR(255) NULL,
    [发运方式编码] VARCHAR(255) NULL,
    [发运方式名称] VARCHAR(255) NULL,
    [利润中心] VARCHAR(255) NULL,
    [发货退货单子表标识] VARCHAR(255) NULL,
    [业务员对应工号] VARCHAR(255) NULL,
    [存货编码] VARCHAR(255) NULL,
    [制单人] VARCHAR(255) NULL,
    [型号] VARCHAR(255) NULL,
    [终端客户名称] VARCHAR(255) NULL,
    [原币税额] DOUBLE NULL,
    [客户类别] VARCHAR(255) NULL,
    [代理商系统账号] VARCHAR(255) NULL,
    [销售模式] VARCHAR(255) NULL,
    [产品品类] VARCHAR(255) NULL,
    [统一后BL类别] VARCHAR(255) NULL,
    [存货+简称组合键] VARCHAR(255) NULL,
    [众数细分市场] VARCHAR(255) NULL,
    [细分市场（新）_1] VARCHAR(255) NULL,
    [渠道类型] VARCHAR(255) NULL,
    [客户等级] VARCHAR(255) NULL,
    [_毛利率] DOUBLE NULL,
    [_利润_裁剪] DOUBLE NULL
);

-- 源文件: silver_customer_x_product.parquet  (行数: 63815)
CREATE TABLE [silver_customer_x_product] (
    [_月] BIGINT NULL,
    [客户编号] VARCHAR(255) NULL,
    [产品品种] VARCHAR(255) NULL,
    [qty_sum] DOUBLE NULL,
    [rev_sum] DOUBLE NULL,
    [profit_clip_sum] DOUBLE NULL,
    [毛利率%] DOUBLE NULL,
    [产品一级分类] VARCHAR(255) NULL,
    [型号_产品品类] VARCHAR(255) NULL,
    [型号_产品线（新）] VARCHAR(255) NULL,
    [产品品类] VARCHAR(255) NULL
);

-- --------------------------------------------------------------
-- Gold 层（汇总指标，可导入 BI，CSV）
-- --------------------------------------------------------------

-- 源文件: KA_AA月度雷达.csv  (行数: 1108)
CREATE TABLE [KA_AA月度雷达] (
    [客户编号] VARCHAR(255) NULL,
    [月份] VARCHAR(255) NULL,
    [客户层级] VARCHAR(255) NULL,
    [客户等级] VARCHAR(255) NULL,
    [业务负责人] VARCHAR(255) NULL,
    [综合价值层级] VARCHAR(255) NULL,
    [策略名称] DOUBLE NULL,
    [月收入] DOUBLE NULL,
    [月毛利] DOUBLE NULL,
    [月数量] DOUBLE NULL,
    [月毛利率%] DOUBLE NULL,
    [月ASP] DOUBLE NULL,
    [月环比%] DOUBLE NULL,
    [月同比%] DOUBLE NULL
);

-- 源文件: SKU生命周期.csv  (行数: 824)
CREATE TABLE [SKU生命周期] (
    [产品品种] VARCHAR(255) NULL,
    [SKU生命周期阶段] VARCHAR(255) NULL
);

-- 源文件: cross_customer_portfolio_health.csv  (行数: 3193)
CREATE TABLE [cross_customer_portfolio_health] (
    [客户编号] VARCHAR(255) NULL,
    [主动收缩] DOUBLE NULL,
    [健康扩张] DOUBLE NULL,
    [利润优化] DOUBLE NULL,
    [夕阳产品] DOUBLE NULL,
    [成长期] DOUBLE NULL,
    [新品观察] DOUBLE NULL,
    [清仓/偶发] DOUBLE NULL,
    [现金牛] DOUBLE NULL,
    [衰退期] DOUBLE NULL,
    [隐性衰退] DOUBLE NULL,
    [预警增长] DOUBLE NULL,
    [总金额] DOUBLE NULL,
    [主动收缩_占比] DOUBLE NULL,
    [健康扩张_占比] DOUBLE NULL,
    [利润优化_占比] DOUBLE NULL,
    [夕阳产品_占比] DOUBLE NULL,
    [成长期_占比] DOUBLE NULL,
    [新品观察_占比] DOUBLE NULL,
    [清仓/偶发_占比] DOUBLE NULL,
    [现金牛_占比] DOUBLE NULL,
    [衰退期_占比] DOUBLE NULL,
    [隐性衰退_占比] DOUBLE NULL,
    [预警增长_占比] DOUBLE NULL,
    [风险品金额占比] DOUBLE NULL
);

-- 源文件: gold_kpi_daily.csv  (行数: 704)
CREATE TABLE [gold_kpi_daily] (
    [日期] DATE NULL,
    [销售额] DOUBLE NULL,
    [数量] DOUBLE NULL,
    [订单数] BIGINT NULL,
    [客户数] BIGINT NULL,
    [品种数] BIGINT NULL,
    [本月累计销售额] DOUBLE NULL,
    [本月累计天数] BIGINT NULL,
    [Top5客户] VARCHAR(255) NULL,
    [Top5产品] VARCHAR(255) NULL
);

-- 源文件: gold_product_portrait.csv  (行数: 806)
CREATE TABLE [gold_product_portrait] (
    [产品名称] VARCHAR(255) NULL,
    [所属参照组] VARCHAR(255) NULL,
    [帕累托分类] VARCHAR(255) NULL,
    [最新数据月份] VARCHAR(255) NULL,
    [日历月龄] BIGINT NULL,
    [活跃月数] BIGINT NULL,
    [首次6K日期] DATE NULL,
    [首次6K用时(月)] DOUBLE NULL,
    [是否已达6K] VARCHAR(255) NULL,
    [当前画像] VARCHAR(255) NULL,
    [管理层摘要] VARCHAR(255) NULL,
    [销量动能] VARCHAR(255) NULL,
    [盈利健康] VARCHAR(255) NULL,
    [近12月销量] DOUBLE NULL,
    [前12月销量] DOUBLE NULL,
    [连续下降月数] BIGINT NULL,
    [近12月增长率%] DOUBLE NULL,
    [前12月增长率%] DOUBLE NULL,
    [增速方向] VARCHAR(255) NULL,
    [增速变化(pp)] DOUBLE NULL,
    [增速衰减(pp)] DOUBLE NULL,
    [低量品标记] VARCHAR(255) NULL,
    [近12月销售额] DOUBLE NULL,
    [前12月销售额] DOUBLE NULL,
    [营收增长率%] DOUBLE NULL,
    [营收-毛利综合判断] VARCHAR(255) NULL,
    [当月毛利率%] DOUBLE NULL,
    [近12月毛利率%] DOUBLE NULL,
    [前12月毛利率%] DOUBLE NULL,
    [毛利率同比变化(pp)] DOUBLE NULL,
    [历史参照毛利率%] DOUBLE NULL,
    [长期参照毛利率%] DOUBLE NULL,
    [自比健康度%] DOUBLE NULL,
    [他比健康度(pp)] DOUBLE NULL,
    [参照组加权均值%] DOUBLE NULL,
    [参照组均值来源] VARCHAR(255) NULL,
    [公司加权均值%] DOUBLE NULL,
    [vs公司均值(pp)] DOUBLE NULL,
    [毛利率趋势斜率%/月] DOUBLE NULL,
    [斜率等级] VARCHAR(255) NULL,
    [ASP趋势%/月] DOUBLE NULL,
    [ASP趋势方向] VARCHAR(255) NULL,
    [ASP-毛利率联合诊断] VARCHAR(255) NULL,
    [客户集中度-前1大%] DOUBLE NULL,
    [客户集中度-前3大%] DOUBLE NULL,
    [订货波动性CV] DOUBLE NULL,
    [近3月月均订单数] DOUBLE NULL,
    [订单频次变化%] DOUBLE NULL,
    [采购意愿] VARCHAR(255) NULL,
    [价格弹性系数] DOUBLE NULL,
    [价格敏感度] VARCHAR(255) NULL,
    [综合评分] DOUBLE NULL,
    [综合风险等级] VARCHAR(255) NULL,
    [风险主导因子] VARCHAR(255) NULL,
    [毛利率斜率得分] DOUBLE NULL,
    [增速衰减得分] DOUBLE NULL,
    [自比健康度得分] DOUBLE NULL,
    [订货量变化得分] VARCHAR(255) NULL,
    [通用策略建议] VARCHAR(255) NULL,
    [特情说明] VARCHAR(255) NULL,
    [数据质量标记] VARCHAR(255) NULL
);

-- 源文件: gold_product_portrait_history.csv  (行数: 806)
CREATE TABLE [gold_product_portrait_history] (
    [产品名称] VARCHAR(255) NULL,
    [当前画像_t-1] VARCHAR(255) NULL,
    [综合评分_t-1] DOUBLE NULL,
    [综合风险等级_t-1] VARCHAR(255) NULL,
    [近12月毛利率%_t-1] DOUBLE NULL,
    [近12月增长率%_t-1] DOUBLE NULL,
    [近12月销量_t-1] DOUBLE NULL,
    [当前画像_t-2] VARCHAR(255) NULL,
    [综合评分_t-2] DOUBLE NULL,
    [综合风险等级_t-2] VARCHAR(255) NULL,
    [近12月毛利率%_t-2] DOUBLE NULL,
    [近12月增长率%_t-2] DOUBLE NULL,
    [近12月销量_t-2] DOUBLE NULL,
    [当前画像_t-3] VARCHAR(255) NULL,
    [综合评分_t-3] DOUBLE NULL,
    [综合风险等级_t-3] VARCHAR(255) NULL,
    [近12月毛利率%_t-3] DOUBLE NULL,
    [近12月增长率%_t-3] DOUBLE NULL,
    [近12月销量_t-3] DOUBLE NULL,
    [当前画像_t-4] VARCHAR(255) NULL,
    [综合评分_t-4] DOUBLE NULL,
    [综合风险等级_t-4] VARCHAR(255) NULL,
    [近12月毛利率%_t-4] DOUBLE NULL,
    [近12月增长率%_t-4] DOUBLE NULL,
    [近12月销量_t-4] DOUBLE NULL,
    [当前画像_t-5] VARCHAR(255) NULL,
    [综合评分_t-5] DOUBLE NULL,
    [综合风险等级_t-5] VARCHAR(255) NULL,
    [近12月毛利率%_t-5] DOUBLE NULL,
    [近12月增长率%_t-5] DOUBLE NULL,
    [近12月销量_t-5] DOUBLE NULL,
    [当前画像_t-6] VARCHAR(255) NULL,
    [综合评分_t-6] DOUBLE NULL,
    [综合风险等级_t-6] VARCHAR(255) NULL,
    [近12月毛利率%_t-6] DOUBLE NULL,
    [近12月增长率%_t-6] DOUBLE NULL,
    [近12月销量_t-6] DOUBLE NULL,
    [当前画像_t-7] VARCHAR(255) NULL,
    [综合评分_t-7] DOUBLE NULL,
    [综合风险等级_t-7] VARCHAR(255) NULL,
    [近12月毛利率%_t-7] DOUBLE NULL,
    [近12月增长率%_t-7] DOUBLE NULL,
    [近12月销量_t-7] DOUBLE NULL,
    [当前画像_t-8] VARCHAR(255) NULL,
    [综合评分_t-8] DOUBLE NULL,
    [综合风险等级_t-8] VARCHAR(255) NULL,
    [近12月毛利率%_t-8] DOUBLE NULL,
    [近12月增长率%_t-8] DOUBLE NULL,
    [近12月销量_t-8] DOUBLE NULL,
    [当前画像_t-9] VARCHAR(255) NULL,
    [综合评分_t-9] DOUBLE NULL,
    [综合风险等级_t-9] VARCHAR(255) NULL,
    [近12月毛利率%_t-9] DOUBLE NULL,
    [近12月增长率%_t-9] DOUBLE NULL,
    [近12月销量_t-9] DOUBLE NULL,
    [当前画像_t-10] VARCHAR(255) NULL,
    [综合评分_t-10] DOUBLE NULL,
    [综合风险等级_t-10] VARCHAR(255) NULL,
    [近12月毛利率%_t-10] DOUBLE NULL,
    [近12月增长率%_t-10] DOUBLE NULL,
    [近12月销量_t-10] DOUBLE NULL,
    [当前画像_t-11] VARCHAR(255) NULL,
    [综合评分_t-11] DOUBLE NULL,
    [综合风险等级_t-11] VARCHAR(255) NULL,
    [近12月毛利率%_t-11] DOUBLE NULL,
    [近12月增长率%_t-11] DOUBLE NULL,
    [近12月销量_t-11] DOUBLE NULL,
    [当前画像_t-12] VARCHAR(255) NULL,
    [综合评分_t-12] DOUBLE NULL,
    [综合风险等级_t-12] VARCHAR(255) NULL,
    [近12月毛利率%_t-12] DOUBLE NULL,
    [近12月增长率%_t-12] DOUBLE NULL,
    [近12月销量_t-12] DOUBLE NULL
);

-- 源文件: 业务员定价偏离.csv  (行数: 34)
CREATE TABLE [业务员定价偏离] (
    [业务负责人] VARCHAR(255) NULL,
    [所属区域] DOUBLE NULL,
    [总交易笔数] BIGINT NULL,
    [KA合理低价值] BIGINT NULL,
    [MM异常低价数] BIGINT NULL,
    [异常低价占比%] DOUBLE NULL,
    [偏高笔数] BIGINT NULL,
    [偏低关注笔数] BIGINT NULL,
    [客户数] BIGINT NULL,
    [总营收] DOUBLE NULL,
    [定价倾向] VARCHAR(255) NULL,
    [异常低价客户Top5] VARCHAR(255) NULL,
    [集中品类] VARCHAR(255) NULL
);

-- 源文件: 交叉销售建议.csv  (行数: 3196)
CREATE TABLE [交叉销售建议] (
    [客户编号] VARCHAR(255) NULL,
    [推荐品种数] BIGINT NULL,
    [推荐品种] VARCHAR(255) NULL,
    [推荐理由] VARCHAR(255) NULL,
    [客户等级] VARCHAR(255) NULL
);

-- 源文件: 产品关联分析.csv  (行数: 28)
CREATE TABLE [产品关联分析] (
    [产品A] VARCHAR(255) NULL,
    [产品B] VARCHAR(255) NULL,
    [支持度] DOUBLE NULL,
    [置信度(A->B)] DOUBLE NULL,
    [提升度(A->B)] DOUBLE NULL,
    [杠杆率(A->B)] DOUBLE NULL,
    [确信度(A->B)] DOUBLE NULL,
    [共现客户月数] BIGINT NULL
);

-- 源文件: 产品研发建议.csv  (行数: 668)
CREATE TABLE [产品研发建议] (
    [产品名称] VARCHAR(255) NULL,
    [近6月月均销量] DOUBLE NULL,
    [近6月月均收入] DOUBLE NULL,
    [近6月毛利率%] DOUBLE NULL,
    [销量同比%] DOUBLE NULL,
    [高质量客户渗透率%] DOUBLE NULL,
    [高质量客户数] BIGINT NULL,
    [客户数] BIGINT NULL,
    [HPI指数] DOUBLE NULL,
    [需求刚性等级] VARCHAR(255) NULL,
    [销量CV] DOUBLE NULL,
    [ASP] DOUBLE NULL,
    [研发建议] VARCHAR(255) NULL,
    [建议理由] VARCHAR(255) NULL
);

-- 源文件: 产品线迁移.csv  (行数: 10431)
CREATE TABLE [产品线迁移] (
    [客户编号] VARCHAR(255) NULL,
    [期间] VARCHAR(255) NULL,
    [产品线] VARCHAR(255) NULL,
    [产品线收入] DOUBLE NULL,
    [产品线占比] DOUBLE NULL,
    [产品线占比变化] DOUBLE NULL,
    [产品线排名] BIGINT NULL,
    [排名变化] DOUBLE NULL,
    [客户等级] VARCHAR(255) NULL
);

-- 源文件: 价格离散度.csv  (行数: 824)
CREATE TABLE [价格离散度] (
    [产品名称] VARCHAR(255) NULL,
    [客户月记录数] BIGINT NULL,
    [平均价] DOUBLE NULL,
    [标准差] DOUBLE NULL,
    [中位价] DOUBLE NULL,
    [最低价] DOUBLE NULL,
    [最高价] DOUBLE NULL,
    [P25] DOUBLE NULL,
    [P75] DOUBLE NULL,
    [变异系数(CV)] DOUBLE NULL,
    [价格混乱标记] BOOLEAN NULL,
    [样本量标记] VARCHAR(255) NULL
);

-- 源文件: 品类接受度.csv  (行数: 3194)
CREATE TABLE [品类接受度] (
    [客户编号] VARCHAR(255) NULL,
    [主导品类] VARCHAR(255) NULL,
    [主导品类占比] DOUBLE NULL,
    [品类机会标签] VARCHAR(255) NULL,
    [客户等级] VARCHAR(255) NULL
);

-- 源文件: 品类擅长.csv  (行数: 284)
CREATE TABLE [品类擅长] (
    [业务负责人] VARCHAR(255) NULL,
    [产品线] VARCHAR(255) NULL,
    [利润质量分] DOUBLE NULL,
    [增长趋势分] DOUBLE NULL,
    [新品推动分] BIGINT NULL,
    [定价能力分] DOUBLE NULL,
    [交叉销售分] DOUBLE NULL,
    [综合能力分] DOUBLE NULL,
    [擅长类型] VARCHAR(255) NULL,
    [置信度] BIGINT NULL,
    [擅长趋势] VARCHAR(255) NULL,
    [品类收入] DOUBLE NULL,
    [品类毛利率] DOUBLE NULL,
    [客户数] BIGINT NULL
);

-- 源文件: 定价合理性分析.csv  (行数: 50)
CREATE TABLE [定价合理性分析] (
    [客户编号] VARCHAR(255) NULL,
    [产品品种] VARCHAR(255) NULL,
    [渠道类型] VARCHAR(255) NULL,
    [单价] DOUBLE NULL,
    [毛利率%] DOUBLE NULL,
    [产品P15单价] DOUBLE NULL,
    [产品P50单价] DOUBLE NULL,
    [价格偏离P50%] DOUBLE NULL,
    [体量分] BIGINT NULL,
    [采购集中度百分位] DOUBLE NULL,
    [战略合作分] DOUBLE NULL,
    [定价合理性分] DOUBLE NULL,
    [异常低价标记] VARCHAR(255) NULL,
    [归因分析] VARCHAR(255) NULL,
    [客户层级] VARCHAR(255) NULL,
    [帕累托利润分级] VARCHAR(255) NULL,
    [业务负责人] VARCHAR(255) NULL,
    [最高价客户] VARCHAR(255) NULL,
    [最高单价] DOUBLE NULL,
    [产品客户数] BIGINT NULL
);

-- 源文件: 客户产品桥接.csv  (行数: 64407)
CREATE TABLE [客户产品桥接] (
    [_月] VARCHAR(255) NULL,
    [客户编号] VARCHAR(255) NULL,
    [产品品种] VARCHAR(255) NULL,
    [qty_sum] DOUBLE NULL,
    [rev_sum] DOUBLE NULL,
    [profit_clip_sum] DOUBLE NULL,
    [毛利率%] DOUBLE NULL,
    [产品一级分类] VARCHAR(255) NULL,
    [型号_产品品类] VARCHAR(255) NULL,
    [型号_产品线（新）] VARCHAR(255) NULL,
    [产品品类] VARCHAR(255) NULL,
    [_ym] VARCHAR(255) NULL,
    [当前画像] VARCHAR(255) NULL,
    [管理层摘要] VARCHAR(255) NULL,
    [综合评分] DOUBLE NULL,
    [综合风险等级] VARCHAR(255) NULL,
    [帕累托分类] VARCHAR(255) NULL
);

-- 源文件: 客户全景.csv  (行数: 17161)
CREATE TABLE [客户全景] (
    [客户名称] VARCHAR(255) NULL,
    [业务负责人] VARCHAR(255) NULL,
    [渠道类型] VARCHAR(255) NULL,
    [客户层级] VARCHAR(255) NULL,
    [活跃状态] VARCHAR(255) NULL,
    [综合价值层级] VARCHAR(255) NULL,
    [双轴分类] VARCHAR(255) NULL,
    [增长潜力] VARCHAR(255) NULL,
    [风险评级] VARCHAR(255) NULL,
    [客户生命周期] VARCHAR(255) NULL,
    [利润率情况] VARCHAR(255) NULL,
    [主要SKU阶段] VARCHAR(255) NULL,
    [利润贡献等级] VARCHAR(255) NULL,
    [近12月收入] DOUBLE NULL,
    [前12月收入] DOUBLE NULL,
    [收入增长率] DOUBLE NULL,
    [YoY同比增速] DOUBLE NULL,
    [连续增长月数] BIGINT NULL,
    [连续下滑月数] BIGINT NULL,
    [近12月毛利] DOUBLE NULL,
    [近12月毛利率] DOUBLE NULL,
    [毛利率跌幅%] DOUBLE NULL,
    [估算真实利润] DOUBLE NULL,
    [估算真实利润率] DOUBLE NULL,
    [品种总数] BIGINT NULL,
    [在采品种数] BIGINT NULL,
    [实际品类数] BIGINT NULL,
    [产品线数] BIGINT NULL,
    [主导产品线] VARCHAR(255) NULL,
    [主导产品线占比] DOUBLE NULL,
    [品种集中度Top3] DOUBLE NULL,
    [Top5集中度] DOUBLE NULL,
    [强依赖标记] BOOLEAN NULL,
    [品类机会标签] VARCHAR(255) NULL,
    [主导品类] VARCHAR(255) NULL,
    [主导品类占比] DOUBLE NULL,
    [ASP_加权] DOUBLE NULL,
    [ASP_跌幅%] DOUBLE NULL,
    [低价品种收入占比] DOUBLE NULL,
    [中价品种收入占比] DOUBLE NULL,
    [高价品种收入占比] DOUBLE NULL,
    [近12月数量] DOUBLE NULL,
    [订单数] BIGINT NULL,
    [订单处理成本] DOUBLE NULL,
    [订单处理成本率] DOUBLE NULL,
    [常规平均采购间隔] DOUBLE NULL,
    [距上次采购天数] BIGINT NULL,
    [采购中断预警] BOOLEAN NULL,
    [零采购月占比] DOUBLE NULL,
    [收入CV] DOUBLE NULL,
    [最大单月跌幅] DOUBLE NULL,
    [趋势R²] DOUBLE NULL,
    [增长动量] DOUBLE NULL,
    [近6月交易额环比增长率] DOUBLE NULL,
    [策略详细建议] TEXT NULL,
    [策略触发原因] VARCHAR(255) NULL,
    [异常告警汇总] VARCHAR(255) NULL,
    [价值贡献分] DOUBLE NULL,
    [增长动能分] DOUBLE NULL,
    [稳定关系分] DOUBLE NULL,
    [战略潜力分] DOUBLE NULL,
    [效率运营分] DOUBLE NULL,
    [综合价值分] DOUBLE NULL,
    [新品采购占比] DOUBLE NULL,
    [是否采购新品] BOOLEAN NULL,
    [新品采购额] DOUBLE NULL,
    [新品品种数] BIGINT NULL,
    [R_得分] BIGINT NULL,
    [F_得分] BIGINT NULL,
    [M_得分] BIGINT NULL,
    [P_得分] BIGINT NULL,
    [RFMπ_综合分] DOUBLE NULL,
    [客户等级] VARCHAR(255) NULL,
    [产品线HHI] DOUBLE NULL,
    [总采购额] DOUBLE NULL,
    [新品渗透机会] DOUBLE NULL,
    [品种流失金额占比] DOUBLE NULL,
    [近半年营收跌幅] DOUBLE NULL,
    [阶段持续月数] BIGINT NULL,
    [阶段转换次数] BIGINT NULL,
    [首次交易日期] VARCHAR(255) NULL,
    [近12月交易额CV] DOUBLE NULL,
    [预警增长_金额] DOUBLE NULL,
    [隐性衰退_金额] DOUBLE NULL,
    [衰退期_金额] DOUBLE NULL,
    [衰退风险品金额占比] DOUBLE NULL,
    [客户编号] VARCHAR(255) NULL,
    [帕累托利润分级] VARCHAR(255) NULL,
    [机会评级] VARCHAR(255) NULL,
    [利润等级] VARCHAR(255) NULL
);

-- 源文件: 客户月度趋势.csv  (行数: 21858)
CREATE TABLE [客户月度趋势] (
    [客户编号] VARCHAR(255) NULL,
    [月份] VARCHAR(255) NULL,
    [月收入] DOUBLE NULL,
    [月毛利] DOUBLE NULL,
    [月数量] BIGINT NULL,
    [月订单数] BIGINT NULL,
    [MA3] DOUBLE NULL,
    [MA6] DOUBLE NULL,
    [月环比%] DOUBLE NULL,
    [月同比%] DOUBLE NULL,
    [收入斜率] DOUBLE NULL,
    [趋势方向] VARCHAR(255) NULL,
    [客户等级] VARCHAR(255) NULL
);

-- 源文件: 客户组合健康度.csv  (行数: 3196)
CREATE TABLE [客户组合健康度] (
    [客户编号] VARCHAR(255) NULL,
    [总品种数] BIGINT NULL,
    [总金额] DOUBLE NULL,
    [成长期_金额] DOUBLE NULL,
    [现金牛_金额] DOUBLE NULL,
    [预警增长_金额] DOUBLE NULL,
    [隐性衰退_金额] DOUBLE NULL,
    [衰退期_金额] DOUBLE NULL,
    [新品观察_金额] DOUBLE NULL,
    [衰退风险品金额占比] DOUBLE NULL,
    [客户等级] VARCHAR(255) NULL
);

-- 源文件: 客户预测.csv  (行数: 1989)
CREATE TABLE [客户预测] (
    [客户编号] VARCHAR(255) NULL,
    [预测月份] VARCHAR(255) NULL,
    [预测收入] DOUBLE NULL,
    [预测下限(80%CI)] DOUBLE NULL,
    [预测上限(80%CI)] DOUBLE NULL,
    [预测方向] VARCHAR(255) NULL,
    [模型类型] VARCHAR(255) NULL,
    [AIC] DOUBLE NULL,
    [可信] VARCHAR(255) NULL,
    [客户等级] VARCHAR(255) NULL
);

-- 源文件: 市场细分价格.csv  (行数: 21)
CREATE TABLE [市场细分价格] (
    [细分维度] VARCHAR(255) NULL,
    [维度值] VARCHAR(255) NULL,
    [均价] DOUBLE NULL,
    [价格指数] DOUBLE NULL,
    [客户数] BIGINT NULL,
    [总营收] DOUBLE NULL,
    [交易记录数] BIGINT NULL
);

-- 源文件: 异常日志.csv  (行数: 2872)
CREATE TABLE [异常日志] (
    [客户编号] VARCHAR(255) NULL,
    [异常类型] VARCHAR(255) NULL,
    [异常等级] VARCHAR(255) NULL,
    [异常详情] VARCHAR(255) NULL,
    [客户等级] VARCHAR(255) NULL
);

-- 源文件: 提价机会.csv  (行数: 505)
CREATE TABLE [提价机会] (
    [客户编号] VARCHAR(255) NULL,
    [产品品种] VARCHAR(255) NULL,
    [avg_price] DOUBLE NULL,
    [total_rev] DOUBLE NULL,
    [total_qty] DOUBLE NULL,
    [active_months] BIGINT NULL,
    [中位价] DOUBLE NULL,
    [产品总销量] DOUBLE NULL,
    [客户销量占比] DOUBLE NULL,
    [提价空间] DOUBLE NULL,
    [提价比率] DOUBLE NULL,
    [可提价标记] BOOLEAN NULL,
    [客户等级] VARCHAR(255) NULL
);

-- 源文件: 渠道价格对比.csv  (行数: 35)
CREATE TABLE [渠道价格对比] (
    [产品品种] VARCHAR(255) NULL,
    [代理均价] DOUBLE NULL,
    [直供均价] DOUBLE NULL,
    [代理-直供价差%] DOUBLE NULL,
    [代理客户数] BIGINT NULL,
    [直供客户数] BIGINT NULL,
    [总客户数] BIGINT NULL
);

-- 源文件: 经营周期总览.csv  (行数: 42)
CREATE TABLE [经营周期总览] (
    [期间类型] VARCHAR(255) NULL,
    [期间] VARCHAR(255) NULL,
    [收入] DOUBLE NULL,
    [毛利] DOUBLE NULL,
    [数量] DOUBLE NULL,
    [ASP] DOUBLE NULL,
    [毛利率%] DOUBLE NULL,
    [客户数] BIGINT NULL,
    [产品数] BIGINT NULL,
    [订单数] BIGINT NULL,
    [收入环比%] DOUBLE NULL,
    [收入同比%] DOUBLE NULL,
    [毛利环比%] DOUBLE NULL,
    [毛利同比%] DOUBLE NULL,
    [数量环比%] DOUBLE NULL,
    [数量同比%] DOUBLE NULL,
    [ASP环比%] DOUBLE NULL,
    [ASP同比%] DOUBLE NULL
);

-- 源文件: 负毛利分析.csv  (行数: 3196)
CREATE TABLE [负毛利分析] (
    [客户编号] VARCHAR(255) NULL,
    [总采购额] DOUBLE NULL,
    [总毛利润] DOUBLE NULL,
    [在采品种数] BIGINT NULL,
    [整体毛利率%] DOUBLE NULL,
    [负毛利品种数] BIGINT NULL,
    [负毛利损失总额] DOUBLE NULL,
    [负毛利产品清单] TEXT NULL,
    [负毛利品种占比] DOUBLE NULL,
    [停售可增加利润] DOUBLE NULL,
    [负毛利严重等级] VARCHAR(255) NULL,
    [建议动作] TEXT NULL,
    [客户层级] VARCHAR(255) NULL,
    [客户等级] VARCHAR(255) NULL,
    [综合价值层级] VARCHAR(255) NULL,
    [活跃状态] VARCHAR(255) NULL,
    [业务负责人] VARCHAR(255) NULL,
    [近12月收入] DOUBLE NULL,
    [近12月毛利] DOUBLE NULL
);

-- 源文件: 跨客户价格差异.csv  (行数: 637)
CREATE TABLE [跨客户价格差异] (
    [产品名称] VARCHAR(255) NULL,
    [产品一级分类] VARCHAR(255) NULL,
    [客户数] BIGINT NULL,
    [平均价格] DOUBLE NULL,
    [中位数价格] DOUBLE NULL,
    [P25价格] DOUBLE NULL,
    [P75价格] DOUBLE NULL,
    [价格CV] DOUBLE NULL,
    [最低价客户] VARCHAR(255) NULL,
    [最低价] DOUBLE NULL,
    [最高价客户] VARCHAR(255) NULL,
    [最高价] DOUBLE NULL,
    [最高-最低价差%] DOUBLE NULL,
    [价格差异等级] VARCHAR(255) NULL,
    [最低价客户-业务负责人] VARCHAR(255) NULL,
    [最高价客户-业务负责人] VARCHAR(255) NULL
);

-- 源文件: 量价拆解.csv  (行数: 432)
CREATE TABLE [量价拆解] (
    [期间类型] VARCHAR(255) NULL,
    [期间] VARCHAR(255) NULL,
    [分析维度] VARCHAR(255) NULL,
    [维度值] VARCHAR(255) NULL,
    [本期收入] DOUBLE NULL,
    [基期收入] DOUBLE NULL,
    [收入变化] DOUBLE NULL,
    [收入环比%] DOUBLE NULL,
    [本期数量] DOUBLE NULL,
    [基期数量] DOUBLE NULL,
    [数量效应金额] DOUBLE NULL,
    [本期ASP] DOUBLE NULL,
    [基期ASP] DOUBLE NULL,
    [价格效应金额] DOUBLE NULL,
    [结构效应金额] DOUBLE NULL,
    [量价标签] VARCHAR(255) NULL,
    [毛利率%] DOUBLE NULL
);

-- 源文件: 销售人员周期表现.csv  (行数: 920)
CREATE TABLE [销售人员周期表现] (
    [业务负责人] VARCHAR(255) NULL,
    [月份] VARCHAR(255) NULL,
    [月收入] DOUBLE NULL,
    [月毛利] DOUBLE NULL,
    [月数量] DOUBLE NULL,
    [月ASP] DOUBLE NULL,
    [客户数] BIGINT NULL,
    [订单数] BIGINT NULL,
    [月环比%] DOUBLE NULL,
    [月同比%] DOUBLE NULL
);

-- 源文件: 销售画像.csv  (行数: 34)
CREATE TABLE [销售画像] (
    [业务负责人] VARCHAR(255) NULL,
    [客户总数] BIGINT NULL,
    [总营收] DOUBLE NULL,
    [KA_AA客户数] BIGINT NULL,
    [量级] VARCHAR(255) NULL,
    [绝对贡献力] DOUBLE NULL,
    [客户维系力] DOUBLE NULL,
    [品类拓展力] DOUBLE NULL,
    [定价博弈力] DOUBLE NULL,
    [新客开拓力] DOUBLE NULL,
    [客户激活力] DOUBLE NULL,
    [客户升级力] DOUBLE NULL,
    [产品结构优化力] DOUBLE NULL,
    [组合抗风险力] DOUBLE NULL,
    [综合能力分] DOUBLE NULL,
    [能力等级] VARCHAR(255) NULL,
    [亚组] VARCHAR(255) NULL
);

-- 源文件: 降价策略试算.csv  (行数: 3296)
CREATE TABLE [降价策略试算] (
    [产品品种] VARCHAR(255) NULL,
    [降价幅度] DOUBLE NULL,
    [原价] DOUBLE NULL,
    [新价] DOUBLE NULL,
    [预测增量销量] DOUBLE NULL,
    [预测新营收] DOUBLE NULL,
    [营收变化] DOUBLE NULL,
    [盈亏判断] VARCHAR(255) NULL
);
