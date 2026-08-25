# 按源文件聚合 cProfile tottime，输出项目文件耗时排名
import pstats, sys, os, collections

prof = sys.argv[1]
st = pstats.Stats(prof)
per_file = collections.defaultdict(float)
total = 0.0
for (fn, line, name), (cc, nc, tt, ct, callers) in st.stats.items():
    per_file[fn] += tt
    total += tt
proj = [(fn, t) for fn, t in per_file.items() if "site-packages" not in fn]
proj.sort(key=lambda x: -x[1])
print(f"== {os.path.basename(prof)} total={total:.1f}s ==")
for fn, t in proj[:18]:
    short = fn.split("Salels_Analysiscode_toll\\")[-1] if "Salels_Analysiscode_toll" in fn else fn
    print(f"{t:8.2f}s  {short}")
site = sum(t for fn, t in per_file.items() if "site-packages" in fn)
print(f"{site:8.2f}s  [site-packages 合计]")
