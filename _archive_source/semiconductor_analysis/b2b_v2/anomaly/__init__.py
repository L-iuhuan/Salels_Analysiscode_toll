"""
异常检测模块。

包含:
  - inventory.py: 库龄数据加载、BOM拆分、估算降级、客户维度映射
  - rules.py: 6个规则检测器 (采购中断/营收断崖/价格异常/集中度风险/库存呆滞/长库龄积压)
  - isolation_forest.py: Isolation Forest 兜底检测
  - run.py: 汇总入口
"""
