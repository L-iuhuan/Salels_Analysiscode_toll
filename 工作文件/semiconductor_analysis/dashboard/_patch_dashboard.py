# -*- coding: utf-8 -*-
"""
就地修补 dashboard_a.html：
1. C面：把内嵌的无样式 lifecycle body 替换成 iframe，指向同目录的 product_lifecycle.html
2. E面：修 eDecompSwitch 里的 top_cust 拼写 bug
不重跑数据 pipeline，只改 HTML 本身。
"""
import re
from pathlib import Path

HTML = Path(__file__).parent / "dashboard_a.html"
raw = HTML.read_text(encoding="utf-8")
orig_len = len(raw)

# --- Fix 1: C面整段替换 -------------------------------------------------
# 匹配 <div class="tab-content" id="tabC" ...> ... </div>（含 lc-wrapper 那一整块）
c_pattern = re.compile(
    r'<div class="tab-content" id="tabC"[^>]*>\s*'
    r'<div style="width:100%;height:100%;overflow-y:auto"><div class="lc-wrapper">'
    r'.*?'
    r'</div></div>\s*</div>',
    re.DOTALL,
)
c_new = (
    '<div class="tab-content" id="tabC" style="padding:0;height:calc(100vh - 56px);overflow:hidden">\n'
    '  <iframe src="product_lifecycle.html" '
    'style="width:100%;height:100%;border:0;display:block" '
    'title="产品生命周期"></iframe>\n'
    '</div>'
)
new, n1 = c_pattern.subn(c_new, raw, count=1)
assert n1 == 1, f"C面替换失败，命中次数={n1}"

# --- Fix 2: E面 eDecompSwitch 拼写 bug ---------------------------------
# 原代码：'top_cust':'Cat'（应为 'top_cat':'Cat'）— 存在两处映射对象
new2, n2 = re.subn(r"'top_cust':'Cat'", "'top_cat':'Cat'", new)
# 也顺手把冗余的双三元 fallback 化简为单一映射（避免优先级 bug 引发的静默失败）
# 匹配 var b=document.getElementById('eTab'+{...}[k]||('eTab'+{...}[k]));
switch_pattern = re.compile(
    r"var b=document\.getElementById\('eTab'\+\{[^}]+\}\[k\]\|\|\('eTab'\+(\{[^}]+\}\[k\])\)\);"
)
new3, n3 = switch_pattern.subn(r"var b=document.getElementById('eTab'+\1);", new2)

HTML.write_text(new3, encoding="utf-8")
print(f"[OK] C面 iframe 替换: {n1} 处")
print(f"[OK] E面 top_cust 修正: {n2} 处")
print(f"[OK] E面 eDecompSwitch 化简: {n3} 处")
print(f"文件大小 {orig_len:,} -> {len(new3):,} 字符")
