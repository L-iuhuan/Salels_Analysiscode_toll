# 看板 HTML 规范化对比：提取 var X = <json>; 数据块，逐变量深度比对。
# 已知运行间顺序不确定的列表变量（旧报告记载）：F_PRODUCT_LIST / PROD_CHANGE → 序不敏感比对。
import json, re, sys

def extract_vars(path):
    txt = open(path, encoding="utf-8").read()
    out = {}
    # 匹配 var NAME = <json>; （JSON 内可能含分号? json.dumps 不会产生裸分号于字符串外，但字符串内可能含;）
    # 稳妥做法：按 "var NAME = " 切分，逐段取到 "\nvar " 或文件尾
    parts = re.split(r"\nvar ([A-Z_0-9]+) = ", "\n" + txt)
    # parts[0] 是首个 var 前的内容；之后成对 (name, rest)
    for i in range(1, len(parts) - 1, 2):
        name = parts[i]
        rest = parts[i + 1]
        # 数据到行尾分号为止
        end = rest.find(";\n")
        if end == -1:
            end = rest.rfind(";")
        payload = rest[:end]
        try:
            out[name] = json.loads(payload)
        except json.JSONDecodeError:
            out[name] = f"<unparsed:{len(payload)}>"
    # C_DATA: const DATA = {...};
    m = re.search(r"const DATA = (\{.*?\});\s*?\n", txt, re.S)
    if m:
        try:
            out["C_DATA"] = json.loads(m.group(1))
        except json.JSONDecodeError:
            out["C_DATA"] = "<unparsed>"
    return out

def canon(o, unordered_list=False):
    if isinstance(o, dict):
        return {k: canon(v, unordered_list) for k, v in sorted(o.items())}
    if isinstance(o, list):
        items = [canon(v, unordered_list) for v in o]
        if unordered_list:
            return sorted(items, key=lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True))
        return items
    return o

ORDER_INSENSITIVE = {"F_PRODUCT_LIST", "PROD_CHANGE"}

a = extract_vars(sys.argv[1])
b = extract_vars(sys.argv[2])
keys = sorted(set(a) | set(b))
n_ok = n_diff = 0
for k in keys:
    if k not in a:
        print(f"[ONLY-NEW] {k}"); n_diff += 1; continue
    if k not in b:
        print(f"[ONLY-BASE] {k}"); n_diff += 1; continue
    ui = k in ORDER_INSENSITIVE
    if canon(a[k], ui) == canon(b[k], ui):
        n_ok += 1
    else:
        # 精确序比对再试一次（区分"序差异"与"内容差异"）
        strict = canon(a[k], False) == canon(b[k], False)
        relaxed = canon(a[k], True) == canon(b[k], True)
        if not strict and relaxed:
            print(f"[ORDER-DIFF] {k} (内容一致, 仅顺序不同)")
        else:
            print(f"[DIFF] {k}")
        n_diff += 1
print(f"\nvars compared: {len(keys)}, identical: {n_ok}, diff: {n_diff}")
