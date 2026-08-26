"""
终端客户主数据加载与整合。

从 `data/所有的终端客户.xlsx` 加载 CRM 客户主数据，
通过公司名称匹配（精确 + 模糊回退）整合到客户全景画像。

整合字段（稀疏列已填充默认值）：
  - 客户类型、客户分级、TAM(万元)、细分市场、应用场景
  - 销售部门、FAE工程师、合作五档规模、注册资本、公司类型、客户状态
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.data_cleaning import read_excel_auto

# 列名映射（中文 → 英文程序名）
CUSTOMER_MASTER_COL_MAP = {
    "公司工商全称": "公司工商全称",
    "公司简称": "公司简称",
    "客户分级": "客户分级",
    "客户等级": "客户等级",
    "细分市场": "细分市场",
    "细分市场（新）": "细分市场_新",  # 全角括号匹配CRM实际列名
    "应用场景": "应用场景",
    "TAM(万元）": "TAM_万元",       # 全角右括号匹配CRM实际列名
    "合作五档规模": "合作五档规模",
    "交易状态": "交易状态",
    "客户状态": "客户状态",
    "销售部门": "销售部门",
    "FAE工程师": "FAE工程师",
    "代理商/直供": "代理商_直销",
    "注册资本": "注册资本",
    "公司类型": "公司类型",
    "ERP编号": "ERP编号",
    "最后时间": "最后时间",
    "最新时间": "最新时间",
    "拓尔销售": "拓尔销售",             # 新增：销售负责人
    "工商注册地址": "工商注册地址",       # 新增：终端地址→区域分析
    "代理商账号": "代理商账号",           # 新增：代理商名称
    "客户类型": "客户类型",              # 新增：客户类型分类
}

# 稀疏列默认值
SPARSE_DEFAULTS = {
    "客户分级": "未知",
    "客户等级": "未知",
    "客户类别": "未分类",
    "细分市场": "未知",
    "细分市场_新": "未知",
    "应用场景": "未分类",
    "TAM_万元": 0.0,
    "合作五档规模": "未分类",
    "交易状态": "未知",
    "客户状态": "未知",
    "销售部门": "未知",
    "FAE工程师": "未分配",
    "代理商_直销": "未知",
    "注册资本": 0.0,
    "公司类型": "未知",
    "拓尔销售": "未知",
    "工商注册地址": "未知",
    "代理商账号": "未知",
    "客户类型": "未知",
}


def load_customer_master(path: str = None) -> pd.DataFrame:
    """加载终端客户主数据文件。

    参数:
        path: 文件路径。None 时自动在 data/ 目录查找"所有的终端客户.xlsx"

    返回:
        DataFrame: 标准化列名的客户主数据（含匹配键）
    """
    if path is None:
        # [批次⑤ 缺陷A修复] data 目录统一用 config.settings.DATA_DIR（包根 data/）
        from config.settings import DATA_DIR
        data_dir = DATA_DIR
        target = "所有的终端客户.xlsx"
        path = os.path.join(data_dir, target)
        if not os.path.exists(path):
            xlsx_files = [f for f in os.listdir(data_dir) if "终端" in f and f.endswith(".xlsx")]
            if not xlsx_files:
                print("  [客户主数据] 未找到终端客户文件")
                return pd.DataFrame()
            path = os.path.join(data_dir, xlsx_files[0])

    print(f"  [客户主数据] 加载: {path}")
    raw = read_excel_auto(path, sheet_name=0)
    print(f"  [客户主数据] 原始行数: {len(raw)}, 列数: {len(raw.columns)}")

    # 前两列固定为 公司工商全称 和 公司简称
    raw_cols = list(raw.columns)
    df = pd.DataFrame()
    df["公司工商全称"] = raw[raw_cols[0]].astype(str).str.strip() if len(raw_cols) > 0 else ""
    df["公司简称"] = raw[raw_cols[1]].astype(str).str.strip() if len(raw_cols) > 1 else ""

    # 构建原始列名→标准名的映射（按列名中的关键字匹配）
    col_keywords = {
        "客户分级": ("客户分级",),
        "客户等级": ("客户等级",),
        "细分市场": ("细分市场（新）", "细分市场"),  # 全角括号匹配CRM实际列名
        "应用场景": ("应用场景",),
        "TAM_万元": ("TAM", "tam"),
        "合作五档规模": ("合作", "五档", "规模"),
        "交易状态": ("审核状态", "交易状态"),
        "客户状态": ("客户状态",),
        "销售部门": ("销售部门",),
        "FAE工程师": ("FAE", "工程师"),
        "代理商_直销": ("代理商/直供",),  # 修正：匹配CRM"代理商/直供"列
        "注册资本": ("注册资本",),
        "公司类型": ("公司类型",),
        "ERP编号": ("ERP编号", "编号"),
        "客户类别": ("客户类别",),
        "拓尔销售": ("拓尔销售",),            # 新增：销售负责人（终端客户表的销售员）
        "工商注册地址": ("工商注册地址",),      # 新增：终端地址→区域分析
        "代理商账号": ("代理商账号",),          # 新增：终端客户对应的代理商名称
        "客户类型": ("客户类型",),             # 新增：客户类型分类
    }

    for std_name, keywords in col_keywords.items():
        for rc in raw_cols:
            if any(kw in rc for kw in keywords):
                if std_name in df.columns:
                    df[std_name] = raw[rc]
                else:
                    df[std_name] = raw[rc]
                break

    # 填充稀疏列
    for col, default in SPARSE_DEFAULTS.items():
        if col in df.columns:
            df[col] = df[col].fillna(default)
        else:
            df[col] = default

    # 处理 TAM_万元（保留原始空值标记）
    if "TAM_万元" in df.columns:
        df["TAM_是否估算"] = pd.isna(df["TAM_万元"]) if df["TAM_万元"].dtype == float else False
        df["TAM_万元"] = pd.to_numeric(df["TAM_万元"], errors="coerce").fillna(0.0)

    print(f"  [客户主数据] 标准化完成: {len(df)} 行, {len(df.columns)} 列")
    return df


def enrich_customer_portrait(
    portrait_df: pd.DataFrame,
    master_df: pd.DataFrame,
) -> pd.DataFrame:
    """将终端客户主数据合并到客户全景画像。

    匹配策略（按优先级）:
      1. 公司工商全称 精确匹配
      2. 公司简称 精确匹配
      3. 模糊匹配（rapidfuzz.ratio > 85，如可用）

    参数:
        portrait_df: calc_customer_portrait() 输出的客户全景 DataFrame
        master_df: load_customer_master() 返回的客户主数据

    返回:
        DataFrame: 增加了终端客户信息的客户全景画像
    """
    if len(master_df) == 0:
        print("  [客户主数据] 主数据为空，跳过整合")
        return portrait_df

    result = portrait_df.copy()

    # 生成匹配键
    master = master_df.copy()
    master["_匹配键_全称"] = master["公司工商全称"].astype(str).str.strip().str.lower()
    master["_匹配键_简称"] = master["公司简称"].astype(str).str.strip().str.lower()

    # 客户编号（公司名）转为匹配键
    cust_key_col = "客户编号"
    if cust_key_col not in result.columns:
        print(f"  [客户主数据] 画像缺少'{cust_key_col}'列，跳过匹配")
        return result

    result["_匹配键"] = result[cust_key_col].astype(str).str.strip().str.lower()
    n_total = len(result)

    # Step 1: 全称精确匹配
    name_map_full = master.set_index("_匹配键_全称")
    matched_full = result["_匹配键"].isin(name_map_full.index)
    n_full = matched_full.sum()

    # Step 2: 简称精确匹配（未匹配上的）
    remaining = ~matched_full
    name_map_short = master.set_index("_匹配键_简称")
    matched_short = remaining & result["_匹配键"].isin(name_map_short.index)
    n_short = matched_short.sum()

    # 合并匹配结果
    enrich_fields = [c for c in master.columns if not c.startswith("_") and c not in ["公司工商全称", "公司简称"]]

    for idx in result.index:
        key = result.loc[idx, "_匹配键"]
        matched_row = None

        if key in name_map_full.index:
            matched_row = name_map_full.loc[key]
        elif key in name_map_short.index:
            matched_row = name_map_short.loc[key]

        if matched_row is not None:
            for f in enrich_fields:
                if f in matched_row.index:
                    val = matched_row[f]
                    if pd.isna(val):
                        continue
                    try:
                        result.loc[idx, f"终端{f}"] = val
                    except (TypeError, ValueError):
                        result.loc[idx, f"终端{f}"] = str(val)

    # 统计
    n_matched = n_full + n_short
    print(f"  [客户主数据] 匹配结果: {n_matched}/{n_total} ({n_matched/n_total*100:.1f}%)")
    if n_full > 0:
        print(f"    - 全称匹配: {n_full}/{n_total}")
    if n_short > 0:
        print(f"    - 简称匹配: {n_short}/{n_total}")

    # 尝试模糊匹配（如有 rapidfuzz）
    n_unmatched = n_total - n_matched
    if n_unmatched > 0 and n_unmatched < n_total:  # 至少需要有一些成功匹配来建立模式
        try:
            from rapidfuzz import fuzz
            from config.settings import CUSTOMER_TIER_MAP
            fuzzy_threshold = CUSTOMER_TIER_MAP.get("fuzzy_match_threshold", 85)
            unmatched_idx = result[~matched_full & ~matched_short].index
            master_keys_full = master["_匹配键_全称"].values
            master_keys_short = master["_匹配键_简称"].values

            fuzzy_count = 0
            for idx in unmatched_idx:
                key = result.loc[idx, "_匹配键"]
                # Try full name first
                scores_full = [fuzz.ratio(key, mk) for mk in master_keys_full]
                best_full = max(scores_full) if scores_full else 0
                # Try short name
                scores_short = [fuzz.ratio(key, mk) for mk in master_keys_short]
                best_short = max(scores_short) if scores_short else 0

                if best_full >= fuzzy_threshold:
                    matched_row = master.iloc[scores_full.index(best_full)]
                    fuzzy_count += 1
                elif best_short >= fuzzy_threshold:
                    matched_row = master.iloc[scores_short.index(best_short)]
                    fuzzy_count += 1
                else:
                    continue

                for f in enrich_fields:
                    if f in matched_row.index:
                        val = matched_row[f]
                        if pd.isna(val):
                            continue
                        try:
                            result.loc[idx, f"终端{f}"] = val
                        except (TypeError, ValueError):
                            result.loc[idx, f"终端{f}"] = str(val)

            if fuzzy_count > 0:
                print(f"    - 模糊匹配: {fuzzy_count}/{n_unmatched}")
                n_matched += fuzzy_count

        except ImportError:
            pass

    print(f"  [客户主数据] 最终匹配: {n_matched}/{n_total}")

    # 客户层级映射：CRM客户类别 → KA/AA/KM/MM
    from config.settings import CUSTOMER_TIER_MAP
    tier_cols = [c for c in result.columns if c.startswith("终端") and ("客户类别" in c or "客户分级" in c)]
    if tier_cols:
        tier_map = CUSTOMER_TIER_MAP["mapping"]
        src_col = tier_cols[0]  # 取第一个匹配列
        result["客户层级"] = result[src_col].map(
            lambda x: next(
                (v for k, v in tier_map.items() if pd.notna(x) and k in str(x)),
                CUSTOMER_TIER_MAP.get("default", "未分类")
            )
        )

    # 从终端主数据回填核心字段（仅当原值为"未知"或空时）
    # 业务负责人 ← 终端拓尔销售
    if "终端拓尔销售" in result.columns:
        mask = result["业务负责人"].isna() | (result["业务负责人"] == "未知")
        src = result.loc[mask, "终端拓尔销售"]
        src = src.where(src != "未知", pd.NA)
        result.loc[mask, "业务负责人"] = result.loc[mask, "业务负责人"].where(
            ~mask | src.isna(), src
        )
        n_filled = mask.sum() - (result.loc[mask, "业务负责人"].isna() | (result.loc[mask, "业务负责人"] == "未知")).sum()
        if n_filled > 0:
            print(f"  [客户主数据] 业务负责人从CRM回填: {n_filled} 客户")

    # 客户等级 ← 终端客户类别（从CRM客户类别推导A/B/C等级）
    if "终端客户类别" in result.columns:
        _grade_map = CUSTOMER_TIER_MAP.get("grade_mapping", {"KA": "A", "AA": "A", "KM": "B", "MM": "C"})
        def _cat_to_grade(cat_val):
            if not isinstance(cat_val, str):
                return None
            for tier_key, grade in _grade_map.items():
                if tier_key in cat_val:
                    return grade
            return None
        mask = result["客户等级"].isna() | (result["客户等级"] == "未知")
        mapped = result.loc[mask, "终端客户类别"].map(_cat_to_grade)
        result.loc[mask, "客户等级"] = result.loc[mask, "客户等级"].where(
            mapped.isna(), mapped
        )
        n_filled = mask.sum() - (result.loc[mask, "客户等级"].isna() | (result.loc[mask, "客户等级"] == "未知")).sum()
        if n_filled > 0:
            print(f"  [客户主数据] 客户等级从CRM客户类别推导: {n_filled} 客户")

    # 所属区域 ← 终端销售部门（DEPT_REGION_MAP），回退到工商注册地址解析
    from config.settings import DEPT_REGION_MAP as _drm
    if "终端销售部门" in result.columns:
        mask = result["所属区域"].isna() | (result["所属区域"] == "未知")
        # Step 1: department→region mapping
        for dept, region in _drm.items():
            dept_mask = mask & (result["终端销售部门"] == dept)
            result.loc[dept_mask, "所属区域"] = region
        # Step 2: remaining unknown → parse 工商注册地址
        still_unknown = result["所属区域"].isna() | (result["所属区域"] == "未知")
        if still_unknown.any() and "终端工商注册地址" in result.columns:
            import re as _re
            _city_region = {
                "深圳": "华南", "广州": "华南", "东莞": "华南", "佛山": "华南", "惠州": "华南",
                "珠海": "华南", "中山": "华南", "江门": "华南", "肇庆": "华南",
                "上海": "华东", "苏州": "华东", "杭州": "华东", "南京": "华东", "宁波": "华东",
                "无锡": "华东", "合肥": "华东", "常州": "华东", "温州": "华东", "嘉兴": "华东",
                "北京": "华北", "天津": "华北", "石家庄": "华北", "青岛": "华北", "西安": "华北",
                "济南": "华北", "太原": "华北", "郑州": "华中", "武汉": "华中", "长沙": "华中",
                "成都": "西南", "重庆": "西南", "昆明": "西南", "贵阳": "西南",
                "厦门": "华南", "福州": "华南", "泉州": "华南",
            }
            for idx in result.index[still_unknown]:
                addr = str(result.loc[idx, "终端工商注册地址"])
                for city, region in _city_region.items():
                    if city in addr:
                        result.loc[idx, "所属区域"] = region
                        break
        n_filled = mask.sum() - (result.loc[mask, "所属区域"].isna() | (result.loc[mask, "所属区域"] == "未知")).sum()
        if n_filled > 0:
            print(f"  [客户主数据] 所属区域回填: {n_filled} 客户")

    result = result.drop(columns=["_匹配键"], errors="ignore")
    return result
