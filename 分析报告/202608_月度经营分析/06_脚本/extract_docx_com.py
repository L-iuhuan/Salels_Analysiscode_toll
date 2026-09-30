# -*- coding: utf-8 -*-
r"""用 Word COM 提取7月报告纲要（DSE环境python-docx不可用）"""
import time
import pythoncom
import pywintypes
import win32com.client as win32

DOC = r"\\192.168.8.3\财务部\财务电子档案备份\D1经营分析\分析报告\分析报告-202608\2026年7月销售经营分析报告(5).docx"
OUT = r"C:\Users\910373\AppData\Local\Temp\opencode\build\report_outline.txt"

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
pythoncom.CoInitialize()
word = None
try:
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = with_retry(lambda: word.Documents.Open(DOC, ReadOnly=True, AddToRecentFiles=False))
    lines.append(f"段落数: {doc.Paragraphs.Count}  表格数: {doc.Tables.Count}")

    lines.append("\n===== 正文段落(样式|截160字) =====")
    for p in doc.Paragraphs:
        try:
            t = with_retry(lambda: p.Range.Text).replace("\r", "").replace("\x07", "").strip()
            if not t or len(t) < 3:
                continue
            try:
                st = with_retry(lambda: p.Style.NameLocal)
            except Exception:
                st = "?"
            lines.append(f"({st}) {t[:160]}")
        except Exception:
            continue

    lines.append("\n===== 表格结构 =====")
    for ti in range(1, doc.Tables.Count + 1):
        try:
            tb = doc.Tables(ti)
            nrow = with_retry(lambda: tb.Rows.Count)
            ncol = with_retry(lambda: tb.Columns.Count)
            hdr = " | ".join(with_retry(lambda: tb.Cell(1, c).Range.Text).replace("\r\x07", "")[:14] for c in range(1, min(ncol, 9) + 1))
            sample = ""
            if nrow > 1:
                sample = " | ".join(with_retry(lambda: tb.Cell(2, c).Range.Text).replace("\r\x07", "")[:10] for c in range(1, min(ncol, 9) + 1))
            lines.append(f"表{ti}: {nrow}x{ncol} | 表头: {hdr} | 次行: {sample}")
        except Exception as e:
            lines.append(f"表{ti}: <失败 {e}>")
    with_retry(lambda: doc.Close(False))
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("OUTLINE_DONE, lines:", len(lines))
