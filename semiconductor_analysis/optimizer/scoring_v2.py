"""
Optimized factor scoring functions (v2).

Fixes identified from empirical analysis:
1. F4 (decay): data-driven score matrix replacing reversed logic
2. F5 (self-health): fix top inversion (90 < 70 in predictive power)
3. F1f (slope): merge redundant 20/50 buckets (identical decline rate)
4. c6: bucket-based mapping for non-linear relationship
"""
import pandas as pd
import numpy as np

from optimizer.config import (
    DECAY_SCORE_MATRIX,
    CONSECUTIVE_BONUS_PER_MONTH,
    CONSECUTIVE_BONUS_MAX,
    F1F_BUCKETS,
    F5_BUCKETS,
    C6_BUCKETS,
)


# ═══════════════════════════════════════════════════════════════════
# F1f: 毛利率趋势斜率 v2
# ═══════════════════════════════════════════════════════════════════

def score_slope_v2(slope_ratio, zero_profit=False, slope_insufficient=False):
    """
    F1f v2: Merge redundant 20/50 buckets.

    Empirical decline rates:
        slope >= 0:     13.0%  -> score 10
        -0.008 <= s <0: 15.7%  -> score 50  (was 20+50, merged)
        slope < -0.008: 26.1%  -> score 80

    Returns score in [10, 50, 80] + special cases.
    """
    if zero_profit or slope_insufficient:
        return 80
    if slope_ratio is None or (isinstance(slope_ratio, float) and np.isnan(slope_ratio)):
        return 50

    for lo, hi, score in F1F_BUCKETS:
        if lo < slope_ratio <= hi:
            return score
    return 50  # fallback


# ═══════════════════════════════════════════════════════════════════
# F4: 增速衰减 v2
# ═══════════════════════════════════════════════════════════════════

def _classify_yoy_group(yoy_change):
    """Classify yoy_change into risk-relevant groups."""
    if yoy_change is None or pd.isna(yoy_change):
        return "unknown"
    if yoy_change > 0.5:
        return "high_growth"
    elif yoy_change > 0:
        return "growing"
    elif yoy_change > -0.1:
        return "flat"
    else:
        return "shrinking"


def _classify_decay_group(decay_pp):
    """Classify decay_pp into trend groups."""
    if decay_pp is None or pd.isna(decay_pp):
        return "unknown"
    if decay_pp > 0:
        return "accelerating"    # growth rate accelerating (positive = less decay)
    elif decay_pp >= -10:
        return "stable"          # -10 to 0: mild decay
    else:
        return "decelerating"    # < -10: severe decay


def score_decay_v2(decay_pp, yoy_change, consecutive_months=0):
    """
    F4 v2: Data-driven score matrix.

    Uses DECAY_SCORE_MATRIX from config to map (yoy_change, decay_pp) pairs
    to empirically-calibrated scores. Fixes the 70-point scoring inversion.

    Parameters
    ----------
    decay_pp : float
        Growth decay in percentage points (近3月-近12月增长率).
        Negative = slowing down, Positive = accelerating.
    yoy_change : float
        YoY growth rate (ratio, e.g. 0.5 = +50%).
    consecutive_months : int
        Number of consecutive months of decline (for bonus).

    Returns
    -------
    int : 10-100 risk score
    """
    if pd.isna(decay_pp) or decay_pp is None:
        return 20  # low risk default (no info = no bad news)

    yoy_grp = _classify_yoy_group(yoy_change)
    decay_grp = _classify_decay_group(decay_pp)

    score = DECAY_SCORE_MATRIX.get((yoy_grp, decay_grp), 50)

    # Consecutive decline bonus (capped)
    if consecutive_months and consecutive_months > 0:
        bonus = min(consecutive_months * CONSECUTIVE_BONUS_PER_MONTH,
                    CONSECUTIVE_BONUS_MAX)
        score = min(100, score + bonus)

    return score


# ═══════════════════════════════════════════════════════════════════
# F5: 自比健康度 v2
# ═══════════════════════════════════════════════════════════════════

def score_self_health_v2(health_pct, hist_margin_invalid=False):
    """
    F5 v2: Fix top inversion.

    Empirical decline rates:
        SH >= 70%:  11.3%  -> score 10
        SH 50-70%:  27.1%  -> score 40
        SH 30-50%:  37.0%  -> score 70  (actually HIGHEST risk!)
        SH < 30%:   35.3%  -> score 70  (collapsed from 90)

    Returns score in [10, 40, 70].
    """
    if hist_margin_invalid:
        return 50
    if health_pct is None or pd.isna(health_pct):
        return 50

    for lo, hi, score in F5_BUCKETS:
        if lo < health_pct <= hi:
            return score
    return 50  # fallback


# ═══════════════════════════════════════════════════════════════════
# c6: 大客户订货量变化 v2
# ═══════════════════════════════════════════════════════════════════

def score_c6_v2(c6_raw):
    """
    c6 v2: Bucket-based mapping.

    Empirical decline rates:
        c6 <= -0.5: 45.2% -> score 95 (severe shrink)
        -0.5 < c6 <= -0.2: 21.3% -> score 75 (shrink)
        -0.2 < c6 <= 0: 17.4% -> score 50 (slight drop)
        c6 > 0: ~15% (undifferentiated) -> score 25

    Returns score in [25, 50, 75, 95].
    """
    if c6_raw is None or pd.isna(c6_raw):
        return 0  # zero fill for weight redistribution

    for lo, hi, score in C6_BUCKETS:
        if lo < c6_raw <= hi:
            return score
    return 25  # fallback


# ═══════════════════════════════════════════════════════════════════
# Composite scoring
# ═══════════════════════════════════════════════════════════════════

def compute_composite_v2(row, weights, use_c6=True):
    """
    Compute v2 composite risk score from a single row of data.

    Parameters
    ----------
    row : dict-like with fields:
        slope_ratio, zero_profit, slope_insufficient,
        decay_pp, yoy_change, consecutive_months,
        self_health, no_valid_hist_margin,
        c6_raw (optional)
    weights : dict with keys matching factor names
        e.g. {"F1f": 0.368, "F4": 0.260, "F5": 0.362, "c6": 0.105}
    use_c6 : bool, if True and c6 available, include c6 in scoring

    Returns
    -------
    dict with keys: score_v2, f1f_v2, f4_v2, f5_v2, [c6_v2],
                    f1f_w, f4_w, f5_w, [c6_w]
    """
    # Score each factor
    s1 = score_slope_v2(
        row.get("slope_ratio"),
        zero_profit=bool(row.get("zero_profit", False)),
        slope_insufficient=bool(row.get("slope_insufficient", False)),
    )

    s4 = score_decay_v2(
        row.get("decay_pp"),
        row.get("yoy_change"),
        consecutive_months=int(row.get("consecutive_months", 0)),
    )

    s5 = score_self_health_v2(
        row.get("self_health"),
        hist_margin_invalid=bool(row.get("no_valid_hist_margin", False)),
    )

    # Weight assignment with reliability-based redistribution
    w_f1f = float(weights.get("F1f", 0.368))
    w_f4 = float(weights.get("F4", 0.260))
    w_f5 = float(weights.get("F5", 0.362))

    # Check factor reliability
    slope_reliable = not bool(row.get("zero_profit", False)) and \
                     not bool(row.get("slope_insufficient", False))
    decay_reliable = True  # always available if we have panel data
    sh_reliable = not bool(row.get("no_valid_hist_margin", False))

    # Zero out unreliable factor weights
    w = [w_f1f, w_f4, w_f5]
    reliable = [slope_reliable, decay_reliable, sh_reliable]
    for idx in range(3):
        if not reliable[idx]:
            w[idx] = 0.0

    # c6 handling
    c6_available = bool(row.get("c6_available", 0))
    w_c6 = float(weights.get("c6", 0)) if use_c6 and c6_available else 0.0
    s_c6 = score_c6_v2(row.get("c6_raw")) if c6_available else 0

    if w_c6 > 0:
        w.append(w_c6)
        scores = [s1, s4, s5, s_c6]
    else:
        scores = [s1, s4, s5]

    # Redistribute weights for unavailable factors
    sum_w = sum(w)
    if sum_w > 0:
        w = [wi / sum_w for wi in w]
    else:
        # All unreliable: uniform weights
        w = [1.0 / len(w)] * len(w)

    # Composite score
    total = sum(s * wi for s, wi in zip(scores, w))

    result = {
        "score_v2": round(total, 1),
        "f1f_v2": s1,
        "f4_v2": s4,
        "f5_v2": s5,
    }

    if w_c6 > 0 and c6_available:
        result["c6_v2"] = s_c6
        result["c6_weight_used"] = w[-1]
    else:
        result["c6_v2"] = 0
        result["c6_weight_used"] = 0.0

    result["factor_weights"] = {
        "F1f": w[0],
        "F4": w[1] if len(w) > 1 else 0,
        "F5": w[2] if len(w) > 2 else 0,
    }
    if len(w) > 3:
        result["factor_weights"]["c6"] = w[3]

    return result


def score_panel_v2(df, weights, use_c6=True):
    """
    Score entire DataFrame with v2 scoring functions.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain columns matching compute_composite_v2 expectations.
    weights : dict
        Factor weights.
    use_c6 : bool

    Returns
    -------
    pd.DataFrame with added columns: score_v2, f1f_v2, f4_v2, f5_v2, [c6_v2]
    """
    results = []
    for _, row in df.iterrows():
        r = compute_composite_v2(row.to_dict(), weights, use_c6=use_c6)
        results.append(r)

    result_df = pd.DataFrame(results, index=df.index)
    return pd.concat([df, result_df], axis=1)
