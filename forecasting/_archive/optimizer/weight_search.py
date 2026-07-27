"""
Phase 2: Weight grid search with Pareto frontier identification.
"""
import itertools
import numpy as np
import pandas as pd

from optimizer.metrics import compute_classification_metrics
from optimizer.config import (
    CURRENT_THRESHOLDS,
    WEIGHT_SEARCH_3F,
    WEIGHT_SEARCH_4F,
)


def _generate_weight_combinations(config):
    """
    Generate all weight combinations summing to 1.0 with given step.

    Parameters
    ----------
    config : dict with step, min, max, factors

    Yields
    ------
    dict of {factor_name: weight}
    """
    step = config["step"]
    min_w = config["min"]
    max_w = config["max"]
    n_factors = len(config["factors"])

    # Number of steps per factor
    n_steps = int(round((max_w - min_w) / step)) + 1

    # Generate all integer grid points
    values = np.round(np.arange(0, n_steps) * step + min_w, 4)

    if n_factors == 3:
        # x + y + z = 1.0
        for x in values:
            if x > 1.0 - 2 * min_w:
                continue
            for y in values:
                z = round(1.0 - x - y, 4)
                if z < min_w or z > max_w:
                    continue
                yield {config["factors"][0]: x,
                       config["factors"][1]: y,
                       config["factors"][2]: z}
    elif n_factors == 4:
        # w + x + y + z = 1.0
        for w in values:
            if w > 1.0 - 3 * min_w:
                continue
            for x in values:
                if w + x > 1.0 - 2 * min_w:
                    continue
                for y in values:
                    z = round(1.0 - w - x - y, 4)
                    if z < min_w or z > max_w:
                        continue
                    yield {config["factors"][0]: w,
                           config["factors"][1]: x,
                           config["factors"][2]: y,
                           config["factors"][3]: z}
    else:
        raise ValueError(f"Unsupported n_factors: {n_factors}")


def grid_search_3f(f1f_scores, f4_scores, f5_scores, y_true,
                   step=WEIGHT_SEARCH_3F["step"],
                   thresholds=CURRENT_THRESHOLDS,
                   progress=True):
    """
    Grid search over 3-factor weights.

    Parameters
    ----------
    f1f_scores, f4_scores, f5_scores : array-like
        Individual factor scores (0-100).
    y_true : array-like, binary labels
    step : float, weight step
    thresholds : dict with low, mid, high

    Returns
    -------
    pd.DataFrame with all results sorted by F1 descending.
    """
    config = dict(WEIGHT_SEARCH_3F)
    config["step"] = step

    f1f = np.array(f1f_scores)
    f4 = np.array(f4_scores)
    f5 = np.array(f5_scores)
    yt = np.array(y_true)

    thr = (thresholds["low"], thresholds["mid"], thresholds["high"])
    results = []

    combos = list(_generate_weight_combinations(config))
    n_total = len(combos)

    for idx, w in enumerate(combos):
        composite = (w["F1f"] * f1f +
                     w["F4"] * f4 +
                     w["F5"] * f5)

        metrics = compute_classification_metrics(yt, composite, thresholds=thr)
        row = {
            "w_F1f": round(w["F1f"], 4),
            "w_F4": round(w["F4"], 4),
            "w_F5": round(w["F5"], 4),
            "auc": metrics["auc"],
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "f1": metrics["f1"],
            "specificity": metrics["specificity"],
            "monotonic": metrics["monotonic"],
            "extreme_pct": metrics["extreme_pct"],
            "extreme_decline_rate": metrics["extreme_decline_rate"],
            "high_pct": metrics["high_pct"],
            "high_decline_rate": metrics["high_decline_rate"],
        }
        results.append(row)

        if progress and (idx + 1) % 50 == 0:
            print(f"  3F grid: {idx+1}/{n_total} done")

    df = pd.DataFrame(results)
    df = df.sort_values("f1", ascending=False).reset_index(drop=True)
    return df


def grid_search_4f(f1f_scores, f4_scores, f5_scores, c6_scores,
                   c6_available_mask, y_true,
                   step=WEIGHT_SEARCH_4F["step"],
                   thresholds=CURRENT_THRESHOLDS,
                   progress=True):
    """
    Grid search over 4-factor weights (only on c6-available rows).

    Parameters
    ----------
    f1f_scores, f4_scores, f5_scores, c6_scores : array-like
        Individual factor scores.
    c6_available_mask : array-like, bool
        Which rows have c6 available.
    y_true : array-like, binary labels
    step : float
    thresholds : dict

    Returns
    -------
    pd.DataFrame with all results sorted by F1 descending.
    """
    config = dict(WEIGHT_SEARCH_4F)
    config["step"] = step

    mask = np.array(c6_available_mask, dtype=bool)
    if mask.sum() == 0:
        print("  [WARN] No c6-available rows — skipping 4F search")
        return pd.DataFrame()

    f1f = np.array(f1f_scores)[mask]
    f4 = np.array(f4_scores)[mask]
    f5 = np.array(f5_scores)[mask]
    c6 = np.array(c6_scores)[mask]
    yt = np.array(y_true)[mask]

    thr = (thresholds["low"], thresholds["mid"], thresholds["high"])
    results = []

    combos = list(_generate_weight_combinations(config))
    n_total = len(combos)

    for idx, w in enumerate(combos):
        composite = (w["F1f"] * f1f +
                     w["F4"] * f4 +
                     w["F5"] * f5 +
                     w["c6"] * c6)

        metrics = compute_classification_metrics(yt, composite, thresholds=thr)
        row = {
            "w_F1f": round(w["F1f"], 4),
            "w_F4": round(w["F4"], 4),
            "w_F5": round(w["F5"], 4),
            "w_c6": round(w["c6"], 4),
            "auc": metrics["auc"],
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "f1": metrics["f1"],
            "specificity": metrics["specificity"],
            "monotonic": metrics["monotonic"],
            "extreme_pct": metrics["extreme_pct"],
            "extreme_decline_rate": metrics["extreme_decline_rate"],
        }
        results.append(row)

        if progress and (idx + 1) % 50 == 0:
            print(f"  4F grid: {idx+1}/{n_total} (on {mask.sum()} c6-available rows)")

    df = pd.DataFrame(results)
    df = df.sort_values("f1", ascending=False).reset_index(drop=True)
    return df


def find_pareto_frontier(results_df, objectives=("auc", "precision", "f1")):
    """
    Identify Pareto-optimal weight combinations.

    A combination is Pareto-optimal if no other combination is better
    on ALL objectives.

    Parameters
    ----------
    results_df : pd.DataFrame with weight + metric columns
    objectives : tuple of metric column names to maximize

    Returns
    -------
    pd.DataFrame (subset of results_df), sorted by f1 desc.
    """
    df = results_df.copy()

    # Filter to valid combos
    df = df[df["monotonic"] == True].copy()
    df = df[df["precision"].notna()].copy()

    if len(df) == 0:
        return df

    pareto_mask = np.ones(len(df), dtype=bool)

    for i in range(len(df)):
        if not pareto_mask[i]:
            continue
        for j in range(len(df)):
            if i == j or not pareto_mask[j]:
                continue
            # Check if j dominates i
            better_on_all = all(df.iloc[j][obj] >= df.iloc[i][obj]
                                for obj in objectives)
            strictly_better_on_one = any(df.iloc[j][obj] > df.iloc[i][obj]
                                         for obj in objectives)
            if better_on_all and strictly_better_on_one:
                pareto_mask[i] = False
                break

    return df[pareto_mask].sort_values("f1", ascending=False)


def summarize_weight_results(grid_df, top_n=10, pareto_only=True):
    """
    Produce a summary of weight search results.

    Parameters
    ----------
    grid_df : pd.DataFrame from grid_search_*
    top_n : int, number of top results to show
    pareto_only : bool, show only Pareto-optimal

    Returns
    -------
    str, formatted table
    """
    if len(grid_df) == 0:
        return "No results to summarize."

    if pareto_only:
        grid_df = find_pareto_frontier(grid_df)

    lines = []
    lines.append(f"{'Rank':<6} {'F1f_w':<8} {'F4_w':<8} {'F5_w':<8} "
                 f"{'c6_w':<8} {'AUC':<8} {'Prec':<8} {'Recall':<8} "
                 f"{'F1':<8} {'Monotonic':<10} {'Ext%':<8} {'Ext↓%':<8}")
    lines.append("-" * 90)

    for rank, (_, row) in enumerate(grid_df.head(top_n).iterrows(), 1):
        c6_str = f"{row.get('w_c6', 0):.3f}" if 'w_c6' in row else "n/a"
        lines.append(
            f"{rank:<6} {row['w_F1f']:<8.3f} {row['w_F4']:<8.3f} "
            f"{row['w_F5']:<8.3f} {c6_str:<8}"
            f" {row['auc']:<8.4f} {row['precision']:<8.4f} "
            f"{row['recall']:<8.4f} {row['f1']:<8.4f} "
            f"{'[OK]' if row['monotonic'] else '[NO]':<10} "
            f"{row['extreme_pct']:<8.4f} {row['extreme_decline_rate']:<8.4f}"
        )

    return "\n".join(lines)
