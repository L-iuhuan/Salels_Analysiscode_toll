# -*- coding: utf-8 -*-
"""A 车道 backlog ⭐⭐⭐ 单测：glossary 术语卡渲染闭环 + 下拉控件统一。

不直接 import generate_dashboard.py（其模块级会触发全量看板构建，>100s），
改为探测已生成的产物 HTML 与源码，保证轻量化且与验收口径一致。
"""
import glob
import os
import re
import sys

import pytest
import yaml

_DASH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dashboard"))
_PKG = os.path.dirname(_DASH)


def _latest_dashboard_html():
    cands = glob.glob(os.path.join(_PKG, "output", "dashboard", "销售数据分析看板_*.html"))
    return max(cands, key=os.path.getmtime) if cands else None


def _html_content():
    path = _latest_dashboard_html()
    if not path:
        pytest.skip("未找到已生成的看板 HTML，跳过产物探针测试")
    with open(path, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def faces():
    with open(os.path.join(_DASH, "faces.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)["faces"]


def test_all_select_have_form_select_class():
    """template.html 全部 <select> 统一挂 .form-select 类。"""
    with open(os.path.join(_DASH, "template.html"), encoding="utf-8") as f:
        html = f.read()
    tags = re.findall(r"<select\b[^>]*>", html)
    assert tags, "template.html 中应至少存在一个 <select>"
    missing = [t for t in tags if "form-select" not in t]
    assert not missing, f"以下 <select> 未挂 form-select 类：{missing}"


def test_glossary_terms_rendered_in_dashboard_html(faces):
    """faces.yaml 声明的 glossary 术语在看板产物 HTML 的 face-meta 区块中可检索。"""
    html = _html_content()
    for face_id, cfg in faces.items():
        if cfg.get("enabled") is False or cfg.get("visible") is False:
            continue
        if face_id == "R":
            # R 面通过 risk_action md 单独注入，主看板模板未挂 FACE_META_R 占位符，不在本产物探针覆盖
            continue
        meta = f'id="faceMeta{face_id}"'
        assert meta in html, f"面 {face_id} 的 meta 区块未渲染"
        # 定位该面 meta 区块（注意 summary 等子元素也含 faceMeta 字样，须精确匹配面级 id）
        start = html.find(meta)
        nxt = re.search(r'id="faceMeta[A-Z]"', html[start + 1:])
        end = start + 1 + nxt.start() if nxt else -1
        block = html[start:end] if end != -1 else html[start:]
        for item in (cfg.get("glossary") or []):
            term = item.get("term", "")
            assert term in block, f"面 {face_id} 的术语 '{term}' 未在其 meta 区块中渲染"


def test_glossary_definitions_have_quantified_thresholds_or_known_sources(faces):
    """模糊术语须有量级定义：关键阈值/来源取自代码/台账，禁止占位词。"""
    fuzzy_words = {"待定", "也许", "可能", "若干", "适量", "较高", "较低", "前列"}
    quantified_terms = {"KA+AA", "帕累托分类"}  # 本次补量化的重点术语
    for face_id, cfg in faces.items():
        for item in (cfg.get("glossary") or []):
            term = item.get("term", "")
            definition = item.get("definition", "")
            # 通用：不允许出现占位软词
            found_soft = {w for w in fuzzy_words if w in definition}
            assert not found_soft, f"术语 '{term}' 含软词：{found_soft}"
            # 重点量化术语必须带“>、<、≥、≤、%”或明确来源
            if term in quantified_terms:
                assert (re.search(r"[><≥≤%]", definition)
                        or "来源：" in definition
                        or "settings" in definition), \
                    f"术语 '{term}' 未量化：{definition}"


def test_faces_yaml_glossary_sections_present(faces):
    """每个启用且可见的面均声明 glossary（如设计议会要求）。"""
    for face_id, cfg in faces.items():
        if cfg.get("enabled") is False or cfg.get("visible") is False:
            continue
        assert cfg.get("glossary"), f"面 {face_id} 缺少 glossary 节"
