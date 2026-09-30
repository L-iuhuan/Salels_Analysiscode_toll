# -*- coding: utf-8 -*-
"""探测 DeepSeek v4.1-flash vs v4-flash 的 API 基准参数"""
import json, time, urllib.request, urllib.error, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = "https://api.deepseek.com/v1"
KEY = "sk-fcd3cee42ea84b8c813a4946bdca30cc"
MODELS = ["deepseek-v4.1-flash-expires-on-0910", "deepseek-v4-flash"]

def raw(method, path, body=None, timeout=120):
    req = urllib.request.Request(BASE + path,
        data=json.dumps(body).encode() if body else None, method=method,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]

print("="*70); print("1) GET /models 模型列表元数据"); print("="*70)
st, data = raw("GET", "/models")
print(f"HTTP {st}")
for m in data.get("data", []):
    print(f"  - {m['id']}")

print("\n" + "="*70); print("2) 知识截止日期 & 自我参数认知"); print("="*70)
for m in MODELS:
    st, r = raw("POST", "/chat/completions", {
        "model": m, "max_tokens": 300, "temperature": 0,
        "messages": [{"role":"user","content":"Your knowledge cutoff date (year-month) and your max context window in tokens? Answer in one line as JSON: {\"cutoff\":\"...\",\"context\":\"...\"}"}]})
    if st == 200:
        c = r["choices"][0]["message"].get("content","")
        print(f"{m}: {c.strip()}")
    else:
        print(f"{m}: HTTP {st}: {r[:200]}")

print("\n" + "="*70); print("3) thinking 参数控制探测"); print("="*70)
# 试 enable_thinking=false / thinking={"type":"disabled"} / reasoning_effort
variants = [
    ("enable_thinking=false", {"enable_thinking": False}),
    ("thinking.disabled", {"thinking": {"type": "disabled"}}),
    ("reasoning_effort=low", {"reasoning_effort": "low"}),
    ("reasoning_effort=high", {"reasoning_effort": "high"}),
]
for m in MODELS:
    print(f"\n  [{m}]")
    for name, extra in variants:
        body = {"model": m, "max_tokens": 2000, "temperature": 0,
                "messages": [{"role":"user","content":"计算 47*83 等于多少？只给数字。"}]}
        body.update(extra)
        st, r = raw("POST", "/chat/completions", body)
        if st == 200:
            msg = r["choices"][0]["message"]
            rt = (r["usage"].get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
            c = msg.get("content","")[:40].replace("\n"," ")
            print(f"    {name:25s} -> OK reasoning_toks={rt:5d} answer={c}")
        else:
            print(f"    {name:25s} -> HTTP {st}: {str(r)[:120]}")

print("\n" + "="*70); print("4) max_tokens 输出上限探测"); print("="*70)
for m in MODELS:
    print(f"\n  [{m}]")
    for mt in [32768, 65536, 131072]:
        body = {"model": m, "max_tokens": mt, "temperature": 0,
                "messages": [{"role":"user","content":"回复'ok'"}]}
        st, r = raw("POST", "/chat/completions", body)
        if st == 200:
            print(f"    max_tokens={mt:6d} -> 接受")
        else:
            print(f"    max_tokens={mt:6d} -> HTTP {st}: {str(r)[:150]}")
