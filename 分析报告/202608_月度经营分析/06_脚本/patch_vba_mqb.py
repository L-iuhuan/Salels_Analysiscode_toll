# -*- coding: utf-8 -*-
r"""主模板VBA升级: 重算毛利桥→三因子+四因子双口径 + 运行验证 + 副本同步"""
import time
import pythoncom
import pywintypes
import win32com.client as win32

MASTER = r"E:\3-其他资料\数据分析\月度分析模板.xlsm"
COPY = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"
LOGF = r"C:\Users\910373\AppData\Local\Temp\opencode\build\vba_patch_log.txt"

def log(msg):
    with open(LOGF, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

def with_retry(fn, *a, **k):
    last = None
    for i in range(15):
        try:
            return fn(*a, **k)
        except pywintypes.com_error as e:
            if e.hresult in (-2147418111, -2147417846) and i < 14:
                last = e
                time.sleep(2)
                continue
            raise
    raise last

NEW_SUB = r'''Public Sub 重算毛利桥(Optional silentArg As Boolean = True)

    Dim ws As Worksheet

    On Error Resume Next

    Set ws = ThisWorkbook.Worksheets("10-毛利桥")

    On Error GoTo 0

    If ws Is Nothing Then Exit Sub

    Dim n As Long, cS As Long, cD As Long, cQ As Long, cR As Long, cP As Long

    Dim arr As Variant

    arr = 镜像数组(n, cS, cD, cQ, cR, cP)

    Dim mS As Variant, mD As Variant, mQ As Variant, mR As Variant, mP As Variant

    mS = arr(1): mD = arr(2): mQ = arr(3): mR = arr(4): mP = arr(5)



    Dim d0 As Date, d1 As Date, dA0 As Date, dA1 As Date, dB0 As Date, dB1 As Date

    d1 = Application.Evaluate("月止"): d0 = Application.Evaluate("月起")

    dA0 = Application.Evaluate("去年同月起"): dA1 = Application.Evaluate("去年同月止")

    dB0 = Application.Evaluate("上月起"): dB1 = Application.Evaluate("上月止")



    ws.Range("A4:F6").ClearContents

    ws.Range("A10:H14").ClearContents

    ws.Range("A4:F4").Value = Array("口径", "量效应(万)", "价效应(万)", "成本效应(万)", "可比ΔGP(万)", "可比自身毛利率变化")

    ws.Range("A4:F4").Font.Bold = True



    Dim labels(1 To 2) As String, w1(1 To 2) As Date, w2(1 To 2) As Date

    labels(1) = "同比(" & Format(d0, "m月") & "vs去年同月)"

    labels(2) = "环比(" & Format(d0, "m月") & "vs" & Format(dB0, "m月") & ")"

    w1(1) = dA0: w2(1) = dA1

    w1(2) = dB0: w2(2) = dB1



    Dim k As Long, j As Long

    Application.ScreenUpdating = False

    For k = 1 To 2

        Dim dCur As Object, dOld As Object

        Set dCur = CreateObject("Scripting.Dictionary")

        Set dOld = CreateObject("Scripting.Dictionary")

        For j = 1 To n

            If IsDate(mD(j, 1)) Then

                Dim dv As Date: dv = mD(j, 1)

                Dim revv As Double, gpv As Double, qv As Double

                revv = Val(mR(j, 1)): gpv = Val(mP(j, 1)): qv = Val(mQ(j, 1))

                Dim sk As String: sk = CStr(mS(j, 1))

                If Len(sk) > 0 Then

                    If dv >= d0 And dv <= d1 Then

                        If Not dCur.Exists(sk) Then

                            dCur.Add sk, Array(qv, revv, gpv)

                        Else

                            Dim tv As Variant: tv = dCur(sk)

                            tv(0) = tv(0) + qv: tv(1) = tv(1) + revv: tv(2) = tv(2) + gpv

                            dCur(sk) = tv

                        End If

                    ElseIf dv >= w1(k) And dv <= w2(k) Then

                        If Not dOld.Exists(sk) Then

                            dOld.Add sk, Array(qv, revv, gpv)

                        Else

                            Dim tu As Variant: tu = dOld(sk)

                            tu(0) = tu(0) + qv: tu(1) = tu(1) + revv: tu(2) = tu(2) + gpv

                            dOld(sk) = tu

                        End If

                    End If

                End If

            End If

        Next j



        Dim eVol As Double, ePr As Double, eC As Double, dgp As Double

        Dim gp0s As Double, gp1s As Double, r0s As Double, r1s As Double

        Dim q0s As Double, q1s As Double, sq1um0 As Double

        eVol = 0: ePr = 0: eC = 0: dgp = 0: gp0s = 0: gp1s = 0: r0s = 0: r1s = 0

        q0s = 0: q1s = 0: sq1um0 = 0

        Dim kk As Variant, a1 As Variant, a0 As Variant

        For Each kk In dCur.Keys

            If dOld.Exists(kk) Then

                a1 = dCur(kk): a0 = dOld(kk)

                If a1(1) > 0 And a0(1) > 0 And a1(0) > 0 And a0(0) > 0 Then

                    Dim q1 As Double, q0 As Double, p1 As Double, p0 As Double, c1 As Double, c0 As Double

                    q1 = a1(0): q0 = a0(0)

                    p1 = a1(1) / q1: p0 = a0(1) / q0

                    c1 = (a1(1) - a1(2)) / q1: c0 = (a0(1) - a0(2)) / q0

                    eVol = eVol + (q1 - q0) * (p0 - c0)

                    ePr = ePr + q1 * (p1 - p0)

                    eC = eC + q1 * (c0 - c1)

                    q0s = q0s + q0: q1s = q1s + q1

                    sq1um0 = sq1um0 + q1 * (p0 - c0)

                    gp1s = gp1s + a1(2): gp0s = gp0s + a0(2)

                    r1s = r1s + a1(1): r0s = r0s + a0(1)

                End If

            End If

        Next kk

        dgp = gp1s - gp0s



        ' 四因子: 量4=(Q1-Q0)×基准平均单位毛利; 结构4=Σq1×基准UM−Q1×基准平均UM

        Dim eVol4 As Double, eStr As Double, umBar As Double

        If q0s > 0 Then umBar = gp0s / q0s Else umBar = 0

        eVol4 = (q1s - q0s) * umBar

        eStr = sq1um0 - q1s * umBar



        ' 三因子块(锚点, 行5-6)

        ws.Cells(4 + k, 1).Value = labels(k)

        ws.Cells(4 + k, 2).Value = Round(eVol / 10000, 0)

        ws.Cells(4 + k, 3).Value = Round(ePr / 10000, 0)

        ws.Cells(4 + k, 4).Value = Round(eC / 10000, 0)

        ws.Cells(4 + k, 5).Value = Round(dgp / 10000, 0)

        ws.Cells(4 + k, 6).Value = Format(gp0s / r0s, "0.00%") & "→" & Format(gp1s / r1s, "0.00%")



        ' 四因子块(报告口径, 行12-13) + 恒等式残差(H列, 应≈0)

        ws.Cells(11 + k, 1).Value = labels(k)

        ws.Cells(11 + k, 2).Value = Round(eVol4 / 10000, 0)

        ws.Cells(11 + k, 3).Value = Round(eStr / 10000, 0)

        ws.Cells(11 + k, 4).Value = Round(ePr / 10000, 0)

        ws.Cells(11 + k, 5).Value = Round(eC / 10000, 0)

        ws.Cells(11 + k, 6).Value = Round(dgp / 10000, 0)

        ws.Cells(11 + k, 7).Value = Format(gp0s / r0s, "0.00%") & "→" & Format(gp1s / r1s, "0.00%")

        ws.Cells(11 + k, 8).Value = Round((eVol4 + eStr - eVol) / 10000, 1)

    Next k

    ws.Range("B5:E6").NumberFormat = "+#,##0;-#,##0;0"

    ws.Range("B12:F13").NumberFormat = "+#,##0;-#,##0;0"

    ws.Range("A1").Value = "毛利桥(SKU级预计算: 三因子锚点 + 四因子报告口径)"

    ws.Range("A2").Value = "注: 在两期均有销售的SKU集合上计算。三因子(行4-6): 量=ΣΔq×(基准单价-基准单位成本); 价=Σq1×Δ单价; 成本=Σq1×(基准UC-本期UC)。四因子(行11-13, 报告口径): 量=(Q1-Q0)×基准平均单位毛利; 结构=Σq1×基准UM−Q1×基准平均UM; 恒等式: 量4+结构=三因子量(H列残差应≈0)。由VBA重算。"

    ws.Range("A10").Value = "四因子口径(报告表5/R1口径):"

    ws.Range("A11:H11").Value = Array("口径", "量效应(万)", "结构效应(万)", "价效应(万)", "成本效应(万)", "可比ΔGP(万)", "可比自身毛利率变化", "恒等式残差(万)")

    ws.Range("A11:H11").Font.Bold = True

    ws.Range("A8").Value = "最近重算: " & Format(Now, "yyyy-mm-dd hh:mm")

    Application.ScreenUpdating = True

End Sub'''

pythoncom.CoInitialize()
xl = None
try:
    xl = with_retry(lambda: win32.DispatchEx("Excel.Application"))
    xl.Visible = False
    xl.DisplayAlerts = False
    try:
        with_retry(lambda: xl.__setattr__("AutomationSecurity", 1))
    except Exception:
        pass
    wb = with_retry(lambda: xl.Workbooks.Open(MASTER))
    log("master opened")

    vbp = with_retry(lambda: wb.VBProject)
    comps = with_retry(lambda: vbp.VBComponents)
    ncomp = with_retry(lambda: comps.Count)
    target = None
    for i in range(1, ncomp + 1):
        comp = with_retry(lambda: comps(i))
        cm = with_retry(lambda: comp.CodeModule)
        cnt = with_retry(lambda: cm.CountOfLines)
        if not cnt:
            continue
        code = with_retry(lambda: cm.Lines(1, cnt))
        if "Public Sub 重算毛利桥" in code:
            target = (comp, cm, cnt, code)
            break
    if not target:
        log("FAIL: 未找到含重算毛利桥的模块")
        raise SystemExit(1)
    comp, cm, cnt, code = target
    modname = with_retry(lambda: comp.Name)
    log(f"module: {modname}")

    lines = code.replace("\r\n", "\n").split("\n")
    s = next(i for i, l in enumerate(lines) if l.strip() == "Public Sub 重算毛利桥(Optional silentArg As Boolean = True)")
    e = next(i for i in range(s, len(lines)) if lines[i].strip() == "End Sub")
    start_line, del_count = s + 1, e - s + 1
    with_retry(lambda: cm.DeleteLines(start_line, del_count))
    with_retry(lambda: cm.InsertLines(start_line, NEW_SUB))
    log(f"patched: lines {start_line}+{del_count} replaced, new {NEW_SUB.count(chr(10))+1} lines")

    with_retry(lambda: wb.Save())
    log("master saved")

    # 运行宏重算
    with_retry(lambda: xl.Run("重算毛利桥"))
    log("macro executed")

    # 回读验证
    ws = with_retry(lambda: xl.Worksheets("10-毛利桥"))
    def cell(r, c):
        return with_retry(lambda: ws.Cells(r, c).Value)
    got = {"三因子同比量": cell(5, 2), "三因子环比量": cell(6, 2),
           "四因子同比量": cell(12, 2), "四因子同比结构": cell(12, 3),
           "四因子环比量": cell(13, 2), "四因子环比结构": cell(13, 3),
           "残差同比": cell(12, 8), "残差环比": cell(13, 8),
           "stamp": cell(8, 1)}
    log(f"verify: {got}")
    exp = {"三因子同比量": 383, "三因子环比量": -291, "四因子同比量": 313,
           "四因子同比结构": 70, "四因子环比量": -461, "四因子环比结构": 171}
    ok = all(abs(float(got[k]) - v) <= 1 for k, v in exp.items()) and abs(float(got["残差同比"])) <= 0.1 and abs(float(got["残差环比"])) <= 0.1
    log(f"VERIFY {'PASS' if ok else 'FAIL'}")

    # 快照四因子块供副本同步
    snap = {"A1": cell(1, 1), "A2": cell(2, 1), "rows": []}
    for r in range(10, 14):
        snap["rows"].append([cell(r, c) for c in range(1, 9)])
    import json
    json.dump(snap, open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\mb_snapshot.json", "w", encoding="utf-8"), ensure_ascii=False, default=str)
    with_retry(lambda: wb.Save())
    with_retry(lambda: wb.Close(False))
    log("master closed")
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()
print("VBA_PATCH_DONE")
