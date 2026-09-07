# -*- coding: utf-8 -*-
"""R 面编辑功能协议层单测（设计定稿 R面编辑功能设计_20260907.md §9 v3.1）。

覆盖（P0/P1 逐条）：
    1.  往返不变式：export → import → export 逐字节等（归一化 mtime），md 与原件逐字节等
    2.  旧版 md 兼容：output/dashboard/risk_action_202606.md / 202607.md 实文件解析零异常
    3.  emoji 剥离正则：🔴🟠🟢⚪ + VS16 变体 + 无 emoji + emoji 在中间不剥 + 前导空格 + 只剥一个
    4.  先清洗后剥离顺序：竖线先转全角，emoji 剥离发生在语义匹配之前
    5.  import 矩形校验：列数不齐显式报错行号
    6.  envelope 错误格式：{"ok":false,"err":...,"stage":"parse|import|render"} + exit 1
    7.  KPI derived_value/stale 计算（P0-3）
    8.  ## 备注 自由段落节保真（P1）
    9.  mtime 并发校验（P1）；核心列降级渲染（P0-5）；行级色=首列格级 emoji（P0-7）

运行（从 sales_analytics_platform 目录）：python -m pytest test/test_risk_edit_protocol.py -q
"""
import copy
import json
import os
import shutil
import subprocess
import sys

import pytest

_DASH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dashboard"))
_PKG = os.path.dirname(_DASH)
sys.path.insert(0, _DASH)
sys.path.insert(0, _PKG)

import generate_risk_face as grf  # noqa: E402

RISK_MD_DIR = os.path.join(_PKG, "output", "dashboard")
REAL_202606 = os.path.join(RISK_MD_DIR, "risk_action_202606.md")
REAL_202607 = os.path.join(RISK_MD_DIR, "risk_action_202607.md")
SCRIPT = os.path.join(_DASH, "generate_risk_face.py")


# ---------- fixtures ----------

@pytest.fixture()
def md_copy(tmp_path):
    """真实 202607 md 的临时副本 + risk_md_path 注入（import 按月解析重定向到副本）。"""
    dst = tmp_path / "risk_action_202607.md"
    shutil.copyfile(REAL_202607, dst)
    monkey_target = str(dst)

    def _fake(_m):
        return monkey_target

    orig = grf.risk_md_path
    grf.risk_md_path = _fake
    yield str(dst)
    grf.risk_md_path = orig


@pytest.fixture()
def kpi_md(tmp_path):
    """含 KPI 节 + 备注节 + emoji 标色的合成 md（temp 文件路径，export 直读）。"""
    text = """# 风险与行动 · 2026-08

> 头部行一
> 头部行二

## 〇、KPI 卡片

| 标题 | 数值 | 副文本 | 级别 | 来源 |
|---|---|---|---|---|
| 高风险事项 | 99 | 人工覆盖 | 红色 | 派生覆盖 |
| 自定义提示 | 331.0万 | 领导要求展示 | 橙色 | 自定义 |

## 一、当月风险摘要

| 等级 | 事项 | 客户/产品 |
|---|---|---|
| 🔴高 | 客户采购中断 | C001 |
| 中 | 🟠负毛利扩大 | C002 |

## 二、行动清单

| 状态 | 事项 | 负责人 |
|---|---|---|
| 待处理 | 跟进客户 | 张三 |

## 备注

第一段：自由叙述 | 含半角竖线
第二段：待治理

## 三、口径说明（从 faces.yaml 自动带入，勿改）

【当月风险摘要】口径一。
"""
    p = tmp_path / "risk_action_202608.md"
    p.write_text(text, encoding="utf-8")
    return str(p)


def _norm(d):
    """归一化 mtime 字段后的深拷贝（往返不变式比对用）。"""
    c = copy.deepcopy(d)
    c.pop("mtime", None)
    return c


# ---------- 1. 往返不变式 ----------

class TestRoundTrip:
    def test_export_import_export_byte_equal(self, md_copy):
        d1 = grf.export_to_dict(md_copy)
        r1 = grf.import_from_dict(d1, "202607", write=True)
        assert r1["path"] == md_copy
        d2 = grf.export_to_dict(md_copy)
        assert _norm(d1) == _norm(d2)  # 仅 mtime 字段漂移
        # md 文本层二次组装也稳定
        r2 = grf.import_from_dict(d2, "202607", write=True)
        assert r1["md_text"] == r2["md_text"]

    def test_md_bytes_identical_to_original(self, md_copy):
        original = open(REAL_202607, encoding="utf-8").read()
        d1 = grf.export_to_dict(md_copy)
        grf.import_from_dict(d1, "202607", write=True)
        assert open(md_copy, encoding="utf-8").read() == original

    def test_roundtrip_header_caliber_byte_preserved(self, md_copy):
        d1 = grf.export_to_dict(md_copy)
        assert d1["header_raw"].startswith(">")
        assert "【当月风险摘要】" in d1["caliber_raw"]
        grf.import_from_dict(d1, "202607", write=True)
        assert open(md_copy, encoding="utf-8").read() == open(REAL_202607, encoding="utf-8").read()


# ---------- 2. 旧版 md 兼容 ----------

class TestLegacyCompat:
    @pytest.mark.parametrize("path", [REAL_202606, REAL_202607])
    def test_real_files_parse_and_render(self, path):
        if not os.path.exists(path):
            pytest.skip(f"存量文件缺失: {path}")
        d = grf.export_to_dict(path)
        assert grf._is_month(d["month"])
        assert d["risk_table"]["columns"], "风险表表头不应为空"
        assert d["action_table"]["columns"], "行动清单表头不应为空"
        month = d["month"]
        html = grf.build_r_face_inner_html(month)
        assert "当月风险摘要" in html and "行动清单" in html
        # 旧 md 无 KPI 节 → 派生默认 4 卡（不落盘语义），渲染含 kpi-bar
        assert len(d["kpi_cards"]) >= 4
        assert "kpi-bar" in html
        # 旧 md 无 emoji → 全 none
        assert all(c["color"] == "none" for r in d["risk_table"]["rows"] for c in r["cells"])


# ---------- 3/4. emoji 剥离正则 + 先清洗后剥离 ----------

class TestEmojiStrip:
    @pytest.mark.parametrize("text,exp_color,exp_rest", [
        ("🔴紧急", "red", "紧急"),
        ("🟠关注", "orange", "关注"),
        ("🟢好转", "green", "好转"),
        ("⚪备注", "gray", "备注"),
        ("⚪️备注", "gray", "备注"),          # VS16 变体
        ("  🔴 带空格", "red", "带空格"),
        ("无emoji", "none", "无emoji"),
        ("中间🔴不剥", "none", "中间🔴不剥"),   # emoji 在中间不剥
        ("🔴🟠只剥首个", "red", "🟠只剥首个"),  # 只剥一个
    ])
    def test_strip_emoji_regex(self, text, exp_color, exp_rest):
        rest, color = grf._strip_emoji(text)
        assert color == exp_color
        assert rest == exp_rest

    def test_cell_pipeline_clean_before_strip(self):
        """先全角｜清洗后剥离：'🔴a | b' → 竖线先转全角，emoji 再剥，语义匹配拿到干净文本。"""
        cell = grf._cell_parts("🔴a | b")
        assert cell["color"] == "red"
        assert cell["text"] == "a ｜ b"

    def test_semantic_match_after_strip(self):
        """P0-7：语义匹配（r[0]=='高'）在剥离后执行——带 emoji 的 '高' 仍计入派生统计。"""
        part = grf._table_part(["| 等级 | 事项 |", "|---|---|", "| 🔴高 | 事项A |", "| 中 | 事项B |"])
        texts = [r["cells"][0]["text"] for r in part["rows"]]
        assert texts == ["高", "中"]
        assert part["rows"][0]["style"]["row_color"] == "red"


# ---------- 5/6. 矩形校验 / envelope ----------

class TestValidation:
    def _base_data(self, md_copy):
        return grf.export_to_dict(md_copy)

    def test_rectangle_reject_with_row_number(self, md_copy):
        d = self._base_data(md_copy)
        row = d["risk_table"]["rows"][0]
        row["cells"] = row["cells"][:-1]  # 缺一格
        with pytest.raises(grf.ProtocolError) as e:
            grf.import_from_dict(d, "202607", write=False)
        assert "第 1 行" in str(e.value)

    def test_newline_cell_reject_with_coordinate(self, md_copy):
        d = self._base_data(md_copy)
        d["risk_table"]["rows"][0]["cells"][1]["text"] = "第一行\n第二行"
        with pytest.raises(grf.ProtocolError) as e:
            grf.import_from_dict(d, "202607", write=False)
        assert "第 1 行第 2 列" in str(e.value)
        assert "抽屉" in str(e.value)

    def test_bad_color_reject(self, md_copy):
        d = self._base_data(md_copy)
        d["risk_table"]["rows"][0]["cells"][0]["color"] = "purple"
        with pytest.raises(grf.ProtocolError):
            grf.import_from_dict(d, "202607", write=False)

    def test_mtime_conflict(self, md_copy):
        d = grf.export_to_dict(md_copy)
        d["mtime"] = d["mtime"] + 999
        with pytest.raises(grf.ProtocolError) as e:
            grf.import_from_dict(d, "202607", write=False)
        assert "mtime 冲突" in str(e.value)

    def test_month_mismatch(self, md_copy):
        d = grf.export_to_dict(md_copy)
        with pytest.raises(grf.ProtocolError) as e:
            grf.import_from_dict(d, "202606", write=False)
        assert "month 不匹配" in str(e.value)


# ---------- 6. CLI envelope ----------

class TestCliEnvelope:
    def _run(self, args, stdin_text=None):
        return subprocess.run([sys.executable, SCRIPT] + args,
                              capture_output=True, text=True, encoding="utf-8",
                              input=stdin_text, timeout=120, cwd=_PKG)

    def test_export_cli_ok(self):
        r = self._run(["--export-json", "202607"])
        assert r.returncode == 0, r.stdout + r.stderr
        d = json.loads(r.stdout)
        assert d["month"] == "202607"
        assert len(d["kpi_cards"]) >= 4
        assert d["risk_table"]["columns"][:2] == ["等级", "事项"]

    def test_import_cli_envelope_ok(self):
        # 子进程无法看到 monkeypatch，CLI 测试须全程走真实 202607 文件（export 只读 + 恒等 import 回写）
        r1 = self._run(["--export-json", "202607"])
        assert r1.returncode == 0, r1.stdout + r1.stderr
        d = json.loads(r1.stdout)
        r = self._run(["--import-json", "202607"], stdin_text=json.dumps(d, ensure_ascii=False))
        assert r.returncode == 0, r.stdout + r.stderr
        assert json.loads(r.stdout)["ok"] is True

    def test_envelope_export_missing_month(self):
        r = self._run(["--export-json", "209901"])
        assert r.returncode == 1
        env = json.loads(r.stdout)
        assert env["ok"] is False
        assert env["stage"] in ("parse", "import", "render")
        assert env["err"]

    def test_envelope_import_bad_json(self):
        r = self._run(["--import-json", "202607"], stdin_text="{not json")
        assert r.returncode == 1
        env = json.loads(r.stdout)
        assert env["ok"] is False and env["stage"] == "import"

    def test_envelope_import_rectangle(self):
        r1 = self._run(["--export-json", "202607"])
        assert r1.returncode == 0
        d = json.loads(r1.stdout)
        d["risk_table"]["rows"][0]["cells"] = d["risk_table"]["rows"][0]["cells"][:1]
        r = self._run(["--import-json", "202607"], stdin_text=json.dumps(d, ensure_ascii=False))
        assert r.returncode == 1
        env = json.loads(r.stdout)
        assert env["ok"] is False and env["stage"] == "import"
        assert "第 1 行" in env["err"]


# ---------- 7. KPI derived/stale ----------

class TestKpi:
    def test_kpi_section_parse_and_stale(self, kpi_md):
        d = grf.export_to_dict(kpi_md)
        cards = {c["title"]: c for c in d["kpi_cards"]}
        # 派生卡 value=99 ≠ 现算 derived_value（风险表 1 条"高"）→ stale=True（P0-3）
        assert cards["高风险事项"]["source"] == "派生覆盖"
        assert cards["高风险事项"]["derived_value"] == "1"
        assert cards["高风险事项"]["stale"] is True
        # 中风险现算 1 条，md 无覆盖 → 派生默认 stale=False
        assert cards["中风险事项"]["stale"] is False
        # 自定义卡 derived_value=None, stale=False
        assert cards["自定义提示"]["source"] == "自定义"
        assert cards["自定义提示"]["stale"] is False
        assert d["derived_snapshot"]["n_high"] == 1

    def test_kpi_md_level_roundtrip(self, kpi_md, tmp_path):
        """KPI 级别列（红色/橙色文本）↔ 语义枚举往返稳定，且非派生卡落盘。"""
        sub = tmp_path / "roundtrip"
        sub.mkdir()
        target = sub / "risk_action_202608.md"
        shutil.copyfile(kpi_md, target)
        orig = grf.risk_md_path
        grf.risk_md_path = lambda _m: str(target)
        try:
            d = grf.export_to_dict(str(target))  # 从副本导出，mtime 与导入对象一致
            r1 = grf.import_from_dict(d, "202608", write=True)
            d2 = grf.export_to_dict(str(target))
            assert _norm(d) == _norm(d2)
            assert "## 〇、KPI 卡片" in r1["md_text"]
            # md 级别列回写为中文文本（红色/橙色）
            assert "| 高风险事项 | 99 | 人工覆盖 | 红色 | 派生覆盖 |" in r1["md_text"]
            # 备注节逐字节保真（含半角竖线原样保留）
            assert "第一段：自由叙述 | 含半角竖线" in r1["md_text"]
        finally:
            grf.risk_md_path = orig

    def test_kpi_bar_n0_hidden_and_grid(self):
        assert grf._kpi_bar_html([]) == ""
        html5 = grf._kpi_bar_html([{"title": "A", "value": "1", "sub": "", "level": "none"}] * 5)
        assert "repeat(5,1fr)" in html5
        html12 = grf._kpi_bar_html([{"title": "A", "value": "1", "sub": "", "level": "none"}] * 12)
        assert "repeat(8,1fr)" in html12  # >8 固定 8 列换行


# ---------- 8/9. 备注节 / 降级 / 行级色 ----------

class TestRenderProtocol:
    def test_core_column_degrade_hint(self, tmp_path):
        """P0-5：风险表缺「等级」核心列 → 降级普通列 + 口径条提示文本。"""
        text = """# 风险与行动 · 2026-08

> 头部

## 一、当月风险摘要

| 事项 | 客户/产品 |
|---|---|
| 客户采购中断 | C001 |

## 二、行动清单

| 状态 | 事项 |
|---|---|
| 待处理 | 跟进 |
"""
        p = tmp_path / "risk_action_202608.md"
        p.write_text(text, encoding="utf-8")
        d = grf.export_to_dict(str(p))
        assert d["risk_table"]["col_meta"] == [
            {"name": "事项", "locked": False}, {"name": "客户/产品", "locked": False}]
        month = d["month"]
        orig = grf.risk_md_path
        grf.risk_md_path = lambda _m: str(p)
        try:
            parts = grf._build_r_parts(month)
        finally:
            grf.risk_md_path = orig
        assert parts["ok"] is True
        assert "「等级」核心列缺失" in parts["caliber"]
        assert "tag-" not in parts["risk_table"]  # 无等级列 → 无 tag 渲染

    def test_row_color_and_cell_color_render(self, kpi_md):
        d = grf.export_to_dict(kpi_md)
        r = d["risk_table"]["rows"][0]
        assert r["style"]["row_color"] == "red"            # 行级色=首列格级 emoji
        assert r["cells"][1]["color"] == "none"
        assert d["risk_table"]["rows"][1]["cells"][1]["color"] == "orange"  # 格级色
        html = grf._render_table(d["risk_table"])
        assert 'style="background:var(--danger-bg)"' in html  # 行级色淡色底

    def test_notes_rendered_as_paragraphs(self, kpi_md):
        d = grf.export_to_dict(kpi_md)
        assert "第一段：自由叙述 | 含半角竖线" in d["notes_section"]  # 备注节不被 _md_cell 清洗
        month = d["month"]
        orig = grf.risk_md_path
        grf.risk_md_path = lambda _m: kpi_md
        try:
            html = grf.build_r_face_inner_html(month)
        finally:
            grf.risk_md_path = orig
        assert "<h3>备注</h3>" in html
        assert "第二段：待治理" in html

    def test_numeric_align_regex(self):
        assert grf.VALUE_ALIGN_RE.match("331.0万")
        assert grf.VALUE_ALIGN_RE.match("-12.5%")
        assert grf.VALUE_ALIGN_RE.match("1,234.5")
        assert grf.VALUE_ALIGN_RE.match("42") is not None
        assert grf.VALUE_ALIGN_RE.match("abc") is None
