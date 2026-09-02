# -*- coding: utf-8 -*-
"""r24 数据身份/新鲜度测试：身份构建、新鲜度判定（新/旧/同名重存/禁用/不可达）、
[DATA-ID] 标记单行可解析。"""

import json
import os
import sys
import time

import pytest

_PROC = os.path.abspath(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "processing"))
if _PROC not in sys.path:
    sys.path.insert(0, _PROC)

from shared.data_provenance import (  # noqa: E402
    build_data_identity, check_freshness, identity_banner_lines, report_data_identity,
)


def _mk(path, mtime=None):
    path.write_bytes(b"xlsx-bytes")
    if mtime is not None:
        os.utime(str(path), (mtime, mtime))
    return path


def test_build_identity_fields(tmp_path):
    src = _mk(tmp_path / "财务分析-7月.xlsx", mtime=1787831653)
    man = {"ingest": {"time": "2026-08-27T19:48:00+08:00", "period": "202607"}}
    ident = build_data_identity(str(src), "snapshot_share", row_count=199681, manifest=man)
    assert ident["source_name"] == "财务分析-7月.xlsx"
    assert ident["channel_str"] == "快照(数据盘仓)"
    assert ident["snapshot_ingest_time"].startswith("2026-08-27T19:48")
    assert ident["row_count"] == 199681
    assert ident["freshness"]["checked"] is False


def test_freshness_newer_different_file_stale(tmp_path):
    src = _mk(tmp_path / "src.xlsx", mtime=1000)
    share = tmp_path / "share"
    share.mkdir()
    _mk(share / "财务分析-7月（9.1).xlsx", mtime=2000)
    ident = build_data_identity(str(src), "direct")
    check_freshness(ident, str(src), str(share))
    fr = ident["freshness"]
    assert fr["checked"] is True and fr["is_stale"] is True
    assert fr["newest_share_file"] == "财务分析-7月（9.1).xlsx"


def test_freshness_same_file_not_stale(tmp_path):
    share = tmp_path / "share"
    share.mkdir()
    src = _mk(share / "财务分析-7月.xlsx", mtime=2000)
    ident = build_data_identity(str(src), "direct")
    check_freshness(ident, str(src), str(share))
    assert ident["freshness"]["is_stale"] is False


def test_freshness_not_newer_not_stale(tmp_path):
    src = _mk(tmp_path / "src.xlsx", mtime=2000)
    share = tmp_path / "share"
    share.mkdir()
    _mk(share / "财务分析-6月.xlsx", mtime=1000)
    ident = build_data_identity(str(src), "direct")
    check_freshness(ident, str(src), str(share))
    assert ident["freshness"]["checked"] is True
    assert ident["freshness"]["is_stale"] is False


def test_freshness_disabled_or_unreachable(tmp_path):
    src = _mk(tmp_path / "src.xlsx", mtime=1000)
    ident = build_data_identity(str(src), "direct")
    check_freshness(ident, str(src), None)
    assert ident["freshness"]["checked"] is False
    ident2 = build_data_identity(str(src), "direct")
    check_freshness(ident2, str(src), str(tmp_path / "不存在的共享盘"))
    assert ident2["freshness"]["checked"] is False


def test_marker_single_line_json(tmp_path, capsys):
    src = _mk(tmp_path / "财务分析-7月.xlsx", mtime=1787831653)
    ident = build_data_identity(str(src), "snapshot_local", row_count=10)
    out_json = tmp_path / "out" / "data_identity.json"
    report_data_identity(ident, out_json_path=str(out_json), emit_marker=True)
    captured = capsys.readouterr().out
    marker_lines = [l for l in captured.splitlines() if l.startswith("[DATA-ID] ")]
    assert len(marker_lines) == 1, "标记必须单行"
    payload = json.loads(marker_lines[0][len("[DATA-ID] "):])
    assert payload["source_name"] == "财务分析-7月.xlsx"
    assert payload["channel_str"] == "快照(本地仓)"
    assert os.path.isfile(str(out_json)), "身份 json 应落盘"
    assert any("数据身份" in l for l in identity_banner_lines(ident))
