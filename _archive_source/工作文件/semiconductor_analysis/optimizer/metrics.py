"""
Unified metrics computation for model evaluation.
"""
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score


def compute_classification_metrics(y_true, y_pred_proba, thresholds=(50, 60, 75)):
    """
    Compute all classification metrics for a given score vector.

    Parameters
    ----------
    y_true : array-like, binary (0/1)
    y_pred_proba : array-like, float (0-100 risk score)
    thresholds : tuple (low, mid, high)
        Risk level thresholds: <=low=low, low<mid, mid<high, >high=extreme

    Returns
    -------
    dict with keys: auc, precision, recall, f1, specificity,
                    low_pct, medium_pct, high_pct, extreme_pct,
                    low_decline_rate, medium_decline_rate, high_decline_rate,
                    extreme_decline_rate, monotonic, extreme_precision
    """
    y_true = np.array(y_true)
    y_pred = np.array(y_pred_proba)

    valid = ~(np.isnan(y_true) | np.isnan(y_pred))
    y_true_v = y_true[valid].astype(int)
    y_pred_v = y_pred[valid]

    if len(np.unique(y_true_v)) < 2:
        auc = float("nan")
    else:
        auc = roc_auc_score(y_true_v, y_pred_v)

    low_thr, mid_thr, high_thr = thresholds

    # Risk level assignments
    levels = np.zeros(len(y_pred_v), dtype=int)  # 0=low
    levels[(y_pred_v > low_thr) & (y_pred_v <= mid_thr)] = 1  # medium
    levels[(y_pred_v > mid_thr) & (y_pred_v <= high_thr)] = 2  # high
    levels[y_pred_v > high_thr] = 3  # extreme

    # High+extreme flag
    high_extreme = levels >= 2

    # Compute metrics on high+extreme (where business action happens)
    if high_extreme.sum() > 0 and len(np.unique(y_true_v)) > 1:
        prec = precision_score(y_true_v, high_extreme, zero_division=0)
        rec = recall_score(y_true_v, high_extreme, zero_division=0)
        f1 = f1_score(y_true_v, high_extreme, zero_division=0)
    else:
        prec = float("nan")
        rec = float("nan")
        f1 = float("nan")

    tn = ((y_true_v == 0) & (high_extreme == 0)).sum()
    fp = ((y_true_v == 0) & (high_extreme == 1)).sum()
    specificity = tn / (tn + fp) if (tn + fp) > 0 else float("nan")

    # Per-level decline rates
    result = {
        "auc": round(auc, 4),
        "n_valid": int(valid.sum()),
        "n_positive": int(y_true_v.sum()),
        "positive_rate": round(y_true_v.mean(), 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(f1, 4),
        "specificity": round(specificity, 4),
        "threshold_low": low_thr,
        "threshold_mid": mid_thr,
        "threshold_high": high_thr,
    }

    # Per-level stats
    level_names = ["low", "medium", "high", "extreme"]
    prev_l = 0
    monotonic = True
    prev_rate = -1.0

    for lidx, lname in enumerate(level_names):
        if lname == "low":
            mask = y_pred_v <= low_thr
        elif lname == "medium":
            mask = (y_pred_v > low_thr) & (y_pred_v <= mid_thr)
        elif lname == "high":
            mask = (y_pred_v > mid_thr) & (y_pred_v <= high_thr)
        else:
            mask = y_pred_v > high_thr

        n = int(mask.sum())
        rate = round(y_true_v[mask].mean(), 4) if n > 0 else float("nan")

        result[f"{lname}_n"] = n
        result[f"{lname}_pct"] = round(n / len(y_pred_v), 4) if len(y_pred_v) > 0 else 0
        result[f"{lname}_decline_rate"] = rate

        if n > 0 and not np.isnan(rate):
            if rate < prev_rate - 0.005:  # allow 0.5pp tolerance
                monotonic = False
            prev_rate = rate

    result["monotonic"] = monotonic

    return result


def compare_metrics(m1, m2):
    """Return dict of differences m2 - m1 for key metrics."""
    keys = ["auc", "precision", "recall", "f1", "specificity",
            "low_pct", "medium_pct", "high_pct", "extreme_pct"]
    diff = {}
    for k in keys:
        if k in m1 and k in m2:
            v1 = m1[k] if not (isinstance(m1[k], float) and np.isnan(m1[k])) else 0
            v2 = m2[k] if not (isinstance(m2[k], float) and np.isnan(m2[k])) else 0
            diff[k] = round(v2 - v1, 4)
    return diff


def score_bucket_analysis(factor_values, y_true, n_buckets=5):
    """
    Analyze how well a single factor score differentiates risk.
    Returns monotonicity status and bucket analysis.

    Parameters
    ----------
    factor_values : array-like, factor scores (0-100)
    y_true : array-like, binary labels
    n_buckets : int, number of equal-width buckets

    Returns
    -------
    dict with bucket analysis
    """
    df = pd.DataFrame({"score": factor_values, "label": y_true}).dropna()
    if len(df) < 10:
        return {"error": "too few samples"}

    df["bucket"] = pd.qcut(df["score"], q=min(n_buckets, df["score"].nunique()),
                           duplicates="drop", labels=False)

    bucket_stats = df.groupby("bucket").agg(
        n=("label", "count"),
        decline_rate=("label", "mean"),
        mean_score=("score", "mean"),
    ).reset_index()

    # Check monotonicity
    rates = bucket_stats["decline_rate"].values
    monotonic = all(rates[i] <= rates[i+1] + 0.01 for i in range(len(rates)-1))

    # Correlation with label
    corr = df["score"].corr(df["label"])
    # AUC
    if len(np.unique(df["label"])) > 1:
        auc = roc_auc_score(df["label"], df["score"])
    else:
        auc = float("nan")

    return {
        "auc": round(auc, 4),
        "correlation": round(corr, 4),
        "n": len(df),
        "monotonic": bool(monotonic),
        "buckets": bucket_stats.to_dict("records"),
    }
