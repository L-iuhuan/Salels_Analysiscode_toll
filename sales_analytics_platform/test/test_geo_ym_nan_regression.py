# -*- coding: utf-8 -*-
"""8 月数据崩溃回归（generate_dashboard.py E面2056/C面2762 同款 sorted 修复）。

崩溃事实：8 月 silver 第 206899 行为全空行（发货日期/金额/利润/数量全 NaN），
取材段 `rex["_ym"] = rex["_d"].dt.strftime("%Y-%m")` 使该行 _ym=NaN(float)，
E面 `sorted(rex["_ym"].unique())` 混合 float/str → TypeError 崩在 [7/7]。
非 geo 提交引入（_ym 在 geo 挂列之前已建），geo 代码未污染 _ym；
本测试钉住：①崩溃前提可复现 ②生成器内同款过滤惯用式不再炸
③无 NaT 数据（6月型）下过滤式与朴素 sorted 完全一致（零漂移）
④groupby 月度聚合默认 dropna，NaN 月键行本就被排除（全空行零贡献）
⑤解析器对 NaN/None/任意异常输入不炸且返回 (str,str,bool)。
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dashboard"))

from geo_resolver import load_dict, resolve_region  # noqa: E402

D = load_dict()


def _rex_with_nat():
    """模拟取材段 rex：正常行 + 1 行全空行（8 月 silver 206899 行形态，金额全 NaN→0）。"""
    return pd.DataFrame({
        "发货日期": ["2026-08-01", None],
        "金额": [100.0, None],
        "发货地址": ["广东省深圳市宝安区", None],
    })


def _build_ym(rex):
    """与 generate_dashboard.py 取材段同款两式（silver 路径 line ~932）。"""
    rex = rex.copy()
    rex["_d"] = pd.to_datetime(rex["发货日期"], errors="coerce")
    rex["_ym"] = rex["_d"].dt.strftime("%Y-%m")
    return rex


class TestYmNaNCrashRegression:
    def test_nat_row_yields_float_nan_in_ym(self):
        """复现前提：NaT 日期行 → _ym 为 NaN(float)，unique() 混型。"""
        rex = _build_ym(_rex_with_nat())
        assert rex["_ym"].isna().sum() == 1
        assert "float" in {type(x).__name__ for x in rex["_ym"].unique()}

    def test_generator_guard_idiom_sorts_clean(self):
        """生成器 2056/2762 同款惯用式：过滤非字符串月键后 sorted 不炸。"""
        rex = _build_ym(_rex_with_nat())
        all_months = sorted(m for m in rex["_ym"].unique() if isinstance(m, str))
        assert all_months == ["2026-08"]
        assert all(isinstance(m, str) for m in all_months)

    def test_guard_inert_on_nat_free_data(self):
        """6月型数据（无 NaT）：过滤式 ≡ 朴素 sorted——既有数据零漂移。"""
        rex = _build_ym(pd.DataFrame({"发货日期": ["2026-04-01", "2026-05-01", "2026-06-01"]}))
        naive = sorted(rex["_ym"].unique())
        guarded = sorted(m for m in rex["_ym"].unique() if isinstance(m, str))
        assert naive == guarded == ["2026-04", "2026-05", "2026-06"]

    def test_groupby_excludes_nan_month_key(self):
        """佐证：pandas groupby 默认 dropna=True，NaN 月键行本就被月度聚合排除。"""
        rex = _build_ym(_rex_with_nat())
        rex["_rev"] = pd.to_numeric(rex["金额"], errors="coerce").fillna(0)
        t_mo = rex.groupby("_ym").agg(r=("_rev", "sum")).reset_index()
        assert t_mo["_ym"].isna().sum() == 0
        assert float(t_mo["r"].sum()) == 100.0  # 全空行零贡献


class TestResolverDefensive:
    @pytest.mark.parametrize("bad", [None, float("nan"), "", "   ", "nan", "None", 12345, "-" * 50])
    def test_any_input_never_raises_returns_str_tuple(self, bad):
        region, sub, abroad = resolve_region(bad, D)
        assert isinstance(region, str) and isinstance(sub, str) and isinstance(abroad, bool)
        assert region != ""  # region 永不为空串（未识别兜底）

    @pytest.mark.parametrize("bad", [None, float("nan"), "nan", "", "   "])
    def test_emptyish_input_falls_to_unidentified(self, bad):
        assert resolve_region(bad, D)[0] == "未识别"
