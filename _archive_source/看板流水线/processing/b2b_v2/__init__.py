"""
src/ — 高级分析模块包。

各子包按领域组织，独立可导入：
- journey:      客户旅程阶段分类（Task 1）
- behavior:     采购行为模式 + 波动性指标（Task 4, 5）
- profitability: 估算真实利润（Task 6）
- actions:      行动建议优先级排序（Task 2）
- anomaly:      异常检测（Task 3）

所有模块遵守：
- 阈值从 config/settings.py 读取，无硬编码
- 函数有完整 docstring
- 数据缺失时 graceful degradation，不阻断
"""
