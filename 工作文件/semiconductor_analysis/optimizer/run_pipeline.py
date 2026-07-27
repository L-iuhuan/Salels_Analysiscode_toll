"""
Main optimization pipeline orchestrator.

Run: python optimizer/run_pipeline.py [--phases 1,2,3,4] [--output output/optimization]

All phases:
  1: Factor scoring function validation
  2: Weight grid search
  3: Threshold calibration
  4: Time-series cross-validation
"""
import os
import sys
import argparse
import time

# Path injection
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pandas as pd
import numpy as np

from optimizer.data_loader import load_optimization_data, get_labeled_subset, get_available_c6_subset
from optimizer.scoring_v2 import (
    score_slope_v2, score_decay_v2, score_self_health_v2, score_c6_v2,
    compute_composite_v2, score_panel_v2,
)
from optimizer.metrics import score_bucket_analysis
from optimizer.weight_search import (
    grid_search_3f, grid_search_4f,
    find_pareto_frontier, summarize_weight_results,
)
from optimizer.threshold_search import (
    search_thresholds, filter_by_criteria, summarize_thresholds,
)
from optimizer.crossval import run_time_series_cv, crossval_report
from optimizer.reporter import generate_report
from optimizer.config import (
    PREV_WEIGHTS_3F, TRANSITION_WEIGHTS_4F,
    CURRENT_THRESHOLDS, FRONTIER_THRESHOLDS,
)


def phase_1_scoring_validation(df):
    """
    Phase 1: Validate and compare v2 scoring functions against v1.

    For each factor, compute bucket analysis on the new scoring function
    and verify monotonicity has been fixed.
    """
    print("\n" + "="*60)
    print("PHASE 1: FACTOR SCORING FUNCTION VALIDATION")
    print("="*60)

    labeled = get_labeled_subset(df)
    y_true = labeled["decline_label_6m"].values

    results = []

    # --- F1f v2 validation ---
    print("\n--- F1f (Slope) v2 ---")
    f1f_v2 = labeled.apply(
        lambda r: score_slope_v2(r["slope_ratio"],
                                 zero_profit=bool(r.get("zero_profit", False)),
                                 slope_insufficient=bool(r.get("slope_insufficient", False))),
        axis=1
    )
    r1 = score_bucket_analysis(f1f_v2, y_true, n_buckets=5)
    print(f"  AUC: {r1['auc']:.4f}, Correlation: {r1['correlation']:.4f}, "
          f"Monotonic: {'OK' if r1['monotonic'] else 'NO'}")
    results.append(("F1f v2", r1))

    # Compare with existing f1_score
    r1_old = score_bucket_analysis(labeled["f1_score"].values, y_true, n_buckets=5)
    print(f"  (v1 AUC: {r1_old['auc']:.4f}, v1 monotonic: {'[OK]' if r1_old['monotonic'] else '[NO]'})")

    # --- F4 v2 validation ---
    print("\n--- F4 (Decay) v2 ---")
    f4_v2 = labeled.apply(
        lambda r: score_decay_v2(
            r["decay_pp"],
            r["yoy_change"],
            consecutive_months=int(r.get("consecutive_months", 0)),
        ),
        axis=1
    )
    r4 = score_bucket_analysis(f4_v2, y_true, n_buckets=5)
    print(f"  AUC: {r4['auc']:.4f}, Correlation: {r4['correlation']:.4f}, "
          f"Monotonic: {'[OK]' if r4['monotonic'] else '[NO]'}")
    results.append(("F4 v2", r4))

    r4_old = score_bucket_analysis(labeled["f4_score"].values, y_true, n_buckets=5)
    print(f"  (v1 AUC: {r4_old['auc']:.4f}, v1 monotonic: {'[OK]' if r4_old['monotonic'] else '[NO]'})")

    # Check specific reversal fix: F4=70 vs F4=50
    v2_buckets = pd.cut(f4_v2, bins=[0, 30, 50, 70, 100], labels=["10-30", "40-50", "60-70", "80-100"])
    bucket_rates = pd.DataFrame({
        "score_v2": f4_v2,
        "label": y_true,
        "bucket": v2_buckets,
    }).groupby("bucket", observed=False)["label"].mean()
    print(f"  v2 bucket decline rates:\n{bucket_rates.to_string()}")

    # Verify: min decline of top bucket > max decline of lower buckets
    print("  [OK] F4 v2 monotonicity verified" if r4['monotonic'] else "  [NO] F4 v2 still has issues")

    # --- F5 v2 validation ---
    print("\n--- F5 (Self-Health) v2 ---")
    f5_v2 = labeled.apply(
        lambda r: score_self_health_v2(
            r["self_health"],
            hist_margin_invalid=bool(r.get("no_valid_hist_margin", False)),
        ),
        axis=1
    )
    r5 = score_bucket_analysis(f5_v2, y_true, n_buckets=5)
    print(f"  AUC: {r5['auc']:.4f}, Correlation: {r5['correlation']:.4f}, "
          f"Monotonic: {'[OK]' if r5['monotonic'] else '[NO]'}")
    results.append(("F5 v2", r5))

    r5_old = score_bucket_analysis(labeled["f5_score"].values, y_true, n_buckets=5)
    print(f"  (v1 AUC: {r5_old['auc']:.4f}, v1 monotonic: {'[OK]' if r5_old['monotonic'] else '[NO]'})")

    # --- c6 v2 validation ---
    c6_available = labeled[labeled["c6_available"] == 1]
    if len(c6_available) > 0:
        print("\n--- c6 v2 ---")
        c6_v2 = c6_available.apply(lambda r: score_c6_v2(r["c6_raw"]), axis=1)
        r6 = score_bucket_analysis(c6_v2, c6_available["decline_label_6m"].values, n_buckets=4)
        print(f"  AUC: {r6['auc']:.4f}, Correlation: {r6['correlation']:.4f}, "
              f"Monotonic: {'[OK]' if r6['monotonic'] else '[NO]'}")
        results.append(("c6 v2", r6))

    # --- Composite v2 baseline ---
    print("\n--- Composite v2 (transition weights) ---")
    df_v2 = score_panel_v2(labeled, TRANSITION_WEIGHTS_4F, use_c6=True)
    from optimizer.metrics import compute_classification_metrics
    m_v2 = compute_classification_metrics(
        df_v2["decline_label_6m"].values,
        df_v2["score_v2"].values,
        thresholds=(CURRENT_THRESHOLDS["low"], CURRENT_THRESHOLDS["mid"],
                    CURRENT_THRESHOLDS["high"]))
    print(f"  AUC: {m_v2['auc']:.4f}, Precision: {m_v2['precision']:.4f}, "
          f"Recall: {m_v2['recall']:.4f}, F1: {m_v2['f1']:.4f}")

    # Compare with current v1
    m_v1 = compute_classification_metrics(
        labeled["decline_label_6m"].values,
        labeled["risk_score"].values,
        thresholds=(CURRENT_THRESHOLDS["low"], CURRENT_THRESHOLDS["mid"],
                    CURRENT_THRESHOLDS["high"]))
    print(f"  (v1 AUC: {m_v1['auc']:.4f}, Precision: {m_v1['precision']:.4f}, "
          f"Recall: {m_v1['recall']:.4f}, F1: {m_v1['f1']:.4f})")

    # Delta
    print(f"  \u0394 AUC: {m_v2['auc'] - m_v1['auc']:+.4f}, "
          f"\u0394 Precision: {m_v2['precision'] - m_v1['precision']:+.4f}")

    print("\n" + "-"*60)
    print("PHASE 1 COMPLETE")
    print("-"*60)

    return df_v2, {"v1_metrics": m_v1, "v2_metrics": m_v2, "factor_results": results}


def phase_2_weight_search(df_v2):
    """
    Phase 2: Grid search over factor weights.

    Uses Phase 1 optimized scores to search 3-factor and 4-factor weight spaces.
    """
    print("\n" + "="*60)
    print("PHASE 2: WEIGHT GRID SEARCH")
    print("="*60)

    labeled = df_v2[df_v2["decline_label_6m"].notna()].copy()
    y_true = labeled["decline_label_6m"].values

    # 3-factor search
    print("\n--- 3-Factor Weight Search ---")
    w3f = grid_search_3f(
        labeled["f1f_v2"].values,
        labeled["f4_v2"].values,
        labeled["f5_v2"].values,
        y_true,
        step=0.025,
    )

    print(f"  Total combos: {len(w3f)}")
    print(f"  Top result: F1f={w3f.iloc[0]['w_F1f']:.3f}, "
          f"F4={w3f.iloc[0]['w_F4']:.3f}, F5={w3f.iloc[0]['w_F5']:.3f}")
    print(f"  AUC={w3f.iloc[0]['auc']:.4f}, F1={w3f.iloc[0]['f1']:.4f}, "
          f"Prec={w3f.iloc[0]['precision']:.4f}")

    pareto_3f = find_pareto_frontier(w3f)
    print(f"  Pareto frontier: {len(pareto_3f)} combinations")

    # 4-factor search (on c6-available subset)
    print("\n--- 4-Factor Weight Search ---")
    c6_available = labeled[labeled["c6_available"] == 1]
    if len(c6_available) >= 1000:
        w4f = grid_search_4f(
            c6_available["f1f_v2"].values,
            c6_available["f4_v2"].values,
            c6_available["f5_v2"].values,
            c6_available["c6_v2"].values,
            c6_available["c6_available"].values,
            c6_available["decline_label_6m"].values,
            step=0.05,
        )
        if len(w4f) > 0:
            print(f"  Total combos: {len(w4f)}")
            print(f"  Top result: F1f={w4f.iloc[0]['w_F1f']:.3f}, "
                  f"F4={w4f.iloc[0]['w_F4']:.3f}, F5={w4f.iloc[0]['w_F5']:.3f}, "
                  f"c6={w4f.iloc[0]['w_c6']:.3f}")
            print(f"  AUC={w4f.iloc[0]['auc']:.4f}, F1={w4f.iloc[0]['f1']:.4f}, "
                  f"Prec={w4f.iloc[0]['precision']:.4f}")

            pareto_4f = find_pareto_frontier(w4f)
            print(f"  Pareto frontier: {len(pareto_4f)} combinations")
        else:
            w4f = None
            print("  [WARN] No valid c6-available subset for 4F search")
    else:
        w4f = None
        print(f"  [WARN] Only {len(c6_available)} c6-available rows (< 1000), skipping 4F search")

    print("\n" + "-"*60)
    print("PHASE 2 COMPLETE")
    print("-"*60)

    return w3f, w4f


def phase_3_threshold_calibration(df_v2, top_weights):
    """
    Phase 3: Search optimal risk thresholds.

    For each of the top-N weight configurations, search threshold space.
    """
    print("\n" + "="*60)
    print("PHASE 3: THRESHOLD CO-CALIBRATION")
    print("="*60)

    labeled = df_v2[df_v2["decline_label_6m"].notna()].copy()

    # Evaluate with top 3 weight configs from Phase 2
    w_candidates = []
    if top_weights is not None and len(top_weights) > 0:
        for _, row in top_weights.head(3).iterrows():
            w = {"F1f": row["w_F1f"], "F4": row["w_F4"], "F5": row["w_F5"]}
            if "w_c6" in row and row["w_c6"] > 0:
                w["c6"] = row["w_c6"]
            w_candidates.append(w)

    if not w_candidates:
        print("  No weight candidates — using default weights")
        w_candidates = [TRANSITION_WEIGHTS_4F, PREV_WEIGHTS_3F]

    all_threshold_results = []
    for w_idx, w in enumerate(w_candidates):
        print(f"\n  Threshold search for weight config #{w_idx+1}: "
              f"F1f={w.get('F1f',0):.3f}, F4={w.get('F4',0):.3f}, "
              f"F5={w.get('F5',0):.3f}" +
              (f", c6={w['c6']:.3f}" if "c6" in w else ""))

        # Compute composite scores
        use_c6 = "c6" in w and w["c6"] > 0
        scores = []
        for _, row in labeled.iterrows():
            r = compute_composite_v2(row.to_dict(), w, use_c6=use_c6)
            scores.append(r["score_v2"])
        scores = np.array(scores)

        thr_df = search_thresholds(scores, labeled["decline_label_6m"].values)
        all_threshold_results.append(thr_df)

        # Filter by criteria
        filtered = filter_by_criteria(thr_df)
        if len(filtered) > 0:
            best = filtered.iloc[0]
            print(f"    Best: [{best['low']},{best['mid']},{best['high']}] "
                  f"Prec={best['precision']:.4f}, "
                  f"Rec={best['recall']:.4f}, "
                  f"Ext%={best['extreme_pct']:.4f}, "
                  f"Ext↓%={best['extreme_decline_rate']:.4f}")
        else:
            # No config meets all criteria, show top unconstrained
            best = thr_df.iloc[0]
            print(f"    (No config meets filter criteria)")
            print(f"    Top unconstrained: [{best['low']},{best['mid']},{best['high']}] "
                  f"Prec={best['precision']:.4f}, Rec={best['recall']:.4f}")

    print("\n" + "-"*60)
    print("PHASE 3 COMPLETE")
    print("-"*60)

    return all_threshold_results


def phase_4_cross_validation(df_v2, weights, thresholds):
    """
    Phase 4: Time-series cross-validation of final model.
    """
    print("\n" + "="*60)
    print("PHASE 4: TIME-SERIES CROSS-VALIDATION")
    print("="*60)

    use_c6 = "c6" in weights and weights["c6"] > 0

    result = run_time_series_cv(
        df_v2, weights, use_c6=use_c6,
        thresholds=thresholds,
    )

    report = crossval_report(result)
    print(report)

    print("\n" + "-"*60)
    print("PHASE 4 COMPLETE")
    print("-"*60)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Risk Decline Model Optimization Pipeline v4.0")
    parser.add_argument("--phases", type=str, default="1,2,3,4",
                        help="Phases to run: 1=scoring,2=weights,3=thresholds,4=cv")
    parser.add_argument("--output", type=str, default="output/optimization",
                        help="Output directory")
    args = parser.parse_args()

    phases = [int(p.strip()) for p in args.phases.split(",")]
    output_dir = os.path.join(_PROJECT_ROOT, args.output)
    os.makedirs(output_dir, exist_ok=True)

    print("="*60)
    print("  RISK DECLINE MODEL v4.0 OPTIMIZATION")
    print(f"  Phases: {phases}")
    print("="*60)

    # Load data
    print("\nLoading data...")
    t0 = time.time()
    df = load_optimization_data()
    print(f"  Loaded {len(df)} rows in {time.time()-t0:.1f}s")

    df_v2 = None
    w3f = None
    w4f = None
    threshold_results = None
    cv_result = None
    scoring_result = None

    # Phase 1: Scoring function validation
    if 1 in phases:
        df_v2, scoring_result = phase_1_scoring_validation(df)
        # Save v2 scored data for later phases
        df_v2.to_pickle(os.path.join(output_dir, "df_v2_scored.pkl"))
        print(f"  Saved v2-scored data ({len(df_v2)} rows)")

    # Load v2 data if not re-running Phase 1
    if df_v2 is None:
        pkl_path = os.path.join(output_dir, "df_v2_scored.pkl")
        if os.path.exists(pkl_path):
            df_v2 = pd.read_pickle(pkl_path)
            print(f"  Loaded v2-scored data: {len(df_v2)} rows")

    # Phase 2: Weight grid search
    if 2 in phases and df_v2 is not None:
        w3f, w4f = phase_2_weight_search(df_v2)
        # Save weight results
        if w3f is not None:
            w3f.to_csv(os.path.join(output_dir, "weight_3f_results.csv"), index=False)
        if w4f is not None:
            w4f.to_csv(os.path.join(output_dir, "weight_4f_results.csv"), index=False)

    # Phase 3: Threshold calibration
    if 3 in phases and df_v2 is not None:
        # Use best 4F weights if available, else 3F
        if w4f is not None and len(w4f) > 0:
            top_w = w4f
        elif w3f is not None and len(w3f) > 0:
            top_w = w3f
        else:
            top_w = None
        threshold_results = phase_3_threshold_calibration(df_v2, top_w)

    # Phase 4: Cross-validation
    if 4 in phases and df_v2 is not None:
        # Determine best weights and thresholds
        if w4f is not None and len(w4f) > 0:
            best_w = w4f.iloc[0]
            weights = {
                "F1f": best_w["w_F1f"], "F4": best_w["w_F4"],
                "F5": best_w["w_F5"], "c6": best_w["w_c6"]
            } if "w_c6" in best_w else {
                "F1f": best_w["w_F1f"], "F4": best_w["w_F4"],
                "F5": best_w["w_F5"]
            }
        else:
            weights = TRANSITION_WEIGHTS_4F

        if threshold_results and len(threshold_results) > 0:
            # Find best across all threshold configs
            combined = pd.concat(threshold_results, ignore_index=True)
            filtered = filter_by_criteria(combined)
            if len(filtered) > 0:
                best_thr = filtered.iloc[0]
                thresholds = {
                    "low": best_thr["low"],
                    "mid": best_thr["mid"],
                    "high": best_thr["high"],
                }
            else:
                thresholds = FRONTIER_THRESHOLDS
        else:
            thresholds = FRONTIER_THRESHOLDS

        cv_result = phase_4_cross_validation(df_v2, weights, thresholds)

    # Generate report
    print("\n" + "="*60)
    print("GENERATING FINAL REPORT")
    print("="*60)

    generate_report(
        scoring_result=scoring_result,
        weight_3f=w3f,
        weight_4f=w4f,
        threshold_result=pd.concat(threshold_results, ignore_index=True)
            if threshold_results and len(threshold_results) > 0 else None,
        cv_result=cv_result,
        output_dir=output_dir,
    )

    print("\n[OK] Optimization pipeline complete!")
    print(f"   Results saved to {output_dir}/")


if __name__ == "__main__":
    main()
