
"""
特情说明生成 — 产品生命周期专属（v2.9）。

v2.9改进:
- 零销量时跳过自比/他比健康度比较，防语义矛盾
- 所有阈值改为config驱动
- 新增自比健康度极低检测
- 新增衰退期亏损遗漏补充
- _decay_cap_removed 分画像提示（成长期/健康扩张 vs 其他）
- 移除客户数据缺失提示（CM已移除）
"""


def generate_specific_note(row, thr):
    """根据产品各项指标的异常情况自动生成特情说明。

    参数:
        row: 产品数据行（dict-like或Series）
        thr: 阈值字典

    返回:
        str: 特情说明文本
    """
    notes = []

    # 判断是否为零销量（用于后续抑制无效的毛利率比较）
    is_zero_sales = (row.get("\u8fd112\u6708\u9500\u91cf", 0) == 0
                     and row.get("\u5f53\u524d\u753b\u50cf") not in ["\u65b0\u54c1\u89c2\u5bdf", "\u6e05\u4ed3/\u5076\u53d1", None])

    growth_win = row.get("_growth_window", "12\u6708")
    if growth_win not in ("12\u6708", "", None):
        notes.append(f"\u5386\u53f2\u4e0d\u8db312\u6708\uff0c\u589e\u957f\u7387\u57fa\u4e8e{growth_win}\u7a97\u53e3\uff0c\u53ef\u80fd\u4e0d\u7a33\u5b9a")

    if row.get("\u589e\u901f\u65b9\u5411") == "\u51cf\u901f":
        notes.append("\u589e\u957f\u52a8\u80fd\u6b63\u5728\u8870\u51cf")

    cust_warn_line = float(thr.get("note_conc_warning", 0.50))
    if row.get("\u5ba2\u6237\u96c6\u4e2d\u5ea6-\u524d1\u5927%", 0) > cust_warn_line:
        notes.append("\u5ba2\u6237\u96c6\u4e2d\u5ea6\u8fc7\u9ad8\uff0c\u5b58\u5728\u5355\u70b9\u5d29\u5875\u98ce\u9669")

    if row.get("\u659c\u7387\u7b49\u7ea7") in ("\u660e\u663e\u4fb5\u8680", "\u5feb\u901f\u6076\u5316"):
        slope_pct = abs(row.get("\u6bdb\u5229\u7387\u8d8b\u52bf\u659c\u7387%/u6708", 0))
        notes.append(f"\u6bdb\u5229\u7387\u4ee5{slope_pct:.2f}%/\u6708\u901f\u5ea6\u6301\u7eed\u4e0b\u964d")

    if not is_zero_sales:
        sh_warn = float(thr.get("note_self_health_warn_pct", 50)) / 100.0
        if row.get("\u81ea\u6bd4\u5065\u5eb7\u5ea6%", 1.0) < sh_warn and not row.get("_no_valid_hist_margin") and row.get("\u659c\u7387\u7b49\u7ea7") != "\u65e0\u5229\u6da6/\u5f02\u5e38":
            notes.append("\u6bdb\u5229\u7387\u5df2\u8d1d\u7834\u5386\u53f2\u53c2\u7167\u503c\u4e00\u534a")
        his_warn = float(thr.get("note_rel_health_warn_pp", -10))
        if row.get("\u4ed6\u6bd4\u5065\u5eb7\u5ea6(pp)", 0) < his_warn and not row.get("_no_valid_hist_margin") and row.get("\u659c\u7387\u7b49\u7ea7") != "\u65e0\u5229\u6da6/\u5f02\u5e38":
            rh_abs = abs(row["他比健康度(pp)"])
            notes.append(f"毛利率低于参照组均值{rh_abs:.0f}个百分点")

    if row.get("_cv_invalid"):
        notes.append("\u8fd112\u4e2a\u6708\u65e0\u53d1\u8d27\u8bb0\u5f55\uff0c\u8ba2\u5355\u6ce2\u52a8\u6027\u65e0\u6cd5\u8bc4\u4f30")

    if row.get("\u4f4e\u91cf\u54c1\u6807\u8bb0") == "\u8109\u51b2\u53d1\u8d27":
        notes.append("\u8109\u51b2\u53d1\u8d27\uff0c\u8ba2\u5355\u6ce2\u52a8\u6027\u5df2\u8c41\u514d")

    if row.get("_slope_data_insufficient"):
        notes.append("\u6bdb\u5229\u7387\u6709\u6548\u6570\u636e\u4e0d\u8db3\uff0c\u8d8b\u52bf\u5224\u65ad\u4e0d\u53ef\u9760")

    if row.get("\u659c\u7387\u7b49\u7ea7") == "\u65e0\u5229\u6da6/\u5f02\u5e38":
        notes.insert(0, "\u8fd112\u6708\u6bdb\u5229\u7387\u5168\u4e3a\u96f6\uff0c\u76c8\u5229\u80fd\u529b\u4e27\u5931")

    if row.get("_no_valid_hist_margin"):
        notes.insert(0, "\u5386\u53f2\u65e0\u6709\u6548\u6bdb\u5229\u7387\u6570\u636e\uff0c\u76c8\u5229\u5065\u5eb7\u65e0\u6cd5\u8bc4\u4f30")

    sh_extreme = float(thr.get("note_self_extreme_pct", 30)) / 100.0
    sh_val = row.get("\u81ea\u6bd4\u5065\u5eb7\u5ea6%")
    if sh_val is not None and sh_val < sh_extreme:
        notes.append("\u81ea\u6bd4\u5065\u5eb7\u5ea6\u6781\u4f4e\uff0c\u6bdb\u5229\u7387\u4e25\u91cd\u6076\u5316")

    ref_source = row.get("\u53c2\u7167\u7ec4\u5747\u503c\u6765\u6e90")
    if ref_source and ("\u515c\u5e95" in str(ref_source) or "\u4e0d\u6ee1\u8db3" in str(ref_source)):
        notes.insert(0, "\u540c\u7c7b\u53c2\u7167\u7ec4\u4e0d\u8db3\uff0c\u4ed6\u6bd4\u5065\u5eb7\u5ea6\u4ec5\u4f9b\u53c2\u8003")

    pareto = row.get("\u5e15\u7d2f\u6258\u5206\u7c7b")
    if pareto == "\u91cd\u70b9\u4ea7\u54c1":
        margin = row.get("\u8fd112\u6708\u6bdb\u5229\u7387%", 0) or 0
        if 0 < margin < 1:
            leverage = round(1.0 - margin, 4)
            notes.append(f"\u91cd\u70b9\u4ea7\u54c1\uff1a\u82e5\u964d\u672c1%\uff0c\u6bdb\u5229\u7387\u53ef\u63d0\u5347{leverage:.2f}pp\uff0c\u5efa\u8bae\u6301\u7eed\u964d\u672c\u4e0e\u8fed\u4ee3\u5347\u7ea7")
        else:
            notes.append("\u91cd\u70b9\u4ea7\u54c1\uff1a\u5efa\u8bae\u6301\u7eed\u964d\u672c\u4e0e\u8fed\u4ee3\u5347\u7ea7")

    if pareto == "\u5e38\u89c4\u4ea7\u54c1":
        g_rate = row.get("\u8fd112\u6708\u589e\u957f\u7387%", 0)
        high_growth_thr = float(thr.get("note_regular_growth_threshold", 1.0))
        if g_rate > high_growth_thr:
            notes.append("\u9ad8\u589e\u957f\u5e38\u89c4\u4ea7\u54c1\uff0c\u5efa\u8bae\u52a0\u5927\u6295\u5165\u62a2\u5360\u5e02\u573a")

    if row.get("ASP-\u6bdb\u5229\u7387\u8054\u5408\u8bca\u65ad") == "\u4ef7\u683c\u6218\u98ce\u9669":
        notes.append("ASP\u4e0e\u6bdb\u5229\u7387\u540c\u6b65\u4e0b\u964d\uff0c\u5b58\u5728\u4ef7\u683c\u6218\u98ce\u9669\uff0c\u9700\u5173\u6ce8\u7ade\u4e89\u6001\u52bf")

    if is_zero_sales:
        notes.insert(0, "\u8fd112\u6708\u65e0\u53d1\u8d27\u8bb0\u5f55\uff0c\u5f53\u524d\u753b\u50cf\u4e0e\u6bdb\u5229\u7387\u57fa\u4e8e\u96f6\u9500\u91cf\u63a8\u65ad\uff0c\u6bdb\u5229\u7387\u65e0\u5b9e\u9645\u610f\u4e49")

    margin_12m = row.get("\u8fd112\u6708\u6bdb\u5229\u7387%", 0) or 0
    if row.get("_negative_margin"):
        notes.insert(0, "\u5f53\u524d\u5904\u4e8e\u4e8f\u635f\u72b6\u6001\uff08\u8fd112\u6708\u6bdb\u5229\u7387\u4e3a\u8d1f\uff09")
    elif row.get("\u5f53\u524d\u753b\u50cf") == "\u8870\u9000\u671f" and margin_12m < 0:
        notes.insert(0, "\u5f53\u524d\u5904\u4e8e\u4e8f\u635f\u72b6\u6001\uff08\u8fd112\u6708\u6bdb\u5229\u7387\u4e3a\u8d1f\uff09")

    if row.get("_growth_clamped"):
        g_cap = float(thr.get("\u589e\u957f\u7387_\u4e0a\u9650", 5.0))
        g_floor = float(thr.get("\u589e\u957f\u7387_\u4e0b\u9650", -1.0))
        g_raw = row.get("\u8fd112\u6708\u589e\u957f\u7387%", 0)
        if g_raw >= g_cap:
            notes.append(f"\u589e\u957f\u7387\u5df2\u8fbe\u622a\u65ad\u4e0a\u9650({g_cap*100:.0f}%)\uff0c\u5b9e\u9645\u589e\u901f\u66f4\u9ad8")
        elif g_raw <= g_floor:
            notes.append(f"\u589e\u957f\u7387\u5df2\u8fbe\u622a\u65ad\u4e0b\u9650({g_floor*100:.0f}%)\uff0c\u5b9e\u9645\u8dcc\u5e45\u66f4\u6df1")

    if row.get("_decay_cap_removed"):
        portrait = row.get("\u5f53\u524d\u753b\u50cf", "")
        if portrait in ("\u6210\u957f\u671f", "\u5065\u5eb7\u6269\u5f20"):
            notes.append("\u8fd1\u671f\u5df2\u8f6c\u4e3a\u5b9e\u9645\u4e0b\u6ed1\uff0c\u5f53\u524d\u753b\u50cf\u57fa\u4e8e\u66f4\u957f\u7a97\u53e3\u6570\u636e\uff0c\u9700\u7efc\u5408\u5224\u65ad")
        else:
            notes.append("\u7206\u53d1\u589e\u957f\u540e\u8fd1\u671f\u5df2\u8f6c\u4e3a\u5b9e\u9645\u4e0b\u6ed1\uff0c\u589e\u901f\u8870\u51cf\u56e0\u5b50\u672a\u4eab\u53d7\u4e0a\u9650\u4fdd\u62a4")

    strategy = row.get("\u901a\u7528\u7b56\u7565\u5efa\u8bae", "")
    rev_profit_diag = row.get("\u8425\u6536-\u6bdb\u5229\u7efc\u5408\u5224\u65ad", "")
    margin_yoy = row.get("\u6bdb\u5229\u7387\u540c\u6bd4\u53d8\u5316(pp)", 0) or 0
    if ("\u9000\u5e02" in str(strategy) or "\u6362\u4ee3" in str(strategy)) and rev_profit_diag == "\u51cf\u6536\u589e\u5229":
        notes.append("\u6ce8\u610f\uff1a\u6bdb\u5229\u7387\u540c\u6bd4\u56de\u5347\uff0c\u9000\u5e02/\u6362\u4ee3\u5224\u65ad\u9700\u7ed3\u5408\u56de\u5347\u53ef\u6301\u7eed\u6027\u7efc\u5408\u8bc4\u4f30")
    rebound_thr = float(thr.get("note_rebound_threshold_pp", 5))
    if row.get("\u5f53\u524d\u753b\u50cf") == "\u8870\u9000\u671f" and margin_yoy > rebound_thr:
        notes.append(f"\u6bdb\u5229\u7387\u540c\u6bd4\u5927\u5e45\u56de\u5347{margin_yoy:.1f}pp\uff0c\u5efa\u8bae\u590d\u6838\u5f53\u524d\u753b\u50cf\u662f\u5426\u5e94\u4e3a\u4e3b\u52a8\u6536\u7f29")

    if notes:
        return "\uff1b".join(notes)
    return "\u6682\u65e0\u5f02\u5e38\u4fe1\u53f7"
