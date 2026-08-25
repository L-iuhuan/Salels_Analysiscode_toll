# 打印 cProfile 中 site-packages 函数按 tottime 排名
import pstats, sys

prof = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
st = pstats.Stats(prof)
rows = []
for (fn, line, name), (cc, nc, tt, ct, callers) in st.stats.items():
    rows.append((tt, ct, nc, fn, line, name))
rows.sort(key=lambda x: -x[0])
print(f"== {prof} : top {n} by tottime ==")
for tt, ct, nc, fn, line, name in rows[:n]:
    short = fn.replace("C:\\Users\\17986\\AppData\\Roaming\\Python\\Python313\\site-packages\\", "SP\\")
    print(f"{tt:8.2f}s tot {ct:8.2f}s cum n={nc:<10} {short}:{line}({name})")
