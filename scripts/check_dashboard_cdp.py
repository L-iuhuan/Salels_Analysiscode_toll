# -*- coding: utf-8 -*-
r"""
CDP 产物测试门禁 · file:// 直开看板 HTML 做运行时冒烟断言
=====================================================================

把「file:// 直开产物人工验证」固化为可重复门禁脚本（playwright Python 版）：

  python scripts/check_dashboard_cdp.py            # 自动定位最新产物
  python scripts/check_dashboard_cdp.py --html <产物路径>

产物定位（参照壳端 open_dashboard 与 check_js_syntax 的双目录逻辑）：
  优先 output\dashboard\销售数据分析看板_*.html，兼容 dashboard\*.html；
  跳过模板/测试页（template*、*_test*），取 mtime 最新。

断言清单（STATIC_CHECKS + main 内构造的 ①，可扩展——每条 = {名称, 函数}，新增断言往列表里加即可）：
  ① JS 零控制台错误（console error + pageerror 均计）
  ② A 面地域区存在（#sec-geo）
  ③ B 面客户列表渲染（#bList 子节点 > 0）
  ④ 终端客户（代理）视图可用（bSetMode('agent') 后 #bList 子节点 > 0）
  ⑤ 地图 canvas 已渲染（#geoMap 内部 canvas，echarts 默认 canvas 渲染器）
  ⑥ R 面 KPI 卡渲染（切到 R 面后 #tabR .kc 卡数 > 0）

结果：
  全部通过  → 打印 "CDP: ALL OK (n checks)"，exit 0
  任一失败  → 打印失败项明细，exit 1
  HTML 缺失 → 提示「先跑生成」，exit 2
"""

import argparse
import glob
import io
import os
import sys

# GBK/UTF-8 控制台兼容：防止非 GBK 字符在 print 时抛 UnicodeEncodeError 中断门禁
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer,
                                  encoding=sys.stdout.encoding or "utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer,
                                  encoding=sys.stderr.encoding or "utf-8", errors="replace")
except (AttributeError, OSError, ValueError):
    pass

# 仓库根目录 = 本脚本所在目录的上一级
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 断言等待上限：产物 14MB+ 数据内联，低端机渲染地图/列表需数秒
WAIT_MS = 30_000


def _is_prod_html(name: str) -> bool:
    """排除模板/测试页（与壳端 open_dashboard 同款规则）"""
    return name.endswith(".html") and not name.startswith("template") and "_test" not in name


def find_dash_html() -> str:
    """双目录搜索最新看板产物；找不到时返回主路径（供报错提示）。"""
    dirs = [
        os.path.join(REPO_ROOT, "sales_analytics_platform", "output", "dashboard"),
        os.path.join(REPO_ROOT, "sales_analytics_platform", "dashboard"),
    ]
    cands = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if _is_prod_html(name):
                p = os.path.join(d, name)
                if os.path.isfile(p):
                    cands.append(p)
    if cands:
        return max(cands, key=os.path.getmtime)
    return os.path.join(dirs[0], "销售数据分析看板_*.html")


class Check:
    """单条断言：name 报告用名，fn(page) 返回 (ok, detail)。"""

    def __init__(self, name, fn):
        self.name = name
        self.fn = fn

    def run(self, page):
        ok, detail = self.fn(page)
        return ok, detail


# ── 断言实现 ──────────────────────────────────────────

def _b_list_count(page) -> int:
    return page.evaluate("() => document.getElementById('bList').children.length")


def check_console_errors_factory(console_errors):
    """① 控制台错误由 main 统一收集，这里只读取结果（工厂函数闭包捕获列表）"""
    def _check(page):
        ok = not console_errors
        detail = "0 条" if ok else f"{len(console_errors)} 条: {console_errors[0][:160]}"
        return ok, detail
    return _check


def check_sec_geo(page):
    n = page.locator("#sec-geo").count()
    return n > 0, f"sec-geo 计数={n}"


def check_b_list(page):
    page.evaluate("() => switchTab('B')")
    page.wait_for_function("() => document.getElementById('bList').children.length > 0", timeout=WAIT_MS)
    n = _b_list_count(page)
    return n > 0, f"#bList 子节点={n}"


def check_b_agent_mode(page):
    page.evaluate("() => switchTab('B')")
    page.evaluate("() => bSetMode('agent')")
    page.wait_for_function("() => document.getElementById('bList').children.length > 0", timeout=WAIT_MS)
    n = _b_list_count(page)
    return n > 0, f"代理视图 #bList 子节点={n}"


def check_map_canvas(page):
    # ③④切到了 B 面，须先切回 A 面再断言（隐藏状态下 canvas 判 hidden 会误报）
    page.evaluate("() => switchTab('A')")
    page.wait_for_selector("#geoMap canvas", timeout=WAIT_MS)
    n = page.locator("#geoMap canvas").count()
    return n > 0, f"#geoMap canvas 数={n}"


def check_r_kpi(page):
    page.evaluate("() => switchTab('R')")
    page.wait_for_selector("#tabR .kc", timeout=WAIT_MS)
    n = page.locator("#tabR .kc").count()
    return n > 0, f"#tabR .kc KPI 卡数={n}"


# 断言清单（静态部分）：新增断言在此追加即可。
# ①控制台错误断言在 main 内用 check_console_errors_factory 构造（需捕获收集列表）。
STATIC_CHECKS = [
    Check("② A 面地域区存在(#sec-geo)", check_sec_geo),
    Check("③ B 面客户列表渲染(#bList)", check_b_list),
    Check("④ 终端客户(代理)视图可用", check_b_agent_mode),
    Check("⑤ 地图 canvas 已渲染(#geoMap)", check_map_canvas),
    Check("⑥ R 面 KPI 卡渲染(#tabR .kc)", check_r_kpi),
]


def main():
    ap = argparse.ArgumentParser(description="CDP 产物测试门禁：file:// 直开看板 HTML 做运行时断言")
    ap.add_argument("--html", help="指定看板产物路径（默认自动定位最新）")
    args = ap.parse_args()

    html_path = args.html or find_dash_html()
    if not os.path.exists(html_path):
        print(f"[错误] 未找到产物 {html_path}")
        print("先跑生成：python sales_analytics_platform/run_chain.py（或 dashboard/generate_dashboard.py）后重试。")
        sys.exit(2)

    print(f"产物: {html_path}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[错误] 未安装 playwright：python -m pip install playwright && python -m playwright install chromium")
        sys.exit(2)

    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context()
        console_errors = []
        page = ctx.new_page()

        def _on_console(msg):
            if msg.type == "error":
                console_errors.append(msg.text)

        def _on_pageerror(err):
            console_errors.append(f"pageerror: {err}")

        page.on("console", _on_console)
        page.on("pageerror", _on_pageerror)

        page.goto("file:///" + os.path.abspath(html_path).replace("\\", "/"))
        # 首屏渲染就绪：A 面 KPI 卡出现（数据内联，file:// 下无需网络）
        try:
            page.wait_for_selector("#kpiRev", timeout=WAIT_MS)
        except Exception:
            pass

        for c in [Check("① JS 零控制台错误", check_console_errors_factory(console_errors))] + STATIC_CHECKS:
            try:
                ok, detail = c.run(page)
            except Exception as e:
                ok, detail = False, f"断言执行异常: {str(e)[:160]}"
            results.append((c.name, ok, detail))
            print(f"[{'PASS' if ok else 'FAIL'}] {c.name} — {detail}")

        browser.close()

    n_fail = sum(1 for _, ok, _ in results if not ok)
    if n_fail:
        print(f"[结果] CDP 产物门禁未通过（{n_fail}/{len(results)} 项失败）")
        sys.exit(1)
    print(f"CDP: ALL OK ({len(results)} checks)")
    sys.exit(0)


if __name__ == "__main__":
    main()
