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


def build_draft(month):
    """生成总体文档初稿。返回 (md_text, 统计dict)。初稿应用策展规则：同客户合并 + 每类 Top-N。"""
    stats = {"anomaly": 0, "anomaly_overflow": 0, "neg_margin": 0, "neg_overflow": 0,
             "carryover": 0, "meeting": 0}

    # --- 风险摘要：异常日志（高/中；同客户多条合并；Top-N）---
    risk_rows = []
    df = _read_gold("异常日志.csv")
    if df is not None and len(df) > 0:
        df = df[df["异常等级"].isin(["高", "中"])].copy()
        df["_o"] = df["异常等级"].map(RISK_LEVEL_ORDER).fillna(9)
        # 同客户多条异常合并为一条（等级取最高，类型合并）
        df = (df.groupby("客户编号", sort=False)
                .agg(异常等级=("异常等级", "first"),
                     异常类型=("异常类型", lambda s: "、".join(dict.fromkeys(s.astype(str)))),
                     _o=("_o", "min"))
                .reset_index())
        df = df.sort_values(["_o", "客户编号"], kind="stable")
        stats["anomaly_overflow"] = max(0, len(df) - TOP_N_PER_SOURCE)
        df = df.head(TOP_N_PER_SOURCE)
        for _, r in df.iterrows():
            risk_rows.append([r["异常等级"], f"客户{r['异常类型']}", r["客户编号"], "-",
                              "查看客户 360 面", ""])
        stats["anomaly"] = len(df)

    # --- 风险摘要：负毛利（损失 ≤ -阈值；源表负值存储；等级映射 严重/关注/轻微→高/中/低；Top-N）---
    df = _read_gold("负毛利分析.csv")
    if df is not None and len(df) > 0:
        df = df[(df["负毛利品种数"] > 0) & (df["负毛利损失总额"] <= -NEG_MARGIN_MIN_LOSS)].copy()
        df["_等级"] = df["负毛利严重等级"].map(NEG_LVL_MAP).fillna("中")
        df["_o"] = df["_等级"].map(RISK_LEVEL_ORDER).fillna(9)
        df["_损失"] = df["负毛利损失总额"].abs()
        df = df.sort_values(["_o", "_损失"], ascending=[True, False], kind="stable")
        stats["neg_overflow"] = max(0, len(df) - TOP_N_PER_SOURCE)
        df = df.head(TOP_N_PER_SOURCE)
        for _, r in df.iterrows():
            risk_rows.append([r["_等级"], f"负毛利产品 {int(r['负毛利品种数'])} 个", r["客户编号"],
                              _fmt_wan(r["_损失"]),
                              (str(r["建议动作"])[:80] + "…") if pd.notna(r["建议动作"]) else "", ""])
        stats["neg_margin"] = len(df)

    # --- 行动清单：上月未关闭结转 ---
    action_rows = []
    actions = load_actions()
    for it in actions.get("items", []):
        if it.get("status") in ("待处理", "跟进中"):
            action_rows.append([it["status"], it["title"], it.get("owner", ""),
                                it.get("due_date", ""), it.get("note", "")])
            stats["carryover"] += 1

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

    md = f"""# 风险与行动 · {month[:4]}-{month[4:]}

> 本文件由跑批自动生成初稿，请审定后渲染进看板。增删改随意，以本文件为准。
> 渲染：python run_chain.py --dashboard-only（或双击 2_只生成看板.bat）
> 生成时间：{datetime.now():%Y-%m-%d %H:%M} ｜ 数据月份：{month}
> 初稿策展：同客户多条异常已合并；每类最多 Top {TOP_N_PER_SOURCE}；另 {stats['anomaly_overflow'] + stats['neg_overflow']} 条未列入（低优先级/超 Top-N，详见 output\\gold\\ 源表）。人工审定可增删改任何条目。

## 一、当月风险摘要

{_md_table(["等级", "事项", "客户/产品", "损失金额(万元)", "建议动作", "负责人"], risk_rows)}

## 二、行动清单

{_md_table(["状态", "事项", "负责人", "期望完成日", "备注"], action_rows)}

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
        closed = [it for it in actions.get("items", []) if it.get("status") == "已关闭"]
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
        print(f"       异常日志 {stats['anomaly']} 条（另 {stats['anomaly_overflow']} 条超 Top-N 未列入）/ "
              f"负毛利 {stats['neg_margin']} 条（另 {stats['neg_overflow']} 条未列入）/ "
              f"上月结转 {stats['carryover']} 条 / 会议速记 {stats['meeting']} 条")

    return render(month)


if __name__ == "__main__":
    sys.exit(main())
