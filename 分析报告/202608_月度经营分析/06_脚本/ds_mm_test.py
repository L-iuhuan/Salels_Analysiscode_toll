# -*- coding: utf-8 -*-
"""多模态能力测试：基础OCR / 密集图表理解 / 几何视觉推理"""
import json, time, base64, urllib.request, urllib.error, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = "https://api.deepseek.com/v1/chat/completions"
KEY = "sk-fcd3cee42ea84b8c813a4946bdca30cc"
MODELS = ["deepseek-v4.1-flash-expires-on-0910", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp"]
DIR = "C:/Users/910373/AppData/Local/Temp/opencode/"

def b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

IMGS = {
    "ocr":  ("mm_test.png",  "image/png"),
    "chart":("mm_chart.png", "image/png"),
    "geo":  ("mm_geo.png",   "image/png"),
}
IMG_B64 = {k: (f"data:{mime};base64," + b64(DIR + fn)) for k, (fn, mime) in IMGS.items()}

def call(model, content_parts, max_tokens=8000, timeout=300):
    body = {"model": model, "messages": [{"role": "user", "content": content_parts}],
            "temperature": 0, "max_tokens": max_tokens}
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
                    prompt_toks=u.get("prompt_tokens",0),
                    reason_toks=(u.get("completion_tokens_details") or {}).get("reasoning_tokens",0))
    except urllib.error.HTTPError as e:
        return dict(ok=False, status=e.code, error=e.read().decode()[:300])
    except Exception as e:
        return dict(ok=False, status=-1, error=str(e)[:200])

TESTS = [
 ("MM1_OCR", "基础视觉OCR", "ocr",
  "这张图里有什么文字？进度条填充了多少百分比？简短回答。"),
 ("MM2_CHART", "密集图表理解", "chart",
  "描述这张图表：1) 图表类型 2) X轴和Y轴分别表示什么、刻度单位 3) 图中气泡大小代表什么 4) 找到中国(China)和美国(United States)的大致位置并描述它们的相对关系。"),
 ("MM3_GEO", "几何视觉推理", "geo",
  "这是一道几何题：两条平行线之间有一条折线（zig-zag），已知三个角分别是40°、80°、20°，求图中标注的x角度。请先描述你从图中看到的结构，再求解x。"),
]

all_results = {}
for m in MODELS:
    print(f"\n{'='*66}\nMODEL: {m}\n{'='*66}")
    all_results[m] = {}
    for tid, cat, imgkey, prompt in TESTS:
        parts = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": IMG_B64[imgkey]}},
        ]
        r = call(m, parts)
        all_results[m][tid] = r
        if r["ok"]:
            print(f"\n[{tid}] ({cat}) {r['elapsed']}s prompt_toks={r['prompt_toks']} reason_toks={r['reason_toks']} finish={r['finish']}")
            print("---")
            print(r["content"][:1500])
            print("---")
        else:
            print(f"\n[{tid}] ({cat}) HTTP {r['status']}: {r['error'][:200]}")

with open(DIR + "ds_mm_results.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)
print("\nSaved mm results.")
