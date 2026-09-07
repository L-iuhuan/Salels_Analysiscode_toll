# -*- coding: utf-8 -*-
"""geo_resolver 单测：≥12 用例，含两轮探数残余 17 条唯一地址全量断言。

期望值来源：geo_deep_dive.py 探数输出（geo_output.txt，2026-09-07），
每条残余地址的归类经人工核对（韩国=终端工厂直发、香港=贸易商等性质
判断不进 resolver，本处只断言地理位置三元组）。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dashboard"))

from geo_resolver import load_dict, resolve_region, short_to_full_province  # noqa: E402

D = load_dict()

# ---- 探数残余 17 条唯一地址全量断言（addr/geo 两轮探数，收入降序）----
RESIDUAL_17 = [
    # (地址, 期望 region, 期望 sub, 期望 abroad)
    ("#402-#403, 583, Neungheodae-ro, Namdong-gu, Incheon, South Korea", "韩国", "仁川", True),
    ("福田区益田南路3013号南方国际广场B座312-313室", "广东", "深圳市", False),
    ("FOB深圳机场", "广东", "深圳市", False),
    ("Guro-Dong, Daeryung Post Tower 2, #908, Digital-ro 306, Guro-Gu, Seoul", "韩国", "首尔", True),
    ("23511新北市中和區中正路736號9樓之7", "台湾", "新北市", True),
    ("", "未识别", "", False),
    ("Lot No. 1812 SB.RP, Demarcation District 125, Ping Ha Road,Ha Tsuen, Yuen Long, NT HongKong",
     "香港", "新界", True),
    ("23145 新北市新店區寶橋路235巷129號8樓", "台湾", "新北市", True),
    ("测试", "未识别", "", False),
    ("福田区深南大道2001号嘉麟豪庭C座2303室", "广东", "深圳市", False),
    ("荃灣白田霸街5 －21號嘉力工業大廈A座5樓15室", "香港", "新界", True),
    ("宝安区留仙二路中粮商务公园1107", "广东", "深圳市", False),
    ("新店寶橋路235巷123-2號1樓", "台湾", "新北市", True),
    ("EZ RAM TECHNOLOGY LTD./ 翔亿科技股份有限公司", "台湾", "", True),
    ("请补充", "未识别", "", False),
    ("葵涌A11-1F电子仓", "香港", "新界", True),
    ("18934606766", "未识别", "", False),
]


@pytest.mark.parametrize("addr,region,sub,abroad", RESIDUAL_17, ids=[f"res{i+1}" for i in range(17)])
def test_residual_17(addr: str, region: str, sub: str, abroad: bool) -> None:
    """17 条残余地址全量断言（探数 geo_output.txt 期望值）。"""
    assert resolve_region(addr, D) == (region, sub, abroad)


# ---- 大陆常规地址 ----
@pytest.mark.parametrize("addr,region,sub", [
    ("广东省惠州市惠阳区三和经济开发区三和街道京东物流园13号仓1楼", "广东", "惠州市"),
    ("深圳市宝安区西乡街道固兴社区南太路2号南太工业园厂房3栋2层201号", "广东", "深圳市"),
    ("上海上海市浦东新区祝桥镇金亮路11号贵安物流园二库中太仓库", "上海", ""),
    ("北京市海淀区中关村大街1号", "北京", ""),
    ("浙江省杭州市滨江区长河街道越达巷82号", "浙江", "杭州市"),
    ("江苏省苏州市工业园区星湖街328号", "江苏", "苏州市"),
    ("陕西省西安市高新区锦业路69号", "陕西", "西安市"),
    ("福建省厦门市思明区软件园二期", "福建", "厦门市"),
])
def test_mainland(addr: str, region: str, sub: str) -> None:
    assert resolve_region(addr, D) == (region, sub, False)


# ---- 清洗规则 ----
@pytest.mark.parametrize("addr,region,sub", [
    ("停用-广东省深圳市南山区科技园1号", "广东", "深圳市"),   # 停用- 前缀剥离
    ("中国广东深圳宝安区某工业园", "广东", "深圳市"),          # "中国"前缀剥离
    ("内蒙古自治区呼和浩特市赛罕区", "内蒙古", "呼和浩特市"),
    ("广西壮族自治区南宁市青秀区", "广西", "南宁市"),
])
def test_clean_and_autonomous(addr: str, region: str, sub: str) -> None:
    assert resolve_region(addr, D) == (region, sub, False)


# ---- 港澳台/海外 ----
@pytest.mark.parametrize("addr,region,sub,abroad", [
    ("香港新界元朗新田嘉龍路小磡村10號", "香港", "新界", True),
    ("香港九龍尖沙咀彌敦道100號", "香港", "九龙", True),
    ("澳門氹仔偉龍馬路某中心", "澳门", "", True),
    ("台湾省高雄市前镇区中华五路", "台湾", "高雄市", True),
    ("1-1-1 Chiyoda, Tokyo, Japan", "日本", "", True),
    ("Block 80, Jurong East, Singapore 609930", "新加坡", "", True),
])
def test_hmt_overseas(addr: str, region: str, sub: str, abroad: bool) -> None:
    assert resolve_region(addr, D) == (region, sub, abroad)


# ---- 边界 ----
@pytest.mark.parametrize("addr", ["None", "nan", "-", "无", None])
def test_junk_variants(addr: object) -> None:
    assert resolve_region(addr, D) == ("未识别", "", False)


def test_unknown_chinese_addr() -> None:
    """不含任何字典线索的中文地址 → 未识别（不臆断）。"""
    assert resolve_region("幸福大街1号院2号楼", D) == ("未识别", "", False)


def test_pure_english_unknown_country() -> None:
    """外文地址但国名不在词表 → 海外兜底。"""
    assert resolve_region("12 Abbey Road, Bootle, Merseyside", D) == ("海外", "", True)


def test_fob_shenzhen_airport() -> None:
    """FOB 深圳机场 → 深圳（贸易术语特例，实发地）。"""
    assert resolve_region("FOB深圳机场", D) == ("广东", "深圳市", False)


# ---- short_to_full_province（地图 nameMap 兜底用）----
@pytest.mark.parametrize("short,full", [
    ("广东", "广东省"), ("北京", "北京市"), ("内蒙古", "内蒙古自治区"),
    ("广西", "广西壮族自治区"), ("香港", "香港特别行政区"),
    ("澳门", "澳门特别行政区"), ("台湾", "台湾省"), ("未知", "未知"),
])
def test_full_name(short: str, full: str) -> None:
    assert short_to_full_province(short, D) == full


def test_dict_has_no_empty_tables() -> None:
    """字典配置健全性：关键表非空。"""
    for key in ("city_to_province", "provinces_anywhere", "taiwan_cities",
                "hk_regions", "korea_cities", "overseas_countries"):
        assert D.get(key), f"字典表为空: {key}"
