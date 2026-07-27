"""
Phase 3: Threshold co-calibration search.
"""
import numpy as np
import pandas as pd

from optimizer.metrics import compute_classification_metrics
from optimizer.config import THRESHOLD_SEARCH


def search_thresholds(scores, y_true,
                      low_range=None, mid_range=None, high_range=None):
    """
    Grid search over risk thresholds to find optimal configuration.

    Parameters
    ----------
    scores : array-like, composite risk scores (0-100)
    y_true : array-like, binary labels
    low_range : (min, max, step) or None (use config)
    mid_range : (min, max, step) or None
    high_range : (min, max, step) or None

    Returns
    -------
    pd.DataFrame with all threshold combinations and their metrics,
    sorted by composite score (defined below).
    """
    cfg = THRESHOLD_SEARCH

    l_min, l_max, l_step = low_range or (cfg["low"]["min"],
                                          cfg["low"]["max"],
                                          cfg["low"]["step"])
    m_min, m_max, m_step = mid_range or (cfg["mid"]["min"],
                                          cfg["mid"]["max"],
                                          cfg["mid"]["step"])
    h_min, h_max, h_step = high_range or (cfg["high"]["min"],
                                           cfg["high"]["max"],
                                           cfg["high"]["step"])

    scores = np.array(scores)
    yt = np.array(y_true)

    results = []

    low_values = np.arange(l_min, l_max + l_step, l_step)
    mid_values = np.arange(m_min, m_max + m_step, m_step)
    high_values = np.arange(h_min, h_max + h_step, h_step)

    n_total = len(low_values) * len(mid_values) * len(high_values)
    count = 0

    for low in low_values:
        for mid in mid_values:
            if mid <= low:
                continue
            for high in high_values:
                if high <= mid:
                    continue
                if high - mid < 2:
                    continue  # ensure minimum gap

                count += 1
                thr = (int(low), int(mid), int(high))
                metrics = compute_classification_metrics(yt, scores, thresholds=thr)

                # Composite score for ranking
                # Higher is better: precision + auc + (extreme_decline_rate / 40)
                # Penalized for: too small extreme_pct, non-monotonic
                score = metrics.get("precision", 0) or 0
                score += metrics.get("auc", 0) or 0
                score += min(metrics.get("extreme_decline_rate", 0) / 0.40, 1.0)

                if not metrics.get("monotonic", False):
                    score *= 0.5  # halve for non-monotonic

                # Bonus for reasonable extreme coverage (3-8%)
                ep = metrics.get("extreme_pct", 0) or 0
                if 0.03 <= ep <= 0.08:
                    score += 0.2
                elif ep < 0.01 or ep > 0.15:
                    score *= 0.8

                results.append({
                    "low": int(low),
                    "mid": int(mid),
                    "high": int(high),
                    "composite_score": round(score, 4),
                    "auc": metrics["auc"],
                    "precision": metrics["precision"],
                    "recall": metrics["recall"],
                    "f1": metrics["f1"],
                    "specificity": metrics["specificity"],
                    "monotonic": metrics["monotonic"],
                    "low_pct": metrics["low_pct"],
                    "low_decline_rate": metrics["low_decline_rate"],
                    "medium_pct": metrics["medium_pct"],
                    "medium_decline_rate": metrics["medium_decline_rate"],
                    "high_pct": metrics["high_pct"],
                    "high_decline_rate": metrics["high_decline_rate"],
                    "extreme_pct": metrics["extreme_pct"],
                    "extreme_decline_rate": metrics["extreme_decline_rate"],
                })

    df = pd.DataFrame(results)
    df = df.sort_values("composite_score", ascending=False).reset_index(drop=True)
    return df


def filter_by_criteria(df,
                       extreme_decline_min=0.40,
                       extreme_pct_min=0.03,
                       extreme_pct_max=0.12,
                       precision_min=0.35,
                       monotonic_required=True):
    """
    Filter threshold results by business criteria.

    Criteria (by priority):
    1. extreme_decline_rate >= extreme_decline_min (default 40%)
    2. extreme_pct in [extreme_pct_min, extreme_pct_max] (default 3-12%)
    3. monotonicity
    4. precision >= precision_min
    """
    filtered = df.copy()

    if monotonic_required:
        filtered = filtered[filtered["monotonic"] == True]

    filtered = filtered[filtered["extreme_decline_rate"] >= extreme_decline_min]
    filtered = filtered[filtered["extreme_pct"] >= extreme_pct_min]
    filtered = filtered[filtered["extreme_pct"] <= extreme_pct_max]
    filtered = filtered[filtered["precision"] >= precision_min]

    return filtered.sort_values("composite_score", ascending=False)


def summarize_thresholds(thr_df, top_n=10, filtered_only=True):
    """Produce formatted summary of threshold search results."""
    if len(thr_df) == 0:
        return "No threshold results to summarize."

    df = thr_df.copy()
    if filtered_only:
        df = filter_by_criteria(df)
        if len(df) == 0:
            df = thr_df.head(top_n)  # fallback: show top even if no filter match

    lines = []
    lines.append(f"{'Rank':<6} {'Thr(l,m,h)':<18} {'CS':<8} {'AUC':<8} "
                 f"{'Prec':<8} {'Recall':<8} {'F1':<8} {'Ext%':<8} "
                 f"{'Ext↓%':<8} {'Mono':<6}")
    lines.append("-" * 90)

    for rank, (_, row) in enumerate(df.head(top_n).iterrows(), 1):
        thr_str = f"[{row['low']},{row['mid']},{row['high']}]"
        lines.append(
            f"{rank:<6} {thr_str:<18} {row['composite_score']:<8.4f} "
            f"{row['auc']:<8.4f} {row['precision']:<8.4f} "
            f"{row['recall']:<8.4f} {row['f1']:<8.4f} "
            f"{row['extreme_pct']:<8.4f} {row['extreme_decline_rate']:<8.4f} "
            f"{'[OK]' if row['monotonic'] else '[NO]':<6}"
        )

    return "\n".join(lines)
