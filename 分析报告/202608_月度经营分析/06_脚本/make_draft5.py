# -*- coding: utf-8 -*-
r"""draft5 最终抛光：四、标题 + 待确认清单独立文件"""
import time
import pythoncom
import pywintypes
import win32com.client as win32

FINAL = r"E:\3-其他资料\数据分析\2026年8月销售经营分析报告_草稿(修订版).docx"
TODO = r"E:\3-其他资料\数据分析\待确认问题清单_8月报告.txt"

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
    doc = with_retry(lambda: word.Documents.Open(FINAL))
    with_retry(lambda: doc.__setattr__("TrackRevisions", True))
    np_ = with_retry(lambda: doc.Paragraphs.Count)
    target = None
    for i in range(1, np_ + 1):
        p = with_retry(lambda: doc.Paragraphs(i))
        t = with_retry(lambda: p.Range.Text).replace("\r", "").replace("\x07", "").strip()
        if t.startswith("中兴康讯已成为公司YTD第二大客户"):
            target = i
            break
    LOG.append(f"anchor para: {target}")
    if target:
        p = with_retry(lambda: doc.Paragraphs(target))
        with_retry(lambda: p.Range.InsertBefore("四、专项:中兴康讯——规模第二、毛利转负的结构性亏损\r"))
        with_retry(lambda: p.Range.Comments.Add(p.Range.Duplicate,
            "【结构变更】专项由\"追觅\"更换为\"中兴康讯\":追觅连续两月低位已并入3.3客户分析;8月最突出新问题为中兴康讯转亏(数据底表:R-报告补充R3)。"))
        LOG.append("[OK] 四、标题插入")
    # 清理 855 合并段: 找到含"四、将SKU变化"的段, 将其文本规范为单句(修订模式下显示新旧对比)
    for i in range(1, min(target + 3, np_ + 1) if target else 1, 1):
        pass
    for i in range(1, np_ + 1):
        p = with_retry(lambda: doc.Paragraphs(i))
        t = with_retry(lambda: p.Range.Text).replace("\r", "").replace("\x07", "").strip()
        if t.startswith("四、将SKU变化的利润率影响"):
            with_retry(lambda: p.Range.__setattr__("Text",
                "(上条建议已并入第五节行动建议C类跟踪)" + "\r"))
            LOG.append(f"[OK] 清理旧建议段 @{i}")
            break
    nrev = with_retry(lambda: doc.Revisions.Count)
    ncom = with_retry(lambda: doc.Comments.Count)
    with_retry(lambda: doc.Save())
    with_retry(lambda: doc.Close(False))
    LOG.append(f"[DONE] 修订数={nrev} 批注数={ncom}")
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

todo = """2026年8月销售经营分析报告 · 待确认问题清单
================================================
一、业务事实类(需人工确认后方可定稿)
1. 追觅8月收入13.5万的业务背景:项目暂停/型号换代/份额流失?——影响客户专项判断与挽回策略评估。
2. STI3452HFI停售决策执行状态:7月报告已列"立即整改/停售",8月仍在售(亏损收窄至-76万),是延期执行还是有条件保留?
3. 2.1表"判定"列(未落地/初步见效/恶化)为数据推断,各责任部门实际执行情况需确认。
4. 中兴康讯DCDC-18V限价谈判可行性(客户配合度)——专项建议B的前提。

二、数据口径类(已在文中说明,如无异议可定稿)
5. 毛利桥四因子口径(量/结构/价/成本)为本次重构口径,与7月附件原口径(其脚本未存档且内部不自洽)不可直接对比;量/成本两项与原口径一致。
6. 环比-11%的量效应归因:需结合在手订单数据判断是需求走弱还是7月抢单透支(正文已列两种可能)。
7. KA利润同比零增长的口径:KA按客户类别前缀归类,若客户8月存在类别调整(8.25→8.27重述),归因会略有偏移。

三、结构删除类(按确认执行,如需恢复请提供数据)
8. 原第六节(活跃SKU/人员数)、第七节(库存/长库龄)、第八节(forecast/商务政策)已按确认删除;恢复需提供8月对应数据。
9. 原追觅专项已压缩并入3.3客户分析;如需恢复独立专项请说明。

四、自检提示(变化幅度超±50%的项目及说明)
10. 中兴康讯YTD利润同比: +207万 → -126万(转亏,正文专项展开)。
11. 石头YTD收入同比+90%、海康+116%(高基数下的高增长,正文提及,建议关注可持续性)。
12. 音频功放毛利率7.4%(去年同期17.1%)、电脑&计算-2.3%(小体量,已列入新发现问题⑤)。
13. 本月环比收入-11.0%为年内首次负增长(正文以毛利桥量效应归因)。

——生成于2026-09-08,数据底表:月度分析模板(8月9.5源)+月度分析模板_8月报告副本.xlsx(R-报告补充)
"""
open(TODO, "w", encoding="utf-8").write(todo)
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\draft5_log.txt", "w", encoding="utf-8").write("\n".join(LOG))
print("DRAFT5_DONE")
