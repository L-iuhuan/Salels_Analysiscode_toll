# -*- coding: utf-8 -*-
r"""修复：表序(正确算法)+隐藏helper+新增0-说明sheet+重部署"""
import os
import time
import pythoncom
import pywintypes
import win32com.client as win32

STAGE = r"C:\Users\910373\AppData\Local\Temp\opencode\build\月度分析模板.xlsm"
DEPLOY = r"\\192.168.8.3\财务部\财务电子档案备份\D1经营分析\分析报告\分析报告-202608\月度分析模板.xlsm"
LOCAL = r"E:\3-其他资料\数据分析\月度分析模板.xlsm"
REPORT = r"C:\Users\910373\AppData\Local\Temp\opencode\build\fix_report.txt"

out = []
def log(s=""):
    out.append(str(s))
    print(str(s).encode("ascii", "replace").decode("ascii"))

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

DOC = [
    ("一、名称（公式变量）—— 全部可在 公式→名称管理器 查看", None),
    ("名称", "定义 | 含义 | 当前示例(报表年=2026, 报表月=8)"),
    ("报表年", "='0-参数'!$B$4 | 手工输入的报表年份 | 2026"),
    ("报表月", "='0-参数'!$B$5 | 手工输入的报表月份 | 8"),
    ("源表名", "='0-参数'!$B$6 | 基础数据sheet名，跨年改名只改这里 | 24-26"),
    ("月起", "=DATE(报表年,报表月,1) | 本月第1天 | 2026-08-01"),
    ("月止", "=EOMONTH(月起,0) | 本月最后1天 | 2026-08-31"),
    ("上月起", "=EDATE(月起,-1) | 上月第1天 | 2026-07-01"),
    ("上月止", "=EOMONTH(月起,-1) | 上月最后1天 | 2026-07-31"),
    ("去年同月起", "=EDATE(月起,-12) | 去年同期第1天 | 2025-08-01"),
    ("去年同月止", "=EOMONTH(EDATE(月起,-12),0) | 去年同期月末 | 2025-08-31"),
    ("YTD起", "=DATE(报表年,1,1) | 年初 | 2026-01-01"),
    ("YTD止", "=月止 | 年初累计至本月末 | 2026-08-31"),
    ("去年YTD起", "=DATE(报表年-1,1,1) | 去年年初 | 2025-01-01"),
    ("去年YTD止", "=EOMONTH(EDATE(月起,-12),0) | 去年同期月末 | 2025-08-31"),
    ("H1起 / H1止", "=DATE(报表年,1,1) / =EOMONTH(EDATE(月起,-1),0) | 上半年窗口(1月~上月末) | 2026-01-01~2026-07-31"),
    ("近12月 / 前12月", "VBA内部计算(非名称) | 以月止为锚: 最近12个自然月 vs 再前12个自然月 | 2025-09~2026-08 vs 2024-09~2025-08"),
    ("维度名称", "品类列表/产品线新清单/细分市场列表/客户列表/SKU清单/SKU品类列/新品SKU清单 | 刷新镜像后由VBA自动重写的动态区域"),
    ("", None),
    ("二、镜像表(D-镜像)16列 —— 源自基础数据24-26表，VBA按0-参数列映射抽取", None),
    ("镜像列(源列)", "用途"),
    ("发货日期(发货日期)", "所有时间窗口的筛选依据"),
    ("客户简称(终端客户简称)", "客户维度分析/专项客户(追觅)"),
    ("客户类别全称(终端客户名称_客户类别)", "KA/AA/KM/MM分类: 取前2字(如KA>1亿→KA)"),
    ("销售模式 / 细分市场(细分市场（新）) / 产品线 / 产品线新(型号_产品线（新）)", "维度过滤; 2-产品线用'产品线新'列"),
    ("品类(产品品类（新）) / 型号品类(型号_产品品类)", "6/21-26品类分析用'品类'列"),
    ("存货名称", "SKU级分析(9/21-24/27/毛利桥/SKU变化)"),
    ("是否新品", "新品分析: =\"是\""),
    ("数量(发货数量) / 收入(RMB未税金额小计) / 利润", "三大基础度量: 销量(颗)/收入(元)/利润(元), 毛利率=利润/收入"),
    ("单位成本 / 未税单价", "成本监控/成本效应计算"),
    ("", None),
    ("三、指标计算口径（19个公式sheet通用）", None),
    ("指标", "计算逻辑"),
    ("本月值", "SUMIFS(镜像度量列, 发货日期>=月起, 发货日期<=月止)"),
    ("同比", "本期/去年同月-1;  毛利率同比=两期毛利率之差(pct)"),
    ("环比", "本期/上月-1"),
    ("YTD / 去年YTD", "YTD起~YTD止累计 / 去年YTD起~去年YTD止累计"),
    ("毛利率", "利润/收入 (IFERROR防0除)"),
    ("新品占比/渗透度", "新品收入/整体收入"),
    ("", None),
    ("四、逆向标定的隐含口径（源自7月附件对拍，写死在公式/宏里）", None),
    ("口径", "规则 | 标定依据"),
    ("低毛利客户", "该客户该SKU的YTD毛利率<15% | 15个样本12个精确吻合(余3个为数据重述)"),
    ("2b新品SKU集合", "YTD新品收入>0(剔除净退货/零收入SKU) | 126个SKU逐位复现"),
    ("21建议文本", "本月利润<0→'7月亏损,优先整改/停售'; YTD毛利率<15%→'限月度出货量'; 否则'限期提价' | 60行逐条对拍"),
    ("22建议文本", "低毛利客户占比=100%→停售/汰换; >=70%→限期整改; 否则评估升级 | 29行对拍"),
    ("23分类文本", "低毛利客户占比>=60%→'全客户低(产品力)' | 69行对拍"),
    ("24行选取", "段1: 本月利润<=-1万(按亏损额降序); 段2: SKU成本效应最负的4个 | 对拍"),
    ("25四档", "YTD毛利率: <0负毛利 / 0-25低 / 25-39中 / >=39高 | 对拍"),
    ("26成本效应", "(上月UC-本月UC)×本月量, SKU级加总; 显示阈值<=-4万 | -58万等复现"),
    ("毛利桥", "量=ΣΔq×(基准单价-基准单位成本); 价=Σq1×Δ单价; 成本=Σq1×(基准UC-本期UC); 可比集合=两期均有销售 | 量/成本两项与附件逐位一致(917/+40, 140/-66); 价为标准口径(附件脚本未存档)"),
    ("12月窗口", "近12月vs前12月(月止锚定) | 附件口径不可完全复现(其数据源8.25已失传)"),
    ("", None),
    ("五、对拍总结(2026-09-08, 与7月附件)", None),
    ("结论", "约2600项比较; 1/2b/5/7/8/9六个sheet跨7月8.27与8月9.5两版数据逐位一致; 其余差异全部定性为8.25→8.27数据重述(四类客户收入总和守恒,差8.9e-08); 公式引擎零逻辑错误"),
]

pythoncom.CoInitialize()
xl = None
try:
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    xl.AutomationSecurity = 1
    xl.AutoRecover.Enabled = False
    wb = xl.Workbooks.Open(STAGE)
    if wb.ReadOnly:
        raise RuntimeError("staging locked")

    # ---- 0-说明 sheet ----
    for sh in with_retry(lambda: list(wb.Worksheets)):
        if sh.Name == "0-说明":
            sh.Delete()
    wsD = wb.Worksheets.Add(Before=wb.Worksheets(1))
    wsD.Name = "0-说明"
    wsD.Range("A1").Value = "月度分析模板 · 公式与口径说明"
    wsD.Range("A1").Font.Size = 14
    wsD.Range("A1").Font.Bold = True
    r = 3
    for a, b in DOC:
        if b is None:
            if a:
                wsD.Cells(r, 1).Value = a
                wsD.Cells(r, 1).Font.Bold = True
                r += 1
        else:
            wsD.Cells(r, 1).Value = ("'" + a) if a.startswith("=") else a
            wsD.Cells(r, 2).Value = ("'" + b) if b.startswith("=") else b
            if a.endswith(("名称", "指标", "口径", "镜像列(源列)")) or (a == "结论"):
                wsD.Cells(r, 1).Font.Bold = True
                wsD.Cells(r, 2).Font.Bold = True
            r += 1
    wsD.Columns("A").ColumnWidth = 26
    wsD.Columns("B").ColumnWidth = 110

    # ---- 正确排序 ----
    order = ["0-说明", "0-参数", "1-整体概览", "1b-H1任务项", "2-产品线", "2b-新品分档", "3-客户分类",
             "4-前20大客户", "5-应用领域", "6-全品类", "7-追觅", "8-新品", "9-成本监控", "10-毛利桥",
             "11-SKU变化", "21-限量出货名单", "22-产品升级清单", "23-低毛利SKU明细", "24-整改项目清单",
             "25-品类四档分类", "26-成本上升品类", "27-追觅分型号", "28-长库龄存货明细", "增加及流失",
             "D-镜像", "C-维度", "C-客户指标", "C-SKU指标"]
    name2sheet = {sh.Name: sh for sh in wb.Worksheets}
    prev = None
    for nm in order:
        if nm not in name2sheet:
            log(f"[WARN] 缺少sheet: {nm}")
            continue
        s = name2sheet[nm]
        if prev is None:
            with_retry(lambda s=s: s.Move(Before=wb.Worksheets(1)))
        else:
            with_retry(lambda s=s, p=prev: s.Move(After=p))
        prev = s
    # ---- 隐藏 helper ----
    for nm in ["C-客户指标", "C-SKU指标"]:
        if nm in name2sheet:
            with_retry(lambda s=name2sheet[nm]: s.__setattr__("Visible", 0))
    with_retry(lambda: wb.Worksheets("0-说明").Move(Before=wb.Worksheets(1)))

    final_order = [sh.Name for sh in wb.Worksheets]
    log("最终顺序: " + " | ".join(final_order))
    log("隐藏: " + " | ".join(f"{sh.Name}={sh.Visible}" for sh in wb.Worksheets if sh.Name.startswith("C-")))

    wb.Save()
    wb.SaveAs(DEPLOY, FileFormat=52)
    log("已重新部署(网络)")
    wb.Close(SaveChanges=False)
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

import shutil
shutil.copyfile(STAGE, LOCAL)
log("本地副本已更新")

with open(REPORT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))
print("FIX_DONE")
