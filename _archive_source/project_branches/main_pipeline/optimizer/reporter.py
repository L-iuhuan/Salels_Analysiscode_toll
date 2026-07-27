"""
Report generator for optimization results.
"""
import os
import json
import datetime


def generate_report(scoring_result=None, weight_3f=None, weight_4f=None,
                    threshold_result=None, cv_result=None,
                    output_dir="output/optimization"):
    """
    Generate a comprehensive optimization report.

    Parameters
    ----------
    scoring_result : dict with scoring function validation results
    weight_3f : pd.DataFrame with 3-factor weight search results
    weight_4f : pd.DataFrame with 4-factor weight search results
    threshold_result : pd.DataFrame with threshold search results
    cv_result : dict from crossval.run_time_series_cv
    output_dir : str
    """
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "optimization_report.md")
    json_path = os.path.join(output_dir, "optimization_results.json")

    lines = []
    lines.append("# 风险衰退模型 v4.0 — 自动调优报告\n")
    lines.append(f"**生成日期**: {datetime.date.today().isoformat()}\n")

    # Section 1: Scoring function improvements
    lines.append("## Phase 1: 因子评分函数优化\n")
    if scoring_result:
        # scoring_result is a dict — format it
        if "v2_metrics" in scoring_result:
            v1 = scoring_result.get("v1_metrics", {})
            v2 = scoring_result.get("v2_metrics", {})
            lines.append(f"- **v1**: AUC={v1.get('auc','N/A'):.4f}, "
                         f"Precision={v1.get('precision','N/A'):.4f}, "
                         f"Recall={v1.get('recall','N/A'):.4f}, "
                         f"F1={v1.get('f1','N/A'):.4f}")
            lines.append(f"- **v2 (optimized)**: AUC={v2.get('auc','N/A'):.4f}, "
                         f"Precision={v2.get('precision','N/A'):.4f}, "
                         f"Recall={v2.get('recall','N/A'):.4f}, "
                         f"F1={v2.get('f1','N/A'):.4f}")
            delta_auc = v2.get('auc',0) - v1.get('auc',0)
            delta_prec = v2.get('precision',0) - v1.get('precision',0)
            lines.append(f"- **Delta**: AUC={delta_auc:+.4f}, "
                         f"Precision={delta_prec:+.4f}")
        for fr in scoring_result.get("factor_results", []):
            name, r = fr
            lines.append(f"- **{name}**: AUC={r.get('auc','N/A'):.4f}, "
                         f"Corr={r.get('correlation','N/A'):.4f}, "
                         f"Monotonic={'[OK]' if r.get('monotonic') else '[NO]'}")
    else:
        lines.append("（见下方 Phase 1 输出结果）\n")

    # Section 2: Weight search results
    lines.append("\n## Phase 2: 权重网格搜索\n")
    if weight_3f is not None and len(weight_3f) > 0:
        best_3f = weight_3f.iloc[0]
        lines.append("### 三因子最优权重\n")
        lines.append(f"- **F1f** = {best_3f['w_F1f']:.3f}, "
                     f"**F4** = {best_3f['w_F4']:.3f}, "
                     f"**F5** = {best_3f['w_F5']:.3f}")
        lines.append(f"- AUC={best_3f['auc']:.4f}, "
                     f"Precision={best_3f['precision']:.4f}, "
                     f"Recall={best_3f['recall']:.4f}, "
                     f"F1={best_3f['f1']:.4f}")

    if weight_4f is not None and len(weight_4f) > 0:
        best_4f = weight_4f.iloc[0]
        lines.append("\n### 四因子最优权重\n")
        lines.append(f"- **F1f** = {best_4f['w_F1f']:.3f}, "
                     f"**F4** = {best_4f['w_F4']:.3f}, "
                     f"**F5** = {best_4f['w_F5']:.3f}, "
                     f"**c6** = {best_4f['w_c6']:.3f}")
        lines.append(f"- AUC={best_4f['auc']:.4f}, "
                     f"Precision={best_4f['precision']:.4f}, "
                     f"Recall={best_4f['recall']:.4f}, "
                     f"F1={best_4f['f1']:.4f}")
        lines.append(f"- Pareto 前沿方案数: {len(_find_pareto(weight_4f))}")
    lines.append("")

    # Section 3: Threshold calibration
    lines.append("\n## Phase 3: 阈值协同校准\n")
    if threshold_result is not None and len(threshold_result) > 0:
        top_thr = threshold_result.iloc[0]
        lines.append(f"### 最优阈值方案\n")
        lines.append(f"- **阈值**: [{top_thr['low']}, {top_thr['mid']}, {top_thr['high']}]")
        lines.append(f"- Composite Score: {top_thr['composite_score']:.4f}")
        lines.append(f"- AUC: {top_thr['auc']:.4f}")
        lines.append(f"- Precision: {top_thr['precision']:.4f}")
        lines.append(f"- Recall: {top_thr['recall']:.4f}")
        lines.append(f"- F1: {top_thr['f1']:.4f}")
        lines.append(f"- 极高占比: {top_thr['extreme_pct']:.4f} ({top_thr['extreme_pct']*100:.1f}%)")
        lines.append(f"- 极高衰退率: {top_thr['extreme_decline_rate']:.4f}")
        lines.append(f"- 单调性: {'[OK]' if top_thr['monotonic'] else '[NO]'}")
    lines.append("")

    # Section 4: Cross-validation
    lines.append("\n## Phase 4: 时间序列交叉验证\n")
    if cv_result and "aggregate" in cv_result:
        agg = cv_result["aggregate"]
        lines.append(f"- AUC: mean={agg['auc_mean']:.4f}, std={agg['auc_std']:.4f}")
        lines.append(f"- Precision: mean={agg['precision_mean']:.4f}, std={agg['precision_std']:.4f}")
        lines.append(f"- F1: mean={agg['f1_mean']:.4f}")
        lines.append(f"- AUC gap (train-test): mean={agg['auc_gap_mean']:.4f}, max={agg['auc_gap_max']:.4f}")
        lines.append(f"- 时间稳定性: {'[OK] 稳定' if agg['stable'] else '[!]️ 需关注'}")
    lines.append("")

    # Section 5: Recommendations
    lines.append("\n## 推荐配置\n")
    lines.append("```json\n")
    if weight_4f is not None and len(weight_4f) > 0:
        best = weight_4f.iloc[0]
        lines.append('"risk_weights_4f": {\n')
        lines.append(f'    "毛利率趋势斜率": {best["w_F1f"]:.3f},\n')
        lines.append(f'    "增速衰减": {best["w_F4"]:.3f},\n')
        lines.append(f'    "自比健康度": {best["w_F5"]:.3f},\n')
        lines.append(f'    "大客户订货变化(c6)": {best["w_c6"]:.3f}\n')
        lines.append("},\n")
    if threshold_result is not None and len(threshold_result) > 0:
        top = threshold_result.iloc[0]
        lines.append('"risk_thresholds": {\n')
        lines.append(f'    "risk_low_max": {top["low"]},\n')
        lines.append(f'    "risk_mid_max": {top["mid"]},\n')
        lines.append(f'    "risk_high_max": {top["high"]}\n')
        lines.append("}\n")
    lines.append("```\n")

    report = "\n".join(lines)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  Report saved to {report_path}")

    # Save JSON
    json_data = {}
    if weight_3f is not None and len(weight_3f) > 0:
        json_data["weight_3f_best"] = weight_3f.iloc[0].to_dict()
    if weight_4f is not None and len(weight_4f) > 0:
        json_data["weight_4f_best"] = weight_4f.iloc[0].to_dict()
    if threshold_result is not None and len(threshold_result) > 0:
        json_data["threshold_best"] = threshold_result.iloc[0].to_dict()
    if cv_result and "aggregate" in cv_result:
        json_data["cv"] = cv_result["aggregate"]

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    print(f"  JSON saved to {json_path}")

    return report_path


def _find_pareto(weight_df):
    """Quick pareto for report — delegates to weight_search."""
    from optimizer.weight_search import find_pareto_frontier
    return find_pareto_frontier(weight_df)
