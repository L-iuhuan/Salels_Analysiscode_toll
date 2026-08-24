# -*- coding: utf-8 -*-
"""
批次④b 车道B：真实编排契约测试（test_run_all.py）。

覆盖 run_all / shared.fingerprint / run_chain 的保留接口契约：
  1. 指纹决定性（compute_dashboard_fingerprint 两次相等；settings_customer.py 改动→指纹变→字节还原→复原）
  2. 阶段产物校验（_verify_stage_artifacts 对当前 output/ 全部通过；monkeypatch OUTPUT_DIR 到空目录→正确报缺失）
  3. 基线工具自洽（freeze_baseline → golden_diff rescan → 零漂移 exit 0）
  4. 看板门禁（run_chain._gate_dashboard_only 对当前新鲜 preagg.json 放行；篡改指纹 → SystemExit 且码≠0）

运行（从 sales_analytics_platform 目录）：
    python -m pytest test\\test_run_all.py -q
注意：禁止触发全量跑批；本套测试只读当前 output/ 产物（基线自洽一步会读现有 CSV 两次，约 1-2 分钟）。
"""
import io
import json
import os
import subprocess
import sys
import tempfile

import pytest

# ── 路径 ──────────────────────────────────────────────────────
_PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # sales_analytics_platform
_REPO_ROOT = os.path.dirname(_PKG)                                   # 仓库根
_SCRIPTS = os.path.join(_REPO_ROOT, "scripts")

# conftest.py 已注入 processing/；这里兜底再注入一次（幂等）
_PROC = os.path.join(_PKG, "processing")
if _PROC not in sys.path:
    sys.path.insert(0, _PROC)

import run_all                    # noqa: E402  （有 __main__ 守卫，导入不触发跑批）
from shared import fingerprint    # noqa: E402


def _run_utf8(cmd, timeout):
    """以 UTF-8 运行子进程并读取输出（子进程可能输出中文，禁止用默认 GBK 解码）。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, timeout=timeout)


@pytest.fixture(scope="module")
def platform_dir() -> str:
    """销售分析平台目录（本项目内模块级共用）。"""
    return _PKG


@pytest.fixture(scope="module")
def source_data(platform_dir) -> str:
    """当前 data/ 最新 xlsx（与 run_all.find_source_data 一致）。"""
    p = run_all.find_source_data()
    assert p and os.path.exists(p), "data/ 下无 xlsx"
    return p


# ══════════════════════════════════════════════════════════════
# 用例 1：指纹决定性
# ══════════════════════════════════════════════════════════════
class TestFingerprintDeterminism:
    """compute_dashboard_fingerprint 两次调用结果相等；settings 文件字节级改动灵敏、还原复原。"""

    def test_deterministic(self, platform_dir):
        f1 = fingerprint.compute_dashboard_fingerprint(platform_dir)
        f2 = fingerprint.compute_dashboard_fingerprint(platform_dir)
        assert fingerprint.fingerprints_equal(f1, f2), "两次计算指纹不一致"

    def test_sensitive_and_restorable(self, platform_dir):
        cfg = os.path.join(platform_dir, "processing", "config", "settings_customer.py")
        with open(cfg, "rb") as f:
            orig = f.read()
        try:
            f_before = fingerprint.compute_dashboard_fingerprint(platform_dir)
            # 追加一行注释（字节级）→ 指纹应变
            with open(cfg, "ab") as f:
                f.write(b"\n# pytest tamper marker\n")
            f_after = fingerprint.compute_dashboard_fingerprint(platform_dir)
            assert not fingerprint.fingerprints_equal(f_before, f_after), \
                "settings_customer.py 改动后指纹未变化"
        finally:
            # 字节级还原（禁止 git checkout，有前科）
            with open(cfg, "wb") as f:
                f.write(orig)
        f_restored = fingerprint.compute_dashboard_fingerprint(platform_dir)
        assert fingerprint.fingerprints_equal(f_before, f_restored), \
            "settings_customer.py 字节还原后指纹未复原"


# ══════════════════════════════════════════════════════════════
# 用例 2：阶段产物校验
# ══════════════════════════════════════════════════════════════
class TestStageArtifacts:
    """_verify_stage_artifacts 对当前 output/ 全部通过；对空目录正确报缺失。"""

    def test_all_stages_pass(self, platform_dir):
        for stage in run_all._STAGE_ARTIFACTS:
            missing = run_all._verify_stage_artifacts(stage)
            assert missing == [], f"stage={stage} 关键产物缺失/为空: {missing}"

    def test_missing_on_empty_output(self, tmp_path, monkeypatch):
        # monkeypatch OUTPUT_DIR → 临时空目录 → 全部缺失
        monkeypatch.setattr(run_all, "OUTPUT_DIR", str(tmp_path))
        missing = run_all._verify_stage_artifacts("silver")
        assert set(missing) == set(run_all._STAGE_ARTIFACTS["silver"]), \
            f"空目录下应报全部 silver 产物缺失，实际: {missing}"
        # 其它 stage 同理抽查
        for stage in ("product", "customer", "kpi", "cross_ref"):
            assert set(run_all._verify_stage_artifacts(stage)) == set(run_all._STAGE_ARTIFACTS[stage])


# ══════════════════════════════════════════════════════════════
# 用例 3：基线工具自洽（freeze_baseline → golden_diff rescan → 零漂移）
# ══════════════════════════════════════════════════════════════
class TestBaselineToolchain:
    """基线冻结与对拍工具自洽：freeze 后立即 rescan 必须零漂移 exit 0。"""

    def test_self_consistent(self, platform_dir):
        freeze = os.path.join(_SCRIPTS, "freeze_baseline.py")
        golden = os.path.join(_SCRIPTS, "golden_diff.py")
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "baseline")
            r1 = _run_utf8(
                [sys.executable, freeze, "--platform-dir", platform_dir, "--out-dir", out_dir],
                timeout=420,
            )
            assert r1.returncode == 0, f"freeze_baseline 失败:\n{r1.stdout}\n{r1.stderr}"
            summary = os.path.join(out_dir, "summary.json")
            assert os.path.exists(summary), "freeze_baseline 未产出 summary.json"
            r2 = _run_utf8(
                [sys.executable, golden, "--baseline", summary, "--platform-dir", platform_dir],
                timeout=420,
            )
            assert r2.returncode == 0, \
                f"golden_diff rescan 应零漂移 exit0，实际 exit{r2.returncode}:\n{r2.stdout}\n{r2.stderr}"
            assert "无漂移" in r2.stdout, f"golden_diff 未判定无漂移:\n{r2.stdout}"


# ══════════════════════════════════════════════════════════════
# 用例 4：看板门禁
# ══════════════════════════════════════════════════════════════
class TestDashboardGate:
    """run_chain._gate_dashboard_only：新鲜放行；篡改指纹 → SystemExit 且码≠0。

    注意：run_chain 模块级会替换 sys.stdout（io.TextIOWrapper），与 pytest 捕获冲突；
    故在独立子进程内执行门禁，避免破坏 pytest 的输出捕获。
    """

    _DRIVER = r"""# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, r"{platform}")
sys.path.insert(0, os.path.join(r"{platform}", "processing"))
import run_chain
TAMPER = {tamper}
if TAMPER:
    from shared import fingerprint
    fingerprint.compute_dashboard_fingerprint = lambda *a, **k: {{"excel": None, "tampered": True}}
try:
    run_chain._gate_dashboard_only(r"{source}")
except SystemExit as e:
    code = e.code if e.code is not None else 0
    if TAMPER:
        # 篡改场景：期望非零退出
        sys.exit(0 if code != 0 else 1)
    # 新鲜场景：不应 SystemExit
    sys.exit(1)
sys.exit(2 if TAMPER else 0)  # 篡改场景未抛 SystemExit → 失败；新鲜场景未抛 → 通过
"""

    def _run_gate(self, platform_dir, source_data, tamper):
        driver = self._DRIVER.format(platform=platform_dir, source=source_data,
                                     tamper="True" if tamper else "False")
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(driver)
            driver_path = f.name
        try:
            r = _run_utf8([sys.executable, driver_path], timeout=120)
        finally:
            os.unlink(driver_path)
        return r

    def test_accepts_fresh(self, platform_dir, source_data):
        r = self._run_gate(platform_dir, source_data, tamper=False)
        assert r.returncode == 0, f"新鲜 preagg 应放行，实际 exit{r.returncode}:\n{r.stdout}\n{r.stderr}"
        assert "预聚合缓存新鲜" in r.stdout, f"未输出放行信息:\n{r.stdout}"

    def test_rejects_tampered(self, platform_dir, source_data):
        r = self._run_gate(platform_dir, source_data, tamper=True)
        assert r.returncode == 0, f"篡改指纹应被拒（SystemExit≠0），驱动异常 exit{r.returncode}:\n{r.stdout}\n{r.stderr}"
        assert "错误" in r.stdout and "过期" in r.stdout, f"篡改场景应报缓存过期:\n{r.stdout}"
