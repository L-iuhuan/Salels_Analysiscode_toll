# -*- coding: utf-8 -*-
"""Re-run reasoning-heavy tests with reasoning_content capture and larger max_tokens"""
import json, time, urllib.request, sys, io, random
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

API_URL = "https://api.deepseek.com/v1/chat/completions"
API_KEY = "sk-fcd3cee42ea84b8c813a4946bdca30cc"
MODELS = ["deepseek-v4.1-flash-expires-on-0910", "deepseek-v4-flash"]
TEMP = 0.2
MAXT = 12000

# regenerate identical orders (seed 42, same code path as ds_compare.py)
random.seed(42)
statuses = ["paid", "shipped", "refunded", "pending"]
orders = []
for i in range(1, 41):
    sku = f"SKU-{random.randint(100,105)}"
    qty = random.randint(1, 9)
    price = random.randint(10, 99)
    st = random.choice(statuses)
    orders.append(f"order-{i:03d} | {sku} | qty={qty} | price={price} | status={st}")
orders_text = "\n".join(orders)

RETESTS = {
 "T03_logic_liar": dict(cat="逻辑推理", messages=[
    {"role": "user", "content": "甲说：\"乙在说谎。\" 乙说：\"丙在说谎。\" 丙说：\"甲和乙都在说谎。\" 假设每人要么总说真话要么总说谎，谁说的是真话？请严格推导。"}]),
 "T04_code_lru": dict(cat="代码生成", messages=[
    {"role": "user", "content": "用Python实现一个线程安全的LRU缓存类 LRUCache(capacity)，支持 get(key) 和 put(key, value)，要求O(1)复杂度、含类型注解、处理capacity<=0的边界。只需给出完整代码和简短说明。"}]),
 "T05_code_bug": dict(cat="代码调试", messages=[
    {"role": "user", "content": "下面这段Python代码意图是统计列表中出现次数第二多的元素，但有bug。请找出所有bug并给出修正后的完整代码：\n\n```python\ndef second_most_common(items):\n    counts = {}\n    for x in items:\n        counts[x] = counts.get(x, 0)\n    sorted_items = sorted(counts.items(), key=lambda kv: kv[1])\n    if len(sorted_items) < 2:\n        return None\n    return sorted_items[-2][0]\n```"}]),
 "T09_knowledge_lift": dict(cat="知识问答", messages=[
    {"role": "user", "content": "为什么飞机机翼会产生升力？请分别用伯努利原理和牛顿第三定律解释，并指出一个常见误解。"}]),
 "T11_long_context": dict(cat="长上下文", messages=[
    {"role": "user", "content": f"以下是40条订单记录（格式：订单号 | SKU | 数量 | 单价 | 状态）：\n\n{orders_text}\n\n请回答：\n1) SKU-102的总数量是多少？\n2) SKU-103的总销售额（数量×单价之和）是多少？\n3) status=shipped 的订单有几条？\n4) 金额（数量×单价）最大的订单号和金额是多少？\n请逐项简要回答。"}]),
}
MULTI = [
    {"role": "user", "content": "记住以下偏好：我叫李雷，喜欢的编程语言是Rust，不喜欢Java。只需回复'好的'。"},
    {"role": "user", "content": "推荐我一个适合我的新 hobby，要与我的编程语言偏好气质相符，一句话。"},
    {"role": "user", "content": "我刚才说我叫什么？我讨厌的语言是什么？用一行回答。"},
]

def call(model, messages, max_tokens):
    body = {"model": model, "messages": messages, "temperature": TEMP, "max_tokens": max_tokens}
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.loads(r.read().decode())
    el = round(time.perf_counter() - t0, 2)
    msg = data["choices"][0]["message"]
    usage = data.get("usage", {})
    fr = data["choices"][0].get("finish_reason")
    cd = usage.get("completion_tokens_details", {}) or {}
    return dict(content=msg.get("content", "") or "", reasoning=msg.get("reasoning_content", "") or "",
                elapsed=el, finish=fr, usage=usage, reason_toks=cd.get("reasoning_tokens", 0))

RES_PATH = "C:/Users/910373/AppData/Local/Temp/opencode/ds_compare_results.json"
with open(RES_PATH, encoding="utf-8") as f:
    blob = json.load(f)

for m in MODELS:
    print(f"\n===== {m} =====")
    for tid, t in RETESTS.items():
        r = call(m, t["messages"], MAXT)
        blob["results"][m][tid] = dict(cat=t["cat"], content=r["content"], reasoning=r["reasoning"],
            elapsed=r["elapsed"], finish=r["finish"], usage=r["usage"], reason_toks=r["reason_toks"])
        print(f"[{tid}] {r['elapsed']}s finish={r['finish']} reason_toks={r['reason_toks']} content_len={len(r['content'])}")
    # multi-turn retest
    history = []; parts = []
    for turn in MULTI:
        history.append(turn)
        r = call(m, history, 6000)
        parts.append(r["content"] if r["content"] else f"(空, reasoning {r['reason_toks']} tok, finish={r['finish']})")
        history.append({"role": "assistant", "content": r["content"] or "(…)"})
    blob["results"][m]["T12_multiturn"]["content"] = "\n---TURN---\n".join(parts)
    print("[T12_multiturn] retested")

with open(RES_PATH, "w", encoding="utf-8") as f:
    json.dump(blob, f, ensure_ascii=False, indent=2)

# regenerate markdown
md = ["# DeepSeek 对比测试原始输出 (v2, 含 reasoning)", f"- 温度: {TEMP}", "",
      f"## 长上下文题目真值\n```json\n{json.dumps(blob['truth_long_context'], ensure_ascii=False, indent=2)}\n```\n"]
order = ["T01_follow_exact","T02_math_profit","T03_logic_liar","T04_code_lru","T05_code_bug",
         "T06_chinese_poem","T07_translation","T08_json_extract","T09_knowledge_lift",
         "T10_trick_apples","T11_long_context","T12_multiturn","T13_ttft"]
for tid in order:
    anyr = blob["results"][MODELS[0]].get(tid, {})
    md.append(f"\n## {tid} ({anyr.get('cat','')})\n")
    for m in MODELS:
        r = blob["results"][m].get(tid, {})
        meta = f"elapsed={r.get('elapsed')}s ttft={r.get('ttft','-')}s finish={r.get('finish','-')} reason_toks={r.get('reason_toks','-')}"
        block = f"### {m}\n> {meta}\n\n```\n{r.get('content','')}\n```\n"
        if r.get("reasoning"):
            rs = r["reasoning"]
            block += f"\n<details>reasoning ({len(rs)} chars, first 600):\n\n{rs[:600]}\n</details>\n"
        md.append(block)
with open("C:/Users/910373/AppData/Local/Temp/opencode/ds_compare_report.md", "w", encoding="utf-8") as f:
    f.write("\n".join(md))
print("\nReport regenerated.")
