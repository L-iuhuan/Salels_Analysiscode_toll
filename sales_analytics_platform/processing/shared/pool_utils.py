# -*- coding: utf-8 -*-
r"""
共享层 · 多进程 worker 数自适应约束（r26：低内存机器 MemoryError 修复）
=====================================================================

背景（2026-09-02 同事机实报）：产品历史画像 ProcessPoolExecutor(4) 的 spawn worker
在 call_queue 反序列化任务时报 MemoryError——开发机内存富余无感，办公机被 WPS 等
常驻程序占用时水位不够，且该池无兜底导致全链失败。

三道防线：
  ① worker 数按可用物理内存约束（ctypes GlobalMemoryStatusEx，纯 stdlib 零新依赖）；
  ② 环境变量 SALES_POOL_WORKERS 显式覆盖（排障/调优用）；
  ③ 池失败自动降级为进程内串行（零 IPC、严格更省内存，只是慢）——由各调用点实现。

使用：safe_worker_count(default=4, task_len=None) → ≥1 的整数。
"""

import os

# 每个 spawn worker（pandas/numpy + 任务负载反序列化）的保守内存预算（GB）
_PER_WORKER_GB = 1.5


def _avail_phys_gb():
    """Windows 可用物理内存 GB（查询失败返回 None，调用方走保守默认）。"""
    try:
        import ctypes

        class _MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        st = _MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
        return st.ullAvailPhys / (1024 ** 3)
    except Exception:
        return None


def safe_worker_count(default=4, task_len=None):
    """worker 数 = min(环境变量覆盖, 默认, 可用内存预算, 任务数)，下限 1。

    内存预算：可用物理内存 // _PER_WORKER_GB（如剩 3GB → 2 个 worker）。
    环境变量 SALES_POOL_WORKERS 为纯数字时优先（不再做内存约束，便于强制复现/调优）。
    """
    env = os.environ.get("SALES_POOL_WORKERS", "").strip()
    if env.isdigit():
        n = max(1, int(env))
        return n if task_len is None else min(n, task_len)
    n = default
    if task_len is not None:
        n = min(n, task_len)
    avail = _avail_phys_gb()
    if avail is not None:
        n = min(n, max(1, int(avail // _PER_WORKER_GB)))
    return max(1, n)
