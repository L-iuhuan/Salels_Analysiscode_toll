# 实验日志目录

> 多维度分层预测校准测试 — 全链路实验记录

## 目录结构

```
experiment_log/
├── README.md                          ← 本文件
├── master_log.md                      ← 主日志: 全部实验索引和摘要
├── phase_0_baseline/                  ← Phase 0: 基础设施与基线锁定
│   ├── phase_0_gate.md                ← Gate 0 决策记录
│   ├── exp_0.0_trivial_baselines/     ← 平凡基线建立
│   ├── exp_0.0.5_coverage_diagnosis/  ← 产品线覆盖诊断
│   ├── exp_0.1_env_setup/             ← 环境安装与数据锁定
│   ├── exp_0.1.5_method_filter/       ← 方法预筛选
│   ├── exp_0.2_baseline_lock/         ← 基线回测锁定
│   └── exp_0.3_lifecycle_alignment/   ← 生命周期数据对齐
├── phase_1_enhancement/               ← Phase 1: 单一维度增强 (待执行)
├── phase_2_combination/               ← Phase 2: 多维组合与调和 (待执行)
├── phase_3_optimization/              ← Phase 3: 组合优化与动态选择 (待执行)
└── phase_4_validation/                ← Phase 4: 综合验证与交付 (待执行)
```

## 审计追溯

### 入口1: master_log.md
从主日志查看所有实验索引和结论 → 点击日志链接进入单实验详情

### 入口2: 各实验目录
每个实验包含:
- `exp_X.Y_log.md` — 实验日志 (思考过程+结果)
- `output/` — 实验输出数据
- 脚本位于 `output/test/run_X.Y*.py`

### 入口3: 输出数据
所有测试输出: `output/test/` (项目根目录下)

## 实验脚本约定

所有 `run_X.Y.py` 满足:
1. 可独立运行: `python run_X.Y.py`
2. 版本标记: 文件头包含创建日期、实验编号、数据版本
3. 种子固定: `np.random.seed(42)` 在文件顶部
