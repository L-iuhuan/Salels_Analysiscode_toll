# 对比两个 output 目录树下的所有 CSV：先字节比对，不一致则按"排序后值比对"判断是内容差异还是仅行序差异。
import os, sys, hashlib, pandas as pd

dir_a, dir_b = sys.argv[1], sys.argv[2]

def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()

files_a = {}
for root, _, files in os.walk(dir_a):
    for f in files:
        if f.endswith(".csv"):
            files_a[os.path.relpath(os.path.join(root, f), dir_a)] = os.path.join(root, f)
files_b = {}
for root, _, files in os.walk(dir_b):
    for f in files:
        if f.endswith(".csv"):
            files_b[os.path.relpath(os.path.join(root, f), dir_b)] = os.path.join(root, f)

only_a = sorted(set(files_a) - set(files_b))
only_b = sorted(set(files_b) - set(files_a))
common = sorted(set(files_a) & set(files_b))
for f in only_a: print(f"[ONLY-BASE] {f}")
for f in only_b: print(f"[ONLY-NEW ] {f}")

n_byte = n_norm = n_diff = 0
for f in common:
    pa, pb = files_a[f], files_b[f]
    if md5(pa) == md5(pb):
        n_byte += 1
        continue
    try:
        da = pd.read_csv(pa, dtype=str, encoding="utf-8-sig")
        db = pd.read_csv(pb, dtype=str, encoding="utf-8-sig")
    except Exception as e:
        print(f"[READ-ERR] {f}: {e}"); n_diff += 1; continue
    if da.shape != db.shape:
        print(f"[SHAPE-DIFF] {f}: base{da.shape} vs new{db.shape}"); n_diff += 1; continue
    if list(da.columns) != list(db.columns):
        print(f"[COL-DIFF] {f}"); n_diff += 1; continue
    sa = da.apply(lambda r: "\x00".join(r.fillna("<NA>").astype(str)), axis=1).sort_values(kind="mergesort").reset_index(drop=True)
    sb = db.apply(lambda r: "\x00".join(r.fillna("<NA>").astype(str)), axis=1).sort_values(kind="mergesort").reset_index(drop=True)
    if (sa == sb).all():
        print(f"[ORDER-ONLY] {f} (内容一致, 仅行序不同)")
        n_norm += 1
    else:
        nd = (sa != sb).sum()
        print(f"[DIFF] {f}: {nd} 行内容不同 (共 {len(sa)} 行)")
        n_diff += 1

print(f"\ncommon files: {len(common)}, byte-identical: {n_byte}, order-only: {n_norm}, content-diff: {n_diff}")
