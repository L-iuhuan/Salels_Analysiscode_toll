"""
c6 production mapping function.
Maps c6_raw (-1.0 to 5.0) to 0-100 risk score.
Direction: negative c6 = order shrinkage = higher risk.

Usage:
    from c6_production_mapping import c6_to_score, score_c6_vectorized
"""
import pandas as pd
import numpy as np

# ── Bucket-based mapping ──
# Thresholds derived from c6 distribution analysis
# Negative c6 = order shrinkage = HIGH risk
C6_BUCKETS = [
    (-np.inf, -0.5,  95, "严重萎缩 (qty decline >50%)"),
    (-0.5,    -0.2,  75, "明显萎缩 (qty decline 20-50%)"),
    (-0.2,     0.0,  50, "微跌 (qty decline 0-20%)"),
    ( 0.0,     0.2,  30, "持平 (qty change -20%~0%)"),
    ( 0.2,  np.inf,  10, "增长 (qty increase >20%)"),
]


def c6_to_score(c6_raw, default=0):
    """
    Convert c6_raw to a 0-100 risk score.

    Parameters
    ----------
    c6_raw : float or None
        Raw c6 value (top-5 customer order size change rate).
        Clipped to [-1.0, 5.0] during computation.
    default : int
        Default score when c6 is unavailable (default 0 = zero_fill).

    Returns
    -------
    int : 0-100 risk score
    """
    if pd.isna(c6_raw):
        return default

    for lo, hi, score, _ in C6_BUCKETS:
        if lo < c6_raw <= hi:
            return score
    return 50  # fallback (shouldn't reach here)


def c6_to_score_with_fallback(c6_raw, c6_available, fallback_score=None):
    """
    c6 scoring with fallback strategy:
    - If c6_available=1: use bucket mapping
    - If c6_available=0: return fallback_score (None = NaN = exclude from scoring)

    The fallback strategy determines how missing c6 is handled in the
    composite score (weight redistribution vs zero-fill vs mean-fill).
    """
    if c6_available:
        return c6_to_score(c6_raw)
    return fallback_score


def score_c6_vectorized(df, c6_col='c6_raw', avail_col='c6_available',
                       fallback_strategy='zero_fill'):
    """
    Batch score c6 for a DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain c6_col and avail_col.
    fallback_strategy : str
        'zero_fill' (score=0), 'mean_fill' (score=30), or 'nan' (exclude)
    """
    fallback_map = {'zero_fill': 0, 'mean_fill': 30, 'nan': None}
    default = fallback_map.get(fallback_strategy, 0)

    scores = []
    for _, row in df.iterrows():
        avail = row.get(avail_col, 0)
        if avail:
            scores.append(c6_to_score(row.get(c6_col)))
        else:
            scores.append(default)

    return np.array(scores)
