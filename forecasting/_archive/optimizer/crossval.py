"""
Phase 4: Time-series cross-validation for model stability assessment.
"""
import numpy as np
import pandas as pd

from optimizer.metrics import compute_classification_metrics
from optimizer.scoring_v2 import compute_composite_v2, score_decay_v2
from optimizer.config import CV_FOLDS, CURRENT_THRESHOLDS


def run_time_series_cv(df, weights, use_c6=True,
                       folds=None,
                       thresholds=CURRENT_THRESHOLDS):
    """
    Run time-series cross-validation.

    Parameters
    ----------
    df : pd.DataFrame with date_month, factor scores, and v2 scoring columns
    weights : dict of factor weights
    use_c6 : bool
    folds : list of dicts with train/test date tuples
    thresholds : dict

    Returns
    -------
    dict with per-fold results and aggregate metrics.
    """
    if folds is None:
        folds = CV_FOLDS

    thr = (thresholds["low"], thresholds["mid"], thresholds["high"])
    results = []

    for fold_id, fold in enumerate(folds):
        train_start, train_end = fold["train"]
        test_start, test_end = fold["test"]

        # Split data
        train_mask = (df["date_month"] >= train_start) & \
                     (df["date_month"] <= train_end)
        test_mask = (df["date_month"] >= test_start) & \
                    (df["date_month"] <= test_end)

        train_df = df[train_mask].copy()
        test_df = df[test_mask].copy()

        # Compute v2 scores
        train_scores = _compute_scores(train_df, weights, use_c6)
        test_scores = _compute_scores(test_df, weights, use_c6)

        if len(train_scores) == 0 or len(test_scores) == 0:
            continue

        # Evaluate
        train_metrics = compute_classification_metrics(
            train_df["decline_label_6m"].values,
            train_scores, thresholds=thr)

        test_metrics = compute_classification_metrics(
            test_df["decline_label_6m"].values,
            test_scores, thresholds=thr)

        # Stability (train vs test gap)
        auc_gap = abs((train_metrics.get("auc") or 0) -
                      (test_metrics.get("auc") or 0))
        prec_gap = abs((train_metrics.get("precision") or 0) -
                       (test_metrics.get("precision") or 0)) * 100  # in pp

        results.append({
            "fold": fold_id,
            "train_period": f"{train_start}~{train_end}",
            "test_period": f"{test_start}~{test_end}",
            "train_n": len(train_df),
            "test_n": len(test_df),
            "train_auc": train_metrics.get("auc"),
            "test_auc": test_metrics.get("auc"),
            "train_precision": train_metrics.get("precision"),
            "test_precision": test_metrics.get("precision"),
            "train_recall": train_metrics.get("recall"),
            "test_recall": test_metrics.get("recall"),
            "train_f1": train_metrics.get("f1"),
            "test_f1": test_metrics.get("f1"),
            "auc_gap": round(auc_gap, 4),
            "precision_gap_pp": round(prec_gap, 2),
            "train_extreme_pct": train_metrics.get("extreme_pct"),
            "test_extreme_pct": test_metrics.get("extreme_pct"),
            "test_extreme_decline_rate": test_metrics.get("extreme_decline_rate"),
            "monotonic": test_metrics.get("monotonic"),
        })

    # Aggregate
    if len(results) == 0:
        return {"error": "no valid folds"}

    result_df = pd.DataFrame(results)

    agg = {
        "n_folds": len(results),
        "auc_mean": round(result_df["test_auc"].mean(), 4),
        "auc_std": round(result_df["test_auc"].std(), 4),
        "precision_mean": round(result_df["test_precision"].mean(), 4),
        "precision_std": round(result_df["test_precision"].std(), 4),
        "recall_mean": round(result_df["test_recall"].mean(), 4),
        "f1_mean": round(result_df["test_f1"].mean(), 4),
        "auc_gap_mean": round(result_df["auc_gap"].mean(), 4),
        "auc_gap_max": round(result_df["auc_gap"].max(), 4),
        "precision_gap_mean_pp": round(result_df["precision_gap_pp"].mean(), 2),
        "precision_gap_max_pp": round(result_df["precision_gap_pp"].max(), 2),
        "all_monotonic": bool(result_df["monotonic"].all()),
        "extreme_decline_rate_mean": round(
            result_df["test_extreme_decline_rate"].mean(), 4),
        "stable": bool(
            result_df["auc_gap"].max() < 0.03 and
            result_df["precision_gap_pp"].max() < 10
        ),
    }

    return {"per_fold": result_df, "aggregate": agg}


def _compute_scores(df, weights, use_c6=True):
    """Compute v2 composite score for a DataFrame."""
    scores = []
    for _, row in df.iterrows():
        row_d = row.to_dict()
        # Check if c6 score is available
        c6_available = bool(row_d.get("c6_available", 0)) and use_c6

        # Compute composite
        result = compute_composite_v2(row_d, weights, use_c6=c6_available)
        scores.append(result["score_v2"])

    return np.array(scores)


def crossval_report(result):
    """Generate formatted cross-validation report."""
    if "error" in result:
        return f"Error: {result['error']}"

    lines = []
    agg = result["aggregate"]
    folds = result["per_fold"]

    lines.append("=== Time-Series Cross-Validation Report ===")
    lines.append(f"  Folds: {agg['n_folds']}")
    lines.append(f"  AUC: mean={agg['auc_mean']:.4f}, std={agg['auc_std']:.4f}")
    lines.append(f"  Precision: mean={agg['precision_mean']:.4f}, std={agg['precision_std']:.4f}")
    lines.append(f"  Recall: mean={agg['recall_mean']:.4f}")
    lines.append(f"  F1: mean={agg['f1_mean']:.4f}")
    lines.append(f"  Train-Test AUC gap: mean={agg['auc_gap_mean']:.4f}, max={agg['auc_gap_max']:.4f}")
    lines.append(f"  Train-Test Precision gap: mean={agg['precision_gap_mean_pp']:.2f}pp, max={agg['precision_gap_max_pp']:.2f}pp")
    lines.append(f"  All folds monotonic: {'[OK]' if agg['all_monotonic'] else '[NO]'}")
    lines.append(f"  Extreme decline rate mean: {agg['extreme_decline_rate_mean']:.4f}")
    lines.append(f"  Stable (auc_gap<0.03 & prec_gap<10pp): {'[OK]' if agg['stable'] else '[NO]'}")

    lines.append("")
    lines.append("--- Per-Fold Details ---")
    for _, row in folds.iterrows():
        lines.append(
            f"  Fold {int(row['fold'])}: "
            f"train=({row['train_period']}, n={row['train_n']}) "
            f"test=({row['test_period']}, n={row['test_n']})"
        )
        lines.append(
            f"    Train: AUC={row['train_auc']:.4f}, Prec={row['train_precision']:.4f}, "
            f"Rec={row['train_recall']:.4f}, F1={row['train_f1']:.4f}"
        )
        lines.append(
            f"    Test:  AUC={row['test_auc']:.4f}, Prec={row['test_precision']:.4f}, "
            f"Rec={row['test_recall']:.4f}, F1={row['test_f1']:.4f}"
        )
        lines.append(
            f"    Gap: AUC={row['auc_gap']:.4f}, Prec={row['precision_gap_pp']:.2f}pp, "
            f"Ext%={row['test_extreme_pct']:.4f}, Ext↓%={row['test_extreme_decline_rate']:.4f}"
        )

    return "\n".join(lines)
