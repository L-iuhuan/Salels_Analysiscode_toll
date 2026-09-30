# -*- coding: utf-8 -*-
import pythoncom
import shutil
import win32com.client as win32

STAGE = r"C:\Users\910373\AppData\Local\Temp\opencode\build\月度分析模板.xlsm"
DEPLOY = r"\\192.168.8.3\财务部\财务电子档案备份\D1经营分析\分析报告\分析报告-202608\月度分析模板.xlsm"
LOCAL = r"E:\3-其他资料\数据分析\月度分析模板.xlsm"

pythoncom.CoInitialize()
xl = None
try:
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    xl.AutomationSecurity = 1
    xl.AutoRecover.Enabled = False
    wb = xl.Workbooks.Open(STAGE)
    ws27 = wb.Worksheets("27-追觅分型号")
    ws27.Range("N1").Formula = '=报表月&"月量"'
    ws27.Range("O1").Formula = '=报表月&"月收入"'
    xl.Calculate()
    wb.Save()
    wb.SaveAs(DEPLOY, FileFormat=52)
    wb.Close(SaveChanges=False)
    print("DEPLOY_OK")
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

shutil.copyfile(STAGE, LOCAL)
print("SYNC_DONE")
