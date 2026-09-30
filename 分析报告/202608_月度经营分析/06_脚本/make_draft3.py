# -*- coding: utf-8 -*-
r"""draft3 补丁：修 9 个未命中段落 + 四、标题改写（在v2修订基础上继续）"""
import json
import shutil
import time
import pythoncom
import pywintypes
import win32com.client as win32

FINAL = r"E:\3-其他资料\数据分析\2026年8月销售经营分析报告_草稿(修订版).docx"
RD = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\report_data.json", encoding="utf-8"))
SUP = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\supplement.json", encoding="utf-8"))

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

ov = RD["ov"]; cm = SUP["桥_环比"]; sti = RD["sti"]; newp = RD["newp"]
bands = RD["bands"]; zt = SUP["中兴康讯_合计"]; sv = RD["sku_var"]
band5_rev = newp["rev_y"] * 0.0454
band5_pft = band5_rev * (-0.1214)
excl_m = (newp["rev_y"] * newp["m_y"] - band5_pft) / (newp["rev_y"] - band5_rev)

FIX = [
    ("2.1 整改完成情况",
     "2.1 7月报告行动项跟踪(8月回检)",
     "跟踪对象由H1行动项更换为7月报告行动项(H1节点已过,经用户确认)。"),
    ("H1报告整改项逐条核查",
     "7月报告行动项8月回检:成本整改初见成效,客户专项恶化,整体落地仍不足。",
     None),
    ("新品整体仍在托底",
     (f"新品收入占比升至{pct(newp['share_m'],1)}(8月{newp['rev_m']:,.0f}万,新品毛利率{pct(newp['m_m'],1)});"
      f"1-8月{bands[-1][1]}个新品SKU中{bands[4][1]}个负毛利(收入约{band5_rev:,.0f}万),剔除后新品加权毛利率约{pct(excl_m,1)}"
      f"(整体{pct(newp['m_y'],1)})。新品\"量利齐升\"但负毛利尾部仍在(数据底表:2b-新品分档/8-新品)。"),
     None),
    ("低毛利品类新品推广",
     (f"KA客户新增SKU(近12月)主要落在H桥BDC-高压36V({SUP['KA新增SKU品类TOP'][0]['收入万']}万)、POE-PD二合一、DCDC-5V等高毛利品类,"
      f"推广方向与\"结构升级\"一致;DCDC-18V品类新增SKU多但创收弱,新品投放应继续向高毛利品类聚焦(数据底表:R-报告补充R4)。"),
     None),
    ("关键发现:成本上升几乎全部",
     (f"关键发现:成本端压力显著缓解——DCDC-18V-降压2~4A成本效应由上月-58万(占比88%)收窄至-9万,品类8月毛利率{pct(RD['dcdc18']['m_m'],1)}环比改善;"
      f"新上榜为车规H桥栅驱(-11万)、LDO通用(-10万),呈\"接力式\",需纳入下月重点监控(数据底表:26-成本上升品类)。"),
     None),
    ("最大单品:STI3452HFI",
     (f"最大单品:STI3452HFI 8月亏损收窄至{sti['pft_m']}万(7月-98万,8月收入{sti['rev_m']:,.0f}万),单位成本环比{(sti['uc_m']/sti['uc_prev']-1)*100:+.1f}%,"
      f"毛利率仍为{sti['m_m']*100:.1f}%。\"负毛利+成本问题\"未根除,停售决策执行状态见待确认清单(数据底表:9-成本监控)。"),
     None),
    ("结构真正改善仅在3月",
     (f"结构效应2-8月连续为正且8月(+{cm['结构']}万)为年内最大,是毛利率的核心稳定器;价效应此前持续为负,8月首次转正(+{cm['价']}万);"
      f"量效应2月/5月/8月为负,8月最弱。综合毛利率8月{pct(ov['cur']['m'],2)}环比回升,呈企稳迹象(数据底表:R-报告补充R2)。"),
     None),
    ("应用领域毛利变化过程分化",
     (f"应用领域毛利变化两极分化:网通(1月{pct(RD['dom_top'][0]['m_jan'],0)}→8月{pct(RD['dom_top'][0]['m_cur'],0)})仍是主要拖累;"
      f"安防、数码平稳,充电头回升;安防新品渗透{pct(RD['dom_top'][1]['pen'],0)}最高。资源继续从网通向智能清洁、充电头、数码倾斜(数据底表:5-应用领域)。"),
     None),
    ("结论:KA+AA客户整体SKU净增加",
     (f"结论:KA+AA客户净增SKU {sv[0][4]:+,.0f}个(新增{sv[0][2]:.0f}、流失{sv[0][3]:.0f}),新增SKU贡献收入{sv[0][5]:,.0f}万、利润{sv[0][6]:,.0f}万,"
      f"流失SKU损失收入{sv[0][7]:,.0f}万,SKU变化对收入/利润仍为正向贡献(数据底表:11-SKU变化)。"),
     None),
    ("四、从SKU变化透视",
     "四、专项:中兴康讯——规模第二、毛利转负的结构性亏损",
     "【结构变更】专项由\"追觅\"更换为\"中兴康讯\":追觅连续两月低位已并入3.3客户分析;8月最突出的新问题是中兴康讯转亏(数据底表:R-报告补充R3)。"),
]

LOG = []
pythoncom.CoInitialize()
word = None
try:
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = with_retry(lambda: word.Documents.Open(FINAL))
    with_retry(lambda: doc.__setattr__("TrackRevisions", True))
    for fuzzy, new_text, comment in FIX:
        found = with_retry(lambda: doc.Content.Find)
        f = doc.Content.Find
        with_retry(lambda: f.__setattr__("Text", fuzzy[:60]))
        with_retry(lambda: f.__setattr__("Forward", True))
        with_retry(lambda: f.__setattr__("Wrap", 1))
        ok = with_retry(lambda: f.Execute())
        if not ok:
            LOG.append(f"[MISS] {fuzzy[:30]}")
            continue
        rng = f.Parent
        # 扩展到整段
        para = rng.Paragraphs(1)
        with_retry(lambda: para.Range.__setattr__("Text", new_text + "\r"))
        if comment:
            with_retry(lambda: para.Range.Comments.Add(para.Range.Duplicate, comment))
        LOG.append(f"[OK] {new_text[:32]}")
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

open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\draft3_log.txt", "w", encoding="utf-8").write("\n".join(LOG))
print("DRAFT3_DONE")
