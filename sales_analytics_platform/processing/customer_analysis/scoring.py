"""
客户评价体系评分模块（v2.0）。

P2-E: 实现委托给 analysis.scoring，保持 backward compat。

用法（向后兼容）:
    from customer_analysis.scoring import calc_composite_scores, calc_customer_tier
"""

from analysis.scoring import (
    calc_composite_scores,
    calc_customer_tier,
    _minmax_norm,
    _tier_from_score,
    _score_dimension,
    _map_lifecycle_to_score,
    _map_stability_level_to_score,
    _map_tier_to_score,
    _classify_dual_axis,
)
