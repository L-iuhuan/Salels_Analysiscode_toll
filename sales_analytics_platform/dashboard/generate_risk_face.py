# -*- coding: utf-8 -*-
"""风险与行动面 · 测试版生成器（W4）+ R 面编辑功能协议层（v3.1，设计 §9）
设计依据：docs\\看板叙事结构详细设计_20260825.md §3.5（总体文档模式）/ §6.2（独立测试页）
编辑功能设计：project_analysis\\R面编辑功能设计_20260907.md §9（JSON 契约 §9.5 为两侧施工唯一依据）

三个职责：
1. 初稿生成：读 gold 异常/风险表 + action_items.json 结转 + 可选 meeting_track.md
   → 生成 output\\dashboard\\risk_action_YYYYMM.md（已存在人工审定版则不覆盖，除非 --force-draft；
   旧 dashboard\\ 位置保留兼容回退读取，见 risk_md_path()）
2. 渲染：解析总体文档 → 按固定模板（template_risk_test.html，与正式看板同风格）
   → 输出 dashboard\\dashboard_risk_test.html，并把行动清单状态回写 action_items.json
3. 编辑协议（§9 P0-6 stdin 管道）：--export-json / --import-json [month]，JSON 走 stdin/stdout，
   --file 兜底；错误一律 envelope {"ok":false,"err":...,"stage":"parse|import|render"} 到 stdout + exit 1

用法（工作目录 sales_analytics_platform）：
    python dashboard\\generate_risk_face.py              # 初稿（如缺失）+ 渲染
    python dashboard\\generate_risk_face.py --force-draft [--yes]  # 覆盖人工审定版（需 --yes 确认，覆盖前 .bak 备份）
    python dashboard\\generate_risk_face.py --month 202606  # 指定数据月份
    python dashboard\\generate_risk_face.py --export-json 202607            # md → JSON（stdout）
    type payload.json | python dashboard\\generate_risk_face.py --import-json 202607   # JSON → md（stdin）
"""
import argparse
import calendar
import hashlib
import html
import json
import os
import re
import sys
import tempfile
from datetime import datetime

import pandas as pd
import yaml

DASH_DIR = os.path.dirname(os.path.abspath(__file__))
PLATFORM = os.path.dirname(DASH_DIR)
GOLD = os.path.join(PLATFORM, "output", "gold")
SILVER = os.path.join(PLATFORM, "output", "silver")
FACES_YAML = os.path.join(DASH_DIR, "faces.yaml")
RISK_TEMPLATES_YAML = os.path.join(DASH_DIR, "risk_templates.yaml")  # v2 策展阈值+建议模板库
TEMPLATE = os.path.join(DASH_DIR, "template_risk_test.html")
ACTIONS_JSON = os.path.join(DASH_DIR, "action_items.json")
# 迁移拍板：risk_action_*.md 与 meeting_track.md 移至 output\dashboard\（壳端编辑产物与源码目录分离，
# 防 robocopy /MIR 覆盖）。读取时新位置优先、旧 dashboard\ 位置回退（平滑过渡）。
RISK_MD_DIR = os.path.join(PLATFORM, "output", "dashboard")
MEETING_MD = os.path.join(RISK_MD_DIR, "meeting_track.md")

RISK_LEVEL_ORDER = {"高": 0, "中": 1, "低": 2}
NEG_LVL_MAP = {"严重": "高", "关注": "中", "轻微": "低"}  # 负毛利严重等级 → 展示等级
STATUS_ORDER = {"待处理": 0, "跟进中": 1, "已关闭": 2}
NEG_MARGIN_MIN_LOSS = 10000  # 负毛利损失阈值（元；源表为负值存储），设计 §3.2.4
TOP_N_PER_SOURCE = 10  # 初稿每类最多展示条数，设计 §3.2.4（人工审定可推翻）

# ── R 面编辑协议常量（§9.5 契约；两侧施工唯一依据，键名/枚举勿改）──
EMOJI_TO_COLOR = {"🔴": "red", "🟠": "orange", "🟢": "green", "⚪": "gray"}
COLOR_TO_EMOJI = {"red": "🔴", "orange": "🟠", "green": "🟢", "gray": "⚪"}
COLOR_TO_TEXT = {"red": "红色", "orange": "橙色", "green": "绿色", "gray": "灰色"}
TEXT_TO_COLOR = {v: k for k, v in COLOR_TO_TEXT.items()}
# P0-7：剥离正则锚定格首（含 VS16 变体兼容，⚪\uFE0F）；仅格级内容首 emoji，中间不剥
EMOJI_RE = re.compile(r"^\s*(🔴|🟠|🟢|⚪)\uFE0F?\s*")
# P2：数值列右对齐按值正则 ^-?[\d,.]+%?万?$
VALUE_ALIGN_RE = re.compile(r"^-?[\d,.]+%?万?$")
# P0-5：核心列禁删禁改名（编辑器置灰）；渲染端列名特判仅对这两列生效
CORE_COLUMNS = ("等级", "状态")
KPI_SECTION_TITLE = "〇、KPI 卡片"  # 表头驱动新节；缺省=4 张派生卡不落盘
KPI_COLS = ["标题", "数值", "副文本", "级别", "来源"]
KPI_LEVEL_TO_CLS = {"red": "kpi-danger", "orange": "kpi-warning", "green": "kpi-success", "gray": ""}
KPI_TITLES = ("高风险事项", "中风险事项", "负毛利损失合计", "行动项")  # 派生卡标题（第 4 卡既有逻辑）
LEGEND = {"red": "紧急", "orange": "关注", "green": "好转", "gray": "备注"}
ROW_COLOR_BG = {"red": "var(--danger-bg)", "orange": "var(--warning-bg)",
                "green": "var(--success-bg)", "gray": "var(--surface-subtle)"}


def risk_md_path(month):
    """总体文档 risk_action_<month>.md 路径：新位置 output/dashboard 优先，旧 dashboard/ 回退读取。"""
    new = os.path.join(RISK_MD_DIR, f"risk_action_{month}.md")
    if os.path.exists(new):
        return new
    old = os.path.join(DASH_DIR, f"risk_action_{month}.md")
    return old if os.path.exists(old) else new


def _meeting_md_path():
    """会议速记 meeting_track.md 路径：新位置优先，旧 dashboard/ 回退读取。"""
    if os.path.exists(MEETING_MD):
        return MEETING_MD
    old = os.path.join(DASH_DIR, "meeting_track.md")
    return old if os.path.exists(old) else MEETING_MD


# ---------- 基础工具 ----------

def _read_gold(name):
    path = os.path.join(GOLD, name)
    if not os.path.exists(path):
        print(f"  [警告] gold 表缺失: {name}（该来源本期不出候选）")
        return None
    return pd.read_csv(path, encoding="utf-8-sig")


def _data_month():
    """从 silver 聚合表推最新数据月份 → 'YYYYMM'。"""
    path = os.path.join(SILVER, "silver_product_monthly.csv")
    df = pd.read_csv(path, encoding="utf-8-sig", usecols=["_月"])
    return str(df["_月"].max()).replace("-", "")


def _fmt_wan(yuan):
    try:
        return f"{float(yuan) / 10000:.1f}"
    except (TypeError, ValueError):
        return "-"


def _esc(s):
    return html.escape(str(s), quote=False)


def _md_cell(c):
    """单元格清洗：竖线转全角、换行转空格，防止撑破 md 表格结构（负毛利建议动作含 ' | ' 分隔符）。"""
    return str(c).replace("|", "｜").replace("\r", " ").replace("\n", " ").strip()


def _md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        out.append("| " + " | ".join(_md_cell(c) for c in r) + " |")
    return "\n".join(out)


def _parse_md_tables(md_text):
    """把总体文档解析为 {section_title: (headers, rows)}。只认 '## ' 节标题与 | 表格行。
    （遗留接口：build_draft 的 meeting_track.md 并入仍用；总体文档解析走 _parse_doc）"""
    sections = {}
    current = None
    for line in md_text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            current = s[3:].strip()
        elif s.startswith("|") and current:
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue  # 分隔行
            if current not in sections:
                sections[current] = (cells, [])
            else:
                sections[current][1].append(cells)
    return sections


# ---------- 编辑协议解析层（§9 P0-7：全角｜清洗 → emoji 剥离 → 语义匹配）----------

def _strip_emoji(text):
    """格级 emoji 剥离（仅内容首 emoji，正则锚定 ^，中间出现不剥）；返回 (去色文本, 色值枚举)。"""
    m = EMOJI_RE.match(text)
    if m:
        return text[m.end():], EMOJI_TO_COLOR[m.group(1)]
    return text, "none"


def _cell_parts(raw):
    """单元格入解析管线的固定顺序（P0-7）：先 _md_cell 全角｜清洗，再 emoji 剥离，最后语义匹配。
    语义匹配（r[0]=="高"/STATUS_ORDER 等）消费本函数返回值，保证"先剥离后匹配"。"""
    text, color = _strip_emoji(_md_cell(raw))
    return {"text": text, "color": color or "none"}


def _table_part(lines):
    """把节内的 | 表格行解析为表头驱动结构：{"columns": [...], "rows": [{"cells": [{text,color}], "style": {...}}]}。
    行短于表头容错补空（历史脏文档防御）；行级色 = 首列单元格内容级 emoji（P0-7，JSON 侧 style.row_color）。"""
    columns = []
    rows = []
    for s in lines:
        s = s.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue  # 分隔行
        if not columns:
            columns = cells
            continue
        parts = [_cell_parts(c) for c in cells[:len(columns)]]
        while len(parts) < len(columns):
            parts.append({"text": "", "color": "none"})
        rows.append({"cells": parts, "style": {"row_color": parts[0]["color"]}})
    return {"columns": columns, "rows": rows}


def _kpi_row_parts(raw_cells):
    """KPI 卡片行解析：级别列文本（红色/橙色/绿色/灰色）→ 语义枚举，容错回 none。"""
    parts = [_cell_parts(c) for c in raw_cells]
    while len(parts) < len(KPI_COLS):
        parts.append({"text": "", "color": "none"})
    level = TEXT_TO_COLOR.get(parts[3]["text"], "none")
    return {"title": parts[0]["text"], "value": parts[1]["text"], "sub": parts[2]["text"],
            "level": level, "source": parts[4]["text"] or "derived"}


def _parse_doc(md_text):
    """总体文档唯一真源解析器（渲染与 export 共用同一管线）。
    分区结构（§3.1，向后兼容旧 md 无新节按默认处理）：
      # 标题行 / > 头部元信息（header_raw 逐字节保真）/ ## 〇、KPI 卡片 / ## 一、当月风险摘要
      / ## 二、行动清单 / ## 备注（自由段落，_md_cell 不触碰）/ ## 三、口径说明（caliber_raw 锁定逐字节）
    返回 dict: title_line/header_raw/kpi_cards(无节=None)/tables({节标题: _table_part})/notes_raw/caliber_raw。
    """
    doc = {"title_line": "", "header_raw": "", "kpi_cards": None,
           "tables": {}, "notes_raw": "", "caliber_raw": ""}
    lines = md_text.splitlines()
    i = 0
    # 标题行 + 头部元信息（连续 '>' 行块，含其前空行边界逐字节捕获）
    while i < len(lines):
        if lines[i].startswith("# "):
            doc["title_line"] = lines[i]
            i += 1
            break
        i += 1
    header_lines = []
    seen_gt = False
    while i < len(lines):
        s = lines[i]
        if s.startswith(">"):
            header_lines.append(s)
            seen_gt = True
            i += 1
        elif not seen_gt and s.strip() == "":
            i += 1  # 标题与头部之间的空行
        else:
            break
    doc["header_raw"] = "\n".join(header_lines)
    # 分区循环
    while i < len(lines):
        s = lines[i]
        if s.startswith("## "):
            title = s[3:].strip()
            body = []
            i += 1
            while i < len(lines) and not lines[i].startswith("## "):
                body.append(lines[i])
                i += 1
            if KPI_SECTION_TITLE.split("、")[-1] in title or "KPI" in title:
                cards = []
                for ln in body:
                    ln = ln.strip()
                    if not ln.startswith("|"):
                        continue
                    cells = [c.strip() for c in ln.strip("|").split("|")]
                    if all(set(c) <= set("-: ") for c in cells):
                        continue
                    if cells[:len(KPI_COLS)] == KPI_COLS:
                        continue  # 表头行
                    cards.append(_kpi_row_parts(cells))
                doc["kpi_cards"] = cards
            elif "备注" in title:
                doc["notes_raw"] = "\n".join(body).strip("\n")
            elif "口径" in title:
                doc["caliber_raw"] = "\n".join(body).strip("\n")
            else:
                doc["tables"][title] = _table_part(body)
        else:
            i += 1
    return doc


def _find_table(doc, keyword):
    """按关键字在解析分区中定位表格（先精确后包含，兼容节名前后缀变化）。"""
    for title, part in doc["tables"].items():
        if title == keyword:
            return part
    for title, part in doc["tables"].items():
        if keyword in title:
            return part
    return {"columns": [], "rows": []}


def _find_kpi_section(md_text):
    """md 是否含 KPI 节（import 决定该节是否落盘：原 md 无节且全派生 → 不落盘）。"""
    return any(l.startswith("## ") and "KPI" in l for l in md_text.splitlines())


def _title_month(month):
    return f"# 风险与行动 · {month[:4]}-{month[4:]}"


def _is_month(v):
    return isinstance(v, str) and re.fullmatch(r"\d{6}", v) is not None


def _resolve_target_path(month_or_path):
    """解析目标 md 路径：'YYYYMM' 月串走 risk_md_path（新位置优先旧位置回退）；
    其余视为显式文件路径（测试/兜底用途）。校验月串格式防路径注入。"""
    if _is_month(month_or_path):
        return risk_md_path(month_or_path)
    if os.sep in month_or_path or month_or_path.endswith(".md"):
        return month_or_path
    raise ValueError(f"非法 month 参数（须 YYYYMM）: {month_or_path!r}")


# ---------- 初稿生成 ----------

def load_actions():
    if os.path.exists(ACTIONS_JSON):
        with open(ACTIONS_JSON, encoding="utf-8") as f:
            return json.load(f)
    return {"version": "1", "last_batch_month": None, "items": []}


def save_actions(data):
    with open(ACTIONS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------- 策展引擎 v2（设计 §2：8 通道信号源 + 去重合并 + 月度对拍 + Top12）----------

def _load_templates():
    """risk_templates.yaml：阈值 + 建议模板库（代码零文案，可持续调整不改代码）。"""
    if not os.path.exists(RISK_TEMPLATES_YAML):
        return {"top_n": TOP_N_PER_SOURCE, "channels": {}, "seeds": {"min_level": "高", "min_consecutive": 2},
                "templates": {}}
    with open(RISK_TEMPLATES_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _safe_format(tpl, ctx):
    """模板填充：缺省占位符留原样（{xxx} 原样输出），异常不抛。"""
    class _D(dict):
        def __missing__(self, key):
            return "{" + key + "}"
    try:
        return str(tpl).format_map(_D({k: v for k, v in ctx.items()}))
    except Exception:
        return str(tpl)


def _render_template(cfg, rtype, level, ctx, fallback_detail="", alt_key=None):
    """类型×等级模板渲染：先精确（类型→等级），缺等级回退类型任意等级，再回退 _default，最后详情透传。
    alt_key：同类型多数据源时改用替代模板键（如异常日志的 _log_营收断崖），避免数据位错位。"""
    tpls = (cfg.get("templates") or {})
    ctx = dict(ctx)
    ctx.setdefault("detail", fallback_detail)
    by_type = tpls.get(alt_key) or tpls.get(rtype) or {}
    tpl = by_type.get(level) or next(iter(by_type.values()), None)
    if tpl is None:
        dft = tpls.get("_default") or {}
        tpl = dft.get(level) or next(iter(dft.values()), None)
    if tpl is None:
        return str(ctx.get("detail") or "")[:120]
    return _safe_format(tpl, ctx)[:160]


def _sig(customer, rtype, level, loss, context, suggestion, channel):
    """统一信号记录。loss 单位元（无损失口径记 0）。"""
    return {"customer": str(customer).strip(), "types": [rtype], "rtype": rtype,
            "level": level if level in RISK_LEVEL_ORDER else "中",
            "loss": float(loss or 0.0), "context": str(context or ""),
            "suggestion": str(suggestion or ""), "channel": channel}


def _num(v, default=0.0):
    try:
        if pd.isna(v):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


_DETAIL_RE = {
    "rev12m": re.compile(r"近12月收入([\d,]+(?:\.\d+)?)"),
    "growth": re.compile(r"增长率(-?\d+(?:\.\d+)?)%"),
    "months": re.compile(r"连续(下滑|增长)(\d+)个?月"),
}


def _parse_anomaly_detail(detail):
    """异常详情列解析：近12月收入/增长率%/连续下滑N个月 → 建议模板数据位 + 上下文。"""
    out = {}
    m = _DETAIL_RE["rev12m"].search(detail)
    if m:
        out["rev12m"] = f"{float(m.group(1).replace(',', '')) / 10000:.1f}"
    m = _DETAIL_RE["growth"].search(detail)
    if m:
        out["growth"] = m.group(1)
    m = _DETAIL_RE["months"].search(detail)
    if m:
        out["months"] = f"连续{m.group(1)}{m.group(2)}个月"
    return out


def _ch_anomaly_log(cfg):
    """通道1 异常日志（既有增强）：高/中入选；异常详情解析进建议+上下文。"""
    c = (cfg.get("channels") or {}).get("anomaly_log") or {}
    if c.get("enabled", True) is False:
        return []
    df = _read_gold("异常日志.csv")
    if df is None or not len(df):
        return []
    levels = c.get("levels") or ["高", "中"]
    df = df[df["异常等级"].isin(levels)]
    out = []
    for _, r in df.iterrows():
        detail = str(r.get("异常详情") or "").strip()
        info = _parse_anomaly_detail(detail)
        rtype = str(r["异常类型"]).strip() or "异常"
        suggestion = _render_template(cfg, rtype, r["异常等级"], info, fallback_detail=detail,
                                      alt_key=f"_log_{rtype}")
        out.append(_sig(r["客户编号"], rtype, r["异常等级"], 0.0,
                        detail[:60], suggestion, "异常日志"))
    return out


def _ch_neg_margin(cfg):
    """通道8 负毛利（既有）：损失 ≤ -阈值；等级映射 严重/关注/轻微→高/中/低。"""
    c = (cfg.get("channels") or {}).get("neg_margin") or {}
    if c.get("enabled", True) is False:
        return []
    min_loss = float(c.get("min_loss", NEG_MARGIN_MIN_LOSS))
    df = _read_gold("负毛利分析.csv")
    if df is None or not len(df):
        return []
    df = df[(df["负毛利品种数"] > 0) & (df["负毛利损失总额"] <= -min_loss)]
    out = []
    for _, r in df.iterrows():
        level = NEG_LVL_MAP.get(str(r.get("负毛利严重等级") or ""), "中")
        loss = abs(_num(r["负毛利损失总额"]))
        n = int(_num(r["负毛利品种数"]))
        total = int(_num(r.get("在采品种数"))) or n
        raw_pct = _num(r.get("负毛利品种占比"))
        # 负毛利品种占比源表存百分数（15.2 即 15.2%）；>1 视为已是百分数，避免 ×100  twice
        pct = (f"{raw_pct:.0f}" if raw_pct > 1 else f"{raw_pct * 100:.0f}") if raw_pct else \
            f"{n / total * 100:.0f}"
        gold_advice = str(r.get("建议动作") or "").strip()
        if len(gold_advice) > 90:
            gold_advice = gold_advice[:90] + "…"
        ctx = {"n": n, "total": total, "pct": pct, "loss": f"{loss / 10000:.1f}",
               "gold_advice": gold_advice or "逐品种复核定价与成本"}
        context = f"{n}/{total}个品种({pct}%)负毛利，损失{loss / 10000:.1f}万"
        out.append(_sig(r["客户编号"], "负毛利", level, loss, context,
                        _render_template(cfg, "负毛利", level, ctx), "负毛利"))
    return out


def _ch_revenue_shock(month, cfg):
    """通道2 营收异动：客户月度趋势当月行，环比 ≤ -50%（断崖）或 ≥ +50%（新导入）且月收入 ≥ 10万。"""
    c = (cfg.get("channels") or {}).get("revenue_shock") or {}
    if c.get("enabled", True) is False:
        return []
    df = _read_gold("客户月度趋势.csv")
    if df is None or not len(df):
        return []
    m = f"{month[:4]}-{month[4:]}"
    df = df[df["月份"] == m]
    out = []
    for _, r in df.iterrows():
        rev = _num(r.get("月收入"))
        mom = _num(r.get("月环比%"), default=float("nan"))
        if pd.isna(mom) or rev < float(c.get("min_month_revenue", 100000)):
            continue
        ctx = {"cur": f"{rev / 10000:.1f}", "mom": f"{mom:.0f}", "months": ""}
        if mom <= float(c.get("mom_drop", -50)):
            prev = rev / (1 + mom / 100.0) if mom > -100 else 0.0
            out.append(_sig(r["客户编号"], "营收断崖", "高", max(0.0, prev - rev),
                            f"本月收入{rev / 10000:.1f}万，环比{mom:.0f}%",
                            _render_template(cfg, "营收断崖", "高", ctx), "营收异动"))
        elif mom >= float(c.get("mom_surge", 50)):
            out.append(_sig(r["客户编号"], "新导入", "中", 0.0,
                            f"本月收入{rev / 10000:.1f}万，环比{mom:.0f}%（上月≈0）",
                            _render_template(cfg, "新导入", "中", ctx), "营收异动"))
    return out


def _ch_purchase_interrupt(cfg):
    """通道3 采购中断预警：客户全景 预警=True（剔除近12月收入 < 阈值防刷屏）；≥N 天 → 高。"""
    c = (cfg.get("channels") or {}).get("purchase_interrupt") or {}
    if c.get("enabled", True) is False:
        return []
    df = _read_gold("客户全景.csv")
    if df is None or not len(df):
        return []
    df = df[df["采购中断预警"].astype(str) == "True"]
    min_rev = float(c.get("min_rev12m", 0))
    if min_rev:
        df = df[df["近12月收入"].apply(lambda v: _num(v)) >= min_rev]
    out = []
    for _, r in df.iterrows():
        days = _num(r.get("距上次采购天数"))
        rev12m = _num(r.get("近12月收入"))
        zero_pct = _num(r.get("零采购月占比")) * 100
        level = "高" if days >= float(c.get("high_days", 120)) else "中"
        ctx = {"rev12m": f"{rev12m / 10000:.1f}", "days": f"{days:.0f}", "zero_pct": f"{zero_pct:.0f}"}
        reason = str(r.get("策略触发原因") or "").strip()
        context = f"距上次采购{days:.0f}天，零采购月占比{zero_pct:.0f}%" + (f"，{reason}" if reason else "")
        out.append(_sig(r["客户编号"], "采购中断", level, 0.0, context,
                        _render_template(cfg, "采购中断", level, ctx), "采购中断"))
    return out


def _ch_margin_deterioration(cfg):
    """通道4 毛利率恶化：客户全景 毛利率跌幅% ≥ 5pct 且 近12月收入 ≥ 50万。"""
    c = (cfg.get("channels") or {}).get("margin_deterioration") or {}
    if c.get("enabled", True) is False:
        return []
    df = _read_gold("客户全景.csv")
    if df is None or not len(df):
        return []
    df = df[df["毛利率跌幅%"].apply(lambda v: _num(v)) >= float(c.get("min_drop_pct", 5))]
    df = df[df["近12月收入"].apply(lambda v: _num(v)) >= float(c.get("min_rev12m", 500000))]
    out = []
    for _, r in df.iterrows():
        drop = _num(r["毛利率跌幅%"])
        mg = _num(r.get("近12月毛利率"))
        rev12m = _num(r.get("近12月收入"))
        level = "高" if drop >= float(c.get("high_drop_pct", 15)) else "中"
        ctx = {"drop": f"{drop:.1f}", "mg": f"{mg:.1f}", "rev12m": f"{rev12m / 10000:.1f}"}
        out.append(_sig(r["客户编号"], "毛利率恶化", level, 0.0,
                        f"毛利率跌{drop:.1f}pct至{mg:.1f}%",
                        _render_template(cfg, "毛利率恶化", level, ctx), "毛利率恶化"))
    return out


def _ch_decline_risk(cfg):
    """通道5 衰退风险：客户组合健康度 衰退风险品金额占比 ≥ 阈值。"""
    c = (cfg.get("channels") or {}).get("decline_risk") or {}
    if c.get("enabled", True) is False:
        return []
    df = _read_gold("客户组合健康度.csv")
    if df is None or not len(df):
        return []
    df = df[df["衰退风险品金额占比"].apply(lambda v: _num(v)) >= float(c.get("min_share", 0.30))]
    out = []
    for _, r in df.iterrows():
        share = _num(r["衰退风险品金额占比"])
        hidden = _num(r.get("隐性衰退_金额"))
        level = "高" if share >= float(c.get("high_share", 0.50)) else "中"
        ctx = {"pct": f"{share * 100:.0f}", "hidden": f"{hidden / 10000:.1f}"}
        out.append(_sig(r["客户编号"], "衰退风险", level, 0.0,
                        f"衰退风险品金额占比{share * 100:.0f}%",
                        _render_template(cfg, "衰退风险", level, ctx), "衰退风险"))
    return out


def _ch_high_risk_product(cfg):
    """通道6 高风险产品：产品画像 综合风险等级入选 且 品种近12月销售额 ≥ 20万（客户列=产品）。"""
    c = (cfg.get("channels") or {}).get("high_risk_product") or {}
    if c.get("enabled", True) is False:
        return []
    df = _read_gold("gold_product_portrait.csv")
    if df is None or not len(df):
        return []
    levels = c.get("levels") or ["高风险"]
    df = df[df["综合风险等级"].isin(levels)]
    df = df[df["近12月销售额"].apply(lambda v: _num(v)) >= float(c.get("min_product_revenue", 200000))]
    high_levels = c.get("high_levels") or ["极高风险"]
    out = []
    for _, r in df.iterrows():
        grade = str(r["综合风险等级"]).strip()
        level = "高" if grade in high_levels else "中"
        factor = str(r.get("风险主导因子") or "").strip()
        rev = _num(r.get("近12月销售额"))
        gold_advice = str(r.get("通用策略建议") or "").strip()
        if len(gold_advice) > 90:
            gold_advice = gold_advice[:90] + "…"
        ctx = {"factor": factor or "-", "rev": f"{rev / 10000:.1f}",
               "gold_advice": gold_advice or "复盘产品策略"}
        out.append(_sig(r["产品名称"], "高风险产品", level, 0.0,
                        f"综合风险【{grade}】，主导因子：{factor or '-'}，近12月销售额{rev / 10000:.1f}万",
                        _render_template(cfg, "高风险产品", level, ctx), "高风险产品"))
    return out


def _ch_pricing_anomaly(cfg):
    """通道7 定价异常：定价合理性分析 异常低价标记=异常值 且 |偏离P50%| ≥ 10%。"""
    c = (cfg.get("channels") or {}).get("pricing_anomaly") or {}
    if c.get("enabled", True) is False:
        return []
    df = _read_gold("定价合理性分析.csv")
    if df is None or not len(df):
        return []
    flags = set(c.get("abnormal_flags") or ["异常低价"])
    df = df[df["异常低价标记"].astype(str).isin(flags)]
    df = df[df["价格偏离P50%"].apply(lambda v: abs(_num(v))) >= float(c.get("min_deviation", 10))]
    out = []
    for _, r in df.iterrows():
        dev = _num(r["价格偏离P50%"])
        level = "高" if dev <= -float(c.get("high_deviation", 20)) else "中"
        sales = str(r.get("业务负责人") or "").strip() or "-"
        attribution = str(r.get("归因分析") or "").strip()
        ctx = {"sales": sales, "dev": f"{dev:.0f}", "attribution": attribution or "-"}
        out.append(_sig(r["客户编号"], "定价异常", level, 0.0,
                        f"业务员{sales}，偏离P50达{dev:.0f}%（{r['产品品种']}）",
                        _render_template(cfg, "定价异常", level, ctx), "定价异常"))
    return out


def _snapshot_path(month):
    """回填用 erp 快照路径（.parquet 优先，.kbdat 容器回退）。"""
    base = os.path.join(PLATFORM, "data_warehouse", month)
    for name in ("erp_snapshot.parquet", "erp_snapshot.kbdat"):
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    return None


def _backfill_signals(month, cfg):
    """简化回填模式：仅基于 erp 快照重算两通道（营收断崖 + 负毛利）。
    限制：不跑完整 silver→gold 主链（不动主链），口径为快照内 12 个月窗口的简化重算；
    其余 6 通道需 gold 派生表（客户全景/趋势/组合健康度/产品画像/定价分析），历史月不可行。
    """
    path = _snapshot_path(month)
    if not path:
        print(f"  [警告] 无 {month} 快照，简化回填两通道不可用（仅生成头部与空表）")
        return []
    sys.path.insert(0, os.path.join(PLATFORM, "processing"))
    from shared.snapshot_container import load_snapshot_frame  # noqa: PLC0415
    df = load_snapshot_frame(path)
    # 客户键：终端客户简称与 gold 客户编号同源（如 中兴康讯），缺失回退 客户（全称）
    cust_col = "终端客户简称" if "终端客户简称" in df.columns else "客户"
    df = df.assign(_cust=df[cust_col].where(df[cust_col].notna()
                                            & (df[cust_col].astype(str).str.strip() != ""),
                                            df["客户"]))
    cols = {"date": "发货日期", "cust": "_cust", "sku": "存货名称",
            "rev": "RMB 未税金额小计", "cost": "总成本"}
    df = df[[cols[k] for k in ("date", "cust", "sku", "rev", "cost")]].copy()
    df["_d"] = pd.to_datetime(df[cols["date"]], errors="coerce")
    df = df.dropna(subset=["_d"])
    end = pd.Timestamp(int(month[:4]), int(month[4:]), 1) + pd.offsets.MonthEnd(0)
    start = end - pd.DateOffset(months=11)
    win = df[(df["_d"] >= start) & (df["_d"] <= end)]
    c = (cfg.get("channels") or {}).get("neg_margin") or {}
    min_loss = float(c.get("min_loss", NEG_MARGIN_MIN_LOSS))
    c2 = (cfg.get("channels") or {}).get("revenue_shock") or {}
    min_rev = float(c2.get("min_month_revenue", 100000))
    out = []
    # —— 负毛利（快照简化口径：窗口内 客户×SKU 收入<成本 聚合）——
    g = (win.assign(_rev=pd.to_numeric(win[cols["rev"]], errors="coerce").fillna(0),
                    _cost=pd.to_numeric(win[cols["cost"]], errors="coerce").fillna(0))
              .groupby([cols["cust"], cols["sku"]], sort=False)[["_rev", "_cost"]].sum())
    neg = g[g["_rev"] < g["_cost"]]
    if len(neg):
        cust = neg.assign(_loss=neg["_cost"] - neg["_rev"]).groupby(level=0, sort=False)
        for name, grp in cust:
            loss = float(grp["_loss"].sum())
            if loss < min_loss:
                continue
            n = len(grp)
            level = "高" if loss >= 100000 else "中"
            ctx = {"n": n, "total": n, "pct": "-", "loss": f"{loss / 10000:.1f}",
                   "gold_advice": "逐品种复核定价与成本（简化回填口径）"}
            out.append(_sig(name, "负毛利", level, loss,
                            f"{n}个品种负毛利，损失{loss / 10000:.1f}万",
                            _render_template(cfg, "负毛利", level, ctx), "负毛利"))
    # —— 营收断崖（当月 vs 上月 客户月收入环比）——
    win = win.assign(_m=win["_d"].dt.strftime("%Y-%m"))
    piv = win.pivot_table(index=cols["cust"], columns="_m",
                          values=cols["rev"], aggfunc="sum").fillna(0.0)
    cur_m, prev_m = f"{month[:4]}-{month[4:]}", f"{end - pd.DateOffset(months=1):%Y-%m}"
    if cur_m in piv.columns:
        cur = piv[cur_m]
        prev = piv[prev_m] if prev_m in piv.columns else pd.Series(0.0, index=piv.index)
        for cust in piv.index:
            cv, pv = float(cur[cust]), float(prev[cust])
            if cv >= min_rev and pv > 0:
                mom = (cv - pv) / pv * 100.0
                if mom <= float(c2.get("mom_drop", -50)):
                    ctx = {"cur": f"{cv / 10000:.1f}", "mom": f"{mom:.0f}", "months": "环比骤降"}
                    out.append(_sig(cust, "营收断崖", "高", max(0.0, pv - cv),
                                    f"本月收入{cv / 10000:.1f}万，环比{mom:.0f}%",
                                    _render_template(cfg, "营收断崖", "高", ctx), "营收异动"))
            elif cv >= min_rev and pv <= 0:
                ctx = {"cur": f"{cv / 10000:.1f}", "mom": "新导入"}
                out.append(_sig(cust, "新导入", "中", 0.0,
                                f"本月收入{cv / 10000:.1f}万（上月≈0）",
                                _render_template(cfg, "新导入", "中", ctx), "营收异动"))
    return out


def collect_signals(month, cfg, simplified=False):
    """8 通道信号采集（简化回填模式仅两通道，数据源=当月 erp 快照）。"""
    if simplified:
        return _backfill_signals(month, cfg)
    sigs = []
    for fn in (_ch_anomaly_log, _ch_neg_margin, _ch_purchase_interrupt,
               _ch_margin_deterioration, _ch_decline_risk, _ch_high_risk_product,
               _ch_pricing_anomaly):
        sigs.extend(fn(cfg))
    sigs.extend(_ch_revenue_shock(month, cfg))
    return sigs


def merge_signals(sigs):
    """去重合并：同客户多通道 → 一行（类型顿号拼接 / 等级取最高 / 上下文与建议取最严重通道）。"""
    groups, order = {}, []
    for s in sigs:
        if s["customer"] not in groups:
            groups[s["customer"]] = []
            order.append(s["customer"])
        groups[s["customer"]].append(s)
    merged = []
    for cust in order:
        gs = groups[cust]
        gs.sort(key=lambda s: (RISK_LEVEL_ORDER.get(s["level"], 9), -s["loss"]))
        best = gs[0]
        types = []
        for s in gs:
            for t in s["types"]:
                if t not in types:
                    types.append(t)
        merged.append({**best, "types": types, "rtype": "、".join(types),
                       "loss": max(x["loss"] for x in gs),
                       "channels": [x["channel"] for x in gs]})
    return merged


def _norm_types(事项):
    """事项文本 → 风险类型令牌集（兼容旧版"客户XX"前缀与"负毛利产品 N 个"写法）。"""
    t = str(事项 or "").strip()
    if t.startswith("客户"):
        t = t[2:]
    out = set()
    for x in re.split(r"[、，,/]", t):
        x = x.strip()
        if not x:
            continue
        out.add("负毛利" if "负毛利" in x else x)
    return out


_CONT_RE = re.compile(r"连续第\s*(\d+)\s*月")


def _prev_month(month):
    y, m = int(month[:4]), int(month[4:])
    m -= 1
    if m == 0:
        y, m = y - 1, 12
    return f"{y}{m:02d}"


def load_prev_month_risks(month):
    """上月 risk_action md → [{customer, types, level, loss_wan, months}]（无上月/解析失败 → []）。"""
    path = risk_md_path(_prev_month(month))
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        sections = _parse_md_tables(f.read())
    part = None
    for sec, val in sections.items():
        if "风险摘要" in sec:
            part = val
            break
    if not part or not part[0]:
        return []
    headers, rows = part
    idx = {h: i for i, h in enumerate(headers)}
    ci = idx.get("客户/产品", idx.get("客户编号", 2))
    ii, li = idx.get("事项", 1), idx.get("等级", 0)
    di = next((i for h, i in idx.items() if "损失金额" in h), None)
    ti = idx.get("持续")
    out = []
    for r in rows:
        if len(r) <= max(ci, ii):
            continue
        loss_wan = None
        if di is not None and len(r) > di:
            try:
                loss_wan = float(str(r[di]).replace(",", ""))
            except ValueError:
                loss_wan = None
        months = 1
        if ti is not None and len(r) > ti:
            mcont = _CONT_RE.search(str(r[ti]))
            if mcont:
                months = int(mcont.group(1))
        out.append({"customer": r[ci].strip(), "types": _norm_types(r[ii]),
                    "level": r[li].strip() if len(r) > li else "中",
                    "loss_wan": loss_wan, "months": months})
    return out


def annotate_month_over_month(merged, prev):
    """月度对拍（设计 §2.2）：连续第 N 月 + 较上月恶化/好转/持平；返回 (annotated, released)。
    关联键 = 客户编号 × 风险类型（令牌交集匹配，负毛利含别名）。"""
    used = set()
    annotated = []
    for s in merged:
        match = None
        for i, p in enumerate(prev):
            if i in used or p["customer"] != s["customer"] or not (p["types"] & set(s["types"])):
                continue
            if match is None or p["months"] > prev[match]["months"]:
                match = i
        s = dict(s)
        if match is None:
            s["months"], s["持续"], s["较上月"] = 0, "新增", "-"
        else:
            used.add(match)
            p = prev[match]
            s["months"] = p["months"] + 1
            s["持续"] = f"连续第 {s['months']} 月"
            s["较上月"] = _mom_change(s, p)
        annotated.append(s)
    released = [p for i, p in enumerate(prev) if i not in used]
    return annotated, released


def _mom_change(cur, prev):
    """较上月判定：损失额对比（±10% 且 ≥1万 死区）优先，其次等级升降，否则持平。"""
    cl, pl = cur["level"], prev["level"]
    cw, pw = cur["loss"] / 10000.0, prev["loss_wan"]
    if pw is not None and pw > 0 and cw > 0:
        if cw > pw * 1.1 and cw - pw >= 1.0:
            return "较上月恶化"
        if cw < pw * 0.9 and pw - cw >= 1.0:
            return "较上月好转"
    co, po = RISK_LEVEL_ORDER.get(cl, 9), RISK_LEVEL_ORDER.get(pl, 9)
    if co < po:
        return "较上月恶化"
    if co > po:
        return "较上月好转"
    return "持平"


def _month_end_due(month):
    last = calendar.monthrange(int(month[:4]), int(month[4:]))[1]
    return f"{month[:4]}-{month[4:]}-{last:02d}"


def _write_overflow(month, overflow, stats):
    r"""溢出附件：全量未上榜信号 → output\dashboard\风险溢出明细_YYYY-MM.md（通道×等级排序）。"""
    path = os.path.join(RISK_MD_DIR, f"风险溢出明细_{month[:4]}-{month[4:]}.md")
    rows = sorted(overflow,
                  key=lambda s: (s["channel"], RISK_LEVEL_ORDER.get(s["level"], 9), -s["loss"]))
    lines = [f"# 风险溢出明细 · {month[:4]}-{month[4:]}", "",
             f"> 生成时间：{datetime.now():%Y-%m-%d %H:%M} ｜ 合并去重后未进 Top 榜的全量信号"
             f"（共 {len(rows)} 条，按通道×等级排序），深挖时人工查阅，不上主文档。", ""]
    lines.append(_md_table(["通道", "等级", "客户/产品", "风险类型", "损失金额(万元)", "上下文"],
                           [[s["channel"], s["level"], s["customer"], s["rtype"],
                             _fmt_wan(s["loss"]) if s["loss"] > 0 else "-", s["context"]]
                            for s in rows]))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    stats["overflow_file"] = path
    return path


def build_draft(month):
    """生成总体文档初稿（策展引擎 v2）。返回 (md_text, 统计dict)。
    v2 策展：8 通道信号 → 同客户合并 → 上月对拍（连续月/恶化好转/本月解除）→ Top12
    → 溢出附件；高等级+连续≥2月 自动转行动种子。历史月无 gold 时走简化回填（两通道）。"""
    stats = {"signals": 0, "merged": 0, "listed": 0, "overflow": 0, "carryover": 0,
             "meeting": 0, "seeds": 0, "released": 0, "consecutive": 0, "simplified": False}
    cfg = _load_templates()
    top_n = int(cfg.get("top_n") or TOP_N_PER_SOURCE)
    data_month = _data_month()
    simplified = month != data_month
    stats["simplified"] = simplified

    # --- 信号采集 + 合并 + 月度对拍 ---
    sigs = collect_signals(month, cfg, simplified=simplified)
    stats["signals"] = len(sigs)
    merged = merge_signals(sigs)
    stats["merged"] = len(merged)
    annotated, released = annotate_month_over_month(merged, load_prev_month_risks(month))
    stats["released"] = len(released)
    stats["consecutive"] = sum(1 for s in annotated if s["months"] >= 2)
    annotated.sort(key=lambda s: (RISK_LEVEL_ORDER.get(s["level"], 9), -s["loss"]))
    top, overflow = annotated[:top_n], annotated[top_n:]
    stats["listed"], stats["overflow"] = len(top), len(overflow)
    _write_overflow(month, overflow, stats)

    risk_rows = [[s["level"], s["rtype"], s["customer"],
                 _fmt_wan(s["loss"]) if s["loss"] > 0 else "-",
                 s["持续"], s["较上月"], s["suggestion"], ""] for s in top]

    # --- 行动清单：上月未关闭结转（created_month 保留修复在渲染回写处）---
    action_rows = []
    actions = load_actions()
    for it in actions.get("items", []):
        if it.get("status") in ("待处理", "跟进中"):
            action_rows.append([it["status"], it["title"], it.get("owner", ""),
                                it.get("due_date", ""), it.get("note", "")])
            stats["carryover"] += 1

    # --- 行动种子：高等级 + 连续≥N月 → 自动转行动项草稿（负责人空，期望完成日=月末）---
    sc = cfg.get("seeds") or {}
    seed_level, seed_months = sc.get("min_level", "高"), int(sc.get("min_consecutive", 2))
    existing_titles = {r[1] for r in action_rows}
    for s in top:
        if s["level"] == seed_level and s["months"] >= seed_months:
            title = f"[自动种子] {s['customer']}：{s['rtype']}"
            if title in existing_titles:
                continue
            action_rows.append(["待处理", title, "", _month_end_due(month),
                                f"已连续 {s['months']} 月上榜（{s['较上月']}），请指派负责人"])
            existing_titles.add(title)
            stats["seeds"] += 1

    # --- 行动清单：可选速记 meeting_track.md 并入 ---
    _mt_path = _meeting_md_path()
    if os.path.exists(_mt_path):
        with open(_mt_path, encoding="utf-8") as f:
            mt = _parse_md_tables(f.read())
        for _sec, (headers, rows) in mt.items():
            for r in rows:
                if len(r) >= 3 and r[0] != "已关闭":
                    action_rows.append([r[0], r[1], r[2],
                                        r[3] if len(r) > 3 else "",
                                        r[5] if len(r) > 5 else ""])
                    stats["meeting"] += 1

    action_rows.sort(key=lambda r: STATUS_ORDER.get(r[0], 9))

    # --- 备注：本月解除（上月上榜本月消失，闭环反馈；经既有「备注」节渲染进看板）---
    notes_lines = []
    if released:
        notes_lines.append("【本月解除】上月上榜、本月消失（疑似改善，闭环确认）：")
        for p in released:
            types = "、".join(sorted(p["types"])) or "-"
            notes_lines.append(f"- {p['customer']}（{types}，上月等级 {p['level']}）")

    # --- 口径说明（从 faces.yaml R 面 sections 带入）---
    with open(FACES_YAML, encoding="utf-8") as f:
        faces = yaml.safe_load(f)["faces"]
    rsec = faces["R"]["sections"]
    caliber_lines = []
    for s in rsec:
        caliber_lines.append(f"【{s['title']}】{s['definition']}。{s['koujing']}")
    # [r7] R面术语表也渲染进口径节（与其他面 glossary 渲染对齐）
    for _g in (faces["R"].get("glossary") or []):
        caliber_lines.append(f"【术语·{_g['term']}】{_g['definition']}")
    caliber = "\n".join(caliber_lines)

    mode_note = ("简化回填模式：历史月无 gold 派生表，仅基于当月 erp 快照重算"
                 "【营收断崖+负毛利】两通道，其余 6 通道自 202609 起全通道。") if simplified else \
                "8 通道信号源（异常日志/营收异动/采购中断/毛利率恶化/衰退风险/高风险产品/定价异常/负毛利）。"
    md = f"""# 风险与行动 · {month[:4]}-{month[4:]}

> 本文件由跑批自动生成初稿，请审定后渲染进看板。增删改随意，以本文件为准。
> 渲染：python run_chain.py --dashboard-only（或双击 2_只生成看板.bat）
> 生成时间：{datetime.now():%Y-%m-%d %H:%M} ｜ 数据月份：{month}
> 初稿策展（v2）：{mode_note}同客户多通道合并为一行；上榜 Top {top_n}（等级优先+损失额加权）；
> 共 {stats['signals']} 条信号 → 合并 {stats['merged']} 条 → 上榜 {stats['listed']} 条，溢出 {stats['overflow']} 条（详见 风险溢出明细_{month[:4]}-{month[4:]}.md）；
> 与上月对拍：连续≥2月 {stats['consecutive']} 条 / 本月解除 {stats['released']} 条；行动种子 {stats['seeds']} 条。人工审定可增删改任何条目。

## 一、当月风险摘要

{_md_table(["等级", "事项", "客户/产品", "损失金额(万元)", "持续", "较上月", "建议动作", "负责人"], risk_rows)}

## 二、行动清单

{_md_table(["状态", "事项", "负责人", "期望完成日", "备注"], action_rows)}
"""
    if notes_lines:
        md += f"\n## 备注\n\n" + "\n".join(notes_lines) + "\n"
    md += f"""
## 三、口径说明（从 faces.yaml 自动带入，勿改）

{caliber}
"""
    return md, stats


# ---------- 渲染 ----------

_TAG_KIND_MAP = {"等级": {"高": "high", "中": "medium", "低": "low"},
                 "状态": {"待处理": "high", "跟进中": "medium", "已关闭": "low"}}
_CLS_TO_LEVEL = {"kpi-danger": "red", "kpi-warning": "orange", "kpi-success": "green", "": "none"}


def _tag(text, kind_map, prefix="tag"):
    cls = kind_map.get(text, "none")
    return f'<span class="{prefix} {prefix}-{cls}">{_esc(text)}</span>'


def _render_table(part):
    """表头驱动动态列渲染（P0-5/动态列）：列名/列数来自 md 表头；核心列（等级/状态）存在时维持
    tag 色，缺失时降级普通列（调用方在口径条补提示文本）；数值格按值正则右对齐（P2，
    ^-?[\d,.]+%?万?$）；行级色=首列 emoji（style.row_color）→ 淡色底整行。行短于表头容错补空。"""
    columns = part.get("columns") or []
    rows = part.get("rows") or []
    if not columns:
        return ""
    th = "".join(f"<th>{_esc(h)}</th>" for h in columns)
    trs = []
    for row in rows:
        cells = row.get("cells") or []
        row_color = (row.get("style") or {}).get("row_color", "none")
        row_style = f' style="background:{ROW_COLOR_BG[row_color]}"' if row_color in ROW_COLOR_BG else ""
        tds = []
        for i, cell in enumerate(cells):
            if i >= len(columns):
                break
            text = cell.get("text", "")
            cls = ' class="num"' if VALUE_ALIGN_RE.match(text) else ""
            core_map = _TAG_KIND_MAP.get(columns[i])
            if core_map is not None:
                tds.append(f"<td>{_tag(text, core_map)}</td>")
            else:
                cell_prefix = COLOR_TO_EMOJI.get(cell.get("color", "none"), "")
                tds.append(f"<td{cls}>{cell_prefix}{_esc(text)}</td>")
        while len(tds) < len(columns):
            tds.append("<td></td>")
        trs.append("<tr" + row_style + ">" + "".join(tds) + "</tr>")
    body = "".join(trs) or f'<tr><td colspan="{len(columns)}" style="text-align:center;color:var(--text-muted)">本期无内容</td></tr>'
    return f'<table class="data-table"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


def _kc(label, value, sub, cls=""):
    return (f'<div class="kc {cls}"><div class="label">{label}</div>'
            f'<div class="value">{value}</div><div class="sub">{sub}</div></div>')


def _derive(risk_part, action_part):
    """派生 KPI 现算（P0-3）。核心列缺失时降级：对应卡数值 '-'、ints 记 None。
    返回 (derived, ints)：derived={标题:(数值str,副文本str,css_cls)}，ints={n_high,n_mid,loss_sum,n_todo,n_doing}。"""
    risk_cols = risk_part.get("columns") or []
    risk_rows = [r.get("cells") or [] for r in risk_part.get("rows") or []]
    act_cols = action_part.get("columns") or []
    act_rows = [r.get("cells") or [] for r in action_part.get("rows") or []]
    if "等级" in risk_cols:
        li = risk_cols.index("等级")
        n_high = sum(1 for r in risk_rows if li < len(r) and r[li]["text"] == "高")
        n_mid = sum(1 for r in risk_rows if li < len(r) and r[li]["text"] == "中")
    else:
        n_high = n_mid = None
    loss_col = next((i for i, c in enumerate(risk_cols) if "损失金额" in c), None)
    loss_sum = 0.0
    if loss_col is not None:
        for r in risk_rows:
            if loss_col < len(r):
                v = r[loss_col]["text"]
                if v not in ("-", ""):
                    try:
                        loss_sum += float(v)
                    except ValueError:
                        pass
    if "状态" in act_cols:
        si = act_cols.index("状态")
        n_todo = sum(1 for r in act_rows if si < len(r) and r[si]["text"] == "待处理")
        n_doing = sum(1 for r in act_rows if si < len(r) and r[si]["text"] == "跟进中")
    else:
        n_todo = n_doing = None
    derived = {
        "高风险事项": (str(n_high) if n_high is not None else "-", "需立即处理", "kpi-danger"),
        "中风险事项": (str(n_mid) if n_mid is not None else "-", "需关注", "kpi-warning"),
        "负毛利损失合计": (f"{loss_sum:.1f}万" if loss_col is not None else "-",
                        "审定后展示口径", "kpi-danger" if loss_sum > 0 else ""),
        "行动项": (str(n_todo + n_doing) if n_todo is not None else "-",
                   f"待处理 {n_todo} · 跟进中 {n_doing}" if n_todo is not None else "「状态」列缺失，无法统计", ""),
    }
    ints = {"n_high": n_high, "n_mid": n_mid, "loss_sum": loss_sum,
            "n_todo": n_todo, "n_doing": n_doing}
    return derived, ints


def _kpi_cards_for(doc):
    """渲染/导出共用的 KPI 卡数组（§3.3）：md 有 KPI 节用人工卡，否则 4 张派生默认（不落盘语义）。"""
    derived, _ = _derive(_find_table(doc, "风险摘要"), _find_table(doc, "行动清单"))
    if doc.get("kpi_cards"):
        return doc["kpi_cards"]
    return [{"title": t, "value": derived[t][0], "sub": derived[t][1],
             "level": _CLS_TO_LEVEL.get(derived[t][2], "none"), "source": "derived"}
            for t in KPI_TITLES]


def _kpi_bar_html(cards):
    """KPI 卡数组 → kpi-bar HTML（P0-3/P1）：repeat(min(n,8),1fr) Python 计算注入；n=0 隐藏整条。"""
    n = len(cards or [])
    if n == 0:
        return ""
    cols = f"repeat({min(n, 8)},1fr)"
    inner = "".join(
        _kc(c.get("title", ""), c.get("value", ""), c.get("sub", ""),
            KPI_LEVEL_TO_CLS.get(c.get("level", "none"), ""))
        for c in cards)
    return (f'<div class="kpi-bar" style="grid-template-columns:{cols};margin-left:auto;margin-right:auto">\n'
            + inner + "\n</div>\n")


def _notes_html(notes_raw):
    """## 备注 自由段落节渲染（P1）：普通段落区；_md_cell 清洗不触碰该节，import 逐字节回写。"""
    if not (notes_raw or "").strip():
        return ""
    paras = "".join(f"<p>{_esc(ln)}</p>" for ln in notes_raw.splitlines() if ln.strip())
    if not paras:
        return ""
    return '<div class="cb"><h3>备注</h3><div class="caliber">' + paras + "</div></div>\n"


def _build_r_parts(month):
    """解析总体文档并构建 R 面各区块（测试页与正式看板并入共用；编辑协议与渲染同一解析器）。
    返回 dict: ok / err / kpi_bar / risk_table / action_table / caliber / notes_html / stats。
    副作用：行动清单状态回写 action_items.json（P1 稳定键：行内容 sha1 前 8 位）。"""
    md_path = risk_md_path(month)
    if not os.path.exists(md_path):
        return {"ok": False, "err": md_path}
    with open(md_path, encoding="utf-8") as f:
        doc = _parse_doc(f.read())
    risk_part = _find_table(doc, "风险摘要")
    action_part = _find_table(doc, "行动清单")
    derived, ints = _derive(risk_part, action_part)

    # P0-5：核心列降级提示（渲染端列名特判在核心列缺失时降级普通列，口径条补提示文本）
    degrade_hints = []
    if risk_part.get("columns") and "等级" not in risk_part["columns"]:
        degrade_hints.append("「等级」核心列缺失：风险表等级着色与派生统计已降级为普通列。")
    if action_part.get("columns") and "状态" not in action_part["columns"]:
        degrade_hints.append("「状态」核心列缺失：行动清单状态着色与派生统计已降级为普通列。")
    caliber = doc.get("caliber_raw", "")
    if degrade_hints:
        caliber = (caliber + "\n" + "\n".join(degrade_hints)) if caliber else "\n".join(degrade_hints)

    # P1：行动清单状态回写 action_items.json（稳定键 = 行内容 sha1 前 8 位）
    act_cols = action_part.get("columns") or []
    if act_cols:
        idx = {h: i for i, h in enumerate(act_cols)}
        items = []
        for row in action_part.get("rows") or []:
            r = [c["text"] for c in row["cells"]]
            if not r or len(r) < 2:
                continue
            _raw = "|".join(r)
            items.append({
                "id": f"row:{hashlib.sha1(_raw.encode('utf-8')).hexdigest()[:8]}",
                "title": r[1],
                "status": r[0] if r[0] in STATUS_ORDER else "待处理",
                "owner": r[idx["负责人"]] if "负责人" in idx and len(r) > idx["负责人"] else "",
                "due_date": r[idx["期望完成日"]] if "期望完成日" in idx and len(r) > idx["期望完成日"] else "",
                "note": r[idx["备注"]] if "备注" in idx and len(r) > idx["备注"] else "",
                "created_month": month,
                "source": "总体文档",
            })
        actions = load_actions()
        old_by_id = {it.get("id"): it for it in actions.get("items", [])}
        for it in items:  # 结转修复①：created_month 保留首次创建月，不随渲染回写刷新成当月
            old = old_by_id.get(it["id"])
            if old and _is_month(str(old.get("created_month") or "")):
                it["created_month"] = old["created_month"]
        closed = [it for it in actions.get("items", []) if it.get("status") == "已关闭"]
        for it in closed:  # 结转修复②：补 closed_month（归档关闭月）
            if not it.get("closed_month"):
                it["closed_month"] = month
        save_actions({"version": "1", "last_batch_month": month, "items": items + closed})

    risk_cells = [r.get("cells") or [] for r in risk_part.get("rows") or []]
    act_cells = [r.get("cells") or [] for r in action_part.get("rows") or []]
    n_high = ints["n_high"] if ints["n_high"] is not None else 0
    n_mid = ints["n_mid"] if ints["n_mid"] is not None else 0
    return {"ok": True, "kpi_bar": _kpi_bar_html(_kpi_cards_for(doc)),
            "risk_table": _render_table(risk_part),
            "action_table": _render_table(action_part),
            "caliber": caliber,
            "notes_html": _notes_html(doc.get("notes_raw", "")),
            "stats": (len(risk_cells), n_high, n_mid, float(ints["loss_sum"]), len(act_cells))}


def build_r_face_inner_html(month):
    """供 generate_dashboard.py 并入正式看板（W4）：返回 R 面内容 HTML（不含页面框架，
    样式复用 template.html 的 kpi-bar/kc/cb/data-table 组件）。签名不变（公共 API 边界）。"""
    parts = _build_r_parts(month)
    if not parts["ok"]:
        return ('<div class="cb"><h3>风险与行动</h3><div class="note">本月总体文档未生成：'
                '请先在明文窗口跑批后运行 <code>python dashboard\\generate_risk_face.py</code> '
                '生成并审定总体文档（缺失：' + _esc(parts["err"]) + '）</div></div>')
    return (parts["kpi_bar"]
            + '<div class="cb"><h3>一、当月风险摘要</h3><div class="note">初稿由系统按规则生成，经人工审定后展示。</div>'
            + parts["risk_table"] + '</div>\n'
            + '<div class="cb"><h3>二、行动清单</h3><div class="note">状态：待处理 / 跟进中 / 已关闭。未关闭事项跨月自动结转。</div>'
            + parts["action_table"] + '</div>\n'
            + parts.get("notes_html", "")
            + '<div class="cb"><h3>三、口径说明</h3><div class="caliber">'
            + _esc(parts["caliber"]) + '</div></div>')


def render(month):
    parts = _build_r_parts(month)
    if not parts["ok"]:
        print(f"[错误] 总体文档不存在: {parts['err']}")
        return 1
    with open(TEMPLATE, encoding="utf-8") as f:
        page = f.read()
    page = (page
            .replace("%%DATA_MONTH%%", month)
            .replace("%%GEN_TIME%%", f"{datetime.now():%Y-%m-%d %H:%M}")
            .replace("%%RISK_KPI%%", parts["kpi_bar"])
            .replace("%%RISK_TABLE%%", parts["risk_table"])
            # P1：备注自由段落节跟在行动清单表后（测试页模板不新增占位符，运行时拼接）
            .replace("%%ACTION_TABLE%%", parts["action_table"] + parts.get("notes_html", ""))
            .replace("%%CALIBER%%", _esc(parts["caliber"])))
    out = os.path.join(DASH_DIR, "dashboard_risk_test.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)

    n_r, n_high, n_mid, loss_sum, n_act = parts["stats"]
    print(f"[OK] 测试页已生成: {out}")
    print(f"     风险摘要 {n_r} 条（高 {n_high} / 中 {n_mid}）；行动项 {n_act} 条；负毛利损失合计 {loss_sum:.1f} 万")
    return 0


# ---------- 编辑协议：export / import（§9.5 契约，两侧施工唯一依据）----------

class ProtocolError(Exception):
    """协议层错误：err 进 envelope，stage ∈ parse|import|render。"""

    def __init__(self, err, stage="import"):
        super().__init__(err)
        self.err = err
        self.stage = stage


def _check_color(v, where):
    if v not in ("red", "orange", "green", "gray", "none"):
        raise ProtocolError(f"{where}: 非法色值 {v!r}（须 red/orange/green/gray/none）")
    return v


def _export_table(part):
    """表导出：columns/col_meta（核心列 locked=true，P0-5）/rows（cells[{text,color}]+style.row_color）。"""
    columns = part.get("columns") or []
    return {"columns": columns,
            "col_meta": [{"name": c, "locked": c in CORE_COLUMNS} for c in columns],
            "rows": part.get("rows") or []}


def export_to_dict(month_or_path):
    """--export-json 核心：md → §9.5 契约 JSON dict。
    month_or_path: 'YYYYMM'（走 risk_md_path 新位置优先旧位置回退）或显式 md 文件路径。"""
    path = _resolve_target_path(month_or_path)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    month = (month_or_path if _is_month(month_or_path)
             else os.path.splitext(os.path.basename(path))[0].replace("risk_action_", ""))
    with open(path, encoding="utf-8") as f:
        doc = _parse_doc(f.read())
    risk_part = _find_table(doc, "风险摘要")
    action_part = _find_table(doc, "行动清单")
    derived, ints = _derive(risk_part, action_part)
    # P0-3：KPI 卡（md 有节用人工卡覆盖同标题派生卡，附加卡追加；每卡附 derived_value+stale）
    md_cards = {c.get("title"): c for c in (doc.get("kpi_cards") or [])}
    cards = []
    for t in KPI_TITLES:
        c = md_cards.pop(t, None)
        card = {"title": t, "value": derived[t][0], "sub": derived[t][1],
                "level": _CLS_TO_LEVEL.get(derived[t][2], "none"), "source": "derived",
                "derived_value": derived[t][0]}
        if c:
            for k in ("value", "sub", "level", "source"):
                if c.get(k):
                    card[k] = c[k]
        # P0-3：stale = 卡面 value 与现算派生值不一致（无论来源；纯派生卡天然 False）
        card["stale"] = bool(card["derived_value"] is not None
                             and str(card["value"]) != str(card["derived_value"]))
        cards.append(card)
    for t, c in md_cards.items():  # 非派生标题的自定义卡
        cards.append({"title": c.get("title", ""), "value": c.get("value", ""),
                      "sub": c.get("sub", ""), "level": c.get("level", "none"),
                      "source": c.get("source") or "custom",
                      "derived_value": None, "stale": False})
    n_high = ints["n_high"] if ints["n_high"] is not None else 0
    n_mid = ints["n_mid"] if ints["n_mid"] is not None else 0
    return {
        "month": month,
        "mtime": os.path.getmtime(path),
        "header_raw": doc.get("header_raw", ""),
        "kpi_cards": cards,
        "risk_table": _export_table(risk_part),
        "action_table": _export_table(action_part),
        "notes_section": doc.get("notes_raw", ""),
        "caliber_raw": doc.get("caliber_raw", ""),
        "derived_snapshot": {"n_high": n_high, "n_mid": n_mid,
                             "loss_sum": round(float(ints["loss_sum"]), 1)},
        "legend": dict(LEGEND),
    }


def _import_table(data, key):
    """import 表校验（P1 矩形校验：列数不齐显式报错行号）+ 文本规范化（P0-4 换行拒绝）。"""
    part = data.get(key)
    if not isinstance(part, dict) or not part.get("columns"):
        raise ProtocolError(f"{key}: 缺少 columns 或为空")
    columns = [str(c) for c in part["columns"]]
    rows = []
    for rn, row in enumerate(part.get("rows") or [], 1):
        if not isinstance(row, dict):
            raise ProtocolError(f"{key}: 第 {rn} 行不是对象")
        cells = row.get("cells")
        if not isinstance(cells, list) or len(cells) != len(columns):
            got = len(cells) if isinstance(cells, list) else "缺失"
            raise ProtocolError(f"{key}: 第 {rn} 行单元格数 {got} 与列数 {len(columns)} 不一致（矩形校验失败）")
        row_color = _check_color((row.get("style") or {}).get("row_color", "none"),
                                 f"{key} 第 {rn} 行行级色")
        out_cells = []
        for ci, cell in enumerate(cells):
            if not isinstance(cell, dict):
                raise ProtocolError(f"{key} 第 {rn} 行第 {ci + 1} 列不是对象")
            raw = str(cell.get("text", ""))
            if "\n" in raw or "\r" in raw:
                raise ProtocolError(f"{key} 第 {rn} 行第 {ci + 1} 列含换行：请改用编辑器的宽幅抽屉分段编辑"
                                    f"（多条建议用全角｜分隔，由编辑器拆分/回拼）")
            out_cells.append({"text": _md_cell(raw),
                              "color": _check_color(cell.get("color", "none"),
                                                    f"{key} 第 {rn} 行第 {ci + 1} 列色值")})
        if out_cells and out_cells[0]["color"] != "none":
            row_color = out_cells[0]["color"]  # P0-7：行级色=首列单元格内容级 emoji
        rows.append({"cells": out_cells, "style": {"row_color": row_color}})
    return {"columns": columns, "rows": rows}


def _part_md_table(part):
    """表 → md 行（emoji 回编码：color→前缀，§3.2；多条建议的全角｜由编辑器层处理，Python 透传）。
    0 数据行也必须落表头+分隔行，保证列结构在往返中不丢失。"""
    columns = part.get("columns") or []
    if not columns:
        return []
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    for row in part.get("rows") or []:
        cells = []
        for cell in row["cells"]:
            text = cell["text"]
            if cell["color"] in COLOR_TO_EMOJI:
                text = COLOR_TO_EMOJI[cell["color"]] + text
            cells.append(text)
        lines.append("| " + " | ".join(_md_cell(c) for c in cells) + " |")
    return lines


def _compose_md(month, header_raw, cards, risk_part, action_part, notes, caliber_raw, had_kpi):
    """md 组装（单一真源，import 专用）：分区顺序固定（§3.1）。
    KPI 节仅在"原 md 有节或存在非派生卡"时落盘（§3.3：初稿/全派生默认不落盘，保持派生默认）。"""
    parts = [_title_month(month), ""]
    if header_raw:
        parts.append(header_raw)
    parts.append("")
    persist_kpi = bool(cards) and (had_kpi or any(c["source"] != "derived" for c in cards))
    if persist_kpi:
        kpi_rows = [[c["title"], c["value"], c["sub"], COLOR_TO_TEXT.get(c["level"], ""), c["source"]]
                    for c in cards]
        parts += [f"## {KPI_SECTION_TITLE}", "", _md_table(KPI_COLS, kpi_rows), ""]
    parts += ["## 一、当月风险摘要", ""] + _part_md_table(risk_part) + ["",
              "## 二、行动清单", ""] + _part_md_table(action_part) + [""]
    if (notes or "").strip():
        parts += ["## 备注", "", notes.replace("\r\n", "\n").replace("\r", "\n"), ""]
    parts += ["## 三、口径说明（从 faces.yaml 自动带入，勿改）", "", caliber_raw, ""]
    return "\n".join(parts)


def import_from_dict(data, month, write=True):
    """--import-json 核心：§9.5 契约 JSON → md 组装并写盘（P0-2 头部/口径逐字节回写）。
    校验：month 匹配 / mtime 并发（P1）/ 矩形（P1）/ 换行（P0-4）/ 色值枚举。
    write=False 仅组装返回 {"path","md_text"}（往返不变式测试用）。"""
    if not isinstance(data, dict):
        raise ProtocolError("JSON 顶层必须是对象")
    if data.get("month") != month:
        raise ProtocolError(f"month 不匹配：JSON={data.get('month')!r} 参数={month!r}")
    path = _resolve_target_path(month)
    if not os.path.exists(path):
        raise ProtocolError(f"总体文档不存在: {path}", "parse")
    # P1：mtime 并发校验（export 附的 mtime 与 import 时文件实际 mtime 不符 → 冲突）
    exp_mtime = data.get("mtime")
    if isinstance(exp_mtime, (int, float)) and abs(os.path.getmtime(path) - float(exp_mtime)) > 1e-6:
        raise ProtocolError("mtime 冲突：文档在导出后被修改过，请重新导出后再导入")
    with open(path, encoding="utf-8") as f:
        had_kpi = _find_kpi_section(f.read())
    header_raw = str(data.get("header_raw") or "")
    caliber_raw = str(data.get("caliber_raw") or "")
    risk_part = _import_table(data, "risk_table")
    action_part = _import_table(data, "action_table")
    notes = str(data.get("notes_section") or "")
    kpi_cards = data.get("kpi_cards")
    cards = None
    if kpi_cards is not None:
        if not isinstance(kpi_cards, list):
            raise ProtocolError("kpi_cards 必须是数组")
        cards = []
        for i, c in enumerate(kpi_cards):
            if not isinstance(c, dict):
                raise ProtocolError(f"kpi_cards[{i}]: 不是对象")
            cards.append({
                "title": _md_cell(str(c.get("title", ""))),
                "value": _md_cell(str(c.get("value", ""))),
                "sub": _md_cell(str(c.get("sub", ""))),
                "level": _check_color(c.get("level", "none"), f"kpi_cards[{i}].level"),
                "source": str(c.get("source") or "custom"),
            })
    md_text = _compose_md(month, header_raw, cards, risk_part, action_part,
                          notes, caliber_raw, had_kpi)
    if write:
        # P1：原子写（临时文件 + os.replace）——直接 open(path,"w") 会先截断原文件，
        # 若写入中途抛错（编码/磁盘）将留下 0 字节残骸（实测踩坑：cp936 乱码代理对触发）。
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".risk_import_", suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(md_text)
            os.replace(tmp_path, path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    return {"path": path, "md_text": md_text}


# ---------- CLI ----------

def _emit_json(payload):
    # P0-6：stdout 显式按 utf-8 字节写出——Windows 控制台默认 cp936，
    # 经 print 会按 GBK 编码，破坏「--export-json | --import-json」管道契约（§9.6）。
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    buf = getattr(sys.stdout, "buffer", None)
    if buf is not None:
        buf.write(text.encode("utf-8"))
        buf.flush()
    else:
        sys.stdout.write(text)
        sys.stdout.flush()


def _emit_envelope(err, stage):
    _emit_json({"ok": False, "err": str(err), "stage": stage})


def run_protocol(args):
    """--export-json / --import-json 入口（P0-6：JSON 强制 stdin 管道，--file 兜底；
    错误一律 envelope {"ok":false,"err":...,"stage":"parse|import|render"} 到 stdout + exit 1）。"""
    try:
        month = args.month or _data_month()
        if not _is_month(month):
            raise ProtocolError(f"非法 month（须 YYYYMM）: {month!r}",
                                "import" if getattr(args, "import_json", False) else "parse")
        if args.export_json:
            _emit_json(export_to_dict(month))
            return 0
        if args.file:
            with open(args.file, encoding="utf-8") as f:
                data = json.load(f)
        else:
            # §9.6 管道契约：stdin/stdout 一律 UTF-8 字节——Windows 控制台默认 cp936，
            # 直接 json.load(sys.stdin) 会把 UTF-8 字节按 GBK 解出乱码代理对（实测踩坑）。
            data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        import_from_dict(data, month)
        _emit_json({"ok": True, "month": month})
        return 0
    except ProtocolError as e:
        _emit_envelope(e.err, e.stage)
        return 1
    except FileNotFoundError as e:
        _emit_envelope(f"文件不存在: {e}", "parse")
        return 1
    except json.JSONDecodeError as e:
        _emit_envelope(f"JSON 解析失败: {e}", "import")
        return 1
    except Exception as e:  # noqa: BLE001 —— 协议层兜底，错误一律 envelope
        _emit_envelope(f"{type(e).__name__}: {e}", "render")
        return 1


def main():
    ap = argparse.ArgumentParser(description="风险与行动面 · 生成器 + R 面编辑协议（v3.1 §9）")
    ap.add_argument("month", nargs="?", default=None, help="数据月份 YYYYMM（默认取 silver 最新月）")
    ap.add_argument("--month", dest="month_kw", default=None, help=argparse.SUPPRESS)  # 兼容旧式 --month
    ap.add_argument("--force-draft", action="store_true", help="强制重新生成初稿（覆盖人工审定版，须配合 --yes）")
    ap.add_argument("--yes", action="store_true", help="--force-draft 覆盖人工审定版的二次确认（P1）")
    ap.add_argument("--export-json", action="store_true", help="md → JSON（§9.5 契约，写 stdout）")
    ap.add_argument("--import-json", action="store_true", help="JSON（stdin）→ md，自动逐字节回写头部/口径")
    ap.add_argument("--file", default=None, help="JSON 文件路径兜底（import 缺省读 stdin 管道）")
    args = ap.parse_args()
    args.month = args.month or args.month_kw or _data_month()

    if args.export_json or args.import_json:
        return run_protocol(args)

    month = args.month
    md_path = risk_md_path(month)  # 读取语义：新位置优先、旧位置回退

    if os.path.exists(md_path) and not args.force_draft:
        print(f"[跳过] 总体文档已存在（人工审定版不覆盖）: {md_path}")
    else:
        if os.path.exists(md_path) and not args.yes:
            print("[错误] --force-draft 将覆盖已审定文档：请加 --yes 确认（覆盖前自动 .bak 备份）")
            return 1
        if os.path.exists(md_path):
            import shutil
            shutil.copyfile(md_path, md_path + ".bak")  # P1：覆盖前备份
            print(f"[备份] 已备份: {md_path}.bak")
        # 写盘一律落新位置 output/dashboard\（旧 dashboard\ 位置不再写入）
        md_path = os.path.join(RISK_MD_DIR, f"risk_action_{month}.md")
        md, stats = build_draft(month)
        os.makedirs(RISK_MD_DIR, exist_ok=True)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"[初稿] 已生成: {md_path}")
        mode = "简化回填(两通道)" if stats.get("simplified") else "全通道(8通道)"
        print(f"       模式 {mode} ｜ 信号 {stats['signals']} → 合并 {stats['merged']} → 上榜 {stats['listed']} "
              f"（溢出 {stats['overflow']} 条）｜ 连续≥2月 {stats['consecutive']} / 本月解除 {stats['released']} "
              f"｜ 行动：结转 {stats['carryover']} + 种子 {stats['seeds']} + 速记 {stats['meeting']}")

    return render(month)


if __name__ == "__main__":
    sys.exit(main())
