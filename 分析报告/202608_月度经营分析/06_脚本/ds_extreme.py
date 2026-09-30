# -*- coding: utf-8 -*-
"""极限补测：MM3重测 / needle MISS复测 / 超长输出 / 高难推理深度 / 知识截止"""
import json, time, base64, urllib.request, urllib.error, sys, io, random

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = "https://api.deepseek.com/v1/chat/completions"
KEY = "sk-fcd3cee42ea84b8c813a4946bdca30cc"
M41 = "deepseek-v4.1-flash-expires-on-0910"
M40 = "deepseek-v4-flash"
MVIS = "deepseek-v4-flash-vision-exp"
DIR = "C:/Users/910373/AppData/Local/Temp/opencode/"

def call(model, messages, max_tokens=8000, timeout=1800):
    body = {"model": model, "messages": messages, "temperature": 0, "max_tokens": max_tokens}
    req = urllib.request.Request(BASE, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        msg = data["choices"][0]["message"]
        u = data.get("usage", {})
        return dict(ok=True, content=msg.get("content","") or "", elapsed=round(time.perf_counter()-t0,2),
                    finish=data["choices"][0].get("finish_reason"),
                    prompt_toks=u.get("prompt_tokens",0), completion_toks=u.get("completion_tokens",0),
                    reason_toks=(u.get("completion_tokens_details") or {}).get("reasoning_tokens",0),
                    reasoning=(msg.get("reasoning_content","") or "")[:500])
    except urllib.error.HTTPError as e:
        return dict(ok=False, status=e.code, error=e.read().decode()[:300], elapsed=round(time.perf_counter()-t0,2))
    except Exception as e:
        return dict(ok=False, status=-1, error=str(e)[:200], elapsed=round(time.perf_counter()-t0,2))

report = []

# ===== 1. MM3 几何题重测 (max_tokens=32000) =====
print("="*66); print("P1: MM3 几何题重测 max_tokens=32000"); print("="*66)
with open(DIR + "mm_geo.png", "rb") as f:
    geo_b64 = "data:image/png;base64," + base64.b64encode(f.read()).decode()
for m in [M41, MVIS]:
    r = call(m, [{"role":"user","content":[
        {"type":"text","text":"这是一道几何题：两条平行线之间有一条折线（zig-zag），已知三个角分别是40°、80°、20°，求图中标注的x角度。请描述图中结构并求解x。"},
        {"type":"image_url","image_url":{"url":geo_b64}}]}], 32000)
    if r["ok"]:
        verdict = "60" if "60" in r["content"] else "?"
        print(f"  {m}: {r['elapsed']}s reason={r['reason_toks']} finish={r['finish']} 含60°={verdict}")
        print(f"  答案摘录: {r['content'][-300:] if r['content'] else '(空)'}")
        report.append(f"### MM3 重测 {m}\n- {r['elapsed']}s, reason_toks={r['reason_toks']}, finish={r['finish']}\n- 答案末尾: {r['content'][-400:]}")
    else:
        print(f"  {m}: HTTP {r['status']} {r['error'][:120]}")
        report.append(f"### MM3 重测 {m}\n- HTTP {r['status']}: {r['error'][:200]}")

# ===== 2. needle MISS 点复测 (max_tokens=4000, 换seed避开缓存) =====
print("\n" + "="*66); print("P2: needle MISS 点复测 (max_tokens=4000, 新seed)"); print("="*66)
random.seed(99)
TOPICS = ["气象观测","土壤样本","水文记录","植被分布","矿脉勘探","洋流监测","地震波形","冰川运动"]
UNITS = ["站","组","段","区","点","带","层","域"]
def filler_block(n):
    out = []; total = 0; i = 0
    while total < n:
        t = TOPICS[i % len(TOPICS)]; u = UNITS[(i//len(TOPICS)) % len(UNITS)]
        s = (f"{t}第{i}号{u}的记录显示，本期数据较上期变化了{random.randint(1,99)}个单位，"
             f"其中关键指标维持在{random.randint(100,999)}至{random.randint(1000,9999)}之间波动，"
             f"观测人员于{random.randint(1,12)}月{random.randint(1,28)}日完成了例行校验，"
             f"未发现异常信号，相关档案已归入常规序列。\n")
        out.append(s); total += len(s); i += 1
    return "".join(out)
RATIO = 0.5899
NEEDLE2 = "秘钥-烛龙-3351-封存"
Q2 = "\n\n上面的长文中藏有一条格式为【密令：XXX】的指令。请只输出密令内容本身。"
def build_needle(target_tokens, depth=0.5):
    chars = int(target_tokens / RATIO)
    nl = f"\n【密令：{NEEDLE2}】\n"
    pos = int(chars * depth)
    return filler_block(pos) + nl + filler_block(chars - pos) + Q2
for m, lv in [(M41, 256_000), (M40, 64_000)]:
    r = call(m, [{"role":"user","content": build_needle(lv)}], 4000, timeout=600)
    if r["ok"]:
        found = NEEDLE2 in r["content"]
        print(f"  {m} @ {lv:,}: {'FOUND' if found else 'MISS'} ({r['elapsed']}s, actual={r['prompt_toks']:,}, reason={r['reason_toks']})")
        if not found: print(f"    回答: {r['content'][:100]!r}")
        report.append(f"### needle复测 {m}@{lv}: {'FOUND' if found else 'MISS'} ({r['elapsed']}s, reason={r['reason_toks']})")
    else:
        print(f"  {m} @ {lv:,}: HTTP {r['status']}")
        report.append(f"### needle复测 {m}@{lv}: HTTP {r['status']}")

# ===== 3. 高难推理深度 =====
print("\n" + "="*66); print("P3: 高难推理（思考深度上限）"); print("="*66)
truth_mod = pow(2024, 2025, 1000)
truth_mul = 987654321 * 123456789
print(f"  [真值] 2024^2025 mod 1000 = {truth_mod}")
print(f"  [真值] 987654321 x 123456789 = {truth_mul}")
HARD = [
 (f"计算 2024^2025 的最后三位十进制数字（即 mod 1000）。要求给出推导过程。", str(truth_mod)),
 (f"不用计算器，精确计算 987654321 × 123456789 的完整结果。", str(truth_mul)),
]
for m in [M41, M40]:
    for q, truth in HARD:
        r = call(m, [{"role":"user","content": q}], 65536, timeout=1200)
        if r["ok"]:
            hit = truth in r["content"].replace(",", "").replace(" ", "")
            print(f"  {m}: {r['elapsed']}s reason={r['reason_toks']} finish={r['finish']} 答案正确={hit}")
            print(f"    摘录: ...{r['content'][-160:]}")
            report.append(f"### 高难推理 {m}\n- 题目: {q[:30]}...\n- 真值: {truth} | 命中: {hit}\n- {r['elapsed']}s reason_toks={r['reason_toks']} finish={r['finish']}\n- 摘录: ...{r['content'][-300:]}")
        else:
            print(f"  {m}: HTTP {r['status']} {r['error'][:100]}")
            report.append(f"### 高难推理 {m}: HTTP {r['status']}")

# ===== 4. 超长输出极限 =====
print("\n" + "="*66); print("P4: 超长输出极限 (max_tokens=65536)"); print("="*66)
LONGPROMPT = "写一篇《Python asyncio 权威指南》技术教程，要求结构完整（目录+至少15个章节，每章含代码示例和讲解），内容尽可能详尽，不要中途停止。"
for m in [M41, M40]:
    r = call(m, [{"role":"user","content": LONGPROMPT}], 65536, timeout=1800)
    if r["ok"]:
        print(f"  {m}: {r['elapsed']}s completion_toks={r['completion_toks']:,} reason={r['reason_toks']} finish={r['finish']} 内容字符={len(r['content']):,}")
        report.append(f"### 超长输出 {m}\n- completion_toks={r['completion_toks']} reason={r['reason_toks']} finish={r['finish']} elapsed={r['elapsed']}s 字符数={len(r['content'])}")
        with open(DIR + f"long_output_{'v41' if m==M41 else 'v40'}.md", "w", encoding="utf-8") as f:
            f.write(r["content"])
    else:
        print(f"  {m}: HTTP {r['status']} {r['error'][:100]}")
        report.append(f"### 超长输出 {m}: HTTP {r['status']} {r['error'][:150]}")

# ===== 5. 知识截止探测 =====
print("\n" + "="*66); print("P5: 知识截止探测"); print("="*66)
for m in [M41, M40]:
    r = call(m, [{"role":"user","content":"你的训练数据截止到哪一年哪一月？请直接回答你知道的截止日期，不要绕弯。然后列出你知道的最近发生的3件科技行业大事及大致时间。"}], 2000)
    if r["ok"]:
        print(f"  {m}: {r['content'][:400]}")
        report.append(f"### 知识截止 {m}\n{r['content'][:600]}")

with open(DIR + "ds_extreme_report.md", "w", encoding="utf-8") as f:
    f.write("# 极限补测报告\n\n" + "\n\n".join(report))
print("\nSaved extreme report.")
