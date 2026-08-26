# 打印 cProfile 中项目代码函数按 cumtime 排名
import pstats, sys

prof = sys.argv[1]
substr = sys.argv[2] if len(sys.argv) > 2 else "processing"
n = int(sys.argv[3]) if len(sys.argv) > 3 else 25
st = pstats.Stats(prof)
rows = []
for (fn, line, name), (cc, nc, tt, ct, callers) in st.stats.items():
    if substr in fn and "site-packages" not in fn:
        rows.append((ct, tt, nc, fn, line, name))
rows.sort(key=lambda x: -x[0])
print(f"== {prof} : top {n} project funcs by cumtime ==")
for ct, tt, nc, fn, line, name in rows[:n]:
    short = fn.split("processing\\")[-1]
    print(f"{ct:8.2f}s cum {tt:7.2f}s tot n={nc:<8} {short}:{line}({name})")
