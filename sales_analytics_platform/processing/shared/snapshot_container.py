# -*- coding: utf-8 -*-
r"""
共享层 · 快照加密容器（r21 第三步：快照随发布分发，明文不落盘）
=====================================================================

背景：data_warehouse\<YYYYMM>\erp_snapshot.parquet 是行级明文。r21 拍板（方案B）：
快照随代码发布分发到共享盘/客户端，但以"加密容器"形态存在（.kbdat），读取时内存解密
直出 DataFrame——明文永不落盘（共享盘与客户端磁盘上都只有容器）。

容器格式（KBD1）：
  b"KBD1" + struct(">I", len(comp)) + sha256(comp).digest(32B) + xor(comp, keystream)
  comp = zlib.compress(parquet_bytes, 6)

安全边界（如实声明）：密钥随代码分发，本方案防"误触双击 / 顺手拷贝 / 明文被无关程序
索引"，不防有技术动机且能读到代码的人——那层防护是共享盘 ACL 的职责。选型动机：
零新增依赖（纯 stdlib，便携环境不动），非常规扩展名无默认关联程序。

使用：
  write_container(df, path)      # df → .kbdat（原子写）
  load_snapshot_frame(path)      # .parquet（本地快路径）或 .kbdat（分发容器）→ df
  快照定位回退（parquet 缺失取 .kbdat）见 data_cleaning.find_matching_snapshot
"""

import hashlib
import io
import os
import struct
import tempfile
import zlib

import pandas as pd

CONTAINER_EXT = ".kbdat"
_MAGIC = b"KBD1"
_HEADER = struct.Struct(">4sI32s")  # magic + 载荷长度 + sha256(comp)

# 混淆密钥（随代码分发；防误触/防拷贝级别，非密码学对抗——见模块 docstring 安全边界）
_KEY_MATERIAL = bytes.fromhex(
    "9f3b7c1e5a2d84f06b12ce47d9a35f80"
    "4e7b2a9c6d15f38b0a47e2c9d5b81f63"
)


def _keystream(n: int) -> bytes:
    """SHA256 计数器模式密钥流（与载荷等长）。"""
    out = bytearray()
    block = 0
    while len(out) < n:
        out += hashlib.sha256(_KEY_MATERIAL + block.to_bytes(8, "big")).digest()
        block += 1
    return bytes(out[:n])


def _xor(data: bytes) -> bytes:
    """等长 XOR（大整数一次异或，纯 Python 下也比逐字节快两个数量级）。"""
    if not data:
        return b""
    ks = _keystream(len(data))
    x = int.from_bytes(data, "big") ^ int.from_bytes(ks, "big")
    return x.to_bytes(len(data), "big")


def pack_parquet_bytes(parquet_bytes: bytes) -> bytes:
    """parquet 字节 → 容器字节。"""
    comp = zlib.compress(parquet_bytes, 6)
    header = _HEADER.pack(_MAGIC, len(comp), hashlib.sha256(comp).digest())
    return header + _xor(comp)


def unpack_parquet_bytes(blob: bytes) -> bytes:
    """容器字节 → parquet 字节。损坏/篡改/非容器一律 ValueError（中文可读）。"""
    if len(blob) < _HEADER.size:
        raise ValueError("快照容器损坏（头部不完整）")
    magic, comp_len, digest = _HEADER.unpack_from(blob, 0)
    if magic != _MAGIC:
        raise ValueError("非快照容器（标识不符）")
    comp = _xor(blob[_HEADER.size:])
    if len(comp) != comp_len:
        raise ValueError(f"快照容器损坏（长度不符：{len(comp)} != {comp_len}）")
    if hashlib.sha256(comp).digest() != digest:
        raise ValueError("快照容器校验失败（内容被改动或传输损坏）")
    try:
        return zlib.decompress(comp)
    except zlib.error as e:
        raise ValueError(f"快照容器损坏（解压失败：{e}）") from e


def write_container(df: pd.DataFrame, path: str):
    """df → .kbdat（先写同目录临时文件再 os.replace，原子写）。"""
    bio = io.BytesIO()
    df.to_parquet(bio, index=False)
    blob = pack_parquet_bytes(bio.getvalue())
    out_dir = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(suffix=".kbdat_tmp", prefix="kbdat_", dir=out_dir)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def load_snapshot_frame(path: str) -> pd.DataFrame:
    """快照统一读取入口：.parquet 直读（本地快路径），.kbdat 容器内存解密直出。"""
    if str(path).lower().endswith(CONTAINER_EXT):
        with open(path, "rb") as f:
            blob = f.read()
        return pd.read_parquet(io.BytesIO(unpack_parquet_bytes(blob)))
    return pd.read_parquet(path)
