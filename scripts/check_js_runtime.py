# -*- coding: utf-8 -*-
"""运行时冒烟门禁：在 Node vm 沙箱中执行看板全部内联脚本块。

背景（2026-08-27 事故）：Phase1 把 TYPO/COLOR 定义放在使用点之后 → 加载期
TypeError → 整块脚本死亡（图表/交互全灭）。node --check 只查语法、字符串探针
只查存在性，均无法发现此类"语法正确但运行时引用错误"。

原理：白名单全局沙箱（document/window/echarts 等 DOM 与库桩），未定义标识符
照常 ReferenceError —— 与真实浏览器语义一致。任何脚本块加载期抛错即 exit 1。
用法：python scripts\\check_js_runtime.py [dashboard.html 路径]
"""
import io
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _find_dash_html():
    """r23：最新生成的看板 html——新家 output\dashboard\ 优先，兼容旧 dashboard_a.html。"""
    import glob
    pats = [
        os.path.join(ROOT, "sales_analytics_platform", "output", "dashboard", "销售数据分析看板_*.html"),
        os.path.join(ROOT, "sales_analytics_platform", "dashboard", "dashboard_a.html"),
    ]
    cands = [p for pat in pats for p in glob.glob(pat)]
    return max(cands, key=os.path.getmtime) if cands else pats[-1]


DEFAULT_HTML = _find_dash_html()

RUNNER = r"""
// ===== Node 侧：构建白名单沙箱并逐块执行 =====
const fs = require('fs');
const vm = require('vm');
const path = require('path');

// 万能吸收桩：可调用、可取属性、可当构造函数，任何属性访问都返回另一个桩
function makeAbsorber(name) {
  const fn = function () { return absorber; };
  const absorber = new Proxy(fn, {
    get(target, prop) {
      if (prop === Symbol.toPrimitive) return () => `[stub:${name}]`;
      if (prop === 'toString') return () => `[stub:${name}]`;
      if (prop === 'valueOf') return () => 0;
      if (prop === Symbol.iterator) return function* () {};
      if (prop === 'length') return 0;
      if (prop === 'size') return 0;
      return absorber;
    },
    apply() { return absorber; },
    construct() { return absorber; },
    has() { return true; },
    set() { return true; },
    deleteProperty() { return true; },
    ownKeys() { return []; },
    getOwnPropertyDescriptor(target, prop) {
      if (prop === 'length' || prop === 'size') return { configurable: true, enumerable: true };
      return undefined;
    },
    defineProperty() { return true; },
  });
  return absorber;
}

// DOM 元素桩：常用属性给合理原生值，其余吸收
function makeElement() {
  const base = {
    style: {}, classList: { add(){}, remove(){}, toggle(){}, contains(){ return false; } },
    dataset: {},
    children: [], innerHTML: '', textContent: '', value: '', id: '', className: '',
    width: 800, height: 400, offsetWidth: 800, offsetHeight: 400,
    clientWidth: 800, clientHeight: 400,
    getBoundingClientRect: () => ({ top: 0, left: 0, right: 800, bottom: 400, width: 800, height: 400 }),
    appendChild: () => makeElement(), removeChild: () => {}, remove: () => {},
    addEventListener: () => {}, removeEventListener: () => {},
    setAttribute: () => {}, getAttribute: () => null,
    querySelector: () => makeElement(), querySelectorAll: () => [],
    closest: () => null, contains: () => false, focus: () => {}, click: () => {},
    getContext: () => makeAbsorber('ctx'),
  };
  return new Proxy(base, {
    get(t, p) {
      if (p in t) return t[p];
      if (p === 'parentElement' || p === 'parentNode') return makeElement();
      return makeAbsorber('el.' + String(p));
    },
    set(t, p, v) { t[p] = v; return true; },
  });
}

const echartsStub = makeAbsorber('echarts');
const consoleOrig = console;

const sandbox = {
  console: { log(){}, info(){}, warn(){}, error(){}, debug(){} },
  echarts: echartsStub,
  document: makeAbsorber('document'),
  window: null,
  navigator: { userAgent: 'smoke' },
  location: { href: 'file://smoke', search: '', hash: '' },
  localStorage: { getItem: () => null, setItem(){}, removeItem(){} },
  sessionStorage: { getItem: () => null, setItem(){}, removeItem(){} },
  getComputedStyle: () => ({ getPropertyValue: () => '' }),
  setTimeout: () => 0, clearTimeout(){}, setInterval: () => 0, clearInterval(){},
  requestAnimationFrame: () => 0, cancelAnimationFrame(){},
  alert(){}, confirm: () => false, prompt: () => null,
  Date, Math, JSON, Object, Array, String, Number, Boolean, RegExp, Map, Set,
  WeakMap, WeakSet, Promise, Symbol, Proxy, Reflect, Error, TypeError, RangeError,
  parseInt, parseFloat, isNaN, isFinite, encodeURIComponent, decodeURIComponent,
  Uint8Array, Float64Array, Int32Array, Uint32Array, Uint16Array, Int8Array, Int16Array,
};
sandbox.globalThis = sandbox;
sandbox.self = sandbox;
sandbox.top = sandbox;
sandbox.window = new Proxy(sandbox, {
  get(t, p) { if (p in t) return t[p]; return makeAbsorber('window.' + String(p)); },
  set(t, p, v) { t[p] = v; return true; },
  has() { return true; },
});

// document 桩需要可被 getElementById 返回元素（非吸收）以走过常见分支
sandbox.document = new Proxy({
  getElementById: () => makeElement(),
  querySelector: () => makeElement(),
  querySelectorAll: () => [],
  createElement: () => makeElement(),
  createTextNode: () => makeElement(),
  body: makeElement(),
  documentElement: makeElement(),
  head: makeElement(),
  addEventListener: () => {},
  removeEventListener: () => {},
}, {
  get(t, p) {
    if (p in t) return t[p];
    if (p === 'readyState') return 'complete';
    return makeAbsorber('document.' + String(p));
  },
  set(t, p, v) { t[p] = v; return true; },
});

const ctx = vm.createContext(sandbox);

const blocksJson = process.argv[2];
const blocks = JSON.parse(fs.readFileSync(blocksJson, 'utf-8'));
let failed = 0;
blocks.forEach((code, i) => {
  if (!code || !code.trim()) return;
  try {
    vm.runInContext(code, ctx, { filename: 'block' + i + '.js' });
  } catch (e) {
    failed++;
    consoleOrig.error('BLOCK ' + i + ' FAILED: ' + (e && e.constructor && e.constructor.name) + ': ' + (e && e.message));
    consoleOrig.error('  at ' + ((e && e.stack) || '').split('\\n').slice(1, 3).join(' | '));
  }
});
if (failed > 0) { consoleOrig.error('RUNTIME SMOKE: ' + failed + ' block(s) failed'); process.exit(1); }
consoleOrig.log('RUNTIME SMOKE: ALL OK (' + blocks.filter(b => b && b.trim()).length + ' blocks executed, no load-time errors)');
"""


def main():
    html_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HTML
    if not os.path.exists(html_path):
        print(f"[运行时冒烟] 看板 HTML 不存在: {html_path}（先跑生成）")
        sys.exit(2)
    html = io.open(html_path, encoding="utf-8").read()
    blocks = re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)
    inner = [b for b in blocks if b.strip()]
    if not inner:
        print("[运行时冒烟] 未找到内联脚本块")
        sys.exit(2)

    tmpdir = tempfile.mkdtemp(prefix="jsruntime_")
    runner_path = os.path.join(tmpdir, "runner.js")
    blocks_path = os.path.join(tmpdir, "blocks.json")
    io.open(runner_path, "w", encoding="utf-8").write(RUNNER)
    io.open(blocks_path, "w", encoding="utf-8").write(
        __import__("json").dumps(inner, ensure_ascii=False)
    )
    r = subprocess.run(
        ["node", runner_path, blocks_path],
        capture_output=True, text=True, timeout=120,
        env={**os.environ, "NODE_OPTIONS": "--no-warnings"},
    )
    out = (r.stdout or "") + (r.stderr or "")
    for line in out.strip().splitlines():
        print("  " + line)
    if r.returncode != 0:
        print(f"[运行时冒烟] FAIL（exit {r.returncode}）——存在加载期脚本错误")
        sys.exit(1)
    print("[运行时冒烟] PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()
