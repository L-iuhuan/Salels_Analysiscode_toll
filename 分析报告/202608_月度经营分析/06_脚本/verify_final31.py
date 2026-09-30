# -*- coding: utf-8 -*-
r"""v3.1终验: 清残留修订 + 弯引号 + 回落结论修正 + 完整性"""
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
    doc = with_retry(lambda: word.Documents.Open(DST))
    n = with_retry(lambda: doc.Revisions.Count)
    for i in range(n, 0, -1):
        rv = with_retry(lambda: doc.Revisions(i))
        with_retry(lambda: rv.Accept())
    with_retry(lambda: doc.Save())
    nrev = with_retry(lambda: doc.Revisions.Count)
    ncom = with_retry(lambda: doc.Comments.Count)
    nimg = with_retry(lambda: doc.InlineShapes.Count)
    ntab = with_retry(lambda: doc.Tables.Count)
    checks.append(f"1.干净文档: 修订={nrev}(修复前{n}) 批注={ncom} 图={nimg} 表={ntab} -> {'PASS' if nrev==0 and ncom==0 and nimg==6 and ntab==20 else 'FAIL'}")
    np_ = with_retry(lambda: doc.Paragraphs.Count)
    for i in range(1, np_ + 1):
        p = with_retry(lambda: doc.Paragraphs(i))
        t = with_retry(lambda: p.Range.Text).replace("\r", "").replace("\x07", "").strip()
        if t:
            lines.append(t)
    with_retry(lambda: doc.Close(False))
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

full = "\n".join(lines)
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\final_v31_text.txt", "w", encoding="utf-8").write(full)

def cnt(pat):
    return full.count(pat)

dq = cnt('"')
sq = cnt("'")
lq = cnt("\u201c") + cnt("\u201d")
checks.append(f"2.引号: ASCII双引号={dq} ASCII单引号={sq} 中文弯引号={lq} -> {'PASS' if dq==0 and sq==0 and lq>50 else 'FAIL'}")
checks.append(f"3.回落结论: '年内首次回落'={cnt('年内首次回落')} '5月以来首次回落'={cnt('5月以来首次回落')} '年内第三次'={cnt('年内第三次')} '2月春节-39%'={cnt('2月春节-39%')} -> {'PASS' if cnt('年内首次回落')==0 and cnt('5月以来首次回落')>=2 else 'FAIL'}")
checks.append(f"4.保留的正确'首次': 历年8月首次={cnt('历年8月首次')} 4月以来首次={cnt('4月以来首次')} 2025年2月以来首次={cnt('2025年2月以来首次')} (均应>0)")
checks.append(f"5.旧错值: 3,354={cnt('3,354')} 3,118={cnt('3,118')} 51413={cnt('51413')} -> {'PASS' if all(cnt(x)==0 for x in ['3,354','3,118','51413']) else 'FAIL'}")
checks.append(f"6.关键内容仍在: TMS8525GM={cnt('TMS8525GM')} 跷跷板={cnt('跷跷板')} 跨领域推广={cnt('跨领域推广')} 减亏出来的毛利率={cnt('减亏出来的毛利率')} 上月跟踪={cnt('上月跟踪')} -> PASS if all>0")
checks.append(f"7.图注图1-图6: {'PASS' if all(('图%d ' % i) in full for i in range(1, 7)) else 'FAIL'}")
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\final_v31_check.txt", "w", encoding="utf-8").write("\n".join(checks))
print("VERIFY31_DONE")
