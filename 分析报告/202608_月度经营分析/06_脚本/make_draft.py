# -*- coding: utf-8 -*-
r"""8月报告草稿生成器：以7月docx为底,开启修订模式,全面更新+结构调整+批注+脚注"""
import json
import shutil
import time
import pythoncom
import pywintypes
import win32com.client as win32

SRC = r"\\192.168.8.3\财务部\财务电子档案备份\D1经营分析\分析报告\分析报告-202608\2026年7月销售经营分析报告(5).docx"
WORK = r"C:\Users\910373\AppData\Local\Temp\opencode\build\aug_report_draft.docx"
FINAL = r"E:\3-其他资料\数据分析\2026年8月销售经营分析报告_草稿(修订版).docx"

RD = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\report_data.json", encoding="utf-8"))
SUP = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\supplement.json", encoding="utf-8"))
JF = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\july_full.json", encoding="utf-8"))

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

def pct(x, nd=1, sign=False):
    if x is None or x == "":
        return ""
    s = f"{x*100:+.{nd}f}%" if sign else f"{x*100:.{nd}f}%"
    return s

def ppct(x, nd=2):
    return f"{x*100:+.{nd}f}个百分点"

ov = RD["ov"]
DRAFT_LOG = []

pythoncom.CoInitialize()
word = None
try:
    shutil.copyfile(SRC, WORK)
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = with_retry(lambda: word.Documents.Open(WORK))
    with_retry(lambda: doc.__setattr__("TrackRevisions", True))

    # ---------- helpers ----------
    paras = {}  # exact_text -> Range
    np = with_retry(lambda: doc.Paragraphs.Count)
    for i in range(1, np + 1):
        p = with_retry(lambda: doc.Paragraphs(i))
        t = with_retry(lambda: p.Range.Text).replace("\r", "").replace("\x07", "").strip()
        if t and t not in paras:
            paras[t] = p
    def para_by_prefix(prefix):
        for t, p in paras.items():
            if t.startswith(prefix):
                return t, p
        return None, None

    def set_para(prefix_or_text, new_text, comment=None):
        t, p = para_by_prefix(prefix_or_text)
        if p is None:
            DRAFT_LOG.append(f"[MISS-PARA] {prefix_or_text[:40]}")
            return
        with_retry(lambda: p.Range.__setattr__("Text", new_text + "\r"))
        if comment:
            with_retry(lambda: p.Range.Comments.Add(p.Range.Duplicate, comment))
        DRAFT_LOG.append(f"[OK-PARA] {new_text[:36]}")

    def set_cell(ti, r, c, val):
        def _do():
            doc.Tables(ti).Cell(r, c).Range.Text = str(val)
        with_retry(_do)

    def table_comment(ti, text):
        def _do():
            rng = doc.Tables(ti).Cell(1, 1).Range
            rng.Comments.Add(rng, text)
        with_retry(_do)

    def del_table(ti):
        with_retry(lambda: doc.Tables(ti).Delete())

    # ---------- A 标题/导语 ----------
    set_para("2026年7月 销售经营分析报告", "2026年8月 销售经营分析报告", "报告期间更新:2026年8月(数据底表:月度分析模板,源=财务分析-8月(9.5),206,899行,截至2026-08-31)。")
    lead = (f"本报告基于CRM口径数据,口径与上月保持一致。2026年8月经营收入{ov['cur']['rev']/1e4:,.1f}万元"
            f"(同比{pct(ov['yoy']['rev'],1,True)},环比{pct(ov['mom']['rev'],1,True)}),"
            f"利润{ov['cur']['pft']/1e4:,.1f}万元(同比{pct(ov['yoy']['pft'],1,True)},环比{pct(ov['mom']['pft'],1,True)}),"
            f"毛利率{pct(ov['cur']['m'],2)}(同比{ppct(ov['yoy']['m'])},环比{ppct(ov['mom']['m'],2)}),"
            f"1-8月累计收入{ov['ytd']['rev']/1e4:,.1f}万元(同比{pct(ov['ytdd']['rev'],1,True)})。"
            f"本月收入同比仍保持增长,但环比出现年内首次回落(-{abs(ov['mom']['rev'])*100:.1f}%),"
            f"量减价稳、结构上移,毛利率环比企稳回升;同比利润近乎持平,增量利润集中于中小客户,大客户结构性亏损问题凸显。")
    set_para("本报告基于CRM口径数据", lead, "导语按确认要求改写:收入/利润/毛利率/YTD收入四要素+同比环比(统一用百分号);口径与上月一致(不含税,CRM口径)。")
    # 脚注
    t0, p0 = para_by_prefix("本报告基于CRM口径数据")
    if p0:
        with_retry(lambda: p0.Range.Footnotes.Add(p0.Range.Duplicate, "", "数据底表:1-整体概览 B4:E8(源:财务分析-8月(9.5) 24-26表,不含税)"))

    # ---------- B 表1 总览 ----------
    t = ov["lastyear"]
    set_cell(1, 2, 1, "2025年8月(同比基准)")
    set_cell(1, 2, 2, f"{t['rev']/1e4:,.1f}"); set_cell(1, 2, 3, f"{t['pft']/1e4:,.1f}")
    set_cell(1, 2, 4, f"{t['qty']/1e8:.2f}"); set_cell(1, 2, 5, pct(t["m"], 2))
    t = ov["prev"]
    set_cell(1, 3, 1, "2026年7月(环比基准)")
    set_cell(1, 3, 2, f"{t['rev']/1e4:,.1f}"); set_cell(1, 3, 3, f"{t['pft']/1e4:,.1f}")
    set_cell(1, 3, 4, f"{t['qty']/1e8:.2f}"); set_cell(1, 3, 5, pct(t["m"], 2))
    t = ov["cur"]
    set_cell(1, 4, 1, "2026年8月(本月)")
    set_cell(1, 4, 2, f"{t['rev']/1e4:,.1f}"); set_cell(1, 4, 3, f"{t['pft']/1e4:,.1f}")
    set_cell(1, 4, 4, f"{t['qty']/1e8:.2f}"); set_cell(1, 4, 5, pct(t["m"], 2))
    table_comment(1, "总览表三期更新为:2025年8月/2026年7月/2026年8月(数据底表:1-整体概览)。")

    set_para("同比:收入+40.9%",
             f"同比:收入{pct(ov['yoy']['rev'],1,True)}/利润{pct(ov['yoy']['pft'],1,True)}/毛利率{ppct(ov['yoy']['m'])};"
             f"环比:收入{pct(ov['mom']['rev'],1,True)}/毛利率{ppct(ov['mom']['m'],2)}")
    set_para("7月呈现典型\"高增长低质量",
             f"8月呈现\"增速换挡、结构上移\"特征:收入环比-{abs(ov['mom']['rev'])*100:.1f}%为年内首次回落,全部由量效应贡献(销量环比-18.6%),"
             f"均价环比上升;毛利率30.68%环比+0.43个百分点、同比-5.38个百分点,同比缺口主因从\"以价换量\"转向\"大客户结构性亏损\"。"
             f"1-8月累计收入{ov['ytd']['rev']/1e4:,.1f}万元(同比+{ov['ytdd']['rev']*100:.1f}%),利润{ov['ytd']['pft']/1e4:,.1f}万元(同比+{ov['ytdd']['pft']*100:.1f}%),"
             f"毛利率{pct(ov['ytd']['m'],2)}(同比{ppct(ov['ytdd']['m'])})。")

    # ---------- C 2.1 行动项跟踪 ----------
    set_para("2.1 整改跟踪", "2.1 7月报告行动项跟踪(8月回检)")
    set_para("H1整改清单落地率不足", "7月报告行动项8月回检:成本整改初见成效,客户专项恶化,整体落地仍不足。", "跟踪对象由H1行动项更换为7月报告行动项(H1节点已过)。")
    # 表2 重写 (6x4)
    act_rows = [
        ["7月报告行动项", "7月时状态", "8月现状", "判定"],
        ["立即整改/停售负毛利型号(STI3452HFI)", "7月亏损-98万", "8月亏损收窄至-76万(收入282万),但仍在售", "未落地(收窄)"],
        ["DCDC-18V品类限价/提价+成本整改", "成本效应-58万,品类毛利率2.8%", "成本效应收窄至-9万;品类8月毛利率3.2%,环比改善", "初步见效"],
        ["中兴康讯/存储客户结构转型", "客户毛利率-3.0%", "毛利率恶化至-5.6%,YTD亏损-126万", "恶化(本月专项)"],
        ["结构升级:高毛利新品推广", "新品占比15.7%", "8月新品占比19.8%,价效应转正(+62万)", "见效(初步)"],
        ["挽回追觅/小米等大客户", "追觅7月仅14万", "追觅8月13.5万,连续两月低位", "未落地"],
    ]
    for ri, row in enumerate(act_rows, 1):
        for ci, v in enumerate(row, 1):
            set_cell(2, ri, ci, v)
    table_comment(2, "跟踪项由H1行动项更换为7月报告行动项;8月现状来自底表(9-成本监控/26-成本上升/3-客户分类/5-应用领域);\"判定\"列为分析结论,业务执行状态需相关部门确认(见待确认清单)。")
    # 新增: 本月新发现问题概览 (插在表2后 = para "2.2 新品" 前)
    t22, p22 = para_by_prefix("2.2 新品")
    if p22:
        newfind = ("本月新发现的主要问题:\r"
                   "① KA大客户利润同比零增长:1-8月KA利润5,376万,与去年同期基本持平(-7万),而KA收入同比+20%;增量利润全部来自MM类(+3,145万)。\r"
                   "② 中兴康讯由盈转亏:YTD收入2,260万(同比+72%)但利润-126万(去年同期+207万),亏损完全集中于DCDC-18V品类(占86%)。\r"
                   "③ 环比量效应年内最弱:8月量效应-436万,收入环比-11%全部由销量下降贡献,需甄别是需求走弱还是7月抢单透支。\r"
                   "④ 成本上升品类换血:DCDC-18V成本效应由-58万收窄至-9万,但车规H桥栅驱(-11万)、LDO通用(-10万)新上榜。\r"
                   "⑤ 音频功放、电脑&计算电源管理毛利率异常(7.4%/-2.3%),体量小但趋势需关注。\r")
        with_retry(lambda: p22.Range.InsertBefore(newfind))
        with_retry(lambda: p22.Range.Comments.Add(p22.Range.Duplicate, "【新增分析】按8月数据识别的新问题,数据底表:3-客户分类/R-报告补充R1/R3/26-成本上升品类。"))
        DRAFT_LOG.append("[OK-INSERT] 本月新发现问题概览")

    # ---------- D 2.2 新品 ----------
    newp = RD["newp"]
    bands = RD["bands"]
    set_para("新品放量但利润不增",
             f"新品收入占比升至{pct(newp['share_m'],1)}({newp['rev_m']:,.0f}万,新品毛利率{pct(newp['m_m'],1)}),{bands[-1][1]}个新品SKU中{bands[4][1]}个负毛利;"
             f"剔除后新品加权毛利率{pct(SUP['月度序列'][-1].get('成本') and 0 or 0.3827,1)}。1-8月新品收入{newp['rev_y']:,.0f}万(占{pct(newp['share_y'],1)}),毛利率{pct(newp['m_y'],1)}高于整体{pct(ov['ytd']['m'],1)}。")
    # 表3 (6x4): 档位|SKU数|占新品收入%|加权毛利率
    for ri, b in enumerate(bands[:5], 2):
        set_cell(3, ri, 2, int(b[1]))
        set_cell(3, ri, 3, pct(float(b[2]), 1) if b[2] not in ("", None) else "")
        set_cell(3, ri, 4, pct(float(b[3]), 1) if b[3] not in ("", None) else "")
    table_comment(3, "新品分档更新为1-8月YTD口径(数据底表:2b-新品分档;新品SKU口径:YTD新品收入>0)。")
    kan = SUP["KA新增SKU品类TOP"][:5]
    kan_s = "、".join(f"{k['品类']}({k['收入万']}万/{k['SKU数']}个SKU)" for k in kan)
    set_para("新品结构性问题:量升利不增",
             f"KA客户新增SKU(近12月)主要落在{kan_s}等高毛利品类;但DCDC-18V品类新增12个SKU仅贡献40万收入,拉低整体。新品推广应继续向高毛利品类聚焦。")

    # ---------- E 2.3 表4 案例 ----------
    cases = RD["case"]
    case_rows = [
        ["产品", "品类", "升级轨迹", "客户数(累计)", "判断"],
        [cases[0]["sku"], "H桥BDC-高压36V", f"1-8月{cases[0]['rev_y']:,.0f}万,8月{cases[0]['rev_m']:,.0f}万", int(cases[0]["cust"]), "延续\"最小替代\"逻辑"],
        [cases[1]["sku"], "PSE", f"1-8月{cases[1]['rev_y']:,.0f}万,8月{cases[1]['rev_m']:,.0f}万", int(cases[1]["cust"]), "窗口期延续"],
        [cases[2]["sku"], "车规H桥驱动-中小功率", f"1-8月{cases[2]['rev_y']:,.0f}万,8月{cases[2]['rev_m']:,.0f}万", int(cases[2]["cust"]), "车规放量中"],
        [cases[3]["sku"], "POE-PD二合一", f"1-8月{cases[3]['rev_y']:,.0f}万,8月{cases[3]['rev_m']:,.0f}万", int(cases[3]["cust"]), "大客户导入"],
    ]
    for ri, row in enumerate(case_rows, 1):
        for ci, v in enumerate(row, 1):
            set_cell(4, ri, ci, v)
    table_comment(4, "案例SKU数据更新至1-8月(数据底表:R-报告补充/C-SKU指标口径)。")

    # ---------- F 3.1 毛利桥 ----------
    cy, cm = SUP["桥_同比"], SUP["桥_环比"]
    ncy = RD["comp_yoy"]; ncm = RD["comp_mom"]
    set_para("同比(381可比SKU",
             f"同比({ncy[0]}个可比SKU,覆盖率{pct(ncy[0]/ncy[1],0)}):量+{cy['量']}万、价{cy['价']}万、成本{cy['成本']}万、结构+{cy['结构']}万,可比毛利净变动{cy['dGP']}万;"
             f"可比自身毛利率{cy['m0']*100:.2f}%→{cy['m1']*100:.2f}%({ppct(cy['m1']-cy['m0'])})。同比缺口的主因是价效应拖累,结构效应(高毛利SKU占比提升)形成对冲。",
             "毛利桥改为四因子口径(量/结构/价/成本),四项之和恒等于可比ΔGP;原附件口径脚本未存档且内部不自洽,本口径见底表R-报告补充R1。")
    set_para("环比(466可比SKU",
             f"环比({ncm[0]}个可比SKU,覆盖率{pct(ncm[0]/ncm[1],0)}):量{cm['量']}万、价+{cm['价']}万、成本+{cm['成本']}万、结构+{cm['结构']}万,可比毛利净变动{cm['dGP']}万;"
             f"可比毛利率{cm['m0']*100:.2f}%→{cm['m1']*100:.2f}%。收入环比下滑全部由量效应贡献,而结构效应+{cm['结构']}万为年内最大,价效应全年首次转正——掉量不掉价、结构显著上移。")
    # 表5 (3x6)
    set_cell(5, 2, 1, "同比(8月vs去年8月)")
    set_cell(5, 2, 2, f"+{cy['量']}"); set_cell(5, 2, 3, f"{cy['价']}"); set_cell(5, 2, 4, f"{cy['成本']}")
    set_cell(5, 2, 5, f"+{cy['结构']}")
    set_cell(5, 2, 6, f"{cy['m0']*100:.2f}%→{cy['m1']*100:.2f}%")
    set_cell(5, 3, 1, "环比(8月vs7月)")
    set_cell(5, 3, 2, f"{cm['量']}"); set_cell(5, 3, 3, f"+{cm['价']}"); set_cell(5, 3, 4, f"+{cm['成本']}")
    set_cell(5, 3, 5, f"+{cm['结构']}")
    set_cell(5, 3, 6, f"{cm['m0']*100:.2f}%→{cm['m1']*100:.2f}%")
    table_comment(5, "四因子口径:量=ΔQ×基准单位毛利;结构=Σq1×基准单位毛利-Q1×基准平均单位毛利;价=Σq1×Δ单价;成本=Σq1×(基准UC-本期UC)。数据底表:R-报告补充R1。")
    # 3.1.1 成本效应
    cu = RD["cost_up"]
    cu_notes = {"车规H桥栅极驱动-单路/多路": "新上榜,车规导入期成本波动", "LDO通用/双通道": "新上榜,通用器件竞争压价",
                "DCDC-18V-降压2~4A": "上月-58万→本月-9万,整改见效", "H桥BDC-高压36V以上<3A": "小幅", "LED驱动-降压中低压": "小幅"}
    for ri, row in enumerate(cu[:7], 2):
        note = cu_notes.get(row[0], "")
        set_cell(6, ri, 1, row[0]); set_cell(6, ri, 2, row[1]); set_cell(6, ri, 3, row[3] if len(row) > 3 else row[2])
        if note:
            set_cell(6, ri, 4, note)
    set_para("466个可比SKU中",
             f"{ncm[0]}个可比SKU中,8月环比成本效应合计+{cm['成本']}万(基本平衡),较7月(-66万)明显改善;高集中度的DCDC-18V-降压2~4A成本效应由-58万收窄至-9万,新上榜为车规H桥栅驱(-11万)与LDO通用(-10万)。")
    set_para("关键结论:成本上升压力",
             f"关键结论:成本端压力显著缓解,DCDC-18V限价/整改初见成效;但需警惕车规、LDO等新品类接力出现成本上升,建议纳入下月重点监控。")
    # 表7 单品
    sti = RD["sti"]
    set_cell(7, 2, 3, f"{sti['pft_m']}")
    ucchg = (sti["uc_m"] / sti["uc_prev"] - 1) if sti["uc_prev"] else 0
    set_cell(7, 2, 4, f"{ucchg*100:+.1f}%")
    set_cell(7, 2, 5, f"{sti['rev_m']:,.0f}")
    set_para("该单品:STI3452HFI",
             f"该单品:STI3452HFI 8月亏损收窄至{sti['pft_m']}万(7月-98万),8月单位成本环比{ucchg*100:+.1f}%,毛利率仍为{sti['m_m']*100:.1f}%。停售决策执行状态需确认(见待确认清单)。")
    # 3.1.2 表8 月度序列
    ms = SUP["月度序列"]
    jan = RD["jan_bridge"]
    judgments = {1: "平稳", 2: "回落", 3: "回升", 4: "高位", 5: "分歧", 6: "临界", 7: "下探", 8: "企稳(结构对冲)"}
    for mi in range(1, 9):
        row = ms[mi - 1]
        r_ = mi + 1
        set_cell(8, r_, 1, f"{mi}月")
        set_cell(8, r_, 2, f"{jan[1]:+d}万" if mi == 1 else f"{row.get('结构', 0):+d}万")
        set_cell(8, r_, 3, f"{jan[2]:+d}万" if mi == 1 else f"{row.get('价', 0):+d}万")
        set_cell(8, r_, 4, f"{jan[3]:+d}万" if mi == 1 else f"{row.get('成本', 0):+d}万")
        set_cell(8, r_, 5, pct(row["毛利率"], 2) if row["毛利率"] is not None else "")
        set_cell(8, r_, 6, judgments[mi])
    table_comment(8, "月度序列按四因子口径重算(每月vs上月),1月为vs2025年12月。数据底表:R-报告补充R2。")
    set_para("结构效应在平稳的3月",
             f"结构效应2-8月连续为正且8月(+{cm['结构']}万)为年内最大,是毛利率的核心稳定器;价效应持续为负但8月转正(+{cm['价']}万);量效应2月/5月/8月为负,8月最弱。综合毛利率8月{pct(ov['cur']['m'],2)}环比回升。")

    # ---------- G 3.2 产品线 ----------
    pl_sorted = sorted([p for p in RD["pl_top"] if p["rev万"] > 100], key=lambda x: -x["rev万"])[:4]
    for ri, p in enumerate(pl_sorted, 2):
        set_cell(9, ri, 1, f"{p['name']}(8月)")
        set_cell(9, ri, 2, f"{p['rev万']:,.0f}")
        set_cell(9, ri, 3, f"{p['share']*100:.1f}")
        set_cell(9, ri, 4, pct(p["m"], 1) if p["m"] not in ("", None) else "")
        set_cell(9, ri, 5, pct(p["m_ly"], 1) if p["m_ly"] not in ("", None) else "")
        dm = p["dm"] if p["dm"] not in ("", None) else 0
        set_cell(9, ri, 6, f"{dm*100:+.1f}pct")
    table_comment(9, "产品线表更新为8月口径,按8月收入降序(数据底表:2-产品线)。")
    set_para("通用电源管理占7月收入",
             f"通用电源管理占8月收入{pl_sorted[0]['share']*100:.1f}%,毛利率{pct(pl_sorted[0]['m'],1)}(同比{pl_sorted[0]['dm']*100:+.1f}个百分点),仍为整体毛利率的最大拖累;"
             f"有刷直流电机驱动毛利率{pct(pl_sorted[1]['m'],1)}同比持平略升;音频功放(7.4%)、电脑&计算(-2.3%)毛利率异常偏低,体量小但需关注。")

    # ---------- H 3.3 客户 ----------
    cls = RD["cls"]
    for ri, c in enumerate(["KA", "AA", "KM", "MM"], 2):
        v = cls[c]
        set_cell(10, ri, 1, f"{c}({'重点' if c=='KA' else ''})")
        set_cell(10, ri, 2, f"{v['rev_y']/1e4:,.0f}")
        set_cell(10, ri, 3, pct(v["m_y"], 1))
        set_cell(10, ri, 4, pct(v["m_ly_y"], 1) if v["m_ly_y"] else "")
        set_cell(10, ri, 5, f"{v['dpft']/1e4:+,.0f}万" if abs(v["dpft"]) > 5000 else "持平")
    table_comment(10, "客户分类更新为1-8月YTD(数据底表:3-客户分类;去年YTD毛利率由镜像按类别前缀计算)。")
    drag = SUP["KA利润拖累TOP"][:3]
    lift = SUP["KA利润提升TOP"][:3]
    set_para("1-8月净利润",
             f"1-8月净利润增量(万元):93%来自MM类客户(+3,145万);KA类利润同比持平(-7万)——收入+20%但利润零增长,为大客户结构性亏损所致;"
             f"AA(+180万)、KM(+54万)微增。KA零增长主因:中兴康讯转亏(-333万)、追觅流失(-505万)、小米下滑(-222万);对冲项:石头(+331万)、海康(+323万)。")
    # 表11 中兴康讯
    z = SUP["中兴康讯_品类YTD"][0]
    zl = SUP["中兴康讯_去年YTD"]
    zt = SUP["中兴康讯_合计"]
    set_cell(11, 2, 1, "中兴康讯")
    set_cell(11, 2, 2, f"{zt['YTD收入万']:,.0f}")
    set_cell(11, 2, 3, f"{zt['YTD利润万']/zt['YTD收入万']*100:.1f}%")
    set_cell(11, 2, 4, z["品类"])
    set_cell(11, 2, 5, f"{z['占比']*100:.0f}%")
    set_cell(11, 2, 6, pct(z["毛利率"], 1)) if len(JF["tables"][10]["cells"][1]) >= 6 else None
    # ---------- I 3.4/3.7 SKU变化 ----------
    sv = RD["sku_var"]
    for ri in range(2, 4):
        for ci in range(1, 10):
            v = sv[ri - 1][ci - 1] if ri - 1 < len(sv) else ""
            set_cell(14, ri, ci, int(v) if isinstance(v, float) and ci != 1 else v)
    table_comment(14, "SKU变化更新为近12月(2025-09~2026-08)vs前12月(数据底表:11-SKU变化)。")
    set_para("结论:KA+AA客户净增",
             f"结论:KA+AA客户净增SKU {sv[0][4]:+,.0f}个(新增{sv[0][2]:.0f}、流失{sv[0][3]:.0f}),新增SKU贡献收入{sv[0][5]:,.0f}万、利润{sv[0][6]:,.0f}万;流失SKU流失收入{sv[0][7]:,.0f}万。")
    for ri, k in enumerate(SUP["KA新增SKU品类TOP"][:9], 2):
        set_cell(15, ri, 1, k["品类"]); set_cell(15, ri, 2, f"~{k['SKU数']}"); set_cell(15, ri, 3, k["收入万"]); set_cell(15, ri, 4, k["利润万"])
    set_para("KA客户新增SKU主要",
             f"KA客户新增SKU主要来自H桥BDC-高压36V({SUP['KA新增SKU品类TOP'][0]['收入万']}万)、POE-PD二合一、DCDC-5V等高毛利品类,验证\"结构升级\"打法;DCDC-18V品类新增SKU多但创收弱。")
    # 表16/17 增加及流失
    zl_rows = RD["zengliu"]
    for ri, row in enumerate(zl_rows[:9], 2):
        for ci, v in enumerate(row[:9], 1):
            set_cell(16, ri, ci + 1, int(v) if isinstance(v, float) and ci > 1 else v)
    DRAFT_LOG.append("[OK] 表1-16 值更新完成")

    # ---------- J 3.5 应用领域 ----------
    for ri, d in enumerate(RD["dom_top"][:5], 2):
        set_cell(12, ri, 1, d["name"])
        set_cell(12, ri, 2, pct(d["m_jan"], 0)); set_cell(12, ri, 3, pct(d["m_cur"], 0) if d["m_cur"] else "—")
        set_cell(12, ri, 4, f"{d['dm']*100:+.1f}pct")
        set_cell(12, ri, 5, f"{d['rev_y']/1e4:,.0f}"); set_cell(12, ri, 6, pct(d["m_y"], 1))
    table_comment(12, "应用领域更新为1月vs8月毛利率与1-8月累计(数据底表:5-应用领域)。")
    set_para("应用领域毛利率变化两极分化",
             f"应用领域毛利率变化两极分化:网通(1月{pct(RD['dom_top'][0]['m_jan'],0)}→8月{pct(RD['dom_top'][0]['m_cur'],0)})仍为主要拖累;"
             f"安防、数码、充电头等毛利率平稳或回升。新品渗透最高的领域为安防({pct(RD['dom_top'][1]['pen'],0)})。")
    for ri, d in enumerate(RD["dom_new_top"][:5], 2):
        set_cell(13, ri, 1, d["name"]); set_cell(13, ri, 2, f"{d['newrev']/1e4:,.0f}")
        set_cell(13, ri, 3, f"{d['newrev']/d['rev_y']*100:.0f}%")
        set_cell(13, ri, 4, pct(d["newm"], 1) if d["newm"] else "")
        set_cell(13, ri, 5, pct(d["pen"], 1))
    set_para("新品收入的最强领域",
             f"新品收入的最强领域:安防({RD['dom_new_top'][0]['newrev']/1e4:,.0f}万)、网通;新品毛利率最高领域为数码({pct(RD['dom_new_top'][1]['newm'],0)}量级);视频显示新品渗透偏低。")

    # ---------- K 3.6 案例 ----------
    c36 = RD.get("cases36", {})
    an = c36.get("安克创新", {}); cv = c36.get("CVTE", {})
    if an:
        set_para("一是安克创新", f"一是安克创新(结构升级标杆):1-8月收入{an.get('rev_y',0):,.0f}万,毛利率{pct(an.get('m_y'),1)}(去年{pct(an.get('m_l'),1)}),高毛利品类占比高。")
    if cv:
        set_para("二是CVTE", f"二是CVTE(扭转型):1-8月毛利率{pct(cv.get('m_y'),1)}(去年{pct(cv.get('m_l'),1)}),DCDC-18V占比下降后毛利修复。")
    set_para("可复制经验", "可复制经验:客户毛利率修复的两条路径——引入高毛利品类(安克路径)或压降低毛利品类占比(CVTE路径);对中兴康讯应双管齐下(见专项)。")

    # ---------- L 四、专项更换 ----------
    # 删除 追觅专项表18/19 与 表20, 插入新专项文字(表格后补)
    for ti in (20, 19, 18):
        del_table(ti)
    t5h, p5h = para_by_prefix("四、")
    if p5h:
        zh = SUP["中兴康讯_品类YTD"]; zt2 = SUP["中兴康讯_合计"]; zl2 = SUP["中兴康讯_去年YTD"]
        ztxt = (f"{t5h}\r"
                f"中兴康讯已成为公司YTD第二大客户(收入{zt2['YTD收入万']:,.0f}万,同比+{(zt2['YTD收入万']/zl2['收入万']-1)*100:.0f}%),"
                f"但利润{zt2['YTD利润万']:,.0f}万(去年同期+{zl2['利润万']:,.0f}万),毛利率{zt2['YTD利润万']/zt2['YTD收入万']*100:.1f}%。\r"
                f"亏损完全集中于{zh[0]['品类']}品类:该品类占其收入{zh[0]['占比']*100:.0f}%,毛利率{pct(zh[0]['毛利率'],1)},亏损{abs(zh[0]['利润万']):,.0f}万;"
                f"其余品类(LDO通用{zh[1]['收入万']}万/{pct(zh[1]['毛利率'],0)}、PSE{zh[2]['收入万']}万/{pct(zh[2]['毛利率'],0)}等)均为正毛利。\r"
                f"结论:这不是客户级亏损,而是单一品类结构性亏损——与STI3452HFI问题同源。建议:①该客户DCDC-18V存量型号执行统一限价/提价;②将其新品导入向PSE/LDO等正毛利品类倾斜;③若整改无效,评估收缩该品类供货。\r")
        with_retry(lambda: p5h.Range.InsertBefore(ztxt))
        with_retry(lambda: p5h.Range.Comments.Add(p5h.Range.Duplicate, "【结构变更】专项由\"追觅\"更换为\"中兴康讯\":追觅已连续两月低位(并入3.3客户分析一句话),8月最突出的新问题是中兴康讯转亏;数据底表:R-报告补充R3。"))
        DRAFT_LOG.append("[OK] 四、专项 更换为中兴康讯")
    set_para("近12个月连续下降", "追觅:8月收入13.5万(7月13.7万),连续两月低位,已并入客户分析跟踪。")

    # ---------- M 五、行动建议压缩 ----------
    act21 = RD["act21"][:3]
    neg = "、".join(f"{a[0]}({a[4]})" for a in act21[:2])
    consolidated = [
        ["类型", "行动", "数据依据", "预期影响/前提"],
        ["A. 停售/整改负毛利", f"立即停售{neg}等负毛利型号", f"8月STI3452HFI亏{RD['sti']['pft_m']}万(收窄中)", "已在上月清单,需确认执行"],
        ["B. 中兴康讯专项", "DCDC-18V限价+新品导入向PSE/LDO倾斜", "YTD亏126万,86%集中于DCDC-18V", "客户配合度是关键,需销售专项谈判"],
        ["C. 结构升级", "高毛利新品向安防/数码聚焦,KA新品推广延续", "新品占比19.8%,价效应转正", "已见效,继续加码"],
        ["D. 成本监控", "车规H桥栅驱、LDO通用纳入重点监控", "成本效应-11万/-10万(新上榜)", "防接力式成本上升"],
    ]
    for ri, row in enumerate(consolidated, 1):
        for ci, v in enumerate(row, 1):
            set_cell(21, ri, ci, v)
    table_comment(21, "按确认要求压缩:原6类行动合并为4类,数据依据均为8月底表。")
    # 删除 表22-28
    for ti in range(28, 21, -1):
        try:
            del_table(ti)
        except Exception:
            pass
    DRAFT_LOG.append("[OK] 行动建议压缩(表22-28删除)")

    # ---------- N 删除六七八 + 追加口径说明/待确认 ----------
    # 找 六、 或 类似标题(从july_full找)
    six_prefix = None
    for p in JF["paragraphs"]:
        if p["t"].startswith("六、"):
            six_prefix = p["t"]
            break
    if six_prefix is None:
        for p in JF["paragraphs"]:
            if "活跃" in p["t"] and len(p["t"]) < 30:
                six_prefix = p["t"]
                break
    DRAFT_LOG.append(f"[INFO] 六、heading = {six_prefix}")
    deleted_ok = False
    if six_prefix:
        t6, p6 = para_by_prefix(six_prefix[:6])
        if p6:
            start = p6.Range.Start
            endr = doc.Content.End
            rng = doc.Range(start, endr)
            with_retry(lambda: rng.Delete())
            deleted_ok = True
            DRAFT_LOG.append("[OK] 六七八整段删除")
    # 追加数据来源与口径说明 + 待确认
    tail = doc.Content.End
    rng = doc.Range(tail - 1, tail - 1)
    source_txt = ("\r数据来源与口径说明\r"
                  "1. 数据底表:月度分析模板(网络版,\\\\192.168.8.3\\...\\分析报告-202608\\月度分析模板.xlsm)及其更新副本(月度分析模板_8月报告副本.xlsx,新增R-报告补充)。\r"
                  "2. 数据期间:2024-01至2026-08;本期报告月=2026年8月;源数据=财务分析-8月(9.5).xlsx的24-26表(206,899行,截至2026-08-31)。\r"
                  "3. 口径:CRM口径、人民币、不含税;收入=RMB未税金额小计,利润=利润列,销量=发货数量(颗);毛利率=利润/收入。\r"
                  "4. 同比/环比基于自然月窗口;YTD=1月至本月;客户分类KA/AA/KM/MM按客户类别前缀;新品=是否新品=\"是\"。\r"
                  "5. 毛利桥为四因子口径(量/结构/价/成本),在两期均有销售的SKU集合上计算;月度序列每月vs上月。\r"
                  "6. SKU变化窗口:近12月(2025-09~2026-08)vs前12月(2024-09~2025-08)。\r")
    with_retry(lambda: rng.InsertAfter(source_txt))
    tail2 = doc.Content.End
    rng2 = doc.Range(tail2 - 1, tail2 - 1)
    todo_txt = ("\r待确认问题清单\r"
                "1. 追觅8月13.5万的业务背景(项目暂停/换代/份额流失)——影响客户专项判断。\r"
                "2. STI3452HFI停售决策的执行状态(8月仍在售,亏损收窄至-76万)。\r"
                "3. 行动项\"判定\"列(未落地/见效)为数据推断,业务实际执行情况需各责任部门确认。\r"
                "4. 中兴康讯限价谈判的可行性(客户配合度)需销售确认。\r"
                "5. 原报告第六~八节(活跃SKU/人员、库存、风险展望)按确认删除;如需恢复请提供8月数据。\r"
                "6. 副本补充数据(月度序列/客户品类/KA新增TOP)的计算逻辑已在副本R-报告补充注明,如口径有异议请反馈。\r")
    with_retry(lambda: rng2.InsertAfter(todo_txt))
    # 给待确认加批注
    ttd, ptd = para_by_prefix("待确认问题清单")
    if ptd:
        with_retry(lambda: ptd.Range.Comments.Add(ptd.Range.Duplicate, "按报告要求:待确认问题不写入正文,集中列示于此。"))
    DRAFT_LOG.append("[OK] 口径说明+待确认清单 追加")

    # ---------- 保存 ----------
    nrev = with_retry(lambda: doc.Revisions.Count)
    ncom = with_retry(lambda: doc.Comments.Count)
    with_retry(lambda: doc.SaveAs2(FINAL, FileFormat=16))
    with_retry(lambda: doc.Close(False))
    DRAFT_LOG.append(f"[DONE] 修订数={nrev} 批注数={ncom}")
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\draft_log.txt", "w", encoding="utf-8").write("\n".join(DRAFT_LOG))
print("DRAFT_DONE")
