"""
价格分析函数 — 向后兼容重导出层。

P1-D: 实际实现已搬迁至 analysis/pricing/。
所有现有 from shared.pricing import XXX 路径继续有效。
直接按领域导入：from analysis.pricing.pricing_lifecycle import calc_customer_lifecycle_stage
"""

from analysis.pricing.pricing_trends import *
from analysis.pricing.pricing_bands import *
from analysis.pricing.pricing_customer import *
from analysis.pricing.pricing_lifecycle import *
from analysis.pricing.pricing_insights import *
from analysis.pricing.pricing_actions import *
