# 半导体行业销售数据分析系统

产品生命周期分析 + 客户量化评估 + 交叉关联。

## 快速开始

```bash
# 一键运行全部
python run_all.py

# 单独运行
python run_product.py          # 产品生命周期分析
python run_customer.py         # 客户量化分析

# 指定阶段
python run_all.py --stage silver,customer
python run_all.py --skip-product           # 跳过产品分析
python run_all.py --force-silver           # 强制重算Silver层
```

## 系统架构

```
data/*.xlsx ──→ [共享清洗] ──→ Silver层CSV ──→ Gold层CSV ──→ Excel报告
                    │                      ├── 产品快照表(40+指标)
                    │                      ├── 客户全景(60+指标)
                    │                      ├── 价格离散度 / SKU生命周期
                    │                      ├── 提价机会 / 降价策略
                    │                      └── 客户产品桥接 / 组合健康度
                    │
               [Silver层] ← 中间件pickle → [测试诊断]
```

### 数据流

| 层 | 内容 | 存储 |
|----|------|------|
| 源数据 | ERP出货明细(.xlsx) | `data/` |
| Silver | 清洗后行级 + 3张月度聚合 | `output/silver/` (CSV) |
| Gold | 8张分析表 | `output/gold/` (CSV) |
| 报告 | 格式化的多Sheet Excel | `output/report/` |
| 诊断 | 测试中间件+诊断CSV+图表 | `output/test_diag/` |

## 数据要求

- **格式**：Excel文件（单sheet交易明细 + 可选"客户信息表"sheet）
- **必需字段**：客户编号、产品品种、发货数量、金额(RMB未税)、发货日期
- **可选字段**：利润、成本、单价、产品一级/二级分类、是否新品、渠道类型、客户等级
- **时间跨度**：建议 ≥ 24个月

> 如果ERP导出的列名与默认不同，在 `config/settings.py` 的 `ERP_COL_MAP` 中修改。

## 关键文件

| 文件 | 用途 |
|------|------|
| `config/settings.py` | **所有参数集中管理**，无需改主程序 |
| `shared/data_cleaning.py` | 共享清洗 + 双通道月度聚合 |
| `shared/pricing.py` | 价格分析 + 生命周期 + 新品追踪 + 定价建议 |
| `product_lifecycle/profiling.py` | 产品画像引擎（九宫格+5因子风险） |
| `customer_analysis/models.py` | RFM-π评分 + 机会/风险评分 |
| `customer_analysis/run_pipeline.py` | 客户分析管道（Silver→Gold→报告） |
| `run_all.py` | 统一运行入口 |

## 输出报告结构

### 产品报告 (`product_report_*.xlsx`)

| Sheet | 内容 |
|-------|------|
| 产品快照表 | 全量产品画像：九宫格、5因子风险、弹性、预测 |
| 预警清单 | 高风险+预警/衰退/夕阳产品 |
| 画像分布 | 各画像产品数统计 |
| 历史画像追踪 | 12个月滚动画像变迁 |
| 趋势预测汇总 | ETS 3月预测+置信区间 |
| 客户RFM分群 | R/F/M五分位分层 |
| 产品关联分析 | 关联规则(支持度/置信度/提升度) |
| 使用说明 | 指标解释 |

### 客户报告 (`客户分析报告_*.xlsx`)

| Sheet | 内容 |
|-------|------|
| 客户全景 | 60+指标 + RFM-π评分 + 机会/风险评分 |
| 客户产品桥接 | 客户×产品交易明细+产品画像引用 |
| 客户组合健康度 | 各画像产品占比 |
| 价格离散度 | 跨客户价格一致性 |
| SKU生命周期 | 各SKU阶段 |
| 品类接受度 | 品类覆盖情况 |
| 提价机会 | 可提价组合 |
| 降价策略试算 | 4档降价弹性试算 |
| 预警清单 | 高风险客户汇总 |

## 功能状态

所有功能实现状态维护在 **[STATUS.md](STATUS.md)** — 这是单一真相源。

详细设计文档见 `docs/` 目录。

## 许可证

内部使用。
