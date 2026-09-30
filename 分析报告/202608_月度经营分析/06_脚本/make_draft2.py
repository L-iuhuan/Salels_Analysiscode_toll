# -*- coding: utf-8 -*-
r"""8月报告草稿 v2：精确前缀解析 + 尾部整段手术重插"""
import json
import shutil
import time
import pythoncom
import pywintypes
import win32com.client as win32

SRC = r"\\192.168.8.3\财务部\财务电子档案备份\D1经营分析\分析报告\分析报告-202608\2026年7月销售经营分析报告(5).docx"
WORK = r"C:\Users\910373\AppData\Local\Temp\opencode\build\aug_report_draft2.docx"
FINAL = r"E:\3-其他资料\数据分析\2026年8月销售经营分析报告_草稿(修订版).docx"

RD = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\report_data.json", encoding="utf-8"))
SUP = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\supplement.json", encoding="utf-8"))
JF = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\july_full.json", encoding="utf-8"))
JT = {t["ti"]: t for t in JF["tables"]}

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
    return f"{x*100:+.{nd}f}%" if sign else f"{x*100:.{nd}f}%"

def ppct(x, nd=2):
    return f"{x*100:+.{nd}f}个百分点"

# ============ 预检：模糊键 -> July原文精确文本 ============
JP = [p["t"] for p in JF["paragraphs"] if p["t"]]

def resolve(fuzzy):
    for t in JP:
        if fuzzy in t:
            return t
    return None

TARGETS = {}
def T(fuzzy, new_text=None, comment=None):
    exact = resolve(fuzzy)
    TARGETS[fuzzy] = exact
    return exact

need = {
    "title": "2026年7月 销售经营分析报告",
    "lead": "本报告基于CRM",
    "sumline": "同比:收入+40.9%",
    "mcomment": "7月呈现典型",
    "s21": "2.1 整改跟踪",
    "s21intro": "H1整改清单",
    "s22": "2.2 新品",
    "s22intro": "放量但利润不增",
    "s22dir": "新品结构性问题",
    "bridge_yoy": "可比SKU,覆盖91%",
    "bridge_mom": "可比SKU,覆盖97%",
    "cost_intro": "个可比SKU中",
    "cost_key": "关键结论",
    "sti_key": "该单品",
    "struct_series": "结构效应在平稳",
    "pl_key": "通用电源管理占7月收入",
    "cls_key": "净利润",
    "cls_key2": "拖累客户",
    "sv_concl": "净增SKU",
    "ka_new": "KA客户新增SKU主要",
    "dom_key": "两极分化",
    "dom_new": "最受欢迎",
    "case_anke": "安克创新",
    "case_cvte": "CVTE",
    "exp_key": "可复制经验",
    "sec4": "四、",
    "sec5": "五、",
}
resolved = {}
for k, fz in need.items():
    resolved[k] = resolve(fz)
LOG = [f"resolve {k}: {'OK' if resolved[k] else 'MISS'} -> {str(resolved[k])[:40]}" for k, fz in need.items()]

ov = RD["ov"]
cy, cm = SUP["桥_同比"], SUP["桥_环比"]
ncm = RD["comp_mom"]; ncy = RD["comp_yoy"]
newp = RD["newp"]
bands = RD["bands"]
sti = RD["sti"]
z = SUP["中兴康讯_品类YTD"]; zt = SUP["中兴康讯_合计"]; zl = SUP["中兴康讯_去年YTD"]
sv = RD["sku_var"]
cls = RD["cls"]
pl_sorted = sorted([p for p in RD["pl_top"] if p["rev万"] > 100], key=lambda x: -x["rev万"])[:4]
top20 = RD["top20"]

band5_rev = newp["rev_y"] * 0.0454
band5_pft = band5_rev * (-0.1214)
excl_m = (newp["rev_y"] * newp["m_y"] - band5_pft) / (newp["rev_y"] - band5_rev)

pythoncom.CoInitialize()
word = None
try:
    shutil.copyfile(SRC, WORK)
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = with_retry(lambda: word.Documents.Open(WORK))
    with_retry(lambda: doc.__setattr__("TrackRevisions", True))

    paras = {}
    np_ = with_retry(lambda: doc.Paragraphs.Count)
    for i in range(1, np_ + 1):
        p = with_retry(lambda: doc.Paragraphs(i))
        t = with_retry(lambda: p.Range.Text).replace("\r", "").replace("\x07", "").strip()
        if t and t not in paras:
            paras[t] = p
    def P(key):
        exact = resolved.get(key)
        if exact and exact in paras:
            return paras[exact]
        for t, p in paras.items():
            fz = need.get(key, "")
            if fz and fz in t:
                return p
        return None

    def set_para(key, new_text, comment=None):
        p = P(key)
        if p is None:
            LOG.append(f"[MISS-PARA] {key}")
            return
        with_retry(lambda: p.Range.__setattr__("Text", new_text + "\r"))
        if comment:
            with_retry(lambda: p.Range.Comments.Add(p.Range.Duplicate, comment))
        LOG.append(f"[OK-PARA] {new_text[:34]}")

    def set_cell(ti, r, c, val):
        with_retry(lambda: doc.Tables(ti).Cell(r, c).Range.__setattr__("Text", str(val)))

    def table_comment(ti, text):
        def _do():
            rng = doc.Tables(ti).Cell(1, 1).Range
            rng.Comments.Add(rng, text)
        with_retry(_do)

    # ===== A 标题/导语/总览 =====
    set_para("title", "2026年8月 销售经营分析报告", "报告期间更新为2026年8月(数据底表:月度分析模板,源=财务分析-8月(9.5),206,899行,截至2026-08-31)。")
    lead = (f"本报告基于CRM口径数据,口径与上月保持一致。2026年8月经营收入{ov['cur']['rev']/1e4:,.1f}万元"
            f"(同比{pct(ov['yoy']['rev'],1,True)},环比{pct(ov['mom']['rev'],1,True)}),"
            f"利润{ov['cur']['pft']/1e4:,.1f}万元(同比{pct(ov['yoy']['pft'],1,True)},环比{pct(ov['mom']['pft'],1,True)}),"
            f"毛利率{pct(ov['cur']['m'],2)}(同比{ppct(ov['yoy']['m'])},环比{ppct(ov['mom']['m'],2)}),"
            f"1-8月累计收入{ov['ytd']['rev']/1e4:,.1f}万元(同比{pct(ov['ytdd']['rev'],1,True)})。"
            f"本月收入环比出现年内首次回落,量减价稳、结构上移,毛利率环比企稳;同比利润近乎持平,增量利润集中于中小客户,大客户结构性亏损凸显。")
    set_para("lead", lead, "导语按确认要求改写:收入/利润/毛利率/YTD收入四要素+括号内同比环比(统一百分号);口径与上月一致(不含税)。")
    p0 = P("lead")
    if p0:
        with_retry(lambda: p0.Range.Footnotes.Add(p0.Range.Duplicate, "", "数据底表:1-整体概览 B4:E8(源:财务分析-8月(9.5) 24-26表;不含税)"))
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
    table_comment(1, "总览表三期更新:2025年8月/2026年7月/2026年8月(数据底表:1-整体概览)。")
    set_para("sumline",
             f"同比:收入{pct(ov['yoy']['rev'],1,True)}/利润{pct(ov['yoy']['pft'],1,True)}/毛利率{ppct(ov['yoy']['m'])};"
             f"环比:收入{pct(ov['mom']['rev'],1,True)}/毛利率{ppct(ov['mom']['m'],2)}")
    set_para("mcomment",
             f"8月呈现\"增速换挡、结构上移\"特征:收入环比{pct(ov['mom']['rev'],1,True)}为年内首次回落,全部由量效应贡献(销量环比{pct(ov['mom']['qty'],1,True)}),"
             f"均价环比上升;毛利率{pct(ov['cur']['m'],2)}环比{ppct(ov['mom']['m'],2)},同比缺口{ppct(ov['yoy']['m'])}的主因从\"以价换量\"转向\"大客户结构性亏损\"。"
             f"1-8月累计收入{ov['ytd']['rev']/1e4:,.1f}万元(同比+{ov['ytdd']['rev']*100:.1f}%),利润{ov['ytd']['pft']/1e4:,.1f}万元(同比+{ov['ytdd']['pft']*100:.1f}%),"
             f"毛利率{pct(ov['ytd']['m'],2)}(同比{ppct(ov['ytdd']['m'])})。")

    # ===== B 2.1 =====
    set_para("s21", "2.1 7月报告行动项跟踪(8月回检)", None)
    set_para("s21intro", "7月报告行动项8月回检:成本整改初见成效,客户专项恶化,整体落地仍不足。",
             "跟踪对象由H1行动项更换为7月报告行动项(H1节点已过,经用户确认)。")
    act_rows = [
        ["7月报告行动项", "7月时状态", "8月现状", "判定"],
        ["立即整改/停售负毛利型号(STI3452HFI)", "7月亏损-98万", f"8月亏损收窄至{sti['pft_m']}万(收入{sti['rev_m']:,.0f}万),但仍在售", "未落地(收窄)"],
        ["DCDC-18V品类限价/提价+成本整改", "成本效应-58万,品类毛利率2.8%", f"成本效应收窄至-9万;品类8月毛利率{pct(RD['dcdc18']['m_m'],1)}", "初步见效"],
        ["中兴康讯/存储客户结构转型", "客户毛利率-3.0%", f"毛利率恶化至{zt['YTD利润万']/zt['YTD收入万']*100:.1f}%,YTD亏损{zt['YTD利润万']:,.0f}万", "恶化(本月专项)"],
        ["结构升级:高毛利新品推广", "新品占比15.7%", f"8月新品占比{pct(newp['share_m'],1)},价效应转正(+{cm['价']}万)", "见效(初步)"],
        ["挽回追觅/小米等大客户", "追觅7月仅14万", "追觅8月13.5万,连续两月低位", "未落地"],
    ]
    for ri, row in enumerate(act_rows, 1):
        for ci, v in enumerate(row, 1):
            set_cell(2, ri, ci, v)
    table_comment(2, "跟踪项更换为7月报告行动项;8月现状来自底表(9-成本监控/26-成本上升/3-客户分类);\"判定\"为数据推断,业务执行状态见待确认清单。")
    p22 = P("s22")
    if p22:
        nf = ("本月新发现的主要问题:\r"
              "① KA大客户利润同比零增长:1-8月KA利润5,376万(去年同期5,383万),而KA收入同比+20%;增量利润全部来自MM类(+3,145万)。\r"
              "② 中兴康讯由盈转亏:YTD收入2,260万(同比+72%)但利润-126万(去年同期+207万),亏损集中于DCDC-18V品类(占86%)。\r"
              "③ 环比量效应年内最弱:8月量效应-436万,收入环比-11%全部由销量下降贡献,需甄别需求走弱还是7月抢单透支。\r"
              "④ 成本上升品类换血:DCDC-18V成本效应-58万→-9万,但车规H桥栅驱(-11万)、LDO通用(-10万)新上榜。\r"
              "⑤ 音频功放(7.4%)、电脑&计算(-2.3%)毛利率异常,体量小但趋势需关注。\r")
        with_retry(lambda: p22.Range.InsertBefore(nf))
        with_retry(lambda: p22.Range.Comments.Add(p22.Range.Duplicate, "【新增分析】8月数据识别的新问题(数据底表:3-客户分类/R-报告补充R1/R3/26-成本上升品类)。"))
        LOG.append("[OK] 新发现问题概览插入")

    # ===== C 2.2 =====
    set_para("s22intro",
             f"新品收入占比升至{pct(newp['share_m'],1)}(8月{newp['rev_m']:,.0f}万,新品毛利率{pct(newp['m_m'],1)});"
             f"1-8月{bands[-1][1]}个新品SKU中{bands[4][1]}个负毛利(收入{band5_rev:,.0f}万),剔除后新品加权毛利率约{pct(excl_m,1)}"
             f"(整体{pct(newp['m_y'],1)})。新品\"量利齐升\"但负毛利尾部仍在。")
    for ri, b in enumerate(bands[:5], 2):
        set_cell(3, ri, 2, int(b[1]))
        set_cell(3, ri, 3, pct(float(b[2]), 1) if b[2] not in ("", None) else "")
        set_cell(3, ri, 4, pct(float(b[3]), 1) if b[3] not in ("", None) else "")
    table_comment(3, "新品分档更新为1-8月YTD(数据底表:2b-新品分档;新品SKU口径:YTD新品收入>0)。")
    kan = SUP["KA新增SKU品类TOP"][:4]
    kan_s = "、".join(f"{k['品类']}({k['收入万']}万/{k['SKU数']}个SKU)" for k in kan)
    set_para("s22dir", f"KA客户新增SKU(近12月)主要落在{kan_s}等高毛利品类;DCDC-18V品类新增SKU多但创收弱。新品推广继续向高毛利品类聚焦。")

    # ===== D 表4 案例 =====
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

    # ===== E 毛利桥 =====
    set_para("bridge_yoy",
             f"同比({ncy[0]}个可比SKU,覆盖率{pct(ncy[0]/ncy[1],0)}):量+{cy['量']}万、价{cy['价']}万、成本{cy['成本']}万、结构+{cy['结构']}万,可比毛利净变动{cy['dGP']}万;"
             f"可比自身毛利率{cy['m0']*100:.2f}%→{cy['m1']*100:.2f}%({ppct(cy['m1']-cy['m0'])})。同比缺口主因是价效应拖累,结构效应形成对冲。",
             "毛利桥改为四因子口径(量/结构/价/成本,四项之和恒等于可比ΔGP);原附件口径脚本未存档且内部不自洽,经确认采用本口径(数据底表:R-报告补充R1)。")
    set_para("bridge_mom",
             f"环比({ncm[0]}个可比SKU,覆盖率{pct(ncm[0]/ncm[1],0)}):量{cm['量']}万、价+{cm['价']}万、成本+{cm['成本']}万、结构+{cm['结构']}万,可比毛利净变动{cm['dGP']}万;"
             f"可比毛利率{cm['m0']*100:.2f}%→{cm['m1']*100:.2f}%。收入环比下滑全部由量效应贡献;结构效应+{cm['结构']}万为年内最大,价效应全年首次转正——掉量不掉价、结构显著上移。")
    set_cell(5, 2, 1, "同比(8月vs去年8月)")
    set_cell(5, 2, 2, f"+{cy['量']}"); set_cell(5, 2, 3, f"{cy['价']}"); set_cell(5, 2, 4, f"{cy['成本']}")
    set_cell(5, 2, 5, f"+{cy['结构']}")
    set_cell(5, 2, 6, f"{cy['m0']*100:.2f}%→{cy['m1']*100:.2f}%")
    set_cell(5, 3, 1, "环比(8月vs7月)")
    set_cell(5, 3, 2, f"{cm['量']}"); set_cell(5, 3, 3, f"+{cm['价']}"); set_cell(5, 3, 4, f"+{cm['成本']}")
    set_cell(5, 3, 5, f"+{cm['结构']}")
    set_cell(5, 3, 6, f"{cm['m0']*100:.2f}%→{cm['m1']*100:.2f}%")
    table_comment(5, "四因子:量=ΔQ×基准单位毛利;结构=Σq1×基准UM−Q1×基准平均UM;价=Σq1×Δ单价;成本=Σq1×(基准UC−本期UC)。数据底表:R-报告补充R1。")
    cu = RD["cost_up"]
    cu_notes = {"车规H桥栅极驱动-单路/多路": "新上榜,车规导入期成本波动", "LDO通用/双通道": "新上榜,通用器件竞争压价",
                "DCDC-18V-降压2~4A": "上月-58万→-9万,整改见效", "H桥BDC-高压36V以上<3A": "小幅", "LED驱动-降压中低压": "小幅"}
    for ri, row in enumerate(cu[:7], 2):
        set_cell(6, ri, 1, row[0]); set_cell(6, ri, 2, row[1]); set_cell(6, ri, 3, row[2])
        set_cell(6, ri, 4, cu_notes.get(row[0], ""))
    set_para("cost_intro",
             f"{ncm[0]}个可比SKU中,8月环比成本效应合计+{cm['成本']}万(基本平衡),较7月(-66万)明显改善;"
             f"DCDC-18V-降压2~4A成本效应由-58万收窄至-9万;新上榜:车规H桥栅驱(-11万)、LDO通用(-10万)。")
    set_para("cost_key", "关键结论:成本端压力显著缓解,DCDC-18V限价/整改初见成效;警惕车规、LDO等新品类接力出现成本上升,纳入下月重点监控。")
    ucchg = (sti["uc_m"] / sti["uc_prev"] - 1) if sti["uc_prev"] else 0
    set_cell(7, 2, 3, f"{sti['pft_m']}")
    set_cell(7, 2, 4, f"{ucchg*100:+.1f}%")
    set_cell(7, 2, 5, f"{sti['rev_m']:,.0f}")
    set_para("sti_key", f"该单品:STI3452HFI 8月亏损收窄至{sti['pft_m']}万(7月-98万),单位成本环比{ucchg*100:+.1f}%,毛利率仍为{sti['m_m']*100:.1f}%。停售执行状态见待确认清单。")
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
    table_comment(8, "月度序列按四因子口径重算(每月vs上月,1月为vs2025年12月)。数据底表:R-报告补充R2。")
    set_para("struct_series",
             f"结构效应2-8月连续为正且8月(+{cm['结构']}万)为年内最大,是毛利率的核心稳定器;价效应持续为负但8月转正(+{cm['价']}万);"
             f"量效应2月/5月/8月为负,8月最弱。综合毛利率8月{pct(ov['cur']['m'],2)}环比回升,呈企稳迹象。")

    # ===== F 3.2/3.3/3.4/3.5/3.6/3.7 =====
    for ri, p in enumerate(pl_sorted, 2):
        set_cell(9, ri, 1, f"{p['name']}(8月)")
        set_cell(9, ri, 2, f"{p['rev万']:,.0f}"); set_cell(9, ri, 3, f"{p['share']*100:.1f}")
        set_cell(9, ri, 4, pct(p["m"], 1) if p["m"] not in ("", None) else "")
        set_cell(9, ri, 5, pct(p["m_ly"], 1) if p["m_ly"] not in ("", None) else "")
        dm = p["dm"] if p["dm"] not in ("", None) else 0
        set_cell(9, ri, 6, f"{dm*100:+.1f}pct")
    table_comment(9, "产品线表更新为8月口径,按8月收入降序(数据底表:2-产品线)。")
    set_para("pl_key",
             f"通用电源管理占8月收入{pl_sorted[0]['share']*100:.1f}%,毛利率{pct(pl_sorted[0]['m'],1)}(同比{pl_sorted[0]['dm']*100:+.1f}个百分点),仍为整体毛利率最大拖累;"
             f"有刷直流电机驱动毛利率{pct(pl_sorted[1]['m'],1)}稳中有升;音频功放(7.4%)、电脑&计算(-2.3%)毛利率异常偏低,体量小但需关注。")
    for ri, c in enumerate(["KA", "AA", "KM", "MM"], 2):
        v = cls[c]
        set_cell(10, ri, 1, f"{c}({'重点' if c == 'KA' else ''})")
        set_cell(10, ri, 2, f"{v['rev_y']/1e4:,.0f}")
        set_cell(10, ri, 3, pct(v["m_y"], 1))
        set_cell(10, ri, 4, pct(v["m_ly_y"], 1) if v["m_ly_y"] else "")
        set_cell(10, ri, 5, f"{v['dpft']/1e4:+,.0f}万" if abs(v["dpft"]) > 50000 else "基本持平")
    table_comment(10, "客户分类更新为1-8月YTD(数据底表:3-客户分类;去年YTD毛利率由镜像按类别前缀计算)。")
    drag = SUP["KA利润拖累TOP"][:3]
    lift = SUP["KA利润提升TOP"][:3]
    set_para("cls_key",
             f"1-8月增量利润(万元)93%来自MM类(+3,145万);KA类利润同比持平(-7万)——收入+20%但利润零增长;"
             f"AA(+180万)、KM(+54万)微增。KA零增长主因:追觅(-505万)、中兴康讯(-333万)、小米集团(-222万);对冲:石头(+331万)、海康(+323万)。")
    set_para("cls_key2",
             f"重点客户:中兴康讯YTD毛利{zt['YTD利润万']/zt['YTD收入万']*100:.1f}%(转亏,见专项);追觅收入-19%且8月仅13.5万;"
             f"石头(同比+{(top20[0][4]/ (top20[0][2]-top20[0][4]) if top20[0][4] else 0)*100:.0f}%量级)、海康(+116%)高增。")
    # 表11: 中兴 + 其他重点客户
    set_cell(11, 2, 1, "中兴康讯"); set_cell(11, 2, 2, f"{zt['YTD收入万']:,.0f}")
    set_cell(11, 2, 3, f"{zt['YTD利润万']/zt['YTD收入万']*100:.1f}%")
    set_cell(11, 2, 4, z[0]["品类"]); set_cell(11, 2, 5, f"{z[0]['占比']*100:.0f}%"); set_cell(11, 2, 6, pct(z[0]["毛利率"], 1))
    others = [("追觅", top20[2]), ("兆驰", top20[4]), ("共进", top20[6])]
    for k, (nm, row) in enumerate(others, 3):
        set_cell(11, k, 1, nm); set_cell(11, k, 2, f"{row[2]:,.0f}")
        set_cell(11, k, 3, pct(row[3], 1) if row[3] else "")
        set_cell(11, k, 4, "—"); set_cell(11, k, 5, "—"); set_cell(11, k, 6, "—")
    for k in range(len(others) + 3, JT[11]["rows"] + 1):
        for c in range(1, 7):
            set_cell(11, k, c, "")
    table_comment(11, "重点客户更新:中兴康讯(专项详见第四节)、追觅、兆驰、共进(数据底表:R-报告补充R3/4-前20大客户)。")
    for ri in range(2, 4):
        for ci in range(1, 10):
            v = sv[ri - 1][ci - 1] if ri - 1 < len(sv) else ""
            set_cell(14, ri, ci, int(v) if isinstance(v, float) and ci != 1 else v)
    table_comment(14, "SKU变化更新为近12月(2025-09~2026-08)vs前12月(数据底表:11-SKU变化)。")
    set_para("sv_concl",
             f"结论:KA+AA客户净增SKU {sv[0][4]:+,.0f}个(新增{sv[0][2]:.0f}、流失{sv[0][3]:.0f}),新增SKU贡献收入{sv[0][5]:,.0f}万、利润{sv[0][6]:,.0f}万;流失SKU流失收入{sv[0][7]:,.0f}万。")
    for ri, k in enumerate(SUP["KA新增SKU品类TOP"][:9], 2):
        set_cell(15, ri, 1, k["品类"]); set_cell(15, ri, 2, f"~{k['SKU数']}"); set_cell(15, ri, 3, k["收入万"]); set_cell(15, ri, 4, k["利润万"])
    set_para("ka_new",
             f"KA客户新增SKU主要来自H桥BDC-高压36V({SUP['KA新增SKU品类TOP'][0]['收入万']}万)、POE-PD二合一、DCDC-5V等高毛利品类,验证\"结构升级\"打法;DCDC-18V品类新增SKU多但创收弱。")
    zl_rows = RD["zengliu"]
    for ri, row in enumerate(zl_rows[:9], 2):
        for ci, v in enumerate(row[:10], 1):
            set_cell(16, ri, ci, int(v) if isinstance(v, float) and ci > 1 else v)
    for ri, row in enumerate(zl_rows[:7], 2):
        for ci, v in enumerate(row[:10], 1):
            set_cell(17, ri, ci, int(v) if isinstance(v, float) and ci > 1 else v)
    table_comment(16, "增加及流失更新为近12月vs前12月,按新增+流失降序(数据底表:增加及流失sheet,由VBA重算)。")
    for ri, d in enumerate(RD["dom_top"][:5], 2):
        set_cell(12, ri, 1, d["name"])
        set_cell(12, ri, 2, pct(d["m_jan"], 0)); set_cell(12, ri, 3, pct(d["m_cur"], 0) if d["m_cur"] else "—")
        set_cell(12, ri, 4, f"{d['dm']*100:+.1f}pct")
        set_cell(12, ri, 5, f"{d['rev_y']/1e4:,.0f}"); set_cell(12, ri, 6, pct(d["m_y"], 1))
    table_comment(12, "应用领域更新为1月vs8月毛利率与1-8月累计(数据底表:5-应用领域)。")
    set_para("dom_key",
             f"应用领域毛利率变化两极分化:网通(1月{pct(RD['dom_top'][0]['m_jan'],0)}→8月{pct(RD['dom_top'][0]['m_cur'],0)})仍为主要拖累;"
             f"安防、数码、充电头平稳或回升;安防新品渗透{pct(RD['dom_top'][1]['pen'],0)}为最高。")
    for ri, d in enumerate(RD["dom_new_top"][:5], 2):
        set_cell(13, ri, 1, d["name"]); set_cell(13, ri, 2, f"{d['newrev']/1e4:,.0f}")
        set_cell(13, ri, 3, f"{d['newrev']/d['rev_y']*100:.0f}%")
        set_cell(13, ri, 4, pct(d["newm"], 1) if d["newm"] else "")
        set_cell(13, ri, 5, pct(d["pen"], 1))
    set_para("dom_new",
             f"新品收入最强领域:安防({RD['dom_new_top'][0]['newrev']/1e4:,.0f}万)、网通({RD['dom_new_top'][1]['newrev']/1e4:,.0f}万);"
             f"数码新品毛利率{pct(RD['dom_new_top'][2]['newm'],0)}量级领先;视频显示新品渗透偏低。")
    c36 = RD.get("cases36", {})
    an = c36.get("安克创新", {}); cv = c36.get("CVTE", {})
    if an:
        set_para("case_anke", f"一是安克创新(结构升级标杆):1-8月收入{an.get('rev_y',0):,.0f}万,毛利率{pct(an.get('m_y'),1)}(去年{pct(an.get('m_l'),1)}),高毛利品类占比高。")
    if cv:
        set_para("case_cvte", f"二是CVTE(扭转型):1-8月毛利率{pct(cv.get('m_y'),1)}(去年{pct(cv.get('m_l'),1)}),压降低毛利品类占比后毛利修复。")
    set_para("exp_key", "可复制经验:客户毛利率修复的两条路径——引入高毛利品类(安克路径)或压降低毛利品类占比(CVTE路径);对中兴康讯应双管齐下(见专项)。")

    # ===== G 尾部手术: 四、五、六七八 整段删除重插 =====
    p4 = P("sec4")
    p5 = P("sec5")
    six = None
    for t, pp in paras.items():
        if t.startswith("六、"):
            six = pp
            break
    LOG.append(f"[INFO] sec4={resolved['sec4'][:20] if resolved['sec4'] else None} sec5={resolved['sec5'][:20] if resolved['sec5'] else None} six={'found' if six else 'None'}")
    if p4 and p5:
        # 删除 [四、末尾 .. 五、开头) 旧专项内容; [五、末尾 .. 文末) 行动+六七八
        r4end = p4.Range.End
        r5start = p5.Range.Start
        rng_del1 = doc.Range(r4end, r5start)
        with_retry(lambda: rng_del1.Delete())
        rng_del2 = doc.Range(p5.Range.End - 1, doc.Content.End)
        with_retry(lambda: rng_del2.Delete())
        LOG.append("[OK] 旧专项+行动建议+六七八 删除")
        # 在四、后插入新专项
        ins4 = doc.Range(r4end - 1, r4end - 1)
        zh = z
        ztxt = (f"中兴康讯——规模第二、毛利转负的结构性亏损\r"
                f"中兴康讯已成为公司YTD第二大客户(收入{zt['YTD收入万']:,.0f}万,同比+{(zt['YTD收入万']/zl['收入万']-1)*100:.0f}%),"
                f"但利润{zt['YTD利润万']:,.0f}万(去年同期+{zl['利润万']:,.0f}万),毛利率{zt['YTD利润万']/zt['YTD收入万']*100:.1f}%。\r"
                f"亏损完全集中于{zh[0]['品类']}品类:占其收入{zh[0]['占比']*100:.0f}%,毛利率{pct(zh[0]['毛利率'],1)},亏损{abs(zh[0]['利润万']):,.0f}万;"
                f"其余品类(LDO通用{zh[1]['收入万']}万/{pct(zh[1]['毛利率'],0)}、PSE{zh[2]['收入万']}万/{pct(zh[2]['毛利率'],0)}等)均为正毛利。\r"
                f"判断:这不是客户级亏损,而是单一品类结构性亏损——与STI3452HFI问题同源。建议:①该客户DCDC-18V存量型号统一限价/提价;②新品导入向PSE/LDO等正毛利品类倾斜;③整改无效则评估收缩该品类供货。\r")
        with_retry(lambda: ins4.InsertAfter(ztxt))
        with_retry(lambda: ins4.Comments.Add(ins4.Duplicate, "【结构变更】专项由\"追觅\"更换为\"中兴康讯\":追觅连续两月低位已并入3.3;8月最突出新问题为中兴康讯转亏(数据底表:R-报告补充R3)。"))
        # 在五、后插入压缩版行动建议
        ins5 = doc.Range(p5.Range.End - 1, p5.Range.End - 1)
        act_txt = ("按\"停售整改/客户专项/结构升级/成本监控\"四类压缩列示:\r")
        with_retry(lambda: ins5.InsertAfter(act_txt))
        tbl_rng = doc.Range(p5.Range.End - 1, p5.Range.End - 1)
        newtb = with_retry(lambda: doc.Tables.Add(tbl_rng, 5, 4))
        consolidated = [
            ["类型", "行动", "数据依据", "预期影响/前提"],
            ["A. 停售/整改负毛利", "立即停售STI3452HFI等负毛利型号", f"8月STI3452HFI亏{sti['pft_m']}万(收窄中)", "上月已列,需确认执行"],
            ["B. 中兴康讯专项", "DCDC-18V限价+新品导入向PSE/LDO倾斜", "YTD亏126万,86%集中于DCDC-18V", "客户配合度是关键"],
            ["C. 结构升级", "高毛利新品向安防/数码聚焦,KA新品推广延续", f"新品占比{pct(newp['share_m'],1)},价效应转正", "已见效,继续加码"],
            ["D. 成本监控", "车规H桥栅驱、LDO通用纳入重点监控", "成本效应-11万/-10万(新上榜)", "防接力式成本上升"],
        ]
        for ri, row in enumerate(consolidated, 1):
            for ci, v in enumerate(row, 1):
                with_retry(lambda ri=ri, ci=ci, v=v: newtb.Cell(ri, ci).Range.__setattr__("Text", v))
        with_retry(lambda: newtb.Range.Comments.Add(newtb.Range, "按确认要求压缩:原6类行动(表21-28)合并为4类,数据依据均为8月底表。"))
        LOG.append("[OK] 新专项+压缩行动建议 插入")
    # 尾部追加
    tailrng = doc.Range(doc.Content.End - 1, doc.Content.End - 1)
    source_txt = ("\r数据来源与口径说明\r"
                  "1. 数据底表:月度分析模板(\\\\192.168.8.3\\...\\分析报告-202608\\月度分析模板.xlsm)及更新副本(月度分析模板_8月报告副本.xlsx,新增R-报告补充)。\r"
                  "2. 数据期间:2024-01至2026-08;报告月=2026年8月;源数据=财务分析-8月(9.5).xlsx 24-26表(206,899行,截至2026-08-31)。\r"
                  "3. 口径:CRM口径、人民币、不含税;收入=RMB未税金额小计;利润=利润列;销量=发货数量(颗);毛利率=利润/收入。\r"
                  "4. 同比/环比为自然月窗口;YTD=1月至本月;客户分类KA/AA/KM/MM按客户类别前缀;新品=是否新品\"是\"。\r"
                  "5. 毛利桥为四因子口径(量/结构/价/成本),在两期均有销售的SKU集合计算;月度序列每月vs上月(1月vs2025年12月)。\r"
                  "6. SKU变化窗口:近12月(2025-09~2026-08)vs前12月(2024-09~2025-08)。\r"
                  "7. 副本补充数据(R-报告补充)的计算逻辑已在副本内注明。\r")
    with_retry(lambda: tailrng.InsertAfter(source_txt))
    tailrng2 = doc.Range(doc.Content.End - 1, doc.Content.End - 1)
    todo_txt = ("\r待确认问题清单\r"
                "1. 追觅8月13.5万的业务背景(项目暂停/换代/份额流失)。\r"
                "2. STI3452HFI停售决策执行状态(8月仍在售,亏损收窄至-76万)。\r"
                "3. 2.1表\"判定\"列为数据推断,业务实际执行需责任部门确认。\r"
                "4. 中兴康讯限价谈判可行性(客户配合度)需销售确认。\r"
                "5. 原第六~八节(活跃SKU/库存/风险展望)按确认删除,如需恢复请提供8月数据。\r"
                "6. 环比-11%的量效应归因(需求走弱vs7月抢单透支)建议结合订单数据人工判断。\r")
    with_retry(lambda: tailrng2.InsertAfter(todo_txt))
    ptd = None
    for t, pp in paras.items():
        if t.startswith("待确认问题清单"):
            ptd = pp
            break
    LOG.append("[OK] 口径说明+待确认清单")

    nrev = with_retry(lambda: doc.Revisions.Count)
    ncom = with_retry(lambda: doc.Comments.Count)
    with_retry(lambda: doc.SaveAs2(FINAL, FileFormat=16))
    with_retry(lambda: doc.Close(False))
    LOG.append(f"[DONE] 修订数={nrev} 批注数={ncom}")
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\draft2_log.txt", "w", encoding="utf-8").write("\n".join(LOG))
print("DRAFT2_DONE")
