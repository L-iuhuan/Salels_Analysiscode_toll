"""
Data loader for optimization pipeline.

Merges samples.pkl + prospective_labels.csv + c6_factor_raw.csv
into a unified DataFrame for factor scoring and evaluation.
"""
import os
import sys
import pandas as pd
import numpy as np

# Path injection
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config.settings import PROJECT_ROOT as CFG_ROOT, OUTPUT_GOLD, DATA_DIR

# Use config's paths if available, otherwise default
PROJECT_ROOT = CFG_ROOT if os.path.isdir(CFG_ROOT) else _PROJECT_ROOT
OUTPUT_GOLD_DIR = OUTPUT_GOLD if os.path.isdir(OUTPUT_GOLD) else os.path.join(PROJECT_ROOT, "output", "gold")


def load_optimization_data(data_dir=None):
    """
    Load and merge optimization data.

    Returns
    -------
    pd.DataFrame with columns:
        product_id, date_month, decline_label_6m,
        f1_score, f4_score, f5_score, (existing factor scores)
        c6_raw, c6_available,
        slope_ratio, decay_pp, self_health, consecutive_months,
        yoy_change, zero_profit, slope_insufficient, no_valid_hist_margin,
        risk_score (current composite)
    """
    gold_dir = data_dir or OUTPUT_GOLD_DIR
    opt_dir = os.path.join(PROJECT_ROOT, "recession_risk_opt", "data")

    # Locate samples.pkl
    samples_path = os.path.join(opt_dir, "samples.pkl")
    if not os.path.exists(samples_path):
        # Try alternative paths
        alt_paths = [
            os.path.join(PROJECT_ROOT, "data", "samples.pkl"),
            os.path.join(PROJECT_ROOT, "output", "samples.pkl"),
        ]
        for p in alt_paths:
            if os.path.exists(p):
                samples_path = p
                break

    if not os.path.exists(samples_path):
        raise FileNotFoundError(
            f"samples.pkl not found. Tried: {samples_path}"
        )

    # Load samples
    samples = pd.read_pickle(samples_path)
    print(f"  samples.pkl: {samples.shape[0]} rows, {samples['product_id'].nunique()} products")

    # Load prospective labels
    labels_path = os.path.join(gold_dir, "prospective_labels.csv")
    if os.path.exists(labels_path):
        labels = pd.read_csv(labels_path)
        print(f"  prospective_labels.csv: {labels.shape[0]} rows")
    else:
        # Fallback: labels might be in samples
        if "decline_label_6m" in samples.columns:
            labels = samples[["product_id", "date_month", "decline_label_6m",
                              "decline_reason", "y"]].copy()
            print("  Labels found in samples.pkl")
        else:
            raise FileNotFoundError(
                f"prospective_labels.csv not found at {labels_path}"
            )

    # Load c6 data
    c6_path = os.path.join(gold_dir, "c6_factor_raw.csv")
    if os.path.exists(c6_path):
        c6 = pd.read_csv(c6_path)
        print(f"  c6_factor_raw.csv: {c6.shape[0]} rows, {c6['product_id'].nunique()} products")
        has_c6 = True
    else:
        c6 = None
        has_c6 = False
        print("  [INFO] c6_factor_raw.csv not found — running 4-factor search limited")

    # Merge samples + labels
    merge_cols = ["product_id", "date_month"]

    # Ensure column exists in samples for merge
    for col in merge_cols:
        if col not in samples.columns:
            raise KeyError(f"Required column '{col}' not in samples.pkl")

    label_cols = merge_cols + ["decline_label_6m"]
    if "decline_reason" in labels.columns:
        label_cols.append("decline_reason")
    if "y" in labels.columns:
        label_cols.append("y")

    df = samples.merge(labels[label_cols], on=merge_cols, how="left")

    # Merge c6
    if has_c6:
        c6_cols = merge_cols + ["c6_raw", "c6_available"]
        df = df.merge(c6[c6_cols], on=merge_cols, how="left")
        df["c6_available"] = df["c6_available"].fillna(0).astype(int)

    # Ensure critical columns exist
    _ensure_columns(df, samples.columns)

    n_labeled = df["decline_label_6m"].notna().sum()
    print(f"  Merged: {len(df)} rows, {n_labeled} labeled ({n_labeled/len(df)*100:.1f}%)")

    return df


def _ensure_columns(df, sample_cols):
    """Ensure all expected columns have sane defaults."""
    # Factor scores (existing)
    for col in ["f1_score", "f4_score", "f5_score"]:
        if col not in df.columns:
            raise KeyError(f"Required factor score column '{col}' not in merged data")

    # Intermediate variables for re-scoring
    intermediates = {
        "slope_ratio": 0.0,
        "decay_pp": 0.0,
        "self_health": 0.0,
        "yoy_change": 0.0,
        "consecutive_months": 0,
        "zero_profit": False,
        "slope_insufficient": False,
        "no_valid_hist_margin": False,
        "c6_raw": float("nan"),
        "c6_available": 0,
    }
    for col, default in intermediates.items():
        if col not in df.columns:
            df[col] = default

    # Ensure date_month is string for CV splits
    if "date_month" in df.columns and not pd.api.types.is_string_dtype(df["date_month"]):
        df["date_month"] = df["date_month"].astype(str)


def get_labeled_subset(df):
    """Return rows with valid decline_label_6m."""
    return df[df["decline_label_6m"].notna()].copy()


def get_available_c6_subset(df):
    """Return rows with available c6 data + valid label."""
    return df[(df["decline_label_6m"].notna()) & (df["c6_available"] == 1)].copy()
