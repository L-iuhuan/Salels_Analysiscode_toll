# -*- coding: utf-8 -*-
r"""复核6处修改(文件脚本,排除内联编码问题) + 输出全文供对拍"""
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
    np_ = with_retry(lambda: doc.Paragraphs.Count)
    for i in range(1, np_ + 1):
        p = with_retry(lambda: doc.Paragraphs(i))
        t = with_retry(lambda: p.Range.Text).replace("\r", "").replace("\x07", "").strip()
        if t:
            lines.append(t)
    ntab = with_retry(lambda: doc.Tables.Count)
    for ti in range(1, ntab + 1):
        tb = with_retry(lambda: doc.Tables(ti))
        nr = with_retry(lambda: tb.Rows.Count)
        lines.append(f"=== 表{ti} ({nr}行) ===")
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
    nimg = with_retry(lambda: doc.InlineShapes.Count)
    nrev = with_retry(lambda: doc.Revisions.Count)
    with_retry(lambda: doc.Close(False))
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

full = "\n".join(lines)
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\final_text_v4.txt", "w", encoding="utf-8").write(full)

checks.append(f"1.表20 STI修复: 含STI完整名={'立即停售STI3452HFI等负毛利型号' in full}, 残留'-3452HFI'={'-3452HFI' in full}")
checks.append(f"2.已已: 残留={'已已' in full}")
checks.append(f"3.专项四末句: 新句={'需结合9月数据确认是否形成销量下滑趋势' in full}, 旧句残留={'是否是整体销量出现下滑的趋势' in full}")
checks.append(f"4.表18表头: 含(颗)={'销量环比变动(颗)' in full}, 无单位版={'销量环比变动' in full and '销量环比变动(颗)' not in full}")
checks.append(f"5.挽救措施挪位: 新句={'应采取挽救措施、及时跟进采购量持续降低的原因。提升路径' in full}, 旧句残留={'或采取挽救措施' in full}")
checks.append(f"6.五章收尾: {'小结:8月量减价稳' in full and '9月重点跟踪三个信号' in full}")
checks.append(f"7.拖累数-1,060万: {'-1,060万' in full}")
checks.append(f"8.结构: 图={nimg} 表={ntab} 修订={nrev}")
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\fixcheck2.txt", "w", encoding="utf-8").write("\n".join(checks))
print("RECHECK_DONE")
