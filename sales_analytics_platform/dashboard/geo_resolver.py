# -*- coding: utf-8 -*-
"""地域解析器（A面地域分布）——发货地址 → (region, sub, abroad)。

纯函数：resolve_region(address) 依据 geo_dict.json 字典配置解析，
代码零地址词（全部规则数据在字典配置内）。规则清单源自两轮探数
（addr_step3_parse_agg / geo_deep_dive，2026-09-07，17 条残余全断言）。

返回语义：
    region : 省级行政区短名（如 "广东"）/"台湾"/"香港"/"澳门"/"韩国"/其他国家名/"海外"/"未识别"
    sub    : 市级/区域（如 "深圳"/"新北市"/"新界"/"仁川"）；无则空串
    abroad : 台湾/香港/澳门/海外 为 True（含港澳台口径与海外合并展示时用）
"""

import json
import os
import re

_DICT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "geo_dict.json")
_CACHE: dict | None = None

# 大陆省级（34）短名——abroad 判定用（港澳台不在此列）
_MAINLAND = {
    "北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江", "上海", "江苏",
    "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南", "广东", "广西",
    "海南", "重庆", "四川", "贵州", "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆",
}


def load_dict(path: str | None = None) -> dict:
    """加载字典配置（默认 geo_dict.json 同目录）；进程内缓存。"""
    global _CACHE
    p = path or _DICT_PATH
    if _CACHE is None or path is not None:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        if path is None:
            _CACHE = d
        return d
    return _CACHE


def _clean(text: str, d: dict) -> str:
    """去伪前缀（停用-/作废-/OLD-）与"中国"前缀，去首尾空白。"""
    t = text.strip()
    for pre in d.get("strip_prefixes", []):
        if t.startswith(pre):
            t = t[len(pre):].strip()
    for w in d.get("strip_words", []):
        if t.startswith(w):
            t = t[len(w):].strip()
    return t


def _is_junk(t: str, d: dict) -> bool:
    if not t:
        return True
    if any(k in t for k in d.get("junk_keywords", [])):
        return True
    pat = d.get("junk_regex", "")
    return bool(pat and re.match(pat, t))


def _prov_from_prefix(t: str, d: dict) -> str | None:
    """行首直辖市/自治区/特别行政区全称 → 短名。"""
    for full in d.get("province_prefixes", []):
        if t.startswith(full):
            short = full
            for suf in d.get("province_suffix_strip", []):
                short = short.replace(suf, "")
            return short
    return None


def _prov_from_regex(t: str, d: dict) -> str | None:
    """行首『XX省』→ 短名。"""
    pat = d.get("province_regex_short", "")
    if not pat:
        return None
    m = re.match(pat, t)
    return m.group(1)[:-1] if m else None


def _prov_anywhere(t: str, d: dict) -> str | None:
    """任意位置含省名 → 短名（配置序即优先级，长名先于短名）。"""
    for p in d.get("provinces_anywhere", []):
        if p in t:
            return p
    return None


def _city_of(t: str, region: str, d: dict) -> str:
    """在省内地级市表中找首个命中城市（先长后短），返回带'市'显示名。"""
    cands = sorted(
        ((c, p) for c, p in d.get("city_to_province", {}).items() if p == region),
        key=lambda kv: -len(kv[0]),
    )
    for city, _ in cands:
        if t.startswith(city) or (city + "市") in t:
            return city + "市"
        # 省名紧接市名形态（"广东深圳宝安区…"——省名后漏写市名）
        if re.search(re.escape(region) + r"省?" + re.escape(city), t):
            return city + "市"
    return ""


def _kw_hit(t: str, mapping: dict, *, head_only: bool = False) -> str | None:
    """子串命中映射表（key→value），返回首个命中的 value；head_only 只认行首。"""
    for k in sorted(mapping, key=len, reverse=True):
        if head_only:
            if t.startswith(k):
                return mapping[k]
        elif k in t:
            return mapping[k]
    return None


def resolve_region(address: object, d: dict | None = None) -> tuple[str, str, bool]:
    """解析发货地址 → (region, sub, abroad)。空/脏/不可识别 → ("未识别", "", False)。"""
    dd = d if d is not None else load_dict()
    if address is None:
        return ("未识别", "", False)
    t = _clean(str(address), dd)
    if _is_junk(t, dd):
        return ("未识别", "", False)

    # 1) FOB 贸易术语特例（FOB深圳机场 → 深圳，实发地）
    for rule in dd.get("fob_city_overrides", []):
        keys = rule.get("match", [])
        if keys and all(k in t for k in keys):
            return (rule.get("region", "未识别"), rule.get("city", ""), False)

    # 2) 大陆省：行首全称/行首『XX省』/任意位置省名
    region = _prov_from_prefix(t, dd) or _prov_from_regex(t, dd) or _prov_anywhere(t, dd)
    if region in _MAINLAND:
        sub = _city_of(t, region, dd)
        if sub == region + "市":  # 直辖市自身（北京市→sub 留空，避免 上海·上海市）
            sub = ""
        return (region, sub, False)

    # 3) 深圳区名救回（福田区/宝安区… 漏写市名）
    for dist in dd.get("shenzhen_districts", []):
        if t.startswith(dist):
            return ("广东", "深圳市", False)

    # 4) 地级市 → 省（行首或含『XX市』）
    for city in sorted(dd.get("city_to_province", {}), key=len, reverse=True):
        prov = dd["city_to_province"][city]
        if t.startswith(city) or (city + "市") in t:
            return (prov, "" if prov == city else city + "市", False)

    # 5) 台湾（繁体市级 + 邮编形态）
    sub = _kw_hit(t, dd.get("taiwan_cities", {}))
    if sub is not None:
        return ("台湾", sub, True)
    pat = dd.get("taiwan_postal_regex", "")
    if pat and re.match(pat, t):
        return ("台湾", "", True)

    # 6) 香港（区域表 + 英文形态）
    sub = _kw_hit(t, dd.get("hk_regions", {}))
    if sub is not None:
        return ("香港", sub, True)
    pat = dd.get("hk_company_regex", "")
    if pat and re.search(pat, t, re.IGNORECASE):
        return ("香港", "", True)

    # 7) 澳门
    if any(k in t for k in dd.get("macau_keywords", [])):
        return ("澳门", "", True)

    # 8) 韩国（英文/韩文城市表）
    sub = _kw_hit(t, dd.get("korea_cities", {}))
    if sub is not None:
        return ("韩国", sub, True)

    # 9) 公司名当地址（翔亿科技→台湾均德 等）
    for kw, (region_c, sub_c) in dd.get("company_to_region", {}).items():
        if kw in t:
            return (region_c, sub_c, True)

    # 10) 其他国家（英文国名词表）
    sub = _kw_hit(t, dd.get("overseas_countries", {}))
    if sub is not None:
        return (sub, "", True)

    # 11) 其余含外文 → 海外兜底
    if re.search(r"[A-Za-z]{4,}", t):
        return ("海外", "", True)

    return ("未识别", "", False)


def short_to_full_province(short: str, d: dict | None = None) -> str:
    """短省名 → GeoJSON 全称（北京市/内蒙古自治区/台湾省…）；未知原样返回。"""
    dd = d if d is not None else load_dict()
    fn = dd.get("full_name_suffix", {})
    if short in fn.get("municipalities", []):
        return short + "市"
    if short in fn.get("autonomous", {}):
        return fn["autonomous"][short]
    if short in fn.get("special", {}):
        return fn["special"][short]
    if short in _MAINLAND:
        return short + "省"
    return short
