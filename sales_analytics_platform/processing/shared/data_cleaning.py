"""
共享数据清洗管道。

功能：
  - ERP 列名映射（ERP_COL_MAP → 标准中文列名）
  - 负销量保留（filter_negative_qty，当前不剔除，保留退货/红冲行自然冲减）
  - 毛利率计算（winsorize_margins，当前不钳制，保留真实毛利率）
  - 双通道月度聚合（monthly_aggregate_double_pass）
  - 新品标记传播
  - Excel 自动读取（read_excel_auto）

数据流：
  原始 ERP 数据 → rename_erp_columns → filter_negative_qty → winsorize_margins →
  monthly_aggregate_double_pass → 3 张 Silver 表（customer_monthly / product_monthly / customer_x_product）

使用：
  from shared.data_cleaning import ...

  本模块被 run_all.py 和 test/phase1_load.py 共同使用。
  OUTPUT_SILVER 路径与 config/settings.py 保持一致。

注意：
  - Winsorization 当前已禁用（_利润_裁剪 = 原始利润），CLEAN 配置中的 winsor_lower/winsor_upper 保留但不生效
  - 负销量当前不剔除，保留退货/红冲行在聚合时自然冲减
  - 新品标记列（新品标记）在月度聚合时自动传播到 product_monthly
  - 列映射字典 ERP_COL_MAP 在 config/settings.py 中定义
"""

import os
import pandas as pd
import numpy as np

from config.settings import ERP_COL_MAP, DATA_SHEET_NAME

# 共享Silver层输出目录（产品和客户管道共用）
OUTPUT_SILVER = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "output", "silver")
)


def get_excel_engine():
    """检测可用的Excel读取引擎，优先使用calamine（极快）。

    calamine 基于 Rust，读取速度约为 openpyxl 的 5-10 倍。
    回退到 openpyxl 以保证兼容性。

    Returns:
        str or None: 'calamine' 或 None（使用 pandas 默认引擎）
    """
    try:
        import python_calamine  # noqa: F401
        return 'calamine'
    except ImportError:
        return None


def read_excel_auto(*args, **kwargs):
    """pd.read_excel wrapper — 自动选择最快可用引擎 (calamine > openpyxl)。

    calamine 读取速度是 openpyxl 的 5-10 倍，适用于大文件。
    """
    if 'engine' not in kwargs:
        engine = get_excel_engine()
        if engine:
            kwargs['engine'] = engine
    return pd.read_excel(*args, **kwargs)


def validate_required_columns(
    df: pd.DataFrame,
    required_cols: list,
    context: str = "",
) -> list:
    """验证DataFrame是否包含所有必需列，返回缺失列名列表。"""
    missing = [c for c in required_cols if c not in df.columns]
    if missing and context:
        print(f"  [验证] {context}: 缺少必需列 {missing}")
    return missing


def rename_erp_columns(df: pd.DataFrame) -> pd.DataFrame:
    """将ERP原始列名重命名为标准列名（存在则改，不存在则跳过）。"""
    rename_map = {k: v for k, v in ERP_COL_MAP.items() if k in df.columns}
    if rename_map:
        df = df.rename(columns=rename_map)
    return df


def winsorize_margins(
    df: pd.DataFrame,
    profit_col: str = "利润",
    rev_col: str = "金额",
    lower: float = -0.50,
    upper: float = 0.75,
    inplace: bool = True,
) -> pd.DataFrame:
    """计算逐行毛利率并准备利润列（当前不钳制）。

    在行级计算毛利率（_毛利率列），并将利润列复制为_利润_裁剪列。
    当前实现不做Winsorization钳制——保留真实毛利率（含买赠、退货等业务场景），
    让退货/红冲行在聚合时自然冲减收入和利润。

    参数 lower/upper 保留用于未来启用钳制，当前不生效。

    参数:
        df: 包含利润列和收入列的DataFrame
        profit_col: 利润（未税）列名
        rev_col: 收入（未税）列名
        lower: 毛利率下限（当前不生效，保留接口）
        upper: 毛利率上限（当前不生效，保留接口）
        inplace: 是否原地修改

    返回:
        增加了'_毛利率'和'_利润_裁剪'两列的DataFrame（_利润_裁剪 = 原始利润，未钳制）
    """
    result = df if inplace else df.copy()
    result["_毛利率"] = result[profit_col] / result[rev_col].replace(0, float("nan"))
    # 不钳制：保留真实毛利率（含买赠、退货等业务场景）
    result["_利润_裁剪"] = result[profit_col]
    return result


def filter_negative_qty(
    df: pd.DataFrame,
    qty_col: str = "数量",
    inplace: bool = True,
) -> pd.DataFrame:
    """保留负销量记录（退货/红冲），不做物理剔除。

    当前实现不剔除负销量——保留退货/红冲行，让它们在月度聚合时自然冲减收入和利润。
    仅打印负销量记录数量供感知，不修改数据。

    参数:
        df: 包含销量列的DataFrame
        qty_col: 销量列名
        inplace: 是否原地修改

    返回:
        原DataFrame（不剔除任何行）
    """
    result = df if inplace else df.copy()
    # 不剔除负销量：保留退货/红冲行，让它们在聚合时自然冲减
    neg_count = (result[qty_col] < 0).sum()
    if neg_count > 0:
        print(f"  负销量保留: {neg_count} 条负销量记录保留（不做剔除）")
    return result


def build_cust_info(raw_df: pd.DataFrame,
                    cust_col: str = "客户编号",
                    cat_col_raw: str = "终端客户名称_客户类别",
                    cat_col: str = "客户类别",
                    channel_col: str = "销售模式",
                    sales_col: str = "实际业务员",
                    channel_map: dict = None,
                    grade_map: dict = None) -> pd.DataFrame:
    """统一从行级数据构建客户信息 DataFrame（渠道/类别/等级/业务负责人）。

    批次①（T2/P0-1）：run_all.py 新鲜路径与 run_pipeline.py 缓存重载路径
    都通过本函数构建 cust_info，保证两条路径的客户属性标签一致。

    口径（与生产链式路径一致，基线锁定）：
      - 客户编号 fillna("未知客户")（空客户编号统一归并）
      - 客户类别列名归一：缓存路径用原始列名"终端客户名称_客户类别"，
        新鲜路径用重命名后"客户类别" → 统一为重命名后口径
      - 渠道类型：销售模式映射（经销→代理，直销→直供），缺失填"未知"
      - 客户等级：客户类别映射（KA/AA→A，KM→B，MM→C），缺失填"未知"
      - 业务负责人：实际业务员首值

    参数:
        raw_df: 行级数据（可含原始列名或已重命名列名）
        cust_col / cat_col_raw / cat_col / channel_col / sales_col: 相关列名
        channel_map: 销售模式→渠道映射（默认 经销→代理/直销→直供）
        grade_map: 客户类别→客户等级映射（默认 KA/AA→A/KM→B/MM→C）

    返回:
        cust_info DataFrame（含"客户编号"）；无可用属性列时返回 None。
    """
    df = raw_df.copy()
    df[cust_col] = df[cust_col].fillna("未知客户")
    # 列名归一：统一为重命名后口径"客户类别"
    if cat_col_raw in df.columns and cat_col not in df.columns:
        df = df.rename(columns={cat_col_raw: cat_col})

    cust_records = {}
    # 渠道类型：从"销售模式"列映射（经销→代理，直销→直供）
    if channel_col in df.columns:
        cm = channel_map or {"经销": "代理", "直销": "直供"}
        cust_records["渠道类型"] = (
            df.groupby(cust_col)[channel_col].first().map(cm).fillna("未知")
        )
    # 客户类别 + 客户等级（由客户类别推导：KA/AA→A, KM→B, MM→C）
    if cat_col in df.columns:
        cust_records["客户类别"] = df.groupby(cust_col)[cat_col].first()
        gm = grade_map or {"KA": "A", "AA": "A", "KM": "B", "MM": "C"}
        cust_records["客户等级"] = cust_records["客户类别"].map(
            lambda x: next((v for k, v in gm.items() if pd.notna(x) and k in str(x)), "未知")
        )
    # 实际业务员 → 业务负责人
    if sales_col in df.columns:
        cust_records["业务负责人"] = df.groupby(cust_col)[sales_col].first()

    if not cust_records:
        return None
    return pd.DataFrame(cust_records).reset_index()


# ============================================================
# Silver 层 Parquet 双写/读取（批次② 车道C）
# ------------------------------------------------------------
# Parquet 只是 CSV 的**补充**格式：CSV 仍是人可检查的权威副本。
# 双写失败 / parquet 缺失 / parquet 陈旧时，一律回退 CSV，主流程不受影响。
# 读侧只在本目录存在"不早于 CSV"的同名 .parquet 时才改读 parquet（快 3-5 倍），
# 并做 dtype 归一（parquet 往返后 dtypes 可能与 read_csv 推断不同），保证下游计算一致。
# ============================================================

def write_silver_csv_parquet(df: pd.DataFrame, csv_path: str) -> None:
    """写 CSV + 同步写同名 .parquet（同目录）。

    参数:
        df: 要落盘的 DataFrame
        csv_path: CSV 完整路径（parquet 取同 basename、后缀 .parquet）
    """
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    pq_path = os.path.splitext(csv_path)[0] + ".parquet"
    try:
        df.to_parquet(pq_path, index=False)
    except Exception as e:  # noqa: BLE001 —— Parquet 是补充格式，写失败只警告不阻断
        print(f"  [警告] parquet 双写失败（不影响主流程）: {os.path.basename(pq_path)}: "
              f"{type(e).__name__}: {e}")


def load_silver_table(csv_path: str, dtype: dict = None,
                      low_memory: bool = True, encoding: str = "utf-8-sig") -> pd.DataFrame:
    """加载 Silver 表：优先同名 .parquet（存在且 mtime>=CSV），否则读 CSV。

    parquet 读取后按 dtype 做归一，使 dtypes 与 read_csv(dtype=...) 一致；
    dtype 中不存在的列自动忽略（避免 astype 缺列报错）。
    """
    pq_path = os.path.splitext(csv_path)[0] + ".parquet"
    if os.path.exists(pq_path) and os.path.exists(csv_path) \
            and os.path.getmtime(pq_path) >= os.path.getmtime(csv_path):
        try:
            df = pd.read_parquet(pq_path)
            if dtype:
                _dtype = {k: v for k, v in dtype.items() if k in df.columns}
                if _dtype:
                    df = df.astype(_dtype)
            print(f"  [读取] {os.path.basename(csv_path)} ← parquet ({len(df)} 行)")
            return df
        except Exception as e:  # noqa: BLE001 —— parquet 异常一律回退 CSV
            print(f"  [警告] parquet 读取失败，回退 CSV: {type(e).__name__}: {e}")
    return pd.read_csv(csv_path, encoding=encoding, dtype=dtype, low_memory=low_memory)


def monthly_aggregate_double_pass(
    df: pd.DataFrame,
    date_col: str = "发货日期",
    profit_col: str = "利润",
    rev_col: str = "金额",
    qty_col: str = "数量",
    cost_col: str = "成本",
    cust_col: str = "客户编号",
    prod_col: str = "产品品种",
    order_col: str = None,
    winsor_lower: float = -0.50,
    winsor_upper: float = 0.75,
) -> dict:
    """双通道月度聚合：同时生成客户级和产品级的月度聚合表。

    这是共享数据管道的核心入口，一次调用同时输出两套系统需要的silver层数据。

    参数:
        df: 清洗后的行级数据（已做负销量过滤、Winsorization）
        date_col, profit_col, rev_col, qty_col, cost_col: 列名
        cust_col: 客户编号列名
        prod_col: 产品品种列名
        order_col: 订单号列名（用于统计订单数）。不指定时自动尝试常见列名。

    返回:
        dict:
          'customer_monthly': 客户×月份聚合表
          'product_monthly':  产品×月份聚合表
          'customer_x_product': 客户×产品×月份聚合表（下钻桥梁基础数据）
    """
    df = df.copy()
    # 确保日期列为datetime（防止未解析的字符串导致Period转换失败丢失行）
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    before_drop = len(df)
    df = df.dropna(subset=[date_col])
    dropped = before_drop - len(df)
    if dropped > 0:
        print(f"  [聚合] 日期无效剔除: {dropped} 行 ({dropped/before_drop*100:.2f}%)")
    df["_月"] = df[date_col].dt.to_period("M")

    # 客户×月份
    cust_monthly = (
        df.groupby(["_月", cust_col])
        .agg(
            qty_sum=(qty_col, "sum"),
            rev_sum=(rev_col, "sum"),
            cost_sum=(cost_col, "sum"),
            profit_raw_sum=(profit_col, "sum"),
            profit_clip_sum=("_利润_裁剪", "sum"),
            order_count=(order_col or "客户订单号", "nunique")
            if (order_col or "客户订单号") in df.columns
            else (qty_col, "count"),
        )
        .reset_index()
    )
    cust_monthly["毛利率%"] = (
        cust_monthly["profit_clip_sum"] / cust_monthly["rev_sum"].replace(0, float("nan")) * 100
    )

    # 产品×月份（动态agg：基础指标 + 可选新品标记）
    _prod_agg = {
        "qty_sum": (qty_col, "sum"),
        "rev_sum": (rev_col, "sum"),
        "cost_sum": (cost_col, "sum"),
        "profit_raw_sum": (profit_col, "sum"),
        "profit_clip_sum": ("_利润_裁剪", "sum"),
    }
    # 如果源数据有"新品标记"（来自ERP的"是否新品"列），携带至Silver层
    if "新品标记" in df.columns:
        _prod_agg["新品标记"] = ("新品标记", "first")

    prod_monthly = (
        df.groupby(["_月", prod_col])
        .agg(**_prod_agg)
        .reset_index()
    )
    # 批次①（T4）：avg_price 向量化——sum(金额)/sum(数量)，等价于原逐组 lambda，
    # 避免逐组索引切片（大表下收益数十秒）；qty_sum<=0 时同样为 NaN（与原逻辑一致）。
    prod_monthly["avg_price"] = (
        prod_monthly["rev_sum"] / prod_monthly["qty_sum"].replace(0, float("nan"))
    )
    prod_monthly.loc[prod_monthly["qty_sum"] <= 0, "avg_price"] = float("nan")
    # 保持列顺序与历史 schema 一致：avg_price 位于 profit_clip_sum 与 新品标记 之间
    _prod_base_cols = ["_月", prod_col, "qty_sum", "rev_sum", "cost_sum",
                       "profit_raw_sum", "profit_clip_sum"]
    _prod_extra_cols = [c for c in prod_monthly.columns
                        if c not in _prod_base_cols and c != "avg_price"]
    prod_monthly = prod_monthly[_prod_base_cols + ["avg_price"] + _prod_extra_cols]
    prod_monthly["毛利率%"] = (
        prod_monthly["profit_clip_sum"] / prod_monthly["rev_sum"].replace(0, float("nan")) * 100
    )

    # 客户×产品×月份（下钻桥梁）
    cust_prod_monthly = (
        df.groupby(["_月", cust_col, prod_col])
        .agg(
            qty_sum=(qty_col, "sum"),
            rev_sum=(rev_col, "sum"),
            profit_clip_sum=("_利润_裁剪", "sum"),
        )
        .reset_index()
    )
    cust_prod_monthly["毛利率%"] = (
        cust_prod_monthly["profit_clip_sum"] / cust_prod_monthly["rev_sum"].replace(0, float("nan")) * 100
    )

    return {
        "customer_monthly": cust_monthly,
        "product_monthly": prod_monthly,
        "customer_x_product": cust_prod_monthly,
    }



# Silver层CSV读取时的dtype优化映射（减少内存占用约40%）
# 使用位置: run_pipeline.py 中加载silver_*.csv时传入dtype参数
SILVER_DTYPE_CUSTOMER_MONTHLY = {
    "客户编号": "category",
    "rev_sum": "float32",
    "profit_raw_sum": "float32",
    "profit_clip_sum": "float32",
    "cost_sum": "float32",
    "qty_sum": "float32",
    "order_count": "int32",
}

SILVER_DTYPE_PRODUCT_MONTHLY = {
    "产品品种": "category",
    "rev_sum": "float32",
    "profit_raw_sum": "float32",
    "profit_clip_sum": "float32",
    "cost_sum": "float32",
    "qty_sum": "float32",
    "order_count": "int32",
}

SILVER_DTYPE_CUSTOMER_X_PRODUCT = {
    "客户编号": "category",
    "产品品种": "category",
    "rev_sum": "float32",
    "profit_raw_sum": "float32",
    "profit_clip_sum": "float32",
    "cost_sum": "float32",
    "qty_sum": "float32",
    "order_count": "int32",
    "产品一级分类": "category",
}


# ============================================================
# 统一 Silver 层构建（产品和客户管道共用）
# ============================================================

def build_silver_layer(
    source_path: str,
    col_map: dict = None,
    *,
    date_filter_start: str = None,
    save_cleaned_rows: bool = False,
    cat_col_propagation: bool = False,
    output_dir: str = None,
    incomplete_month_threshold_day: int = None,
) -> dict:
    """统一 Silver 层构建：从 Excel 读取 → 清洗 → 月度聚合 → CSV 输出。

    消除 product_lifecycle/run.py 与 customer_analysis/silver.py
    之间 build_silver_layer() 的代码重复。

    参数:
        source_path: 源 Excel 文件路径
        col_map: 列名映射字典。
            键: 销量列, 营收列, 利润列, 客户列, 发货日期列,
                产品名称列, 订单号列, 成本列, 分类参照列
        date_filter_start: 可选，日期过滤起始值（如 "2024-01-01"）。
            为 None 时不过滤（产品管道行为）。
        save_cleaned_rows: 是否额外保存清理后行级数据到 silver_cleaned_rows.csv
        cat_col_propagation: 是否将 产品一级分类 合并到 customer_x_product 表
        output_dir: Silver CSV 输出目录。默认 shared.OUTPUT_SILVER。
        incomplete_month_threshold_day: 不完整月检测阈值。
            当最新月份的最大日期 < 此值，自动剔除该月数据并回退基准月。
            None 表示不检测（产品管道在 _prepare_data 中已有此逻辑）。

    返回:
        dict: {"customer_monthly", "product_monthly", "customer_x_product"}
    """
    # ---- 1. 列名解析 ----
    if col_map:
        qty_col = col_map.get("销量列", "数量")
        rev_col = col_map.get("营收列", "金额")
        profit_col = col_map.get("利润列", "利润")
        cust_col = col_map.get("客户列", "客户编号")
        date_col = col_map.get("发货日期列", "发货日期")
        prod_col = col_map.get("产品名称列", "产品品种")
        order_col = col_map.get("订单号列", None)
        cost_col = col_map.get("成本列", "成本")
        cat_col = col_map.get("分类参照列", "产品一级分类")
    else:
        qty_col = "数量"
        rev_col = "金额"
        profit_col = "利润"
        cust_col = "客户编号"
        date_col = "发货日期"
        prod_col = "产品品种"
        order_col = None
        cost_col = "成本"
        cat_col = "产品一级分类"

    # ---- 2. 读取 & ERP 列重命名 ----
    raw = read_excel_auto(source_path, sheet_name=DATA_SHEET_NAME)
    raw = rename_erp_columns(raw)
    print(f"  原始行数: {len(raw)}")

    # ---- 3. 日期窗口过滤（客户管道专用） ----
    if date_filter_start is not None:
        start_ts = pd.Timestamp(date_filter_start)
        before = len(raw)
        raw = raw[raw[date_col] >= start_ts].copy()
        print(f"  窗口过滤({start_ts.date()}): {before} → {len(raw)} 行")

    # ---- 4. 不完整月检测 ----
    if incomplete_month_threshold_day is not None:
        raw_month = raw[date_col].dt.to_period("M")
        _latest = raw_month.max()
        _mask = raw_month == _latest
        _max_day = raw.loc[_mask, date_col].max().day if _mask.any() else 31
        if _max_day < incomplete_month_threshold_day:
            print(f"  [警告] 最新月份 {_latest} 数据可能不完整（仅到{_max_day}号，阈值{incomplete_month_threshold_day}天）")
            print(f"   已自动剔除 {_latest} 的 {_mask.sum()} 行数据，基准月自动回退")
            raw = raw[~_mask].copy()

    # ---- 5. 行级清洗 ----
    raw = filter_negative_qty(raw, qty_col=qty_col)
    raw = winsorize_margins(raw, profit_col=profit_col, rev_col=rev_col)

    # ---- 6. 合并客户信息表 ----
    try:
        cust_info = read_excel_auto(source_path, sheet_name="客户信息表")
        info_cols = [
            c for c in
            ["客户编号", "渠道类型", "客户等级", "所属区域", "业务负责人"]
            if c in cust_info.columns
        ]
        raw = raw.merge(cust_info[info_cols], on=cust_col, how="left")
        print(f"  已合并客户信息 ({len(cust_info)} 条)")
    except (ValueError, FileNotFoundError, KeyError):
        # 客户信息表缺失时填入默认值
        for col in ["渠道类型", "客户等级", "所属区域", "业务负责人"]:
            raw[col] = "未知"

    # ---- 7. 双通道月度聚合 ----
    silver = monthly_aggregate_double_pass(
        raw, date_col=date_col, profit_col=profit_col,
        rev_col=rev_col, qty_col=qty_col, cost_col=cost_col,
        cust_col=cust_col, prod_col=prod_col, order_col=order_col,
    )

    # ---- 8. 产品线列传递（客户管道专用） ----
    if cat_col_propagation:
        # 产品一级分类
        if "产品一级分类" in raw.columns:
            prod_to_line = raw[[prod_col, "产品一级分类"]].drop_duplicates()
            silver["customer_x_product"] = silver["customer_x_product"].merge(
                prod_to_line, on=prod_col, how="left"
            )
        # 型号_产品品类（品类细分，用于主导品类下沉分析）
        if "型号_产品品类" in raw.columns:
            prod_to_cat = raw[[prod_col, "型号_产品品类"]].drop_duplicates()
            silver["customer_x_product"] = silver["customer_x_product"].merge(
                prod_to_cat, on=prod_col, how="left"
            )
        # v4.10: 型号_产品线（新）— 新口径产品线列
        if "型号_产品线（新）" in raw.columns:
            prod_to_newline = raw[[prod_col, "型号_产品线（新）"]].drop_duplicates()
            silver["customer_x_product"] = silver["customer_x_product"].merge(
                prod_to_newline, on=prod_col, how="left"
            )

    # ---- 9. 写出 CSV（批次② 车道C：customer_x_product 同步写同名 .parquet）----
    out_dir = output_dir or OUTPUT_SILVER
    os.makedirs(out_dir, exist_ok=True)
    for key, df in silver.items():
        path = os.path.join(out_dir, f"silver_{key}.csv")
        if key == "customer_x_product":
            write_silver_csv_parquet(df, path)  # 双写 CSV + parquet（补充格式）
        else:
            df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  写入 {path} ({len(df)} 行)")

    # ---- 10. 保存清理后行级数据（产品管道复用优化；批次② 同步写同名 .parquet）----
    if save_cleaned_rows:
        rows_path = os.path.join(out_dir, "silver_cleaned_rows.csv")
        write_silver_csv_parquet(raw, rows_path)  # 双写 CSV + parquet（补充格式）
        print(f"  清洗行级数据: {len(raw)} 行")

    return silver
