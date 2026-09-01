# -*- coding: utf-8 -*-
"""r21 快照加密容器测试：roundtrip / 防篡改 / 损坏拒绝 / parquet 透传 / 快照定位容器回退。"""

import json
import os
import sys

import pandas as pd
import pytest

_PROC = os.path.abspath(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "processing"))
if _PROC not in sys.path:
    sys.path.insert(0, _PROC)

from shared.snapshot_container import (  # noqa: E402
    CONTAINER_EXT, load_snapshot_frame, unpack_parquet_bytes, write_container,
)
from shared.data_cleaning import find_matching_snapshot  # noqa: E402
from shared.excel_com import sha256_full  # noqa: E402


def _sample_df():
    return pd.DataFrame({
        "金额": [100.5, 200.0, None],
        "品名": ["A", "B", "C"],
        "数量": [1, 2, 3],
        "日期": pd.to_datetime(["2026-07-01", "2026-07-02", None]),
    })


def test_roundtrip_mixed_types(tmp_path):
    df = _sample_df()
    p = tmp_path / f"snap{CONTAINER_EXT}"
    write_container(df, str(p))
    assert p.stat().st_size > 0
    out = load_snapshot_frame(str(p))
    pd.testing.assert_frame_equal(out, df, check_dtype=False)


def test_tamper_detected(tmp_path):
    df = _sample_df()
    p = tmp_path / "snap.kbdat"
    write_container(df, str(p))
    blob = bytearray(p.read_bytes())
    blob[-1] ^= 0xFF  # 篡改最后一字节
    p.write_bytes(bytes(blob))
    with pytest.raises(ValueError):
        load_snapshot_frame(str(p))


def test_truncated_container_rejected():
    with pytest.raises(ValueError):
        unpack_parquet_bytes(b"KBD1\x00\x00\x00")


def test_wrong_magic_rejected():
    with pytest.raises(ValueError):
        unpack_parquet_bytes(b"XXXX" + b"\x00" * 64)


def test_parquet_passthrough(tmp_path):
    df = _sample_df()
    p = tmp_path / "snap.parquet"
    df.to_parquet(str(p), index=False)
    pd.testing.assert_frame_equal(load_snapshot_frame(str(p)), df, check_dtype=False)


def test_find_matching_snapshot_kbdat_fallback(tmp_path):
    """仓里只有 .kbdat（发布分发形态）时，快照定位与读取整链可用。"""
    wh = tmp_path / "data_warehouse"
    period_dir = wh / "202607"
    period_dir.mkdir(parents=True)
    src = tmp_path / "财务分析-7月.xlsx"
    src.write_bytes(b"fake-ciphertext-bytes")
    df = _sample_df()
    write_container(df, str(period_dir / f"erp_snapshot{CONTAINER_EXT}"))
    st = os.stat(str(src))
    man = {"source": {"name": src.name, "size": st.st_size,
                      "sha256_full": sha256_full(str(src))}}
    (period_dir / "manifest.json").write_text(json.dumps(man), encoding="utf-8")

    hit = find_matching_snapshot(str(src), str(wh))
    assert hit is not None, "kbdat-only 仓库应能命中快照"
    hit_path, hit_man = hit
    assert hit_path.endswith(f"erp_snapshot{CONTAINER_EXT}")
    assert hit_man["source"]["name"] == src.name
    pd.testing.assert_frame_equal(load_snapshot_frame(hit_path), df, check_dtype=False)


def test_find_matching_snapshot_rename_tolerant(tmp_path):
    """r21 改名容错：源文件名与 manifest 不同（财务侧常见加日期后缀）但 size+sha256_full
    全同时，按内容身份仍命中；内容不同则正确 miss。"""
    wh = tmp_path / "data_warehouse"
    period_dir = wh / "202607"
    period_dir.mkdir(parents=True)
    src = tmp_path / "财务分析-7月（8.27) .xlsx"  # 名字与 manifest 记录的不同
    src.write_bytes(b"same-ciphertext")
    df = pd.DataFrame({"金额": [9.9]})
    df.to_parquet(str(period_dir / "erp_snapshot.parquet"), index=False)
    st = os.stat(str(src))
    man = {"source": {"name": "财务分析-7月.xlsx", "size": st.st_size,
                      "sha256_full": sha256_full(str(src))}}
    (period_dir / "manifest.json").write_text(json.dumps(man), encoding="utf-8")

    hit = find_matching_snapshot(str(src), str(wh))
    assert hit is not None, "改名但内容相同的源应命中快照"
    pd.testing.assert_frame_equal(load_snapshot_frame(hit[0]), df, check_dtype=False)

    # 内容不同 → 正确 miss（名字和哈希都对不上）
    src.write_bytes(b"changed-ciphertext")
    assert find_matching_snapshot(str(src), str(wh)) is None


def test_snapshot_share_root_fallback(tmp_path, monkeypatch):
    """r22：本地仓 miss 时回退数据盘仓根（模拟 D1\\data_warehouse）。"""
    import shared.data_cleaning as dc

    local_wh = tmp_path / "local_wh"
    local_wh.mkdir()                      # 本地仓为空 → 必 miss
    share_wh = tmp_path / "share_wh"
    period_dir = share_wh / "202607"
    period_dir.mkdir(parents=True)
    src = tmp_path / "财务分析-7月.xlsx"
    src.write_bytes(b"ciphertext")
    df = _sample_df()
    write_container(df, str(period_dir / f"erp_snapshot{CONTAINER_EXT}"))
    st = os.stat(str(src))
    man = {"source": {"name": src.name, "size": st.st_size,
                      "sha256_full": sha256_full(str(src))}}
    (period_dir / "manifest.json").write_text(json.dumps(man), encoding="utf-8")

    monkeypatch.setattr(dc, "_WAREHOUSE_ROOT", str(local_wh))
    monkeypatch.setattr(dc, "share_warehouse_root", lambda: str(share_wh))
    hit = dc.find_snapshot_local_or_share(str(src))
    assert hit is not None, "本地 miss 应回退数据盘仓命中"
    assert hit[0].endswith(f"erp_snapshot{CONTAINER_EXT}")
    pd.testing.assert_frame_equal(load_snapshot_frame(hit[0]), df, check_dtype=False)


def test_snapshot_share_disabled_returns_none(tmp_path, monkeypatch):
    """r22：数据盘回退禁用（share_warehouse_root→None）且本地 miss → 返回 None。"""
    import shared.data_cleaning as dc

    local_wh = tmp_path / "local_wh"
    local_wh.mkdir()
    src = tmp_path / "财务分析-7月.xlsx"
    src.write_bytes(b"ciphertext")
    monkeypatch.setattr(dc, "_WAREHOUSE_ROOT", str(local_wh))
    monkeypatch.setattr(dc, "share_warehouse_root", lambda: None)
    assert dc.find_snapshot_local_or_share(str(src)) is None


def test_share_warehouse_root_resolution(monkeypatch, tmp_path):
    """r22：数据盘仓根三级解析——环境变量优先，无环境变量回内置默认。"""
    import shared.data_cleaning as dc

    monkeypatch.setenv("SALES_DATA_SHARE_DIR", str(tmp_path / "D1"))
    assert dc.share_warehouse_root() == str(tmp_path / "D1" / "data_warehouse")
    monkeypatch.delenv("SALES_DATA_SHARE_DIR", raising=False)
    root = dc.share_warehouse_root()
    assert root.endswith("data_warehouse") and root.startswith("\\\\")
