# -*- coding: utf-8 -*-
"""版本确认必修批次 M1-M4 单测（议会终审裁决）
M1 gold「未知客户」零值行从 B_CUSTS 剔除 + DQ 统计（源码探针钉住）
M2 geoOpenDrawer 泄漏+竞态修复（dispose + 代际守卫，源码探针）
M3 DATA_SHEET_NAME 硬编码 → resolve_data_sheet 探测（模拟 sheet 列表）
M4 空客户编号六处统一哨兵 _CUST_NAN_KEYS/_cust_key_ok（AST 抽取 + 调用点计数）
运行（从 sales_analytics_platform 目录）：python -m pytest test/test_version_confirmation.py -q
"""
import ast
import os
import sys

import pandas as pd
import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DASH = os.path.join(_ROOT, "dashboard")
_SRC_PATH = os.path.join(_DASH, "generate_dashboard.py")
_TPL_PATH = os.path.join(_DASH, "template.html")
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

with open(_SRC_PATH, encoding="utf-8-sig") as _f:
    SRC = _f.read()
with open(_TPL_PATH, encoding="utf-8-sig") as _f:
    TPL = _f.read()


def _load_helper():
    """AST 抽取 M4 哨兵常量+判定函数（generate_dashboard.py 不可整模块 import）。"""
    tree = ast.parse(SRC)
    ns = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", "") == "_CUST_NAN_KEYS" for t in node.targets):
            exec(compile(ast.Module(body=[node], type_ignores=[]), _SRC_PATH, "exec"), ns)
        if isinstance(node, ast.FunctionDef) and node.name == "_cust_key_ok":
            exec(compile(ast.Module(body=[node], type_ignores=[]), _SRC_PATH, "exec"), ns)
    assert "_CUST_NAN_KEYS" in ns and "_cust_key_ok" in ns, "M4 哨兵常量/函数未找到"
    return ns


# ---------------- M4 ----------------

class TestCustNanKeys:
    def test_sentinel_set_exact(self):
        ns = _load_helper()
        assert ns["_CUST_NAN_KEYS"] == {"nan", "None", "", "未知客户"}

    @pytest.mark.parametrize("bad", ["nan", "None", "", "未知客户", "  nan  ", " 未知客户 "])
    def test_reject(self, bad):
        assert _load_helper()["_cust_key_ok"](bad) is False

    @pytest.mark.parametrize("good", ["C001", "TPLINK", "深圳市金宝鑫科技有限公司", "KA-1"])
    def test_accept(self, good):
        assert _load_helper()["_cust_key_ok"](good) is True

    def test_six_sites_use_helper(self):
        """六处统一调用：_cust_key_ok 引用（含 .map() 形态）≥10 处，旧内联四元组清零。"""
        assert SRC.count("_cust_key_ok") >= 10, SRC.count("_cust_key_ok")
        assert 'isin(["nan","None","","未知客户"])' not in SRC
        assert 'not in ("nan","None","","未知客户")' not in SRC
        assert 'cid in ("nan","None","","未知客户")' not in SRC

    def test_pairs_filtered(self):
        """jx pairs 循环内新增哨兵剔除（原不滤，nan 行点击无响应）。"""
        i = SRC.find('for _c, _gc in _g.groupby("c"):')
        assert 0 < i and "_cust_key_ok(_c)" in SRC[i:i + 200]


# ---------------- M1 ----------------

class TestUnknownCustRowDropped:
    def test_call_loop_skips_sentinel(self):
        i = SRC.find("call=[]")
        assert 0 < i
        seg = SRC[i:i + 700]
        assert "_call_skip_unknown" in seg and "_cust_key_ok(cid)" in seg

    def test_dq_line_present(self):
        assert "无客户编号交易行（客户维度已剔除" in SRC
        assert "_cn_rex" in SRC

    def test_gold_fillna_documented(self):
        """data_cleaning 仍归并空客户编号（口径不变），断裂点在看板侧已修。"""
        with open(os.path.join(_ROOT, "processing", "shared", "data_cleaning.py"),
                  encoding="utf-8") as f:
            dc = f.read()
        assert 'fillna("未知客户")' in dc


# ---------------- M2 ----------------

class TestGeoDrawerRace:
    def test_dispose_before_open(self):
        i = TPL.find("function geoOpenDrawer(key){")
        assert 0 < i
        seg = TPL[i:i + 1200]
        assert "disposeInContainer" in seg and "TABS.drawer._content" in seg

    def test_generation_guard(self):
        i = TPL.find("function geoOpenDrawer(key){")
        seg = TPL[i:i + 2600]
        assert "_GEO_DET_GEN" in seg
        assert "if(_gen!==_GEO_DET_GEN)return;" in seg


# ---------------- M3 ----------------

class _FakeXL:
    def __init__(self, names):
        self.sheet_names = names


class TestResolveDataSheet:
    def _make_pd(self, monkeypatch, names, header_cols=("发货日期", "金额"), xl_raises=False):
        import pandas as real_pd
        if xl_raises:
            monkeypatch.setattr(real_pd, "ExcelFile",
                                lambda *a, **k: (_ for _ in ()).throw(IOError("boom")))
        else:
            monkeypatch.setattr(real_pd, "ExcelFile", lambda p, engine=None: _FakeXL(names))
        monkeypatch.setattr(real_pd, "read_excel",
                            lambda p, sheet_name=0, nrows=0, engine=None, usecols=None:
                            pd.DataFrame(columns=list(header_cols)))
        from processing.config.settings import resolve_data_sheet
        return resolve_data_sheet

    def test_preferred_hit_backward_compatible(self, monkeypatch):
        f = self._make_pd(monkeypatch, ["24-26", "说明", "25-27"])
        assert f("dummy.xlsx") == "24-26"

    def test_year_pattern_fallback_2027(self, monkeypatch):
        """2027 场景：源表改名 "25-27"，优先项未命中 → 探测到年份模式 sheet。"""
        f = self._make_pd(monkeypatch, ["说明", "25-27", "汇总"])
        assert f("dummy.xlsx") == "25-27"

    def test_first_pattern_wins(self, monkeypatch):
        f = self._make_pd(monkeypatch, ["25-27", "26-28"])
        assert f("dummy.xlsx") == "25-27"

    def test_sheet0_header_ok(self, monkeypatch):
        f = self._make_pd(monkeypatch, ["发货明细", "说明"], header_cols=("发货日期", "金额"))
        assert f("dummy.xlsx") == 0

    def test_sheet0_header_bad_still_zero(self, monkeypatch):
        f = self._make_pd(monkeypatch, ["目录", "说明"], header_cols=("无关列",))
        assert f("dummy.xlsx") == 0

    def test_xl_open_error_falls_back_zero(self, monkeypatch):
        f = self._make_pd(monkeypatch, [], xl_raises=True)
        assert f("dummy.xlsx") == 0
