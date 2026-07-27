"""
客户分析评分模型。

P2-E: 实现委托给 analysis.rfm_pi，保持 backward compat。

用法（向后兼容）:
    from customer_analysis.models import score_rfm_pi
"""

from analysis.rfm_pi import score_rfm_pi, _normalize_0_100
