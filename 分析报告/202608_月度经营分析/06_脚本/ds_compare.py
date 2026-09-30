# -*- coding: utf-8 -*-
"""DeepSeek model comparison: deepseek-v4.1-flash-expires-on-0910 vs deepseek-v4-flash"""
import json, time, urllib.request, urllib.error, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

API_URL = "https://api.deepseek.com/v1/chat/completions"
API_KEY = "sk-fcd3cee42ea84b8c813a4946bdca30cc"
MODELS = ["deepseek-v4.1-flash-expires-on-0910", "deepseek-v4-flash"]
TEMP = 0.2

# ---------- long context payload (synthetic, verifiable) ----------
import random
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
# ground truth computed here
from collections import defaultdict
qty_by_sku = defaultdict(int); rev_by_sku = defaultdict(int); cnt_status = defaultdict(int)
rev_max = -1; max_order = None
for o in orders:
    _, sku, q, p, st = [x.strip() for x in o.split("|")]
    q = int(q.split("=")[1]); p = int(p.split("=")[1]); st = st.split("=")[1]
    qty_by_sku[sku] += q; rev_by_sku[sku] += q * p; cnt_status[st] += 1
    if q * p > rev_max: rev_max, max_order = q * p, o.split("|")[0].strip()
LC_TRUTH = {
    "total_qty_SKU-102": qty_by_sku.get("SKU-102", 0),
    "revenue_SKU-103": rev_by_sku.get("SKU-103", 0),
    "count_shipped": cnt_status["shipped"],
    "max_revenue_order": f"{max_order} ({rev_max})",
}

TESTS = [
    dict(id="T01_follow_exact", cat="指令遵循", max_tokens=200, messages=[
        {"role": "user", "content": "Reply with EXACTLY 5 English words, no punctuation, nothing else. Topic: the ocean."}]),
    dict(id="T02_math_profit", cat="数学推理", max_tokens=1500, messages=[
        {"role": "user", "content": "一个商店进了120件商品，每件成本25元。第一周以40元卖出35件，第二周以八折价卖出50件，剩余商品以成本价全部清仓。求总利润（元）？请给出分步计算过程和最终答案。"}]),
    dict(id="T03_logic_liar", cat="逻辑推理", max_tokens=1500, messages=[
        {"role": "user", "content": "甲说：\"乙在说谎。\" 乙说：\"丙在说谎。\" 丙说：\"甲和乙都在说谎。\" 假设每人要么总说真话要么总说谎，谁说的是真话？请严格推导。"}]),
    dict(id="T04_code_lru", cat="代码生成", max_tokens=3000, messages=[
        {"role": "user", "content": "用Python实现一个线程安全的LRU缓存类 LRUCache(capacity)，支持 get(key) 和 put(key, value)，要求O(1)复杂度、含类型注解、处理capacity<=0的边界。只需给出完整代码和简短说明。"}]),
    dict(id="T05_code_bug", cat="代码调试", max_tokens=2000, messages=[
        {"role": "user", "content": "下面这段Python代码意图是统计列表中出现次数第二多的元素，但有bug。请找出所有bug并给出修正后的完整代码：\n\n```python\ndef second_most_common(items):\n    counts = {}\n    for x in items:\n        counts[x] = counts.get(x, 0)\n    sorted_items = sorted(counts.items(), key=lambda kv: kv[1])\n    if len(sorted_items) < 2:\n        return None\n    return sorted_items[-2][0]\n```"}]),
    dict(id="T06_chinese_poem", cat="中文创作", max_tokens=800, messages=[
        {"role": "user", "content": "以《秋夜》为题写一首五言绝句（四句、每句五字、押韵），然后用两句话解释诗中的意象。"}]),
    dict(id="T07_translation", cat="翻译", max_tokens=800, messages=[
        {"role": "user", "content": "将下面这段话翻译成地道中文，注意习语处理：\n\nWhen the startup's funding fell through at the eleventh hour, the CEO decided to bite the bullet and lay off half the team rather than let the company go under."}]),
    dict(id="T08_json_extract", cat="结构化输出", max_tokens=400, messages=[
        {"role": "user", "content": "从文本中提取信息，只输出一个JSON对象（无其他文字），键固定为 name/phone/email/city/district：\n\n客户张三，联系电话13800138000，邮箱 zhang@example.com，现居浙江省杭州市西湖区文三路。"}]),
    dict(id="T09_knowledge_lift", cat="知识问答", max_tokens=2000, messages=[
        {"role": "user", "content": "为什么飞机机翼会产生升力？请分别用伯努利原理和牛顿第三定律解释，并指出一个常见误解。"}]),
    dict(id="T10_trick_apples", cat="陷阱题", max_tokens=600, messages=[
        {"role": "user", "content": "我有3个苹果，吃了2个，又买了5个，然后把手里的一半送给朋友，最后剩几个？"}]),
    dict(id="T11_long_context", cat="长上下文", max_tokens=1000, messages=[
        {"role": "user", "content": f"以下是40条订单记录（格式：订单号 | SKU | 数量 | 单价 | 状态）：\n\n{orders_text}\n\n请回答：\n1) SKU-102的总数量是多少？\n2) SKU-103的总销售额（数量×单价之和）是多少？\n3) status=shipped 的订单有几条？\n4) 金额（数量×单价）最大的订单号和金额是多少？\n请逐项简要回答。"}]),
    dict(id="T12_multiturn", cat="多轮对话", max_tokens=600, multi=[
        {"role": "user", "content": "记住以下偏好：我叫李雷，喜欢的编程语言是Rust，不喜欢Java。只需回复'好的'。"},
        {"role": "user", "content": "推荐我一个适合我的新 hobby，要与我的编程语言偏好气质相符，一句话。"},
        {"role": "user", "content": "我刚才说我叫什么？我讨厌的语言是什么？用一行回答。"}]),
]

def call_api(model, messages, max_tokens, stream=False):
    body = {"model": model, "messages": messages, "temperature": TEMP,
            "max_tokens": max_tokens, "stream": stream}
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"})
    t0 = time.perf_counter()
    if not stream:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read().decode())
        elapsed = time.perf_counter() - t0
        content = data["choices"][0]["message"].get("content", "")
        usage = data.get("usage", {})
        return dict(ok=True, content=content, elapsed=round(elapsed, 2),
                    usage=usage)
    else:
        # streaming: measure TTFT
        with urllib.request.urlopen(req, timeout=180) as r:
            ttft = None; chunks = []; t_first = None
            for raw in r:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"): continue
                payload = line[5:].strip()
                if payload == "[DONE]": break
                try: d = json.loads(payload)
                except: continue
                if ttft is None:
                    ttft = round(time.perf_counter() - t0, 2)
                delta = d.get("choices", [{}])[0].get("delta", {})
                if delta.get("content"): chunks.append(delta["content"])
        elapsed = round(time.perf_counter() - t0, 2)
        return dict(ok=True, content="".join(chunks), elapsed=elapsed, ttft=ttft, usage={})

results = {m: {} for m in MODELS}
for m in MODELS:
    print(f"\n{'='*70}\nMODEL: {m}\n{'='*70}")
    for t in TESTS:
        if "multi" in t:
            history = []; contents = []; turns_meta = []
            for turn in t["multi"]:
                history.append(turn)
                rr = call_api(m, history, t["max_tokens"])
                turns_meta.append(f"{rr['elapsed']}s")
                contents.append(rr["content"])
                history.append({"role": "assistant", "content": rr["content"]})
            results[m][t["id"]] = dict(cat=t["cat"], content="\n---TURN---\n".join(contents),
                                       elapsed="+".join(turns_meta), usage={}, note="multi-turn")
            print(f"[{t['id']}] ({t['cat']}) turns: {'+'.join(turns_meta)}")
        else:
            r = call_api(m, t["messages"], t["max_tokens"])
            results[m][t["id"]] = dict(cat=t["cat"], content=r["content"],
                                       elapsed=r["elapsed"], usage=r["usage"])
            u = r["usage"]; ct = u.get("completion_tokens", "?")
            tps = round(ct / r["elapsed"], 1) if isinstance(ct, int) and isinstance(r["elapsed"], (int, float)) and r["elapsed"] > 0 else "?"
            print(f"[{t['id']}] ({t['cat']}) {r['elapsed']}s | {ct} tok | {tps} tok/s")
    # streaming TTFT test
    r = call_api(m, [{"role":"user","content":"用中文写一段120字左右的短文，主题：山间晨雾。"}], 500, stream=True)
    results[m]["T13_ttft"] = dict(cat="流式TTFT", content=r["content"],
                                  elapsed=r["elapsed"], ttft=r["ttft"])
    print(f"[T13_ttft] TTFT={r['ttft']}s total={r['elapsed']}s len={len(r['content'])}")

with open(OUT := "C:/Users/910373/AppData/Local/Temp/opencode/ds_compare_results.json", "w", encoding="utf-8") as f:
    json.dump({"truth_long_context": LC_TRUTH, "results": results}, f, ensure_ascii=False, indent=2)

# markdown report
md = ["# DeepSeek 对比测试原始输出", f"- 温度: {TEMP}", "", f"## 长上下文题目真值\n```json\n{json.dumps(LC_TRUTH, ensure_ascii=False, indent=2)}\n```\n"]
for t in TESTS + [dict(id="T13_ttft", cat="流式TTFT")]:
    md.append(f"\n## {t['id']} ({t['cat']})\n")
    for m in MODELS:
        r = results[m][t["id"]]
        meta = f"elapsed={r.get('elapsed')}s ttft={r.get('ttft','-')}s"
        md.append(f"### {m}\n> {meta}\n\n```\n{r['content']}\n```\n")
with open("C:/Users/910373/AppData/Local/Temp/opencode/ds_compare_report.md", "w", encoding="utf-8") as f:
    f.write("\n".join(md))
print(f"\nSaved: {OUT}")
