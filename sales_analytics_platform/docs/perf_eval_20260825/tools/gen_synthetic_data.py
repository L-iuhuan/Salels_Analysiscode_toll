# 生成与生产同规模的合成 ERP 出货明细数据，用于本地性能实测。
# 规模对齐 2026-07-26 效率评估报告: 191725 行 / 3142 客户 / 818 产品 / 2024-01~2026-06
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)

N = 191_725
N_CUST = 3142
N_PROD = 818
N_SALES = 42

lines = ["MOS管", "集成电路", "二三极管", "电容电阻", "电源器件", "电感磁珠", "晶振", "连接器", "传感器", "光电器件", "保护器件"]
cats = ["功率MOS", "模拟IC", "数字IC", "整流二极管", "MLCC", "铝电解", "LDO", "DC-DC", "功率电感", "温补晶振", "Type-C", "温度传感器", "TVS", "ESD"]

# 客户: 编号 + 层级 (KA/AA/KM/MM), 收入帕累托分布
cust_ids = np.array([f"CUST{i:04d}" for i in range(1, N_CUST + 1)])
tiers = rng.choice(["KA", "AA", "KM", "MM"], size=N_CUST, p=[0.03, 0.07, 0.25, 0.65])
cust_tier = dict(zip(cust_ids, tiers))
cust_w = rng.pareto(1.2, size=N_CUST) + 0.05
cust_p = cust_w / cust_w.sum()

# 产品: 所属产品线/品类固定
prod_ids = np.array([f"SKU-{i:04d}" for i in range(1, N_PROD + 1)])
prod_line = rng.choice(lines, size=N_PROD)
prod_cat = rng.choice(cats, size=N_PROD)
prod_series = np.array([f"系列{rng.integers(1, 30)}" for _ in range(N_PROD)])
prod_w = rng.pareto(1.1, size=N_PROD) + 0.02
prod_p = prod_w / prod_w.sum()

sales_names = np.array([f"业务员{i:02d}" for i in range(1, N_SALES + 1)])

# 日期: 2024-01-01 ~ 2026-06-30, 近期略密
dates = pd.date_range("2024-01-01", "2026-06-30", freq="D")
dw = np.ones(len(dates)) + np.linspace(0, 0.8, len(dates))
dw /= dw.sum()

rows = {
    "终端客户简称": rng.choice(cust_ids, size=N, p=cust_p),
    "存货名称": rng.choice(prod_ids, size=N, p=prod_p),
    "发货日期": rng.choice(dates, size=N, p=dw),
    "实际业务员": rng.choice(sales_names, size=N),
    "ERP订单号": [f"PO{rng.integers(1, 90000):06d}" for _ in range(N)],
    "客户订单号": [f"CO{rng.integers(1, 70000):06d}" for _ in range(N)],
}
df = pd.DataFrame(rows)

qty = rng.integers(10, 6000, size=N).astype(float)
neg = rng.random(N) < 0.02
qty[neg] *= -1
price = np.round(rng.lognormal(mean=2.2, sigma=1.1, size=N), 4)
amount = np.round(qty * price, 2)
margin = np.clip(rng.normal(0.32, 0.15, size=N), -0.4, 0.7)
profit = np.round(amount * margin, 2)
cost = np.round(amount - profit, 2)

df["发货数量"] = qty
df["未税单价"] = price
df["RMB 未税金额小计"] = amount
df["利润"] = profit
df["总成本"] = cost
df["产品线"] = df["存货名称"].map(dict(zip(prod_ids, prod_line)))
df["产品系列"] = df["存货名称"].map(dict(zip(prod_ids, prod_series)))
df["型号_产品品类"] = df["存货名称"].map(dict(zip(prod_ids, prod_cat)))
df["型号_产品线（新）"] = df["产品线"]
df["产品品类（新）"] = df["型号_产品品类"]
df["是否新品"] = np.where(rng.random(N) < 0.06, "Y", "N")
df["终端客户名称_客户类别"] = df["终端客户简称"].map(cust_tier)

out = r"C:\Users\17986\AppData\Local\Temp\opencode\Salels_Analysiscode_toll\sales_analytics_platform\data\synthetic_erp.xlsx"
import os
os.makedirs(os.path.dirname(out), exist_ok=True)
with pd.ExcelWriter(out, engine="xlsxwriter") as w:
    df.to_excel(w, sheet_name="24-26", index=False)
print(f"written: {out}  rows={len(df)}  size={os.path.getsize(out)/1e6:.1f}MB")
