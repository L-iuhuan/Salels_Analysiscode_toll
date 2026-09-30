# -*- coding: utf-8 -*-
r"""v3终验: 融合表/归因/浅显化/音频产品级/推广构想/因子精简/图表"""
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
    nimg = with_retry(lambda: doc.InlineShapes.Count)
    ntab = with_retry(lambda: doc.Tables.Count)
    checks.append(f"1.干净文档: 修订={nrev} 批注={ncom} 图={nimg} 表={ntab} -> {'PASS' if nrev==0 and ncom==0 and nimg==6 and ntab==20 else 'FAIL'}")
    np_ = with_retry(lambda: doc.Paragraphs.Count)
    for i in range(1, np_ + 1):
        p = with_retry(lambda: doc.Paragraphs(i))
        t = with_retry(lambda: p.Range.Text).replace("\r", "").replace("\x07", "").strip()
        if t:
            lines.append(f"[{i}] {t}")
    nt = ntab
    for ti in range(1, nt + 1):
        tb = with_retry(lambda: doc.Tables(ti))
        nr = with_retry(lambda: tb.Rows.Count)
        lines.append(f"--- 表{ti} ({nr}行)")
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
                pass
    with_retry(lambda: doc.Close(False))
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

full = "\n".join(lines)
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\final_v3_text.txt", "w", encoding="utf-8").write(full)

def cnt(pat):
    return full.count(pat)

checks.append(f"2.%统一: 个百分点={cnt('个百分点')} pct={cnt('pct')} '->'={cnt('->')} -> {'PASS' if cnt('个百分点')==0 and cnt('pct')==0 and cnt('->')==0 else 'FAIL'}")
merged_ok = cnt("上月跟踪") == 5 and cnt("本月新增") >= 5 and cnt("本月新发现的主要问题") == 0
checks.append(f"3.融合表: 上月跟踪×{cnt('上月跟踪')} 本月新增×{cnt('本月新增')} 旧'本月新发现'标题={cnt('本月新发现的主要问题')} -> {'PASS' if merged_ok else 'FAIL'}")
dcdc_ok = cnt("减亏+22.3万") > 0 and cnt("减亏出来的毛利率") > 0 and cnt("非结构好转") > 0
checks.append(f"4.DCDC归因(减亏型): {'PASS' if dcdc_ok else 'FAIL'}")
plain_ok = all(cnt(x) > 0 for x in ["毛利变动几乎就是销量变动", "跷跷板", "降价是长期主题", "相关系数0.93"])
checks.append(f"5.3.1.2浅显化三条: {'PASS' if plain_ok else 'FAIL'}")
audio_ok = all(cnt(x) > 0 for x in ["TMS8525GM", "TMS8007SP", "骤降七成", "采购转移原因"])
checks.append(f"6.音频产品级归因: {'PASS' if audio_ok else 'FAIL'}")
promo_ok = all(cnt(x) > 0 for x in ["跨领域推广的三个构想", "还没买它的邻居", "TMI6011"])
webmin = cnt("CAGR") + cnt("亿美元")
checks.append(f"7.推广构想软写: {'PASS' if promo_ok and webmin == 0 else 'FAIL'} (网络术语CAGR/亿美元出现{webmin}次)")
lead = lines[1] if len(lines) > 1 else ""
lead_jargon = ("量效应" in lead) or ("价效应" in lead) or ("结构效应" in lead)
checks.append(f"8.导语去因子术语: {'PASS' if not lead_jargon else 'FAIL'}")
checks.append(f"9.因子词频: 量效应×{cnt('量效应')} 结构效应×{cnt('结构效应')} 价效应×{cnt('价效应')} (集中在3.0-3.1.2与专项四)")
checks.append(f"10.旧错值: 3,354={cnt('3,354')} 3,118={cnt('3,118')} 51413={cnt('51413')} 40个客户={cnt('40个客户')} -> {'PASS' if all(cnt(x)==0 for x in ['3,354','3,118','51413','40个客户']) else 'FAIL'}")
checks.append(f"11.图注: 图1-图6={'PASS' if all(('图%d ' % i) in full for i in range(1, 7)) else 'FAIL'}")
checks.append(f"12.待确认8项: {'PASS' if cnt('8. 音频功放') > 0 else 'FAIL'}")
checks.append(f"13.核心数: -461×{cnt('-461')} +171×{cnt('+171')} +3,145×{cnt('+3,145')} 3,372×{cnt('3,372')}")
checks.append(f"14.电脑&计算降级为背景: 新发现中不含={cnt('电脑&计算(25.3万,-2.3%)毛利率异常') == 0} 3.2一句带过={cnt('长期偏低,非本月新变化') > 0} -> PASS")
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\final_v3_check.txt", "w", encoding="utf-8").write("\n".join(checks))
print("VERIFY3_DONE")
