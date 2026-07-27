"""
审计 generate_dashboard.py 中所有数据源使用情况
"""
import re

with open('generate_dashboard.py', encoding='utf-8') as f:
    code = f.read()

# 数据源关键词
sources = {
    'raw_excel': 'Raw Excel (24-26 sheet)',
    'scm': 'Silver customer_monthly',
    'cxp': 'Silver customer_x_product (桥接表)',
    'df': 'Gold 客户全景.csv',
    'raw_rows': 'Silver cleaned_rows.csv',
    'kaaa': 'Gold KA+AA客户',
    'r26/r25': 'Raw Excel 2026/2025过滤',
}

# 关键用途
uses = {
    'TREND': 'A面月度柱状图数据',
    'trend_tiers': 'A面层级筛选趋势',
    'karev': 'A面KA+AA月度折线',
    'csa/SA': 'A面客户列表',
    'ka_kpi': 'A面KA月度卡片',
    'kpi_r/kpi_p等': 'A面顶部KPI卡片',
    'scat': 'A面KA散点图',
    'pie': 'A面K类饼图',
    'B_CUSTS/call': 'B面客户数据',
    'B_TREND/ctr': 'B面客户月度趋势',
    'cid_fin': 'B面客户财务数据(YTD等)',
    'new_detail': 'B面新品明细',
    'cid_12m_data': 'B面品类结构(品种/品类/饼图)',
    'product_change_detail': 'A面产品变迁窗口',
    'prank': 'B面Top5产品',
    'cid_margin': 'B面毛利率(旧,已废弃)',
}

with open('audit_output.txt', 'w', encoding='utf-8') as f:
    f.write("=== generate_dashboard.py 数据源审计 ===\n\n")

    # 1. 列出所有pd.read_csv/read_excel
    f.write("【数据加载】\n")
    for line in code.split('\n'):
        if 'pd.read' in line:
            f.write(f"  {line.strip()}\n")

    f.write("\n【数据用途→数据源映射】\n")
    for var, desc in uses.items():
        # Find where it's built
        f.write(f"\n  {var} ({desc}):\n")
        # Check raw_excel references
        if var in code:
            # Find the construction line
            for i, line in enumerate(code.split('\n')):
                if f'{var} = ' in line or f'{var}=' in line:
                    f.write(f"    构建: line {i+1}: {line.strip()[:100]}\n")
                    break

    f.write("\n\n【需要从Silver迁移到Raw Excel的项】\n")
    items = [
        ("TREND (A面月度柱状图)", "scm → raw_excel", "按_月聚合 rev/profit"),
        ("trend_tiers (层级筛选)", "scm → raw_excel", "加层级列后按_月+层级聚合"),
        ("karev (KA+AA折线)", "scm → raw_excel", "筛选KA/AA客户后按月聚合"),
        ("scat (KA散点图)", "scm → raw_excel", "按客户YTD聚合"),
        ("B面 cid_12m_data (品类数/饼图)", "cxp → raw_excel", "按客户+产品品类聚合"),
        ("B面 cid_fin (YTD/上月等)", "scm → raw_excel", "按客户+时间切片聚合"),
        ("B面 ctr (客户月度趋势)", "scm → raw_excel", "按客户+月聚合"),
        ("product_change_detail (产品变迁)", "cxp → raw_excel", "按客户+产品+时间切片聚合"),
        ("prank (Top5产品)", "cxp → raw_excel", "按客户+产品聚合"),
        ("A面客户列表(月环比)", "scm → raw_excel", "单月对比"),
    ]
    for name, change, note in items:
        f.write(f"  - {name}: {change}  ({note})\n")

    f.write("\n\n【保持不变(来自Gold层,非收入/利润)】\n")
    keep = [
        "客户层级/综合价值层级/风险评级/业务负责人等属性 → df (客户全景.csv)",
        "策略建议/策略原因/异常告警 → df",
        "RFMπ分数/综合评分 → df",
        "双轴分类/生命周期/活跃状态 → df",
        "新品标记/新品采购额等 → cleaned_rows.csv (仅新品标记字段)",
        "产品名称/当前画像等C面数据 → gold_product_portrait.csv",
    ]
    for item in keep:
        f.write(f"  - {item}\n")

print("Done. 查看 audit_output.txt")
