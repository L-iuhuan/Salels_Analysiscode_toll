# -*- coding: utf-8 -*-
"""极限压测：真实上下文窗口(needle) + 超长输出 + 高难推理深度"""
import json, time, urllib.request, urllib.error, sys, io, random

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = "https://api.deepseek.com/v1/chat/completions"
KEY = "sk-fcd3cee42ea84b8c813a4946bdca30cc"
M41 = "deepseek-v4.1-flash-expires-on-0910"
M40 = "deepseek-v4-flash"

def call(model, messages, max_tokens=2000, extra=None, timeout=600):
    body = {"model": model, "messages": messages, "temperature": 0, "max_tokens": max_tokens}
    if extra: body.update(extra)
    req = urllib.request.Request(BASE, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        el = round(time.perf_counter() - t0, 2)
        msg = data["choices"][0]["message"]
        u = data.get("usage", {})
        return dict(ok=True, status=200, content=msg.get("content","") or "",
                    reasoning=msg.get("reasoning_content","") or "",
                    elapsed=el, finish=data["choices"][0].get("finish_reason"),
                    prompt_toks=u.get("prompt_tokens",0),
                    completion_toks=u.get("completion_tokens",0),
                    reason_toks=(u.get("completion_tokens_details") or {}).get("reasoning_tokens",0))
    except urllib.error.HTTPError as e:
        el = round(time.perf_counter() - t0, 2)
        return dict(ok=False, status=e.code, error=e.read().decode()[:300], elapsed=el)
    except Exception as e:
        return dict(ok=False, status=-1, error=str(e)[:300], elapsed=round(time.perf_counter()-t0,2))

# ---------- 填充文本生成 ----------
random.seed(7)
TOPICS = ["气象观测","土壤样本","水文记录","植被分布","矿脉勘探","洋流监测","地震波形","冰川运动"]
UNITS = ["站","组","段","区","点","带","层","域"]
def filler_block(n):
    """生成约 n 字符的自然中文填充文本"""
    out = []
    total = 0
    i = 0
    while total < n:
        t = TOPICS[i % len(TOPICS)]; u = UNITS[(i//len(TOPICS)) % len(UNITS)]
        s = (f"{t}第{i}号{u}的记录显示，本期数据较上期变化了{random.randint(1,99)}个单位，"
             f"其中关键指标维持在{random.randint(100,999)}至{random.randint(1000,9999)}之间波动，"
             f"观测人员于{random.randint(1,12)}月{random.randint(1,28)}日完成了例行校验，"
             f"未发现异常信号，相关档案已归入常规序列。\n")
        out.append(s); total += len(s); i += 1
    return "".join(out)

print("="*70); print("STEP 0: 校准 token/字符比率"); print("="*70)
probe = filler_block(20000)
r = call(M41, [{"role":"user","content": probe + "\n以上文本有多少个句号？只回答数字。"}], 100)
ratio = r["prompt_toks"] / len(probe) if r["ok"] else 0.7
print(f"probe: {len(probe)} chars -> {r['prompt_toks']} prompt_toks, ratio={ratio:.4f} tok/char")

def build_needle_prompt(target_tokens, needle, depth=0.5):
    target_chars = int(target_tokens / ratio)
    needle_line = f"\n【密令：{needle}】\n"
    pos = int(target_chars * depth)
    pre = filler_block(pos)
    post = filler_block(target_chars - pos - len(needle_line))
    return pre + needle_line + post

NEEDLE = "星舰-青鸾-7429-出库"
QUESTION = "\n\n上面的长文中藏有一条格式为【密令：XXX】的指令。请只输出密令内容本身，不要任何其他文字。"

print("\n" + "="*70); print("STEP 1: 上下文窗口逐级压测 (needle @ 50% 深度)"); print("="*70)
LEVELS = [64_000, 128_000, 256_000, 512_000, 1_000_000]
results_ctx = {M41: {}, M40: {}}
for m in [M41, M40]:
    print(f"\n----- {m} -----")
    for lv in LEVELS:
        prompt = build_needle_prompt(lv, NEEDLE) + QUESTION
        r = call(m, [{"role":"user","content": prompt}], 200, timeout=900)
        if r["ok"]:
            found = NEEDLE in r["content"]
            results_ctx[m][lv] = dict(actual=r["prompt_toks"], found=found, elapsed=r["elapsed"])
            print(f"  target={lv:>9,} actual={r['prompt_toks']:>9,} tok | {'FOUND' if found else 'MISS '} | {r['elapsed']}s")
            if not found:
                print(f"    (answer was: {r['content'][:80]!r})")
        else:
            results_ctx[m][lv] = dict(error=f"HTTP {r['status']}", msg=r["error"][:200])
            print(f"  target={lv:>9,} -> HTTP {r['status']}: {r['error'][:150]}")
            break  # 报错即停，不继续加压

# 若 1M 通过，再测 90% 深度
for m in [M41, M40]:
    if 1_000_000 in results_ctx[m] and results_ctx[m][1_000_000].get("found"):
        prompt = build_needle_prompt(1_000_000, NEEDLE, depth=0.9) + QUESTION
        r = call(m, [{"role":"user","content": prompt}], 200, timeout=900)
        if r["ok"]:
            found = NEEDLE in r["content"]
            results_ctx[m]["1M@90%"] = dict(actual=r["prompt_toks"], found=found, elapsed=r["elapsed"])
            print(f"  {m} 1M@90%: {'FOUND' if found else 'MISS'} ({r['elapsed']}s)")

with open("C:/Users/910373/AppData/Local/Temp/opencode/ds_ctx_results.json", "w", encoding="utf-8") as f:
    json.dump(results_ctx, f, ensure_ascii=False, indent=2)
print("\nSaved ctx results.")
