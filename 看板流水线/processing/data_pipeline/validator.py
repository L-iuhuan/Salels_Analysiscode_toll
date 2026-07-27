"""
SimpleValidator — 轻量级数据验证器（纯 pandas，无额外依赖）。

在管线的 4 个节点插入验证：
  V1: raw      — 源数据（ERP 导出）
  V2: clean    — 清洗后（负销量过滤 + Winsorization）
  V3: silver   — 月度聚合后（客户/产品/交叉表）
  V4: gold     — 客户/产品 Gold 层输出

所有验证方法为 staticmethod，返回 {"valid": bool, "issues": list[str]}。
验证失败仅打印警告，不阻断管线（warn + continue）。
"""

import pandas as pd
from typing import List, Dict, Any, Optional


class SimpleValidator:
    """轻量级数据验证器。"""

    # ----------------------------------------------------------------
    # 通用检查方法
    # ----------------------------------------------------------------

    @staticmethod
    def check_required_columns(df: pd.DataFrame, required: List[str]) -> List[str]:
        """检查必填列是否存在，返回缺失列名列表。"""
        return [c for c in required if c not in df.columns]

    @staticmethod
    def check_null_constraint(
        df: pd.DataFrame, cols: List[str], max_null_pct: float = 0.50
    ) -> List[str]:
        """检查指定列的空值率是否超过阈值。"""
        issues = []
        for col in cols:
            if col not in df.columns:
                issues.append(f"{col}: column missing")
                continue
            null_pct = df[col].isna().mean()
            if null_pct > max_null_pct:
                issues.append(
                    f"{col}: {null_pct:.1%} null (threshold: {max_null_pct:.1%})"
                )
        return issues

    @staticmethod
    def check_value_range(
        df: pd.DataFrame, col: str, lo: Optional[float] = None, hi: Optional[float] = None
    ) -> List[str]:
        """检查数值列的值范围。"""
        if col not in df.columns:
            return [f"{col}: column missing"]
        s = df[col].dropna()
        issues = []
        if lo is not None and (s < lo).any():
            n = (s < lo).sum()
            issues.append(f"{col}: {n} rows below {lo} (min={s.min():.2f})")
        if hi is not None and (s > hi).any():
            n = (s > hi).sum()
            issues.append(f"{col}: {n} rows above {hi} (max={s.max():.2f})")
        return issues

    @staticmethod
    def check_category_values(
        df: pd.DataFrame, col: str, allowed: List[str]
    ) -> List[str]:
        """检查分类列的值是否在允许集合内。"""
        if col not in df.columns:
            return [f"{col}: column missing"]
        actual = set(df[col].dropna().unique())
        invalid = actual - set(allowed)
        if invalid:
            return [f"{col}: invalid values {invalid}"]
        return []

    # ----------------------------------------------------------------
    # 阶段特定验证
    # ----------------------------------------------------------------

    @staticmethod
    def _report(
        issues: List[str], stage: str, context: str = ""
    ) -> Dict[str, Any]:
        """格式化验证结果。"""
        prefix = f"  [Validator:{stage}]"
        if issues:
            for issue in issues:
                print(f"{prefix} {issue}")
        if context:
            print(f"{prefix} {context}")
        return {"valid": len(issues) == 0, "issues": issues}

    def validate(self, df: pd.DataFrame, stage: str) -> Dict[str, Any]:
        """统一验证入口 — 按阶段路由到 validate_raw / validate_clean。"""
        if stage == "raw":
            return self.validate_raw(df)
        elif stage == "clean":
            return self.validate_clean(df)
        else:
            print(f"  [Validator] 未知验证阶段 '{stage}'，跳过")
            return {"valid": True, "issues": []}

    def validate_raw(self, df: pd.DataFrame) -> Dict[str, Any]:
        """V1：源数据验证。"""
        issues = []
        issues += self.check_required_columns(
            df, ["客户编号", "产品品种", "数量", "金额", "发货日期"]
        )
        issues += self.check_null_constraint(df, ["客户编号", "发货日期"])
        issues += self.check_value_range(df, "金额", lo=0)
        return self._report(issues, "raw")

    def validate_clean(self, df: pd.DataFrame) -> Dict[str, Any]:
        """V2：清洗后数据验证。"""
        issues = []
        issues += self.check_required_columns(
            df, ["客户编号", "产品品种", "数量", "金额", "利润", "发货日期", "_毛利率"]
        )
        issues += self.check_value_range(df, "数量", lo=0)
        issues += self.check_value_range(df, "_毛利率", lo=-0.50, hi=0.75)
        issues += self.check_null_constraint(df, ["发货日期"])
        return self._report(issues, "clean")

    def validate_silver(
        self, silver: Dict[str, pd.DataFrame]
    ) -> Dict[str, Any]:
        """V3：Silver 层验证。"""
        all_issues = []
        for key, df in silver.items():
            issues = []
            issues += self.check_required_columns(df, ["_月", "rev_sum", "qty_sum"])
            issues += self.check_value_range(df, "rev_sum", lo=0)
            issues += self.check_value_range(df, "qty_sum", lo=0)
            if issues:
                for issue in issues:
                    print(f"  [Validator:silver/{key}] {issue}")
            all_issues.extend(issues)
        return {"valid": len(all_issues) == 0, "issues": all_issues}

    def validate_gold(
        self, df: pd.DataFrame, label: str = "gold"
    ) -> Dict[str, Any]:
        """V4：Gold 层验证。

        检查评分列范围 [0,100] 和常见分类字段的有效性。
        """
        issues = []
        # 自动检测评分列
        score_cols = [
            c for c in df.columns if "得分" in str(c) or "分值" in str(c) or "评分" in str(c)
        ]
        for col in score_cols:
            if col in df.columns:
                s = df[col].dropna()
                if len(s) > 0:
                    if (s < 0).any() or (s > 100).any():
                        issues.append(
                            f"{col}: score out of [0,100] range (min={s.min():.1f}, max={s.max():.1f})"
                        )

        # 空行检查
        if len(df) == 0:
            issues.append("DataFrame is empty")

        return self._report(issues, f"gold/{label}")
