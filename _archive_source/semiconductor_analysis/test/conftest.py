"""
共享测试基础设施：路径、中间件(pickle)管理、日志、测试结果结构。

独立运行示例：
    python -c "from test.conftest import p; print(p.DATA_FILE)"

所有 phase 脚本通过此模块统一路径和缓存逻辑。
"""

import sys, os, pickle, json, time, warnings
from datetime import datetime
from typing import Any, Optional
from dataclasses import dataclass, field, asdict

# 仅忽略pandas类型推断警告，保留DeprecationWarning等关键信息
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*is_period_dtype.*")

# ── 路径 ──────────────────────────────────────────────────────
_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_TEST_DIR)
sys.path.insert(0, PROJECT_ROOT)

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DIAG_DIR = os.path.join(PROJECT_ROOT, "output", "test_diag")
CHART_DIR = os.path.join(DIAG_DIR, "charts")
PKL_PATH = os.path.join(DIAG_DIR, "_intermediate.pkl")

# 自动检测数据文件（取第一个 .xlsx）
def _find_data_file() -> str:
    candidates = [f for f in os.listdir(DATA_DIR) if f.endswith(".xlsx")]
    if not candidates:
        raise FileNotFoundError(f"在 {DATA_DIR} 中未找到 .xlsx 数据文件")
    return os.path.join(DATA_DIR, sorted(candidates)[-1])  # 取最新的

DEFAULT_DATA_FILE = _find_data_file()

# ── 中间件管理 ────────────────────────────────────────────────

def save_intermediates(data: dict, path: str = PKL_PATH) -> str:
    """序列化中间数据到 pickle，供 Phase 2/3 复用。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(data, f)
    return path


def load_intermediates(path: str = PKL_PATH) -> dict:
    """加载 Phase 1 保存的中间数据。"""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"中间件 {path} 不存在。请先运行 phase1_load.py。"
        )
    with open(path, "rb") as f:
        return pickle.load(f)


def has_intermediates(path: str = PKL_PATH) -> bool:
    """检查中间件是否存在。"""
    return os.path.exists(path)


# ── 日志 ───────────────────────────────────────────────────────

def log(msg: str, sep: str = "=", width: int = 70):
    """带分隔线的日志输出。"""
    print()
    print(msg)
    print(sep * width)


def header(msg: str):
    """大标题。"""
    n = len(msg)
    print()
    print("=" * (n + 6))
    print(f"==  {msg}  ==")
    print("=" * (n + 6))


# ── 测试结果结构 ───────────────────────────────────────────────

@dataclass
class TestCaseResult:
    """单个测试用例的结果。"""
    id: str                     # 如 "TEST-A"
    name: str                   # 中文名
    status: str = ""            # "PASS" | "FAIL" | "SKIP" | "WARN"
    summary: str = ""           # 一句话总结
    details: dict = field(default_factory=dict)  # 关键指标
    error: str = ""             # 异常信息

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TestSuiteResult:
    """整个测试套件的结果。"""
    suite_name: str = ""
    timestamp: str = ""
    duration_s: float = 0.0
    data_file: str = ""
    test_cases: list = field(default_factory=list)
    summary: dict = field(default_factory=lambda: {
        "total": 0, "pass": 0, "fail": 0, "skip": 0, "warn": 0
    })

    def add(self, case: TestCaseResult):
        self.test_cases.append(case)
        s = self.summary
        s["total"] += 1
        if case.status == "PASS":
            s["pass"] += 1
        elif case.status == "FAIL":
            s["fail"] += 1
        elif case.status == "SKIP":
            s["skip"] += 1
        elif case.status == "WARN":
            s["warn"] += 1

    def to_dict(self) -> dict:
        return {
            "suite_name": self.suite_name,
            "timestamp": self.timestamp,
            "duration_s": round(self.duration_s, 1),
            "data_file": self.data_file,
            "summary": self.summary,
            "test_cases": [c.to_dict() for c in self.test_cases],
        }


# ── 输出写入 ───────────────────────────────────────────────────

def save_summary_json(result: TestSuiteResult, path: str = None):
    """保存 JSON 测试摘要到 DIAG_DIR。"""
    if path is None:
        path = os.path.join(DIAG_DIR, "test_summary.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
    return path


def save_markdown_report(result: TestSuiteResult, path: str = None):
    """保存 Markdown 测试报告到 DIAG_DIR。"""
    if path is None:
        path = os.path.join(DIAG_DIR, "BATCH_A_TEST_REPORT.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)

    lines = []
    lines.append("# 测试评估报告（自动化生成）\n")
    lines.append(f"**测试日期**: {result.timestamp}")
    lines.append(f"**测试套件**: {result.suite_name}")
    lines.append(f"**数据文件**: {result.data_file}")
    lines.append(f"**执行时长**: {result.duration_s:.1f}s")
    lines.append("")

    # 汇总表
    s = result.summary
    lines.append("## 测试结果汇总\n")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 总数 | {s['total']} |")
    lines.append(f"| PASS | {s['pass']} |")
    lines.append(f"| FAIL | {s['fail']} |")
    lines.append(f"| WARN | {s['warn']} |")
    lines.append(f"| SKIP | {s['skip']} |")
    lines.append(f"| 通过率 | {s['pass']/max(s['total'],1)*100:.0f}% |")
    lines.append("")

    # 逐项
    lines.append("## 逐项测试结果\n")
    for tc in result.test_cases:
        icon = {"PASS": "[OK]", "FAIL": "[FAIL]", "SKIP": "[SKIP]", "WARN": "[WARN]"}.get(tc.status, "[?]")
        lines.append(f"### {icon} {tc.id}: {tc.name}")
        lines.append(f"**状态**: {tc.status}")
        lines.append(f"**摘要**: {tc.summary}")
        if tc.details:
            lines.append("**关键指标**:")
            for k, v in tc.details.items():
                lines.append(f"- {k}: {v}")
        if tc.error:
            lines.append(f"**错误**: {tc.error}")
        lines.append("")

    # 附录
    lines.append("---")
    lines.append(f"*报告自动生成于 {result.timestamp}*")

    content = "\n".join(lines)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def save_diag_csv(df, name: str):
    """保存诊断 CSV 到 DIAG_DIR。"""
    path = os.path.join(DIAG_DIR, f"diag_{name}.csv")
    os.makedirs(DIAG_DIR, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


# ── 辅助函数 ───────────────────────────────────────────────────

def ensure_diag_dir():
    """确保诊断输出目录存在。"""
    os.makedirs(DIAG_DIR, exist_ok=True)
    os.makedirs(CHART_DIR, exist_ok=True)
