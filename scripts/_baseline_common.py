# -*- coding: utf-8 -*-
r"""
批次⓪ 基线工具链 · 共享采集逻辑
=====================================================================

本模块被 freeze_baseline.py（冻结基线）与 golden_diff.py（漂移对比）
共同引用，负责"采集销售分析平台当前产物状态"这一件事，输出一个
纯 JSON 可序列化的 dict。

采集内容：
  1. CSV 画像：output/silver 与 output/gold 下每个 CSV 的
     filename / row_count / columns（有序）/ dtypes /
     schema_hash（col:dtype 对的 sha256）/ 数值列合计（round 6）。
  2. 看板内嵌 JSON：解析 dashboard/dashboard_a.html 里的
     "var X = <json>;" / "const X = <json>;" 顶层赋值，
     输出 top-level keys 清单（name/type/len），并把深度≤3 的
     标量 KPI 抽成扁平点路径 dict（"kpis"）。
  3. 元信息：git HEAD（subprocess）、时间戳、Python 版本、
     data/ 目录文件（name/size/mtime/前 8MB sha256）。

仅依赖标准库 + pandas。
"""

import datetime
import hashlib
import json
import os
import re
import subprocess
import sys

import pandas as pd

# ── 常量 ──
SUM_ROUND = 6            # 数值列合计的舍入精度
KPI_MAX_DEPTH = 3        # KPI 扁平点路径的最大深度（顶层变量名计为第 1 层）
ARRAY_LEN_CAP = 50       # 数组超过该长度时只记录长度
SHA_HEAD_SIZE = 8 * 1024 * 1024  # 前 8MB 的 sha256

# 顶层赋值语句匹配：`var/let/const NAME = `，仅保留全大写变量名，
# 以天然排除模板 JS 里的循环变量（for (var i=0; ...)）与普通逻辑变量；
# 用行首锚定（re.MULTILINE）避免误命中 JSON 字符串里的字面文本。
_VAR_RE = re.compile(
    r"(?m)^\s*(?:var|let|const)\s+([A-Z][A-Z0-9_]*)\s*=\s*"
)
_CSV_ENCODINGS = ("utf-8-sig", "utf-8", "gbk", "latin-1")


# ============================================================
# 基础工具
# ============================================================

def _sha256_head(path, n=SHA_HEAD_SIZE):
    """文件前 n 字节的 sha256（大文件只读头部，够做完整性指纹）。"""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read(n))
    return h.hexdigest()


def _sha256_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _json_safe(v):
    """把 NaN / ±Inf 规整为 None，保证结果可被严格 JSON 序列化。"""
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            return None
    return v


def _is_scalar(v):
    return v is None or isinstance(v, (bool, int, float, str))


def _json_type(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, dict):
        return "object"
    if isinstance(v, list):
        return "array"
    return "other"


def _json_len(v):
    if isinstance(v, dict):
        return len(v)
    if isinstance(v, list):
        return len(v)
    return None


# ============================================================
# CSV 采集
# ============================================================

def _load_csv(path):
    """容错读取 CSV：utf-8-sig 优先，依次回退 utf-8 / gbk / latin-1。"""
    errs = []
    for enc in _CSV_ENCODINGS:
        try:
            return pd.read_csv(path, encoding=enc, low_memory=False)
        except UnicodeDecodeError as e:
            errs.append(e)
            continue
    if errs:
        raise errs[-1]
    raise RuntimeError(f"CSV 读取失败且无编码错误可参考：{path}")


def collect_csv(path):
    """采集单个 CSV 的结构画像。

    读取失败（如并发跑批导致文件半写/被占用）时抛出异常，
    由调用方决定是否等待重试。
    """
    df = _load_csv(path)
    columns = [str(c) for c in df.columns]
    dtypes = {c: str(df[c].dtype) for c in df.columns}
    schema_str = "\n".join(f"{c}:{dtypes[c]}" for c in df.columns)
    numeric_sums = {}
    num_cols = df.select_dtypes(include="number").columns
    for c in num_cols:
        try:
            s = float(df[c].sum())
        except (TypeError, ValueError):
            continue
        if s != s:  # NaN
            s = 0.0
        numeric_sums[str(c)] = round(s, SUM_ROUND)
    return {
        "row_count": int(len(df)),
        "columns": columns,
        "dtypes": dtypes,
        "schema_hash": _sha256_text(schema_str),
        "numeric_sums": numeric_sums,
    }


def collect_csv_dir(layer_dir):
    """采集目录下所有 CSV，返回 {文件名: 记录}。

    文件不存在/读取失败时记录 status=missing/error，不中断整批采集。
    """
    out = {}
    if not os.path.isdir(layer_dir):
        return out
    for f in sorted(os.listdir(layer_dir)):
        if not f.lower().endswith(".csv"):
            continue
        p = os.path.join(layer_dir, f)
        try:
            rec = collect_csv(p)
            rec["status"] = "ok"
        except FileNotFoundError:
            rec = {"status": "missing"}
        except Exception as e:  # noqa: BLE001 —— 采集中任何单文件异常都记录而非中断
            rec = {"status": "error", "error": f"{type(e).__name__}: {e}"}
        rec["filename"] = f
        out[f] = rec
    return out


# ============================================================
# 看板内嵌 JSON
# ============================================================

def _flatten_kpis(value, prefix, depth, out):
    """把看板 JSON 树里的标量 KPI 抽成扁平点路径 dict。

    规则：
      - dict   → 逐 key 递归（深度 +1，超过 KPI_MAX_DEPTH 即止）
      - 标量   → 直接记录值（NaN/Inf 规整为 null）
      - list：
          长度 > ARRAY_LEN_CAP   → 只记 {"__array_len__": N}
          长度 0                 → 只记 {"__array_len__": 0}
          长度 ≤ CAP 且全为标量  → 记录标量列表本身
          长度 ≤ CAP 但含对象    → 只记 {"__array_len__": N}
                                  （避免用下标路径，防排序不稳定造成噪音漂移）
    """
    if depth > KPI_MAX_DEPTH:
        return
    if isinstance(value, dict):
        for k, v in value.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            _flatten_kpis(v, p, depth + 1, out)
    elif isinstance(value, list):
        if len(value) > ARRAY_LEN_CAP or not all(_is_scalar(x) for x in value):
            out[prefix] = {"__array_len__": len(value)}
        else:
            out[prefix] = [_json_safe(x) for x in value]
    else:
        out[prefix] = _json_safe(value)


def parse_dashboard(html_path):
    """解析看板 HTML 内嵌 JSON。

    返回 dict：{vars: [ {name,type,len} ], kpis: {点路径: 值}, errors: []}。
    若文件非空但解析不到任何顶层变量，视为文件半写/损坏，抛出 RuntimeError，
    由调用方等待后重试。
    """
    with open(html_path, "r", encoding="utf-8") as f:
        text = f.read()
    decoder = json.JSONDecoder()
    vars_ = []
    kpis = {}
    errors = []
    seen = set()
    for m in _VAR_RE.finditer(text):
        name = m.group(1)
        if name in seen:
            continue
        try:
            value, _end = decoder.raw_decode(text, m.end())
        except json.JSONDecodeError:
            continue  # 非 JSON 赋值（函数/表达式等），跳过
        seen.add(name)
        vars_.append({"name": name, "type": _json_type(value), "len": _json_len(value)})
        _flatten_kpis(value, name, 1, kpis)
    if text.strip() and not vars_:
        raise RuntimeError(f"解析不到任何顶层 JSON 变量，文件可能被并发改写：{html_path}")
    return {"vars": vars_, "kpis": kpis, "errors": errors}


def collect_dashboard(dashboard_dir):
    """采集 dashboard_a.html 的内嵌 JSON 结构画像。"""
    html_path = os.path.join(dashboard_dir, "dashboard_a.html")
    if not os.path.isfile(html_path):
        return {"status": "missing", "html_path": html_path}
    st = os.stat(html_path)
    try:
        parsed = parse_dashboard(html_path)
    except Exception as e:  # noqa: BLE001
        return {
            "status": "error",
            "html_path": html_path,
            "size": st.st_size,
            "mtime": st.st_mtime,
            "error": f"{type(e).__name__}: {e}",
        }
    parsed["status"] = "ok"
    parsed["html_path"] = html_path
    parsed["size"] = st.st_size
    parsed["mtime"] = st.st_mtime
    return parsed


# ============================================================
# 元信息
# ============================================================

def _git_head(platform_dir):
    """读取仓库 git HEAD（只读命令，不改动任何 git 状态）。"""
    try:
        r = subprocess.run(
            ["git", "-C", platform_dir, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return None


def _git_branch(platform_dir):
    try:
        r = subprocess.run(
            ["git", "-C", platform_dir, "branch", "--show-current"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return None


def collect_metadata(platform_dir):
    """采集元信息：git HEAD / 时间戳 / Python 版本 / data/ 目录指纹。"""
    data_dir = os.path.join(platform_dir, "data")
    files = []
    if os.path.isdir(data_dir):
        for f in sorted(os.listdir(data_dir)):
            p = os.path.join(data_dir, f)
            if not os.path.isfile(p):
                continue
            st = os.stat(p)
            try:
                sha = _sha256_head(p)
            except OSError:
                sha = None
            files.append({
                "name": f,
                "size": st.st_size,
                "mtime": st.st_mtime,
                "sha256_head": sha,
            })
    return {
        "git_head": _git_head(platform_dir),
        "git_branch": _git_branch(platform_dir),
        "timestamp": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "data_dir_files": files,
    }


# ============================================================
# 总入口
# ============================================================

def collect_summary(platform_dir):
    """采集整个平台的基线摘要（silver/gold CSV + 看板内嵌 JSON + 元信息）。"""
    platform_dir = os.path.abspath(platform_dir)
    if not os.path.isdir(platform_dir):
        raise FileNotFoundError(f"平台目录不存在：{platform_dir}")

    silver_dir = os.path.join(platform_dir, "output", "silver")
    gold_dir = os.path.join(platform_dir, "output", "gold")
    dash_dir = os.path.join(platform_dir, "dashboard")

    return {
        "platform_dir": platform_dir,
        "collected_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "csvs": {
            "silver": collect_csv_dir(silver_dir),
            "gold": collect_csv_dir(gold_dir),
        },
        "dashboard": collect_dashboard(dash_dir),
        "metadata": collect_metadata(platform_dir),
    }


def csvs_summary(summary):
    """打印用摘要：返回 (各层文件数, 总行数, 看板变量数, KPI 数)。"""
    counts = {}
    rows = 0
    for layer in ("silver", "gold"):
        recs = summary.get("csvs", {}).get(layer, {})
        counts[layer] = len(recs)
        for rec in recs.values():
            if rec.get("status") == "ok":
                rows += int(rec.get("row_count", 0))
    dash = summary.get("dashboard", {})
    return counts, rows, len(dash.get("vars", [])), len(dash.get("kpis", {}))
