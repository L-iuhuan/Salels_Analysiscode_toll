# -*- coding: utf-8 -*-
r"""应用用户确认的修改: 4处笔误+3.4挪句+五章收尾扩充 (在用户版文档上surgical edit)"""
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

LOG = []
pythoncom.CoInitialize()
word = None
try:
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = with_retry(lambda: word.Documents.Open(DST))
    with_retry(lambda: doc.__setattr__("TrackRevisions", False))

    def freplace(find_text, repl_text):
        rng = with_retry(lambda: doc.Content)
        f = with_retry(lambda: rng.Find)
        with_retry(lambda: f.ClearFormatting)
        with_retry(lambda: f.Replacement.ClearFormatting)
        with_retry(lambda: f.__setattr__("Text", find_text))
        with_retry(lambda: f.Replacement.__setattr__("Text", repl_text))
        with_retry(lambda: f.__setattr__("Forward", True))
        with_retry(lambda: f.__setattr__("Wrap", 1))
        with_retry(lambda: f.__setattr__("MatchCase", True))
        with_retry(lambda: f.__setattr__("MatchWildcards", False))
        ok = with_retry(lambda: f.Execute(Replace=2))
        LOG.append(f"{'OK ' if ok else 'MISS'} {find_text[:28]}")
        return ok

    # 1. 表20 STI笔误
    freplace("立即停售-3452HFI等负毛利型号", "立即停售STI3452HFI等负毛利型号")
    # 2. 3.8 已已
    freplace("已已进入", "已进入")
    # 3. 专项四末句
    freplace("需要结合9月数据核查是否是整体销量出现下滑的趋势。", "需结合9月数据确认是否形成销量下滑趋势。")
    # 4. 表18表头单位
    freplace("销量环比变动", "销量环比变动(颗)")
    # 5. 3.4 挽救措施挪到追觅句后
    freplace("其问题是收入下滑而非品类结构。提升路径为将采购往高毛利同线品引导，或采取挽救措施，及时跟进采购量持续降低的原因;共进",
             "其问题是收入下滑而非品类结构,应采取挽救措施、及时跟进采购量持续降低的原因。提升路径为将采购往高毛利同线品引导;共进")

    # 6. 五章收尾扩充: 定位"注:"段,整段替换为收尾
    CLOSER = (
        "小结:8月量减价稳、结构改善,毛利率在连续两月下滑后企稳回升;同比利润缺口的破解仍集中在三件事——立即停售STI3452HFI等负毛利型号、DCDC-18V限价提价、三条结构升级路径(PSE放量/POE协议迁移/LDO渗透)的复制推广。\r"
        "本月的积极信号:新品占比升至19.8%,PSE、POE协议、LDO渗透三条路径均有客户实证;四家新客户进场(合计+216万),MM客户户均产出提升60%,中小客户增长引擎健康;价格与结构同时改善,为2025年2月以来首次。\r"
        "未解事项同样清晰:KA利润零增长(追觅/中兴康讯/小米合计拖累-1,060万)、中兴康讯6月起连续亏损扩大、音频功放主力产品失量,需按待确认清单逐项推进。\r"
        "9月重点跟踪三个信号:①价格与结构能否连续两月同时改善(见3.1.2);②销量是否继续下滑——若连续两月为负,需求走弱的判断成立(见专项四);③STI3452HFI停售后的DCDC-18V真实毛利率(见3.1.1)。\r"
        "以上行动建议明确责任人与完成时限,纳入本月经营例会逐项确认,并在9月报告的行动项回检中闭环。\r"
    )
    rng = with_retry(lambda: doc.Content)
    f = with_retry(lambda: rng.Find)
    with_retry(lambda: f.ClearFormatting)
    with_retry(lambda: f.__setattr__("Text", "注:以上行动建议需明确责任人与完成时限,建议本月经营例会逐项确认并纳入下月回检。"))
    with_retry(lambda: f.__setattr__("Forward", True))
    with_retry(lambda: f.__setattr__("Wrap", 1))
    ok = with_retry(lambda: f.Execute())
    if ok:
        pr = with_retry(lambda: f.Parent.Paragraphs(1).Range)
        with_retry(lambda: pr.__setattr__("Text", CLOSER))
        with_retry(lambda: pr.Font.__setattr__("NameFarEast", "宋体"))
        with_retry(lambda: pr.Font.__setattr__("Size", 10.5))
        LOG.append("OK 五章收尾扩充(5段)")
    else:
        LOG.append("MISS 五章注段未找到")

    nrev = with_retry(lambda: doc.Revisions.Count)
    for i in range(nrev, 0, -1):
        rv = with_retry(lambda: doc.Revisions(i))
        with_retry(lambda: rv.Accept())
    with_retry(lambda: doc.Save())
    ntab = with_retry(lambda: doc.Tables.Count)
    nimg = with_retry(lambda: doc.InlineShapes.Count)
    with_retry(lambda: doc.Close(False))
    LOG.append(f"[DONE] tables={ntab} images={nimg} revisions={with_retry(lambda: 0)}")
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\apply_fixes_log.txt", "w", encoding="utf-8").write("\n".join(str(x) for x in LOG))
print("APPLY_DONE")
