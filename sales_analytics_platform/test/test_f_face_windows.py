# -*- coding: utf-8 -*-
"""F 面「半年度专项」方案C 窗口语义单测（设计稿 project_analysis\F面重设计方案C_20260907.md）。

覆盖（任务书 ≥8 用例）：
    1. _half_windows 12 个月全覆盖 + 7 月边界（已完结最近半年度=当年 H1）
    2. 窗口区间 ym 字符串格式（与 rex["_ym"] 比较友好）
    3. _win_frame 三窗过滤正确性（合成月度帧，校验窗口内求和/窗口外剔除）
    4. _win_frame 空窗口 → 空帧（列结构保留）
    5. _win_last_two_months 窗口内末两月锚定（V1 缺陷场景：8 月数据锚=8月 vs 7月，非全局上月错位）
    6. _win_last_two_months 窗口首月钳制（前月越窗 → None）
    7. _win_last_two_months 窗口内无数据 → (None, None)
    8. _mom_pct null 语义（前月无数据/为 0/末月无数据 → None，禁止填 0 伪造）

取数方式：generate_dashboard.py 是整管脚本（import 即跑全量），故用 AST 抽取
模块级纯函数（_half_windows/_win_frame/_win_last_two_months/_mom_pct）在隔离命名空间编译，
只注入 pandas——与主流程同一份源码，不存在副本漂移。

运行（从 sales_analytics_platform 目录）：python -m pytest test/test_f_face_windows.py -q
"""
import ast
import os

import pandas as pd
import pytest

_DASH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dashboard"))
_SRC_PATH = os.path.join(_DASH, "generate_dashboard.py")

_PURE_FUNCS = ("_half_windows", "_win_frame", "_win_last_two_months", "_mom_pct")


def _load_pure_funcs():
    """AST 抽取 F 面窗口纯函数（generate_dashboard.py 不可整模块 import：顶层即全量跑批）。"""
    with open(_SRC_PATH, encoding="utf-8-sig") as f:
        tree = ast.parse(f.read())
    ns = {"pd": pd}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in _PURE_FUNCS:
            exec(compile(ast.Module(body=[node], type_ignores=[]), _SRC_PATH, "exec"), ns)
    missing = set(_PURE_FUNCS) - set(ns)
    assert not missing, f"纯函数未在 generate_dashboard.py 找到: {missing}"
    return ns


_g = _load_pure_funcs()
_half_windows = _g["_half_windows"]
_win_frame = _g["_win_frame"]
_win_last_two_months = _g["_win_last_two_months"]
_mom_pct = _g["_mom_pct"]


def _mk_month(ym, rev):
    return pd.DataFrame({"_ym": [ym], "_rev": [float(rev)], "_profit": [float(rev) * 0.2],
                         "_qty": [10.0], "_cust": ["C1"]})


def _sample_rex_by_ym():
    """2025-07 ~ 2026-08 每月一帧，rev=月份数字（如 2026-08 → 8.0），便于手算校验。"""
    out = {}
    for y, months in ((2025, range(7, 13)), (2026, range(1, 9))):
        for m in months:
            out[f"{y}-{m:02d}"] = _mk_month(f"{y}-{m:02d}", m)
    return out


class TestHalfWindows:
    @pytest.mark.parametrize("month,cur,ph,py", [
        ("2026-01", "2026H1", "2025H2", "2025H1"),
        ("2026-02", "2026H1", "2025H2", "2025H1"),
        ("2026-03", "2026H1", "2025H2", "2025H1"),
        ("2026-04", "2026H1", "2025H2", "2025H1"),
        ("2026-05", "2026H1", "2025H2", "2025H1"),
        ("2026-06", "2026H1", "2025H2", "2025H1"),
        ("2026-07", "2026H1", "2025H2", "2025H1"),   # 7 月边界：H2 刚开始 → 已完结最近半年度（当年 H1）
        ("2026-08", "2026H2", "2026H1", "2025H2"),
        ("2026-09", "2026H2", "2026H1", "2025H2"),
        ("2026-10", "2026H2", "2026H1", "2025H2"),
        ("2026-11", "2026H2", "2026H1", "2025H2"),
        ("2026-12", "2026H2", "2026H1", "2025H2"),
    ])
    def test_half_windows_12months(self, month, cur, ph, py):
        w_cur, w_ph, w_py = _half_windows(month)
        assert w_cur["label"] == cur
        assert w_ph["label"] == ph
        assert w_py["label"] == py

    def test_july_boundary_takes_completed_half(self):
        """7 月数据（H2 刚开始）→ W_cur=当年 H1（已完结），而非 H2。用户拍板的开放决策点。"""
        w_cur, w_ph, w_py = _half_windows("2026-07")
        assert w_cur["key"] == "26h1"
        assert w_cur["start"] == "2026-01-01" and w_cur["end"] == "2026-06-30"
        assert w_ph["key"] == "25h2"
        assert w_py["key"] == "25h1"

    def test_int_period_input_equivalent(self):
        """入参兼容 YYYYMM int（任务书契约）。"""
        a = _half_windows(202608)
        b = _half_windows("2026-08")
        assert a[0] == b[0] and a[1] == b[1] and a[2] == b[2]

    def test_window_interval_ym_string_compare_friendly(self):
        """8 月数据三窗区间：ym 字符串可字典序比较（与 rex['_ym'] 同格式）。"""
        w_cur, w_ph, w_py = _half_windows("2026-08")
        assert (w_cur["ym_start"], w_cur["ym_end"]) == ("2026-07", "2026-12")
        assert (w_ph["ym_start"], w_ph["ym_end"]) == ("2026-01", "2026-06")
        assert (w_py["ym_start"], w_py["ym_end"]) == ("2025-07", "2025-12")
        assert w_cur["ym_start"] <= "2026-08" <= w_cur["ym_end"]


class TestWinFrame:
    def test_three_window_filter_sums(self):
        """三窗过滤正确性：窗口内月份求和、窗口外剔除（数据月份 2026-08）。"""
        rex_by_ym = _sample_rex_by_ym()
        w_cur, w_ph, w_py = _half_windows("2026-08")
        cur = _win_frame(rex_by_ym, w_cur)
        ph = _win_frame(rex_by_ym, w_ph)
        py = _win_frame(rex_by_ym, w_py)
        # 2026H2 当前仅有 7/8 月数据 → 7+8=15
        assert float(cur["_rev"].sum()) == 15.0
        assert set(cur["_ym"]) == {"2026-07", "2026-08"}
        # 2026H1 → 1+2+3+4+5+6=21
        assert float(ph["_rev"].sum()) == 21.0
        # 2025H2 → 7+8+9+10+11+12=57
        assert float(py["_rev"].sum()) == 57.0

    def test_empty_window_returns_empty_frame_with_columns(self):
        rex_by_ym = _sample_rex_by_ym()
        w_future, _, _ = _half_windows("2027-02")
        empty = _win_frame(rex_by_ym, w_future)
        assert len(empty) == 0
        assert list(empty.columns) == list(_mk_month("2026-01", 1).columns)


class TestWinLastTwoMonths:
    def test_anchor_last_two_months_inside_window(self):
        """V1 缺陷场景实证：8 月数据、W_cur=2026H2 → 锚=2026-08 vs 2026-07（窗口内），
        而非旧实现的全局"上一月"错位锚（7 月数据时锚=6月落在 H1 窗口外 → mom 恒空）。"""
        rex_by_ym = _sample_rex_by_ym()
        w_cur, _, _ = _half_windows("2026-08")
        cur_ym, prev_ym = _win_last_two_months(rex_by_ym, w_cur)
        assert cur_ym == "2026-08"
        assert prev_ym == "2026-07"

    def test_july_data_anchor_inside_h1(self):
        """7 月数据、W_cur=2026H1（窗口=1-6 月）→ 锚=窗口内末月 2026-06 vs 2026-05。
        这正是旧缺陷的修复点：旧全局锚=6 月（落在 H1 外→mom 恒空），新锚永远在窗口内。"""
        rex_by_ym = _sample_rex_by_ym()
        w_cur, _, _ = _half_windows("2026-07")
        cur_ym, prev_ym = _win_last_two_months(rex_by_ym, w_cur)
        assert (cur_ym, prev_ym) == ("2026-06", "2026-05")

    def test_first_month_of_window_prev_clamped_to_none(self):
        """末月=窗口首月时前月越窗 → prev=None（窗口内取，绝不越窗）。"""
        rex_by_ym = {"2026-07": _mk_month("2026-07", 7)}
        w_cur, _, _ = _half_windows("2026-08")
        cur_ym, prev_ym = _win_last_two_months(rex_by_ym, w_cur)
        assert cur_ym == "2026-07"
        assert prev_ym is None

    def test_no_data_in_window_returns_none_pair(self):
        rex_by_ym = {"2025-12": _mk_month("2025-12", 12)}
        w_cur, _, _ = _half_windows("2026-08")
        assert _win_last_two_months(rex_by_ym, w_cur) == (None, None)


class TestMomPct:
    def test_normal_pair(self):
        assert _mom_pct(120.0, 100.0) == 20.0
        assert _mom_pct(80.0, 100.0) == -20.0

    def test_prev_zero_or_none_is_null_not_zero(self):
        """null 语义（任务书红线）：前月无数据或为 0 → None（JSON null→模板 '—'），禁止填 0 伪造。"""
        assert _mom_pct(100.0, 0.0) is None
        assert _mom_pct(100.0, None) is None

    def test_cur_none_is_null(self):
        assert _mom_pct(None, 100.0) is None

    def test_cur_zero_legit_negative_100(self):
        """末月真实归零（有前月数据）→ -100 是合法值，不得误杀。"""
        assert _mom_pct(0.0, 100.0) == -100.0
