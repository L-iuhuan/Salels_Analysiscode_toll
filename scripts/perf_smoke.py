# -*- coding: utf-8 -*-
r"""
性能冒烟门禁 · 校验 preagg.json 中的阶段耗时
=====================================================================

解析 sales_analytics_platform/output/dashboard/preagg.json（生成器结尾写入的
耗时记录 dict，含各阶段耗时），做两个断言：

  1. 端到端总耗时  < MAX_TOTAL_SEC     （默认 600s）
  2. 看板段耗时    < MAX_DASHBOARD_SEC （默认 180s）

用法：
  python scripts/perf_smoke.py

结果：
  全部达标       → 打印实际值/阈值，exit 0
  任一超限       → 打印实际值/阈值，exit 1
  文件缺失       → 打印提示，exit 2
  文件内无耗时   → 打印诊断（实际键名），exit 2
"""

import io
import json
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
PREAGG_PATH = os.path.join(REPO_ROOT, "sales_analytics_platform", "output", "dashboard", "preagg.json")

# ── 阈值（秒），顶部常量便于调整 ──
MAX_TOTAL_SEC = 600.0      # 端到端总耗时上限
MAX_DASHBOARD_SEC = 180.0  # 看板段耗时上限

# ── 耗时记录键名 ──
# 生成器结尾写入 preagg.json 的 dict（可能整体挂在某个键下，也可能是顶层 dict）。
# 实际键名以文件为准；此处提供精确键 + 模糊兜底两路匹配，键名变更只需改这里。
TIMING_DICT_KEYS = ["timing", "perf", "stage_time", "duration", "耗时"]
TOTAL_KEYS = ["total", "total_sec", "total_elapsed", "total_s", "总耗时", "end_to_end", "e2e"]
DASHBOARD_KEYS = ["dashboard", "dashboard_sec", "dashboard_elapsed", "dashboard_s",
                  "看板段", "看板", "dash"]

# 判断"某个键像耗时记录"的关键子串（用于诊断打印与模糊兜底）
TIMING_SUBSTRINGS = ["耗时", "elapsed", "duration", "timing", "_sec", "seconds", "cost", "stage"]


def _iter_items(obj, path=()):
    """递归遍历 JSON 树，产出 (路径, 键, 值)。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield (path + (k,), k, v)
            yield from _iter_items(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _iter_items(v, path + (str(i),))


def _looks_like_timing_key(key):
    """模糊判断键名是否与耗时相关。"""
    k = str(key).lower()
    return any(s in k for s in TIMING_SUBSTRINGS)


def _to_seconds(value):
    """把数值 / 字符串（如 "123.4" / "123.4s"）统一转成秒。非数字返回 None。"""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip().lower().rstrip("s秒").strip()
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _find_value(obj, key_set, skip_prefixes=("fingerprint",)):
    """递归查找首个键名命中 key_set 的值（忽略大小写）。

    精确匹配优先；模糊兜底要求值可解析为秒数，并跳过指纹子树——
    fingerprint 全是元数据哈希（如 dashboard_code 的 sha256），绝非耗时。
    """
    exact = {k.lower(): k for k in key_set}
    # 1) 精确匹配
    for path, key, value in _iter_items(obj):
        if path and path[0] in skip_prefixes:
            continue
        if isinstance(key, str) and key.lower() in exact:
            return value
    # 2) 模糊兜底：键名含 key_set 中任一项 且 值可解析为秒数
    for path, key, value in _iter_items(obj):
        if path and path[0] in skip_prefixes:
            continue
        if isinstance(key, str) and any(k.lower() in key.lower() for k in key_set):
            if _to_seconds(value) is not None:
                return value
    return None


def _print_actual_keys(data):
    """打印实际键名（诊断用）：顶层键 + 所有疑似耗时键。"""
    print("  preagg.json 顶层键: " + ", ".join(str(k) for k in (data.keys() if isinstance(data, dict) else ["<非对象>"])))
    hits = [(path, key, value) for path, key, value in _iter_items(data)
            if isinstance(key, str) and _looks_like_timing_key(key)]
    if hits:
        print("  发现的疑似耗时记录:")
        for path, key, value in hits:
            print(f"    {'/'.join(path)} = {value!r}")
    else:
        print("  未发现任何疑似耗时记录（键名中含 耗时/elapsed/duration/timing/_sec/seconds 等的键）")


def main():
    if not os.path.exists(PREAGG_PATH):
        print(f"[错误] 未找到 {PREAGG_PATH}")
        print("先跑完整生成：python sales_analytics_platform/run_chain.py（或 dashboard/generate_dashboard.py）后重试。")
        sys.exit(2)

    try:
        with open(PREAGG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[错误] {PREAGG_PATH} 无法解析: {e}")
        sys.exit(2)

    if not isinstance(data, dict):
        print(f"[错误] {PREAGG_PATH} 顶层不是 dict（实际 {type(data).__name__}），无法读取耗时记录。")
        sys.exit(2)

    print(f"解析 {PREAGG_PATH}")
    _print_actual_keys(data)

    # ── 提取耗时：优先在"耗时 dict"内找，找不到则在整个 JSON 树里兜底 ──
    timing_dict = _find_value(data, TIMING_DICT_KEYS)
    scope = timing_dict if isinstance(timing_dict, dict) else data

    total_val = _find_value(scope, TOTAL_KEYS)
    dash_val = _find_value(scope, DASHBOARD_KEYS)

    if total_val is None and dash_val is None and not isinstance(timing_dict, dict):
        print(f"\n[错误] preagg.json 中未找到耗时记录（期望含「端到端总耗时 / 看板段耗时」的 dict）。")
        print("       请确认生成器已在结尾把各阶段耗时写入 preagg.json，或在脚本顶部调整键名。")
        sys.exit(2)

    total_s = _to_seconds(total_val)
    dash_s = _to_seconds(dash_val)
    if total_s is None and dash_s is None:
        print(f"\n[错误] 找到的耗时字段无法解析为秒数（total={total_val!r}, dashboard={dash_val!r}）。")
        sys.exit(2)

    # ── 断言 ──
    ok = True
    if total_s is not None:
        ok_here = total_s < MAX_TOTAL_SEC
        ok = ok and ok_here
        mark = "OK" if ok_here else "超限"
        print(f"\n[断言] 端到端总耗时: 实际 {total_s:.1f}s < 阈值 {MAX_TOTAL_SEC:.0f}s  →  {mark}")
    else:
        print("\n[跳过] 端到端总耗时: 未找到对应字段（total 类键）")

    if dash_s is not None:
        ok_here = dash_s < MAX_DASHBOARD_SEC
        ok = ok and ok_here
        mark = "OK" if ok_here else "超限"
        print(f"[断言] 看板段耗时:   实际 {dash_s:.1f}s < 阈值 {MAX_DASHBOARD_SEC:.0f}s  →  {mark}")
    else:
        print("[跳过] 看板段耗时: 未找到对应字段（dashboard 类键）")

    print("-" * 64)
    if ok:
        print("性能冒烟门禁通过。")
        sys.exit(0)
    print("性能冒烟门禁未通过：耗时超限，请优化或核实阈值。")
    sys.exit(1)


if __name__ == "__main__":
    main()
