# -*- coding: utf-8 -*-
"""R 面策展引擎 v2 单测（设计：project_analysis\\R面生成质量深化设计_20260908.md §2）。

覆盖：8 通道入选规则 / 异常详情解析 / 模板渲染 / 去重合并 / Top12 排序 /
上月对拍（连续月、恶化好转、本月解除，构造两月 md）/ 行动种子 / 结转修复 / 溢出附件。

运行（从 sales_analytics_platform 目录）：python -m pytest test/test_risk_curation.py -q
"""
import json
import os
import sys

import pandas as pd
import pytest

_DASH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dashboard"))
_PKG = os.path.dirname(_DASH)
sys.path.insert(0, _DASH)
sys.path.insert(0, _PKG)

import generate_risk_face as grf  # noqa: E402

CFG = grf._load_templates()


def _gold(dfs):
    """按表名注入合成 gold 数据（缺失表返回 None，静默）。"""
    def fake(name):
        return dfs.get(name)
    return fake


# ---------- 异常详情解析与模板 ----------

def test_parse_anomaly_detail():
    info = grf._parse_anomaly_detail("近12月收入17,894, 增长率-100%, 连续下滑2个月")
    assert info["rev12m"] == "1.8"
    assert info["growth"] == "-100"
    assert info["months"] == "连续下滑2个月"


def test_parse_anomaly_detail_empty():
    assert grf._parse_anomaly_detail("") == {}


def test_template_render_and_missing_placeholder():
    tpl = grf._render_template(CFG, "采购中断", "高",
                               {"rev12m": "50.0", "days": "130", "zero_pct": "30"})
    assert "50.0万" in tpl and "130天" in tpl
    tpl2 = grf._render_template(CFG, "采购中断", "高", {})
    assert "{rev12m}" in tpl2  # 缺省占位符留原样，不抛异常


def test_template_fallback_default():
    out = grf._render_template(CFG, "未识别类型XYZ", "高", {}, fallback_detail="详情ABC")
    assert "详情ABC" in out


# ---------- 通道入选规则 ----------

def test_ch_anomaly_log_levels_and_detail():
    df = pd.DataFrame({"客户编号": ["C1", "C2"],
                       "异常类型": ["营收断崖", "库存呆滞"],
                       "异常等级": ["高", "低"],   # 低不入选
                       "异常详情": ["近12月收入17894, 增长率-100%, 连续下滑2个月", "x"]})
    out = grf._ch_anomaly_log(CFG)  # noqa: F841 占位防误读
    out = []
    old = grf._read_gold
    grf._read_gold = _gold({"异常日志.csv": df})
    try:
        out = grf._ch_anomaly_log(CFG)
    finally:
        grf._read_gold = old
    assert len(out) == 1 and out[0]["customer"] == "C1" and out[0]["level"] == "高"
    assert "1.8万" in out[0]["suggestion"]


def test_ch_revenue_shock_drop():
    df = pd.DataFrame({"客户编号": ["C1", "C2"], "月份": ["2026-08", "2026-08"],
                       "月收入": [200000.0, 200000.0], "月环比%": [-60.0, -20.0]})
    old = grf._read_gold
    grf._read_gold = _gold({"客户月度趋势.csv": df})
    try:
        out = grf._ch_revenue_shock("202608", CFG)
    finally:
        grf._read_gold = old
    assert len(out) == 1 and out[0]["types"] == ["营收断崖"] and out[0]["level"] == "高"
    assert abs(out[0]["loss"] - (500000.0 - 200000.0)) < 1  # 上月 50万 → 损失 30万


def test_ch_revenue_shock_surge_and_min_rev():
    df = pd.DataFrame({"客户编号": ["C1", "C2", "C3"], "月份": ["2026-08"] * 3,
                       "月收入": [200000.0, 50000.0, 150000.0],
                       "月环比%": [80.0, -80.0, float("nan")]})
    old = grf._read_gold
    grf._read_gold = _gold({"客户月度趋势.csv": df})
    try:
        out = grf._ch_revenue_shock("202608", CFG)
    finally:
        grf._read_gold = old
    assert [s["customer"] for s in out] == ["C1"]           # C2 月收入<10万、C3 环比缺失
    assert out[0]["types"] == ["新导入"] and out[0]["level"] == "中"


def test_ch_purchase_interrupt():
    df = pd.DataFrame({"客户编号": ["C1", "C2", "C3"],
                       "采购中断预警": ["True", "True", "False"],
                       "近12月收入": [500000.0, 50000.0, 900000.0],   # C2 低于 10万阈值
                       "距上次采购天数": [200.0, 200.0, 300.0],
                       "零采购月占比": [0.5, 0.5, 0.5],
                       "策略触发原因": ["中断预警(>61天)", "", ""]})
    old = grf._read_gold
    grf._read_gold = _gold({"客户全景.csv": df})
    try:
        out = grf._ch_purchase_interrupt(CFG)
    finally:
        grf._read_gold = old
    assert len(out) == 1 and out[0]["customer"] == "C1" and out[0]["level"] == "高"  # ≥120天


def test_ch_margin_deterioration():
    df = pd.DataFrame({"客户编号": ["C1", "C2", "C3"],
                       "毛利率跌幅%": [20.0, 3.0, 8.0],        # C2 跌幅不足
                       "近12月收入": [600000.0, 900000.0, 100000.0],  # C3 收入不足
                       "近12月毛利率": [10.0, 10.0, 10.0]})
    old = grf._read_gold
    grf._read_gold = _gold({"客户全景.csv": df})
    try:
        out = grf._ch_margin_deterioration(CFG)
    finally:
        grf._read_gold = old
    assert len(out) == 1 and out[0]["customer"] == "C1" and out[0]["level"] == "高"  # ≥15pct


def test_ch_decline_risk():
    df = pd.DataFrame({"客户编号": ["C1", "C2"],
                       "衰退风险品金额占比": [0.6, 0.1],
                       "隐性衰退_金额": [800000.0, 0.0]})
    old = grf._read_gold
    grf._read_gold = _gold({"客户组合健康度.csv": df})
    try:
        out = grf._ch_decline_risk(CFG)
    finally:
        grf._read_gold = old
    assert len(out) == 1 and out[0]["level"] == "高" and "60%" in out[0]["context"]


def test_ch_high_risk_product():
    df = pd.DataFrame({"产品名称": ["P1", "P2", "P3"],
                       "综合风险等级": ["极高风险", "高风险", "低风险"],
                       "近12月销售额": [500000.0, 500000.0, 900000.0],
                       "风险主导因子": ["增速衰减", "增速衰减", "x"],
                       "通用策略建议": ["换代", "观察", "x"]})
    old = grf._read_gold
    grf._read_gold = _gold({"gold_product_portrait.csv": df})
    try:
        out = grf._ch_high_risk_product(CFG)
    finally:
        grf._read_gold = old
    by_name = {s["customer"]: s for s in out}
    assert set(by_name) == {"P1", "P2"}
    assert by_name["P1"]["level"] == "高" and by_name["P2"]["level"] == "中"


def test_ch_pricing_anomaly():
    df = pd.DataFrame({"客户编号": ["C1", "C2", "C3"],
                       "产品品种": ["S1", "S2", "S3"],
                       "异常低价标记": ["异常低价", "异常低价", "正常"],
                       "价格偏离P50%": [-25.0, -12.0, -30.0],
                       "业务负责人": ["张三", "李四", "王五"],
                       "归因分析": ["归因A", "归因B", "归因C"]})
    old = grf._read_gold
    grf._read_gold = _gold({"定价合理性分析.csv": df})
    try:
        out = grf._ch_pricing_anomaly(CFG)
    finally:
        grf._read_gold = old
    assert [s["customer"] for s in out] == ["C1", "C2"]
    assert out[0]["level"] == "高" and out[1]["level"] == "中"   # ≤-20% → 高
    assert "张三" in out[0]["suggestion"]


def test_ch_neg_margin_threshold_and_level():
    df = pd.DataFrame({"客户编号": ["C1", "C2"],
                       "负毛利品种数": [3, 1],
                       "负毛利损失总额": [-50000.0, -5000.0],   # C2 低于 1万阈值
                       "负毛利严重等级": ["严重", "严重"],
                       "在采品种数": [10, 10], "负毛利品种占比": [0.3, 0.1],
                       "建议动作": ["停售", "停售"]})
    old = grf._read_gold
    grf._read_gold = _gold({"负毛利分析.csv": df})
    try:
        out = grf._ch_neg_margin(CFG)
    finally:
        grf._read_gold = old
    assert len(out) == 1 and out[0]["level"] == "高" and out[0]["loss"] == 50000.0


# ---------- 去重合并 / Top12 ----------

def test_merge_signals_same_customer():
    sigs = [grf._sig("C1", "负毛利", "高", 100000.0, "ctx1", "sugg1", "负毛利"),
            grf._sig("C1", "采购中断", "中", 0.0, "ctx2", "sugg2", "采购中断"),
            grf._sig("C2", "衰退风险", "中", 0.0, "ctx3", "sugg3", "衰退风险")]
    merged = grf.merge_signals(sigs)
    assert len(merged) == 2
    c1 = next(m for m in merged if m["customer"] == "C1")
    assert c1["level"] == "高" and c1["rtype"] == "负毛利、采购中断" and c1["loss"] == 100000.0
    assert c1["suggestion"] == "sugg1"   # 取最严重通道的建议


def test_top12_sort_level_then_loss():
    sigs = []
    for i in range(13):
        sigs.append(grf._sig(f"C{i:02d}", "负毛利", "高" if i < 5 else "中",
                             float(1000000 - i * 100000), "c", "s", "负毛利"))
    merged = grf.merge_signals(sigs)
    merged.sort(key=lambda s: (grf.RISK_LEVEL_ORDER.get(s["level"], 9), -s["loss"]))
    top = merged[:12]
    assert len(top) == 12
    assert [s["level"] for s in top[:5]] == ["高"] * 5    # 等级优先：5 高全进
    assert top[0]["loss"] >= top[-1]["loss"]             # 损失额加权降序
    assert merged[12]["customer"] == "C12"               # 损失最小者溢出


# ---------- 上月对拍（构造两月 md）----------

def _prev_md(rows):
    lines = ["# 风险与行动 · 2026-07", "", "## 一、当月风险摘要", "",
             "| 等级 | 事项 | 客户/产品 | 损失金额(万元) | 持续 | 较上月 | 建议动作 | 负责人 |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines) + "\n"


def test_norm_types_compat():
    assert grf._norm_types("客户采购中断、库存呆滞") == {"采购中断", "库存呆滞"}
    assert grf._norm_types("负毛利产品 5 个") == {"负毛利"}


def test_load_prev_month_risks(tmp_path):
    md = _prev_md([["高", "负毛利", "C1", "10.0", "连续第 2 月", "较上月恶化", "x", ""],
                   ["中", "客户采购中断", "C2", "-", "新增", "-", "y", ""]])
    p = tmp_path / "risk_action_202607.md"
    p.write_text(md, encoding="utf-8")
    old = grf.risk_md_path
    grf.risk_md_path = lambda m: str(p)
    try:
        prev = grf.load_prev_month_risks("202608")
    finally:
        grf.risk_md_path = old
    assert len(prev) == 2
    assert prev[0]["months"] == 2 and prev[0]["loss_wan"] == 10.0
    assert prev[1]["types"] == {"采购中断"}


def test_annotate_consecutive_and_change():
    prev = [{"customer": "C1", "types": {"负毛利"}, "level": "高", "loss_wan": 10.0, "months": 2},
            {"customer": "C2", "types": {"采购中断"}, "level": "高", "loss_wan": None, "months": 1}]
    merged = [grf._sig("C1", "负毛利", "高", 150000.0, "c", "s", "负毛利"),
              grf._sig("C3", "衰退风险", "中", 0.0, "c", "s", "衰退风险")]
    ann, rel = grf.annotate_month_over_month(merged, prev)
    c1 = next(a for a in ann if a["customer"] == "C1")
    assert c1["months"] == 3 and c1["持续"] == "连续第 3 月"
    assert c1["较上月"] == "较上月恶化"          # 15万 vs 10万，+50%
    c3 = next(a for a in ann if a["customer"] == "C3")
    assert c3["持续"] == "新增" and c3["较上月"] == "-"
    assert len(rel) == 1 and rel[0]["customer"] == "C2"   # 本月解除


def test_mom_change_level_based():
    merged = [grf._sig("C1", "负毛利", "中", 0.0, "c", "s", "负毛利")]
    prev = [{"customer": "C1", "types": {"负毛利"}, "level": "高", "loss_wan": None, "months": 1}]
    ann, _ = grf.annotate_month_over_month(merged, prev)
    assert ann[0]["较上月"] == "较上月好转"       # 等级 高→中
    merged2 = [grf._sig("C1", "负毛利", "高", 100000.0, "c", "s", "负毛利")]
    prev2 = [{"customer": "C1", "types": {"负毛利"}, "level": "高", "loss_wan": 10.0, "months": 1}]
    ann2, _ = grf.annotate_month_over_month(merged2, prev2)
    assert ann2[0]["较上月"] == "持平"           # 损失与等级均持平


# ---------- build_draft 端到端（合成 gold + 上月 md）----------

@pytest.fixture()
def draft_env(tmp_path, monkeypatch):
    """注入：数据月 202608、合成 gold、上月 202607 md、tmp 动作库与输出目录。"""
    gold_dfs = {
        "异常日志.csv": pd.DataFrame({"客户编号": ["C9"], "异常类型": ["营收断崖"],
                              "异常等级": ["高"], "异常详情": ["近12月收入200000, 增长率-90%, 连续下滑3个月"]}),
        "负毛利分析.csv": pd.DataFrame(
            {"客户编号": ["C1"], "负毛利品种数": [2], "负毛利损失总额": [-120000.0],
             "负毛利严重等级": ["严重"], "在采品种数": [10], "负毛利品种占比": [0.2],
             "建议动作": ["停售负毛利品种"]}),
        "客户月度趋势.csv": pd.DataFrame(
            {"客户编号": ["C1"], "月份": ["2026-08"], "月收入": [300000.0], "月环比%": [-60.0]}),
        "客户全景.csv": pd.DataFrame(
            {"客户编号": ["C1"], "采购中断预警": [False], "近12月收入": [0.0], "距上次采购天数": [0.0],
             "零采购月占比": [0.0], "策略触发原因": [""], "毛利率跌幅%": [0.0], "近12月毛利率": [0.0]}),
        "客户组合健康度.csv": pd.DataFrame(
            {"客户编号": ["C1"], "衰退风险品金额占比": [0.0], "隐性衰退_金额": [0.0]}),
        "gold_product_portrait.csv": pd.DataFrame(
            {"产品名称": ["P1"], "综合风险等级": ["低风险"], "近12月销售额": [0.0],
             "风险主导因子": [""], "通用策略建议": [""]}),
        "定价合理性分析.csv": pd.DataFrame(
            {"客户编号": ["C1"], "产品品种": ["S1"], "异常低价标记": ["正常"],
             "价格偏离P50%": [0.0], "业务负责人": [""], "归因分析": [""]}),
    }
    prev = tmp_path / "risk_action_202607.md"
    prev.write_text(_prev_md([["高", "负毛利", "C1", "10.0", "连续第 2 月", "较上月恶化", "x", ""],
                              ["高", "客户采购中断", "C8", "-", "新增", "-", "y", ""]]),
                    encoding="utf-8")
    actions = tmp_path / "action_items.json"
    actions.write_text(json.dumps({"version": "1", "last_batch_month": None, "items": []}),
                       encoding="utf-8")
    monkeypatch.setattr(grf, "_read_gold", _gold(gold_dfs))
    monkeypatch.setattr(grf, "_data_month", lambda: "202608")
    monkeypatch.setattr(grf, "risk_md_path", lambda m: str(prev) if m == "202607" else str(tmp_path / f"risk_action_{m}.md"))
    monkeypatch.setattr(grf, "ACTIONS_JSON", str(actions))
    monkeypatch.setattr(grf, "RISK_MD_DIR", str(tmp_path))
    return tmp_path


def test_build_draft_end_to_end(draft_env):
    md, stats = grf.build_draft("202608")
    assert stats["listed"] == 2                        # C1(负毛利+营收断崖+营收异动合并) 与 C9
    assert stats["consecutive"] == 1 and stats["released"] == 1
    assert "连续第 3 月" in md and "较上月恶化" in md
    assert "本月解除" in md and "C8" in md             # 解除进备注节
    assert "## 备注" in md
    # 行动种子：C1 高 + 连续 3 月 → 种子（rtype 为多通道合并串）；负责人空、期望完成日=月末
    assert stats["seeds"] == 1
    assert "[自动种子] C1：" in md and "2026-08-31" in md
    # 溢出附件已写
    over = draft_env / "风险溢出明细_2026-08.md"
    assert over.exists()


def test_build_draft_columns(draft_env):
    md, _ = grf.build_draft("202608")
    header = "| 等级 | 事项 | 客户/产品 | 损失金额(万元) | 持续 | 较上月 | 建议动作 | 负责人 |"
    assert header in md


# ---------- 结转修复（created_month 保留 / closed_month 补写）----------

def test_carryover_created_month_preserved(draft_env):
    md_path = draft_env / "risk_action_202608.md"
    md_path.write_text(
        "# 风险与行动 · 2026-08\n\n## 一、当月风险摘要\n\n"
        "| 等级 | 事项 | 客户/产品 |\n|---|---|---|\n| 高 | 负毛利 | C1 |\n\n"
        "## 二、行动清单\n\n"
        "| 状态 | 事项 | 负责人 | 期望完成日 | 备注 |\n|---|---|---|---|---|\n"
        "| 待处理 | 老事项A | 张三 | 2026-08-31 | n |\n"
        "| 已关闭 | 老事项B | 李四 | 2026-07-31 | n |\n",
        encoding="utf-8")
    # 预置：老事项A 由 202607 创建（id=行内容 sha1 前8位，与回写算法一致）
    def row_id(cells):
        raw = "|".join(cells)
        import hashlib
        return "row:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    data = {"version": "1", "last_batch_month": "202607", "items": [
        {"id": row_id(["待处理", "老事项A", "张三", "2026-08-31", "n"]),
         "title": "老事项A", "status": "待处理", "owner": "张三",
         "due_date": "2026-08-31", "note": "n", "created_month": "202607",
         "source": "总体文档"},
        {"id": "row:legacy01", "title": "老事项B", "status": "已关闭",
         "owner": "李四", "due_date": "2026-07-31", "note": "n",
         "created_month": "202606", "source": "总体文档"},
    ]}
    (draft_env / "action_items.json").write_text(json.dumps(data, ensure_ascii=False),
                                                 encoding="utf-8")
    parts = grf._build_r_parts("202608")
    assert parts["ok"]
    saved = json.loads((draft_env / "action_items.json").read_text(encoding="utf-8"))
    items = {it["title"]: it for it in saved["items"]}
    assert items["老事项A"]["created_month"] == "202607"     # 不被刷成 202608
    assert items["老事项B"]["closed_month"] == "202608"      # 补写关闭月


# ---------- 溢出附件 ----------

def test_overflow_file_sorted(tmp_path):
    sigs = [grf._sig("C2", "负毛利", "中", 50000.0, "c", "s", "负毛利"),
            grf._sig("C1", "负毛利", "高", 90000.0, "c", "s", "负毛利"),
            grf._sig("C3", "衰退风险", "高", 0.0, "c", "s", "衰退风险")]
    stats = {}
    grf.RISK_MD_DIR = str(tmp_path)
    try:
        path = grf._write_overflow("202608", sigs, stats)
    finally:
        grf.RISK_MD_DIR = os.path.join(grf.PLATFORM, "output", "dashboard")
    text = open(path, encoding="utf-8").read()
    assert "共 3 条" in text
    i_high = text.index("| 负毛利 | 高 |")
    i_mid = text.index("| 负毛利 | 中 |")
    i_dec = text.index("| 衰退风险 | 高 |")
    assert i_dec < i_high < i_mid                        # 通道×等级排序（通道名序：衰退风险<负毛利）
