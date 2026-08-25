# -*- coding: utf-8 -*-
"""
Dashboard 自缓存指纹（批次③ 车道D 与 车道P 共享契约）。

提供：
  compute_dashboard_fingerprint(platform_dir, excel_path=None) -> dict
  fingerprints_equal(a, b) -> bool

 指纹键（严格按共享接口契约）：
  excel          : {name, size, mtime, sha256_8mb}（data/ 最新 xlsx；excel_path 可显式传入）
  settings       : processing/config/settings*.py 三个文件拼接（LF 归一）后的 sha256
  dashboard_code : dashboard/generate_dashboard.py（LF 归一）sha256
  template       : dashboard/template.html（LF 归一）sha256
  outputs        : output/silver 与 output/gold 全部文件的 (文件名+大小+mtime) 有序列表 sha256
  dept_md        : data/部门-人员-职务对应.md 的 {size, mtime, sha256全文}（批次③车道P 契约扩展：
                   该文件影响看板 D_DEPT_LIST/F_DEPT_MARGINS，须纳入指纹防漏）

  不入指纹的说明（W4 并入后修订）：R 面总体文档 dashboard/risk_action_*.md **不入指纹**——
  其内容在两路径（全算/缓存命中）都实时从 md 现算（同 C面毛利率轴"永远现算"模式），
  人工审定编辑不需要使缓存失效，否则"改文档→秒级重渲染"流程会被门禁误拦。

 说明：存量 preagg.json 指纹缺 dept_md 键时，fingerprints_equal（严格 ==）判"不新鲜"，
       促使一次全量重跑重盖戳（批次③车道P 契约扩展行为）。


缓存文件约定（车道D 使用）：output/dashboard/preagg.json = {"fingerprint": {...}, "payload": {...}}
"""
import hashlib
import json
import os

_SHA_HEAD_SIZE = 8 * 1024 * 1024  # 与批次⓪ _baseline_common 一致的 8MB 头部指纹


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _read_lf_norm(path: str) -> str:
    """读取文本并做 LF 归一（\r\n / \r → \n），保证跨平台指纹一致。"""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read().replace("\r\n", "\n").replace("\r", "\n")


def _excel_fingerprint(excel_path: str):
    if not excel_path or not os.path.isfile(excel_path):
        return None
    st = os.stat(excel_path)
    with open(excel_path, "rb") as f:
        head = f.read(_SHA_HEAD_SIZE)
    return {
        "name": os.path.basename(excel_path),
        "size": st.st_size,
        "mtime": st.st_mtime,
        "sha256_8mb": hashlib.sha256(head).hexdigest(),
    }


def _latest_excel(platform_dir: str):
    """与 generate_dashboard.py 一致的取数逻辑：data/ 下最新 mtime 的 .xlsx。"""
    cands = sorted(
        [f for f in os.listdir(os.path.join(platform_dir, "data"))
         if f.lower().endswith(".xlsx") and not f.startswith("~$")],
        key=lambda n: os.path.getmtime(os.path.join(platform_dir, "data", n)),
        reverse=True,
    )
    return os.path.join(platform_dir, "data", cands[0]) if cands else None


def compute_dashboard_fingerprint(platform_dir: str, excel_path: str = None) -> dict:
    platform_dir = os.path.abspath(platform_dir)
    if excel_path is None:
        excel_path = _latest_excel(platform_dir)

    # settings: 三个 settings*.py（settings.py / settings_product.py / settings_customer.py）拼接 LF 归一 sha256
    settings_dir = os.path.join(platform_dir, "processing", "config")
    settings_parts = []
    for name in sorted(n for n in os.listdir(settings_dir) if n.startswith("settings") and n.endswith(".py")):
        settings_parts.append(_read_lf_norm(os.path.join(settings_dir, name)))
    # faces.yaml 也进 settings 键（W4 插拔：面开关影响计算与输出，变更必须使缓存失效）
    faces_file = os.path.join(platform_dir, "dashboard", "faces.yaml")
    if os.path.isfile(faces_file):
        settings_parts.append(_read_lf_norm(faces_file))
    settings = _sha256_text("\n".join(settings_parts))

    # dashboard_code / template
    dash_file = os.path.join(platform_dir, "dashboard", "generate_dashboard.py")
    tpl_file = os.path.join(platform_dir, "dashboard", "template.html")
    dashboard_code = _sha256_text(_read_lf_norm(dash_file))
    template = _sha256_text(_read_lf_norm(tpl_file))

    # outputs: output/silver 与 output/gold 全部文件 (文件名+大小+mtime) 有序列表 sha256
    recs = []
    for sub in ("silver", "gold"):
        d = os.path.join(platform_dir, "output", sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            p = os.path.join(d, fn)
            if not os.path.isfile(p):
                continue
            st = os.stat(p)
            recs.append((sub, fn, st.st_size, st.st_mtime))
    outputs = _sha256_text(json.dumps(recs, ensure_ascii=False, default=str))

    # dept_md: data/部门-人员-职务对应.md（影响看板 D_DEPT_LIST/F_DEPT_MARGINS；批次③车道P 契约扩展）
    dept_md = None
    dept_path = os.path.join(platform_dir, "data", "部门-人员-职务对应.md")
    if os.path.isfile(dept_path):
        st = os.stat(dept_path)
        with open(dept_path, "rb") as f:
            dept_content = f.read()
        dept_md = {
            "size": st.st_size,
            "mtime": st.st_mtime,
            "sha256": hashlib.sha256(dept_content).hexdigest(),
        }

    return {
        "excel": _excel_fingerprint(excel_path),
        "settings": settings,
        "dashboard_code": dashboard_code,
        "template": template,
        "outputs": outputs,
        "dept_md": dept_md,
    }


def fingerprints_equal(a, b) -> bool:
    """两个指纹字典是否一致（严格相等）。"""
    return a == b
