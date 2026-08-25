# -*- coding: utf-8 -*-
"""风险与行动面 · 测试版生成器（W4）
设计依据：docs\\看板叙事结构详细设计_20260825.md §3.5（总体文档模式）/ §6.2（独立测试页）

两个职责：
1. 初稿生成：读 gold 异常/风险表 + action_items.json 结转 + 可选 meeting_track.md
   → 生成 dashboard\\risk_action_YYYYMM.md（已存在人工审定版则不覆盖，除非 --force-draft）
2. 渲染：解析总体文档 → 按固定模板（template_risk_test.html，与正式看板同风格）
   → 输出 dashboard\\dashboard_risk_test.html，并把行动清单状态回写 action_items.json

用法（工作目录 sales_analytics_platform）：
    python dashboard\\generate_risk_face.py              # 初稿（如缺失）+ 渲染
    python dashboard\\generate_risk_face.py --force-draft  # 强制重新生成初稿（慎用，覆盖人工审定）
    python dashboard\\generate_risk_face.py --month 202606  # 指定数据月份
"""
import argparse
import html
import json
import os
import sys
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
MEETING_MD = os.path.join(DASH_DIR, "meeting_track.md")

RISK_LEVEL_ORDER = {"高": 0, "中": 1, "低": 2}
NEG_LVL_MAP = {"严重": "高", "关注": "中", "轻微": "低"}  # 负毛利严重等级 → 展示等级
STATUS_ORDER = {"待处理": 0, "跟进中": 1, "已关闭": 2}
NEG_MARGIN_MIN_LOSS = 10000  # 负毛利损失阈值（元；源表为负值存储），设计 §3.2.4
TOP_N_PER_SOURCE = 10  # 初稿每类最多展示条数，设计 §3.2.4（人工审定可推翻）


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
    """把总体文档解析为 {section_title: (headers, rows)}。只认 '## ' 节标题与 | 表格行。"""
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
    if os.path.exists(MEETING_MD):
        with open(MEETING_MD, encoding="utf-8") as f:
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

def _tag(text, kind_map, prefix="tag"):
    cls = kind_map.get(text, "none")
    return f'<span class="{prefix} {prefix}-{cls}">{_esc(text)}</span>'


def _render_table(headers, rows, num_cols=()):
    th = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    trs = []
    for r in rows:
        tds = []
        for i, c in enumerate(r):
            if i >= len(headers):
                break  # 防御：单元格多于表头（历史脏文档）时截断，不崩溃
            cls = ' class="num"' if i in num_cols else ""
            if headers[i] == "等级":
                tds.append(f"<td>{_tag(c, {'高': 'high', '中': 'medium', '低': 'low'})}</td>")
            elif headers[i] == "状态":
                tds.append(f"<td>{_tag(c, {'待处理': 'high', '跟进中': 'medium', '已关闭': 'low'})}</td>")
            else:
                tds.append(f"<td{cls}>{_esc(c)}</td>")
        trs.append("<tr>" + "".join(tds) + "</tr>")
    body = "".join(trs) or f'<tr><td colspan="{len(headers)}" style="text-align:center;color:var(--text-muted)">本期无内容</td></tr>'
    return f'<table class="data-table"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


def _kc(label, value, sub, cls=""):
    return (f'<div class="kc {cls}"><div class="label">{label}</div>'
            f'<div class="value">{value}</div><div class="sub">{sub}</div></div>')


def _build_r_parts(month):
    """解析总体文档并构建 R 面各区块（测试页与正式看板并入共用）。
    返回 dict: ok / err / risk_kpi / risk_table / action_table / caliber / stats。
    副作用：行动清单状态回写 action_items.json（跨月结转的持久化层）。"""
    md_path = os.path.join(DASH_DIR, f"risk_action_{month}.md")
    if not os.path.exists(md_path):
        return {"ok": False, "err": md_path}
    with open(md_path, encoding="utf-8") as f:
        md = f.read()
    sec = _parse_md_tables(md)

    def get(keyword):
        for title, (headers, rows) in sec.items():
            if keyword in title:
                return headers, rows
        return [], []

    risk_h, risk_rows = get("风险摘要")
    act_h, act_rows = get("行动清单")

    # KPI 卡
    n_high = sum(1 for r in risk_rows if r and r[0] == "高")
    n_mid = sum(1 for r in risk_rows if r and r[0] == "中")
    loss_col = risk_h.index("损失金额(万元)") if "损失金额(万元)" in risk_h else None
    loss_sum = sum(float(r[loss_col]) for r in risk_rows
                   if loss_col is not None and len(r) > loss_col and r[loss_col] not in ("-", ""))
    n_todo = sum(1 for r in act_rows if r and r[0] == "待处理")
    n_doing = sum(1 for r in act_rows if r and r[0] == "跟进中")

    risk_kpi = (
        _kc("高风险事项", n_high, "需立即处理", "kpi-danger")
        + _kc("中风险事项", n_mid, "需关注", "kpi-warning")
        + _kc("负毛利损失合计", f"{loss_sum:.1f}万", "审定后展示口径", "kpi-danger" if loss_sum > 0 else "")
        + _kc("行动项", f"{n_todo + n_doing}", f"待处理 {n_todo} · 跟进中 {n_doing}")
    )

    # 口径说明（取 md 第三节的纯文本）
    caliber = ""
    marker = "## 三、口径说明"
    if marker in md:
        caliber = md.split(marker, 1)[1].strip()

    # 行动清单状态回写 action_items.json（持久化层；json 不是人工编辑对象）
    if act_h:
        idx = {h: i for i, h in enumerate(act_h)}
        items = []
        for r in act_rows:
            if not r or len(r) < 2:
                continue
            items.append({
                "id": f"manual:{r[1]}:{month}",
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

    return {"ok": True, "risk_kpi": risk_kpi,
            "risk_table": _render_table(risk_h, risk_rows, num_cols={3}),
            "action_table": _render_table(act_h, act_rows),
            "caliber": caliber,
            "stats": (len(risk_rows), n_high, n_mid, loss_sum, len(act_rows))}


def build_r_face_inner_html(month):
    """供 generate_dashboard.py 并入正式看板（W4）：返回 R 面内容 HTML（不含页面框架，
    样式复用 template.html 的 kpi-bar/kc/cb/data-table 组件）。"""
    parts = _build_r_parts(month)
    if not parts["ok"]:
        return ('<div class="cb"><h3>风险与行动</h3><div class="note">本月总体文档未生成：'
                '请先在明文窗口跑批后运行 <code>python dashboard\\generate_risk_face.py</code> '
                '生成并审定总体文档（缺失：' + _esc(parts["err"]) + '）</div></div>')
    return ('<div class="kpi-bar" style="grid-template-columns:repeat(4,1fr);max-width:960px;margin-left:auto;margin-right:auto">\n'
            + parts["risk_kpi"] + '\n</div>\n'
            + '<div class="cb"><h3>一、当月风险摘要</h3><div class="note">初稿由系统按规则生成，经人工审定后展示。</div>'
            + parts["risk_table"] + '</div>\n'
            + '<div class="cb"><h3>二、行动清单</h3><div class="note">状态：待处理 / 跟进中 / 已关闭。未关闭事项跨月自动结转。</div>'
            + parts["action_table"] + '</div>\n'
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
            .replace("%%RISK_KPI%%", parts["risk_kpi"])
            .replace("%%RISK_TABLE%%", parts["risk_table"])
            .replace("%%ACTION_TABLE%%", parts["action_table"])
            .replace("%%CALIBER%%", _esc(parts["caliber"])))
    out = os.path.join(DASH_DIR, "dashboard_risk_test.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)

    n_r, n_high, n_mid, loss_sum, n_act = parts["stats"]
    print(f"[OK] 测试页已生成: {out}")
    print(f"     风险摘要 {n_r} 条（高 {n_high} / 中 {n_mid}）；行动项 {n_act} 条；负毛利损失合计 {loss_sum:.1f} 万")
    return 0


def main():
    ap = argparse.ArgumentParser(description="风险与行动面 · 测试版生成器")
    ap.add_argument("--force-draft", action="store_true", help="强制重新生成初稿（覆盖人工审定版，慎用）")
    ap.add_argument("--month", default=None, help="数据月份 YYYYMM（默认取 silver 最新月）")
    args = ap.parse_args()

    month = args.month or _data_month()
    md_path = os.path.join(DASH_DIR, f"risk_action_{month}.md")

    if os.path.exists(md_path) and not args.force_draft:
        print(f"[跳过] 总体文档已存在（人工审定版不覆盖）: {md_path}")
    else:
        md, stats = build_draft(month)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"[初稿] 已生成: {md_path}")
        print(f"       异常日志 {stats['anomaly']} 条（另 {stats['anomaly_overflow']} 条超 Top-N 未列入）/ "
              f"负毛利 {stats['neg_margin']} 条（另 {stats['neg_overflow']} 条未列入）/ "
              f"上月结转 {stats['carryover']} 条 / 会议速记 {stats['meeting']} 条")

    return render(month)


if __name__ == "__main__":
    sys.exit(main())
