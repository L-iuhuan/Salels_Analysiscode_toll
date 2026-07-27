"""
Isolation Forest 兜底检测器。

当规则检测器全部通过时，对多维指标矩阵跑 IF 捕获规则未覆盖的异常。
结果不会覆盖规则检测结果，仅作为补充标记。
"""

import pandas as pd
import numpy as np

from config.settings import ANOMALY_DETECTION

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False


# These columns are required for the IF feature matrix.
# Fall back gracefully if some are missing.
FEATURE_CANDIDATES = [
    ("近12月收入", "revenue"),
    ("收入增长率", "growth"),
    ("近12月毛利率", "margin"),
    ("订单数", "orders"),
    ("在采品种数", "sku_count"),
    ("距上次采购天数", "last_purchase_days"),
    ("收入CV", "revenue_cv"),
    ("新品采购占比", "new_product_ratio"),
    ("Top1品种金额占比", "top1_conc"),
    ("ASP变化率", "asp_change"),
    ("连续下滑月数", "decline_months"),
    ("客单价", "avg_order_value"),
]


def _build_feature_matrix(customer_df: pd.DataFrame) -> tuple[np.ndarray, list[str], pd.Index]:
    """Build feature matrix from customer profile, filling missing columns with 0.

    Returns: (X, feature_names, customer_ids)
    """
    features = []
    names = []

    for col_name, _fallback in FEATURE_CANDIDATES:
        if col_name in customer_df.columns:
            s = pd.to_numeric(customer_df[col_name], errors="coerce").fillna(0)
            features.append(s.values)
            names.append(col_name)

    if len(features) < 3:
        return np.array([]), names, customer_df.index

    X = np.column_stack(features)
    # Clip extreme values
    X = np.clip(X, np.nanpercentile(X, 1, axis=0), np.nanpercentile(X, 99, axis=0))

    return X, names, customer_df["客户编号"].values if "客户编号" in customer_df.columns else customer_df.index


def detect_anomaly_isolation_forest(customer_df: pd.DataFrame) -> pd.DataFrame:
    """对多维指标矩阵跑 Isolation Forest。

    参数:
        customer_df: 客户全景表

    返回:
        DataFrame: [客户编号, 异常得分, 异常维度]
        仅在规则检测器全部通过时作为补充标记。
    """
    if not HAS_SKLEARN:
        print("  [IF] sklearn未安装，跳过Isolation Forest检测")
        return pd.DataFrame(columns=["客户编号", "异常得分", "异常维度"])

    if not ANOMALY_DETECTION.get("enable_isolation_forest", True):
        return pd.DataFrame(columns=["客户编号", "异常得分", "异常维度"])

    contamination = ANOMALY_DETECTION.get("contamination", 0.05)

    X, feature_names, cust_ids = _build_feature_matrix(customer_df)

    if len(X) < 10:
        print(f"  [IF] 样本不足 ({len(X)}), 跳过")
        return pd.DataFrame(columns=["客户编号", "异常得分", "异常维度"])

    if len(feature_names) < 3:
        print(f"  [IF] 特征不足 ({len(feature_names)}), 跳过")
        return pd.DataFrame(columns=["客户编号", "异常得分", "异常维度"])

    # Standardize
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Fit IF
    model = IsolationForest(
        contamination=contamination,
        random_state=42,
        n_estimators=100,
    )
    preds = model.fit_predict(X_scaled)
    scores = model.decision_function(X_scaled)

    # Identify anomalies (prediction = -1)
    anomaly_mask = preds == -1
    n_anomalies = int(anomaly_mask.sum())

    if n_anomalies == 0:
        print(f"  [IF] 未检测到异常 (n={len(X)})")
        return pd.DataFrame(columns=["客户编号", "异常得分", "异常维度"])

    # For each anomaly, find top 2 contributing dimensions
    # We approximate contribution by feature deviation from median
    median = np.median(X_scaled, axis=0)
    results = []

    for i in np.where(anomaly_mask)[0]:
        deviations = np.abs(X_scaled[i] - median)
        top_indices = np.argsort(deviations)[-2:][::-1]
        top_dims = ", ".join(
            f"{feature_names[j]}(偏离{deviations[j]:.1f}σ)" for j in top_indices
        )
        results.append({
            "客户编号": cust_ids[i],
            "异常得分": round(float(scores[i]), 4),
            "异常维度": top_dims,
        })

    df = pd.DataFrame(results)
    df = df.sort_values("异常得分", kind='stable')

    print(f"  [IF] 检测到 {n_anomalies} 个异常 (n={len(X)}, contamination={contamination})")
    return df
