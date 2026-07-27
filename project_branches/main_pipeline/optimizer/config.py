"""
Optimization search space and configuration definitions.
"""
import numpy as np

# ── Project paths ──
PROJECT_ROOT = None  # resolved at runtime by data_loader

# ── Previous production config (v3.1-core, baseline for comparison) ──
PREV_WEIGHTS_3F = {
    "F1f": 0.411,
    "F4": 0.236,
    "F5": 0.353,
}

# ── Current production config (v4.0, deployed) ──
PRODUCTION_WEIGHTS_4F = {
    "F1f": 0.100,
    "F4": 0.600,
    "F5": 0.200,
    "c6": 0.100,
}

# Candidate 4-factor weights from earlier analysis (v3.5 transition)
TRANSITION_WEIGHTS_4F = {
    "F1f": 0.368,
    "F4": 0.260,
    "F5": 0.362,
    "c6": 0.105,
}

# Optimized 4-factor weights (AUC-Shapley from report)
SHAPLEY_WEIGHTS_4F = {
    "F1f": 0.217,
    "F4": 0.314,
    "F5": 0.313,
    "c6": 0.293,
}

# ── Current risk thresholds ──
CURRENT_THRESHOLDS = {"low": 50, "mid": 60, "high": 75}

# Frontier threshold candidate
FRONTIER_THRESHOLDS = {"low": 50, "mid": 60, "high": 63}

# ── Phase 2: Weight grid search space ──
WEIGHT_SEARCH_3F = {
    "step": 0.025,
    "min": 0.05,
    "max": 0.70,
    "factors": ["F1f", "F4", "F5"],
}

WEIGHT_SEARCH_4F = {
    "step": 0.05,
    "min": 0.05,
    "max": 0.60,
    "factors": ["F1f", "F4", "F5", "c6"],
}

# ── Phase 3: Threshold search space ──
THRESHOLD_SEARCH = {
    "low": {"min": 30, "max": 60, "step": 5},
    "mid": {"min": 50, "max": 70, "step": 5},
    "high": {"min": 55, "max": 80, "step": 2},
}

# ── Phase 4: Time series CV folds ──
CV_FOLDS = [
    {"train": ("2020-07", "2023-12"), "test": ("2024-01", "2024-06")},
    {"train": ("2020-07", "2024-06"), "test": ("2024-07", "2024-12")},
    {"train": ("2020-07", "2024-12"), "test": ("2025-01", "2025-06")},
    {"train": ("2020-07", "2025-06"), "test": ("2025-07", "2025-11")},
]

# ── F4 score matrix (data-driven) ──
# yoy groups: high_growth (>0.5), growing (0~0.5), flat (-0.1~0), shrinking (<=-0.1)
# decay groups: accelerating (>0pp), stable (-10~0pp), decelerating (<-10pp)
DECAY_SCORE_MATRIX = {
    # (yoy_group, decay_group): score
    ("high_growth", "accelerating"): 20,    # 10.8% decline
    ("high_growth", "stable"):       10,    # ~4% decline
    ("high_growth", "decelerating"): 10,    # 2.3% decline
    ("growing",     "accelerating"): 40,    # 20.2% decline
    ("growing",     "stable"):       30,    # ~12% decline
    ("growing",     "decelerating"): 20,    # 4.5% decline
    ("flat",        "accelerating"): 70,    # 30.8% decline
    ("flat",        "stable"):       60,    # 28.6% decline
    ("flat",        "decelerating"): 50,    # 11.2% decline
    ("shrinking",   "accelerating"): 80,    # 54.5% decline
    ("shrinking",   "stable"):       80,    # 51.8% decline
    ("shrinking",   "decelerating"): 70,    # 34.4% decline
}

# consecutive decline bonus
CONSECUTIVE_BONUS_PER_MONTH = 5
CONSECUTIVE_BONUS_MAX = 25

# ── F1f buckets (data-driven merge) ──
F1F_BUCKETS = [
    (0.0,       np.inf,  10),    # 13.0% decline
    (-0.008,    0.0,     50),    # 15.7% decline (merged 20+50)
    (-np.inf,  -0.008,   80),    # 26.1% decline
]

# ── F5 buckets (fix top inversion) ──
F5_BUCKETS = [
    (0.70, np.inf, 10),    # 11.3% decline
    (0.50, 0.70,   40),    # 27.1% decline
    (0.30, 0.50,   70),    # 37.0% decline (highest!)
    (-np.inf, 0.30, 70),   # 35.3% decline — COLLAPSED from 90 to 70
]

# ── c6 buckets ──
C6_BUCKETS = [
    (-np.inf, -0.5,  95),    # 45.2% decline: severe shrink
    (-0.5,    -0.2,  75),    # 21.3% decline: shrink
    (-0.2,     0.0,  50),    # 17.4% decline: slight drop
    (0.0,      np.inf, 25),  # ~15% decline: stable/growth (undifferentiated)
]
