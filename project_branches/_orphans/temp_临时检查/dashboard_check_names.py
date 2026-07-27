import pandas as pd
df = pd.read_csv(r'C:\Users\45091\Desktop\工作文件\semiconductor_analysis\output\gold\客户全景.csv')
names = df['客户名称'].astype(str)
bad = [n for n in names if "'" in n or '"' in n or '\\' in n]
print(f'Total: {len(names)}, Bad names: {len(bad)}')
for n in bad[:20]:
    print(repr(n))
