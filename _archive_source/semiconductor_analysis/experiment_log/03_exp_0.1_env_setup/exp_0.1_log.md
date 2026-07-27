# 实验 0.1: 环境安装与数据版本锁定

## 元信息
- 日期: 2026-06-12
- Python版本: 3.12.10
- 前置实验: 0.0, 0.0.5 ✅

## 实验假设
statsforecast, hierarchicalforecast, tsfresh 可成功安装；数据文件和配置可被锁定为可复现版本。

## 执行过程

### 步骤1: Python库安装
- 命令: `pip install statsforecast hierarchicalforecast tsfresh`
- 耗时: ~2min
- 安装结果:
  - statsforecast 2.0.3 ✅
  - hierarchicalforecast 1.5.1 ✅
  - tsfresh 0.21.2 ✅
  - 关联依赖: coreforecast 0.0.17, utilsforecast 0.2.16, fugue 0.9.7, triad 1.0.2, stumpy 1.14.1
- 副作用: pandas 3.0.2 → 2.3.3 (降级, statsforecast依赖约束), scipy 1.17.1 → 1.15.3

### 步骤2: 数据文件确认
- 原始数据: `data/财务分析-5月（6.3）.xlsx` — 216MB, 67列
- 配置文件路径从E:盘更新为本地C:盘路径

### 步骤3: 配置锁定
- 原配置: `quarterly_forecast_package/forecast_config.default.json`
- 锁定版: `output/test/forecast_config.locked.json`
- 关键变更: `data_path` 从 `E:/...` → `C:/Users/45091/Desktop/工作文件/semiconductor_analysis/data/...`

### 步骤4: 种子固定
- `np.random.seed(42)` + `random.seed(42)` 在所有实验脚本中固定

## 安装验证

| 库 | 版本 | 用途 | 状态 |
|---|---|---|---|
| statsforecast | 2.0.3 | 间歇性方法(Croston/TSB/ADIDA), SES等 | ✅ |
| hierarchicalforecast | 1.5.1 | 分层调和(MinTrace/BottomUp/TopDown) | ✅ |
| tsfresh | 0.21.2 | 时序特征提取(Phase 2探索性) | ✅ |
| pandas | 2.3.3 | 数据处理 | ✅ |
| numpy | 2.4.4 | 数值计算 | ✅ |
| scikit-learn | 1.8.0 | Ridge回归, 分类器(Phase 2/3) | ✅ |

## 外部依赖Fallback评估

| 库 | 失败替代方案 | 风险 |
|---|---|---|
| statsforecast | 自实现Naive/MA/指数平滑/Holt简化版 | 间歇性方法(Croston/TSB)需自行实现 |
| hierarchicalforecast | 手工Bottom-up/Top-down调和 | 实现复杂度中等 |
| tsfresh | 直接跳过探索性特征实验 | 不影响主流程 |

## 成功标准判定

| 标准 | 预期 | 实际 | 判定 |
|---|---|---|---|
| 三库成功安装 | pip list显示已安装 | 3/3安装成功 | ✅ |

## 结论

环境就绪。pandas降级不影响现有预测脚本（脚本使用基础DataFrame操作）。Fallback路径已准备但暂不需要。

## 输出文件
- `output/test/forecast_config.locked.json`: 更新本地路径的锁定配置
