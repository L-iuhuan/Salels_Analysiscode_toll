# -*- coding: utf-8 -*-
"""r26 多进程 worker 自适应测试：环境变量覆盖、任务数截断、内存预算约束、下限保护。"""

import os
import sys

_PROC = os.path.abspath(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "processing"))
if _PROC not in sys.path:
    sys.path.insert(0, _PROC)

import shared.pool_utils as pu  # noqa: E402


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("SALES_POOL_WORKERS", "2")
    assert pu.safe_worker_count(default=8, task_len=12) == 2
    monkeypatch.setenv("SALES_POOL_WORKERS", "16")   # 覆盖不受任务数以外约束
    assert pu.safe_worker_count(default=4, task_len=12) == 12  # 仍受任务数截断


def test_task_len_cap(monkeypatch):
    monkeypatch.delenv("SALES_POOL_WORKERS", raising=False)
    monkeypatch.setattr(pu, "_avail_phys_gb", lambda: 64.0)
    assert pu.safe_worker_count(default=4, task_len=3) == 3


def test_memory_budget(monkeypatch):
    monkeypatch.delenv("SALES_POOL_WORKERS", raising=False)
    monkeypatch.setattr(pu, "_avail_phys_gb", lambda: 3.0)    # 3GB → 2 worker
    assert pu.safe_worker_count(default=4, task_len=12) == 2
    monkeypatch.setattr(pu, "_avail_phys_gb", lambda: 1.2)    # 极低 → 下限 1
    assert pu.safe_worker_count(default=4, task_len=12) == 1


def test_query_failure_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("SALES_POOL_WORKERS", raising=False)
    monkeypatch.setattr(pu, "_avail_phys_gb", lambda: None)
    assert pu.safe_worker_count(default=4, task_len=12) == 4


def test_real_query_returns_positive_or_none():
    v = pu._avail_phys_gb()
    assert v is None or v > 0
