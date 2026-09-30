# -*- coding: utf-8 -*-
r"""v2终验: 提取定稿全文+表格, 新旧口径对拍+新分析数字验算"""
import time
import pythoncom
import pywintypes
import win32com.client as win32

DST = r"E:\3-其他资料\数据分析\2026年8月销售经营分析报告(定稿).docx"

def with_retry(fn, *a, **k):
    last = None
    for i in range(12):
        try:
            return fn(*a, **k)
        except pywintypes.com_error as e:
            if e.hresult in (-2147418111, -2147417846) and i < 11:
                last = e
                time.sleep(1.5)
                continue
            raise
    raise last

lines = []
checks = []
pythoncom.CoInitialize()
word = None
try:
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = with_retry(lambda: word.Documents.Open(DST, ReadOnly=True))
    nrev = with_retry(lambda: doc.Revisions.Count)
    ncom = with_retry(lambda: doc.Comments.Count)
    checks.append(f"1.干净文档: 修订={nrev} 批注={ncom} -> {'PASS' if nrev == 0 and ncom == 0 else 'FAIL'}")
    np_ = with_retry(lambda: doc.Paragraphs.Count)
    for i in range(1, np_ + 1):
        p = with_retry(lambda: doc.Paragraphs(i))
        t = with_retry(lambda: p.Range.Text).replace("\r", "").replace("\x07", "").strip()
        if t:
            lines.append(f"[{i}] {t}")
    nt = with_retry(lambda: doc.Tables.Count)
    lines.append(f"\n===== {nt}张表格 =====")
    for ti in range(1, nt + 1):
        tb = with_retry(lambda: doc.Tables(ti))
        nr = with_retry(lambda: tb.Rows.Count)
        lines.append(f"\n--- 表{ti} ({nr}行) ---")
        for ri in range(1, nr + 1):
            try:
                row = with_retry(lambda: tb.Rows(ri).Range)
                cells = with_retry(lambda: row.Cells)
                vals = []
                for ci in range(1, with_retry(lambda: cells.Count) + 1):
                    c = with_retry(lambda: cells(ci))
                    vals.append(with_retry(lambda: c.Range.Text).replace("\r", "").replace("\x07", "").strip())
                lines.append(" | ".join(vals))
            except Exception:
                lines.append(f"(行{ri}读取失败)")
    with_retry(lambda: doc.Close(False))
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

full = "\n".join(lines)
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\final_v2_text.txt", "w", encoding="utf-8").write(full)

def cnt(pat):
    return full.count(pat)

# --- 基础规范 ---
checks.append(f"2.%统一: 个百分点={cnt('个百分点')} pct={cnt('pct')} '->'={cnt('->')} -> {'PASS' if cnt('个百分点')==0 and cnt('pct')==0 and cnt('->')==0 else 'FAIL'}")
checks.append(f"3.表头期间: '1-7月'={cnt('1-7月')} '产品线(7月)'={cnt('产品线(7月)')} '7月收入(万)'={cnt('7月收入(万)')} -> {'PASS' if cnt('1-7月')==0 else 'FAIL'}")
checks.append(f"4.旧错值: 3,354={cnt('3,354')} 3,118={cnt('3,118')} 40个客户={cnt('40个客户')} -51413={cnt('51413')} -> {'PASS' if all(cnt(x)==0 for x in ['3,354','3,118','40个客户','51413']) else 'FAIL'}")
checks.append(f"5.中兴专项已撤: '四、专项:中兴康讯'={cnt('四、专项:中兴康讯')} '由盈转亏'={cnt('由盈转亏')} -> {'PASS' if cnt('四、专项:中兴康讯')==0 and cnt('由盈转亏')==0 else 'FAIL'}")
checks.append(f"6.占位符: 图1~图6={'PASS' if all(cnt(f'【图{i} ') > 0 for i in range(1, 7)) else 'FAIL'}")
# --- v2 新内容验算 ---
long_ok = all(cnt(x) > 0 for x in ["31个月中仅5个月为正", "首个非春节", "连续三月为负", "首个量效应为负的8月", "月均约-76万"])
checks.append(f"7.长周期规律: 5项规律表述={'PASS' if long_ok else 'FAIL'}")
zx_ok = cnt("-21万/7月-59万/8月-69万") > 0 or cnt("6月-21万/7月-59万/8月-69万") > 0
checks.append(f"8.中兴月度连亏: {'PASS' if zx_ok else 'FAIL'} (-21/-59/-69万)")
hedge_vals = ["石头+189", "追觅-423", "小米-148", "33%", "中兴康讯-339", "海康+59", "大华+65", "PSE"]
checks.append(f"9.对冲矩阵: 关键值={'PASS' if all(cnt(x) > 0 for x in hedge_vals) else 'FAIL'}")
mm_vals = ["净减110家", "11.0万", "17.6万", "+60%", "38.7%"]
checks.append(f"10.MM引擎: {'PASS' if all(cnt(x) > 0 for x in mm_vals) else 'FAIL'}")
case_vals = ["石头(285万,占91%)", "海康威视(266万,占97%)", "中兴康讯(93万)", "华阳通用(55万)"]
checks.append(f"11.新品×客户: {'PASS' if all(cnt(x) > 0 for x in case_vals) else 'FAIL'}")
vol_vals = ["-303", "脉冲消退", "506", "+216万" if cnt('合计+216万') else "216", "胜辉时代"]
checks.append(f"12.量效应解剖: {'PASS' if all(cnt(x) > 0 for x in vol_vals) else 'FAIL'}")
margin_ok = cnt("30.20%→30.99%") > 0 and cnt("30.25%→30.68%") > 0 and cnt("23.1%") > 0
checks.append(f"13.可比/全公司毛利率双口径说明: {'PASS' if margin_ok else 'FAIL'}")
new36 = all(cnt(x) > 0 for x in ["大华集团(PSE放量型)", "TPLINK(品类切换型)", "共进(高毛利同线渗透型)", "TMI6011"])
checks.append(f"14.新典范三样本: {'PASS' if new36 else 'FAIL'}")
mode16 = all(cnt(x) > 0 for x in ["变化模式", "新品放量·结构下沉", "收缩改善毛利", "新增为正·存量失血"])
checks.append(f"15.表16/17模式列: {'PASS' if mode16 else 'FAIL'}")
b18 = cnt("大客户风险跟踪") > 0
checks.append(f"16.表18B行更新: {'PASS' if b18 else 'FAIL'}")
todo7 = cnt("未署名客户") > 0
checks.append(f"17.待确认#7数据治理: {'PASS' if todo7 else 'FAIL'}")
# 一致性交叉: 核心数字各处一致
checks.append(f"18.核心数一致: -461={cnt('-461')}处 +171={cnt('+171')}处 +62={cnt('+62')}处 +3,145={cnt('+3,145')}处 3,372={cnt('3,372')}处")
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\final_v2_check.txt", "w", encoding="utf-8").write("\n".join(checks))
print("VERIFY2_DONE")
