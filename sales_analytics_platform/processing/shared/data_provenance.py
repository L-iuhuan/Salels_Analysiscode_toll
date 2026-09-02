# -*- coding: utf-8 -*-
r"""
共享层 · 数据身份与新鲜度（r24：数据可见性改善第 1+2 层）
=====================================================================

问题背景：客户端跑批用的是哪份数据（本地快照 / 数据盘快照 / 本机直读）、是不是最新，
使用人员看不见——对结果的理解决策有偏差风险。本模块在跑批时构建"数据身份"并做
新鲜度检查，三路输出：
  1) 控制台横幅（跑批日志立即可见）
  2) output\dashboard\data_identity.json（供看板 tab-bar 徽标，generate_dashboard 消费）
  3) stdout 单行 [DATA-ID] JSON 标记（供壳 0.3.24 状态条解析，与 [STAGE] 同款协议风格）

身份内容：源文件名/大小/修改时间、读取通道、快照采集时间（manifest 现成字段）、
行数。新鲜度：扫数据共享盘最新"财务分析-*.xlsx"，比当前源更新且内容特征不同 →
stale 告警；共享盘不可达/禁用 → checked=False 静默（不阻断跑批）。

注意：本模块是"可见性层"不是"完整性层"——快照命中的字节一致性由 find_matching_snapshot
的 size+sha256_full 身份键保证；新鲜度同名同大小时的比对用 8MB 头哈希（防"重存不改正"
误报），深度修订漏报由身份键兜底（内容不同则回落直读）。
"""

import datetime
import json
import os

# 读取通道 → 用户可读名。r25：措辞守 r19 中性红线——"明文/解密"字样不得出现在
# 用户可见文案（r24 引入的"(明文直读)/(本机解密)"后缀属违规，已去）；看板徽标
# 已完全不展示通道（见 generate_dashboard._identity_replacements），详情留悬停提示。
CHANNEL_LABELS = {
    "snapshot_local": "快照(本地仓)",
    "snapshot_share": "快照(数据盘仓)",
    "direct": "标准读取",
    "com": "兼容读取",
}


def _fmt_ts(ts):
    if not ts:
        return ""
    try:
        return datetime.datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError):
        return str(ts)


def build_data_identity(source_path, channel, row_count=None, manifest=None):
    """构建数据身份 dict（freshness 由 check_freshness 补充后再落盘/打印）。"""
    st = os.stat(source_path) if source_path and os.path.isfile(source_path) else None
    man = manifest if isinstance(manifest, dict) else {}
    ing = man.get("ingest", {}) if isinstance(man.get("ingest", {}), dict) else {}
    return {
        "source_name": os.path.basename(source_path) if source_path else "",
        "source_size": st.st_size if st else None,
        "source_mtime": st.st_mtime if st else None,
        "source_mtime_str": _fmt_ts(st.st_mtime) if st else "",
        "channel": channel,
        "channel_str": CHANNEL_LABELS.get(channel, channel),
        "snapshot_ingest_time": ing.get("time"),
        "snapshot_period": ing.get("period"),
        "row_count": int(row_count) if row_count is not None else None,
        "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "freshness": {"checked": False, "is_stale": False, "newest_share_file": None,
                      "newest_share_mtime_str": "", "note": ""},
    }


def check_freshness(ident, source_path, data_share_dir):
    """扫数据共享盘最新 财务分析-*.xlsx 与当前源比对，更新且内容特征不同 → stale。

    便宜优先：mtime（+60s 容差）+ 文件名/大小判定为主；同名同大小时比 8MB 头哈希
    （防"重存不改正"误报）。不可达/禁用（data_share_dir 空/None/扫不动）→ checked=False。
    就地更新 ident["freshness"] 并返回 ident。
    """
    fr = ident["freshness"]
    if not data_share_dir:
        fr["note"] = "数据共享盘未配置/禁用，跳过检查"
        return ident
    try:
        files = [os.path.join(data_share_dir, f) for f in os.listdir(data_share_dir)
                 if f.startswith("财务分析-") and f.endswith(".xlsx") and not f.startswith("~$")]
    except OSError:
        fr["note"] = "数据共享盘不可达，跳过检查"
        return ident
    if not files:
        fr["note"] = "共享盘无比对文件"
        return ident
    if not source_path or not os.path.isfile(source_path):
        fr["note"] = "当前源文件不存在（快照按名回溯），跳过检查"
        return ident
    newest = max(files, key=os.path.getmtime)
    fr["checked"] = True
    fr["newest_share_file"] = os.path.basename(newest)
    fr["newest_share_mtime_str"] = _fmt_ts(os.path.getmtime(newest))
    if os.path.abspath(newest) == os.path.abspath(source_path):
        fr["note"] = "当前源即共享盘最新文件"
        return ident
    st_src, st_new = os.stat(source_path), os.stat(newest)
    if st_new.st_mtime <= st_src.st_mtime + 60:
        fr["note"] = "共享盘最新文件不比当前源新"
        return ident
    if os.path.basename(newest) != os.path.basename(source_path) or st_new.st_size != st_src.st_size:
        fr["is_stale"] = True
    else:
        from shared.excel_com import sha256_head
        try:
            if sha256_head(newest) != sha256_head(source_path):
                fr["is_stale"] = True
            else:
                fr["note"] = "共享盘同名文件头一致（疑重存），不算更新"
        except OSError:
            fr["is_stale"] = True  # 读不了宁可疑（告警层语义）
    return ident


def identity_banner_lines(ident):
    """控制台横幅行（list[str]，调用方逐行 print）。"""
    fr = ident.get("freshness", {})
    lines = [f"  [数据身份] 源文件: {ident.get('source_name', '')}"
             f" ({(ident.get('source_size') or 0) / 1e6:.1f}MB, 修改于 {ident.get('source_mtime_str', '')})"]
    line2 = f"            读取通道: {ident.get('channel_str', '')}"
    if ident.get("snapshot_ingest_time"):
        line2 += " | 快照采集: " + str(ident["snapshot_ingest_time"])[:16].replace("T", " ")
    if ident.get("row_count") is not None:
        line2 += f" | 行数: {ident['row_count']:,}"
    lines.append(line2)
    if fr.get("checked"):
        if fr.get("is_stale"):
            lines.append(f"  [新鲜度!!] 共享盘存在更新数据文件: {fr.get('newest_share_file')}"
                         f"（{fr.get('newest_share_mtime_str')}），本看板基于 {ident.get('source_name')}")
        elif fr.get("note"):
            lines.append(f"  [新鲜度] {fr['note']}")
    else:
        lines.append(f"  [新鲜度] {fr.get('note') or '未检查'}")
    return lines


def report_data_identity(ident, out_json_path=None, emit_marker=True):
    """打印横幅 + 原子落 json + 打 [DATA-ID] 单行 JSON 标记（壳解析用）。"""
    for line in identity_banner_lines(ident):
        print(line)
    if out_json_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_json_path)), exist_ok=True)
        tmp = out_json_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(ident, f, ensure_ascii=False, indent=2)
        os.replace(tmp, out_json_path)
    if emit_marker:
        slim = {k: ident.get(k) for k in ("source_name", "source_mtime_str", "channel_str",
                                          "snapshot_ingest_time", "row_count")}
        slim["freshness"] = ident.get("freshness", {})
        print("[DATA-ID] " + json.dumps(slim, ensure_ascii=False), flush=True)
