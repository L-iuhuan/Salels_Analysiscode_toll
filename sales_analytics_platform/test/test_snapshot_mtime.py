# -*- coding: utf-8 -*-
"""r24 快照 mtime 优先判定测试（存在 / 缺失 / 过期三态）。"""

import json
import os
import sys
import time

import pandas as pd
import pytest

_PROC = os.path.abspath(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "processing"))
if _PROC not in sys.path:
    sys.path.insert(0, _PROC)

from shared.data_cleaning import (  # noqa: E402
    _derive_period_from_path,
    find_snapshot_by_mtime,
)


def _sample_df():
    return pd.DataFrame({
        "金额": [100.5, 200.0],
        "品名": ["A", "B"],
        "日期": pd.to_datetime(["2026-08-01", "2026-08-02"]),
    })


def test_snapshot_fresh_hits(tmp_path):
    """快照存在且 mtime 严格新于 Excel → 命中。"""
    wh = tmp_path / "data_warehouse"
    period_dir = wh / "202608"
    period_dir.mkdir(parents=True)

    src = tmp_path / "财务分析-8月.xlsx"
    src.write_bytes(b"fake")

    pq_path = period_dir / "erp_snapshot.parquet"
    _sample_df().to_parquet(str(pq_path), index=False)
    (period_dir / "manifest.json").write_text(
        json.dumps({"source": {"name": src.name}}), encoding="utf-8")

    # 让 Excel mtime 旧于快照
    now = time.time()
    os.utime(str(src), (now - 10, now - 10))
    os.utime(str(pq_path), (now, now))

    hit = find_snapshot_by_mtime(str(src), str(wh))
    assert hit is not None
    assert hit[0] == str(pq_path)


def test_snapshot_stale_misses(tmp_path):
    """快照存在但 mtime 不新于 Excel → 视为过期，返回 None。"""
    wh = tmp_path / "data_warehouse"
    period_dir = wh / "202608"
    period_dir.mkdir(parents=True)

    src = tmp_path / "财务分析-8月.xlsx"
    src.write_bytes(b"fake")

    pq_path = period_dir / "erp_snapshot.parquet"
    _sample_df().to_parquet(str(pq_path), index=False)

    now = time.time()
    os.utime(str(src), (now, now))
    os.utime(str(pq_path), (now - 10, now - 10))

    assert find_snapshot_by_mtime(str(src), str(wh)) is None


def test_snapshot_missing_misses(tmp_path):
    """仓库不存在或当月无快照 → 返回 None。"""
    src = tmp_path / "财务分析-8月.xlsx"
    src.write_bytes(b"fake")
    assert find_snapshot_by_mtime(str(src), str(tmp_path / "not_exists")) is None


def test_derive_period_from_filename(tmp_path, monkeypatch):
    """文件名含 'X月' 时按文件名推导 period（跨年回退）。"""
    p = tmp_path / "财务分析-1月.xlsx"
    p.write_bytes(b"fake")
    # 当前时间 2026-09，1月应属于上一年
    assert _derive_period_from_path(str(p)) == "202601"
