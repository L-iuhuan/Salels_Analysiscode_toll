# -*- coding: utf-8 -*-
r"""
共享层 · Excel COM 解密读取 + 快照注入（r16 从 scripts\ingest_snapshot.py 抽取，消除重复实现）
=====================================================================

DSE/亿赛通密文 Excel（文件头非 ZIP/PK）无法被 calamine/openpyxl 读取；
全员电脑装有 DSE 客户端 + Office，可经 Excel COM 透明解密读取。

本模块提供：
  read_encrypted_com(path, sheet_name, strict=False)  → (df, used_sheet)
       COM 解密读；strict=True 时指定 sheet 不存在返回 (None, None)。
       源为 UNC 路径时先复制到本地临时文件再 COM（COM 只读本地文件）。
  write_erp_snapshot(df, source_path, warehouse_root, sheet_name, read_seconds=None)
       COM 成功后按 ingest 同款落仓：data_warehouse\<YYYYMM>\erp_snapshot.parquet + manifest
       （r17：manifest source 写 name+size+sha256_full 作身份键，弃 mtime；补全审计字段
       columns/columns_hash/sums/read_seconds；原子写）。
  derive_period / coerce_object_columns / coerce_datetime_columns / sha256_head / sha256_full
  / column_sums（ingest_snapshot 与流水线注入共用的小工具，从 ingest 原样迁来，行为不变）

  调用方：
  - scripts\ingest_snapshot.py（原 _read_encrypted_com/_derive_period/... 改从此导入，行为不变）
  - processing\shared\data_cleaning.read_excel_auto 的 COM 兜底（快照 miss + calamine 失败后）

  r21（2026-09-01，客户机"对方 Excel 正忙"排障落地）：
    ①忙码表补齐 RETRYLATER 等三码（r20 注释声称含、数值实缺）；
    ②DispatchEx 直连微软 Excel 本尊 CLSID，失败回退 ProgID（免疫 WPS 抢注 Excel.Application）；
    ③持续正忙→结束自有实例重开新实例（共 3 轮），全部耗尽才抛中性指引 RuntimeError；
    ④重试痕迹改打 stderr，失败时并入报错、成功时透传（此前 30 次重试日志全被吞）；
    ⑤超时路径 run()→Popen 自管 PID（r18 的 e.pid 实为 AttributeError，杀进程树从未生效）。

"""

import datetime
import hashlib
import json
import os
import pickle
import re
import shutil
import subprocess
import sys
import tempfile
import time
import warnings

import pandas as pd

# 消除 `python -m shared.excel_com` 与 shared 包经 data_cleaning 已导入本模块叠加时的
# runpy 良性告警（"found in sys.modules after import of package ..."，无实际影响）
warnings.filterwarnings("ignore", message=".*found in sys.modules.*")

_SHA_HEAD = 8 * 1024 * 1024  # sha256 前 8MB
# r18 ①：COM 子进程超时上限（DSE 弹窗未处理/Excel 异常时防无限阻塞；正常读取 60-90s）
# r21：300→420——抗忙"弃实例重开"最多 3 轮（每轮退避≈18s+呼叫耗时），需给足预算防正常轮次被误杀
_COM_TIMEOUT = 420

# r20：COM 呼叫被拒退避重试——Excel COM 服务器正忙/有未关闭弹窗时拒绝呼叫
# r21：忙码表补齐——r20 注释即声称含 RETRYLATER 但数值一直缺失（RPC_E_SERVERCALL_RETRYLATER
#       = -2147417846 不在表内）；另补 RPC_E_RETRY / RPC_E_SERVERCALL_REJECTED
_CALL_REJECTED_HRESULTS = (
    -2147418111,  # RPC_E_CALL_REJECTED          被呼叫方拒绝
    -2147418109,  # 0x80010003                   呼叫终止类
    -2147418110,  # RPC_E_CALL_CANCELED          呼叫被取消
    -2147417847,  # RPC_E_RETRY                  服务器请稍后再试
    -2147417846,  # RPC_E_SERVERCALL_RETRYLATER  服务器忙稍后重试
    -2147417845,  # RPC_E_SERVERCALL_REJECTED    消息过滤器拒绝
)
_COM_RETRY_DELAY = 1.5    # 秒
_COM_RETRY_MAX = 12       # r21：单轮退避上限（12×1.5s≈18s/轮，配合实例重开轮数）
_COM_INSTANCE_ROUNDS = 3  # r21：持续正忙时"弃实例→重开新实例"总轮数（含首轮）
_MS_EXCEL_CLSID = "{00024500-0000-0000-C000-000000000046}"  # r21：微软 Excel 本尊 CLSID（直连绕过 ProgID 抢注）


class _ComBusyExhausted(Exception):
    """r21 内部信号：单轮退避预算耗尽（对方持续正忙）——上层据此弃实例重开，不直接面向用户。"""


def _is_call_rejected(e):
    """判断异常是否为"呼叫被拒"类（RPC_E_CALL_REJECTED 等三码）。"""
    hr = getattr(e, "hresult", None)
    if hr is None and getattr(e, "args", None):
        hr = e.args[0]
    return hr in _CALL_REJECTED_HRESULTS


def _com_call(fn, *args, **kwargs):
    """COM 呼叫退避重试包装：呼叫被拒时 sleep 1.5s 重试（上限 _COM_RETRY_MAX 次/轮）。

    r21 两改：①重试日志改打 stderr——父进程失败时会把 stderr 尾部并进报错；此前重试
    痕迹全写 stdout 被捕获吞掉，报错时零可观测（2026-08-31 客户机排障实锤）；
    ②预算耗尽改抛内部 _ComBusyExhausted，由 _read_com_in_process 决定"弃实例重开"
    还是转最终 RuntimeError（用户可见文案保持中性，不出现 DSE/加密/解密/COM 字样）。
    """
    attempts = 0
    while True:
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if not _is_call_rejected(e):
                raise
            if attempts >= _COM_RETRY_MAX:
                raise _ComBusyExhausted(
                    f"持续正忙：呼叫被拒 {attempts} 次") from e
            attempts += 1
            print(f"  [兼容读取] 对方 Excel 正忙，等待重试 ({attempts}/{_COM_RETRY_MAX})…",
                  file=sys.stderr)
            time.sleep(_COM_RETRY_DELAY)


def naive_cell(v):
    """COM 返回的 datetime 单元：去时区（win32timezone 非标准，pandas 会推断成无法序列化的 datetime64[tz]）。"""
    if isinstance(v, datetime.datetime):
        if v.tzinfo is not None:
            try:
                return v.replace(tzinfo=None)
            except Exception:
                return v
    return v


def resolve_sheet(ws_names, prefer):
    """优先 prefer（如 DATA_SHEET_NAME），缺失回退首个 sheet。"""
    if prefer in ws_names:
        return prefer
    return ws_names[0] if ws_names else None


def _excel_pids():
    """当前本机 EXCEL.EXE 的 PID 集合（tasklist CSV 解析；失败返回空集，仅用于进程归属）。"""
    try:
        out = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH", "/FI", "IMAGENAME eq EXCEL.EXE"],
            capture_output=True, text=True, timeout=10).stdout
        pids = set()
        for line in out.splitlines():
            parts = [p.strip('"') for p in line.split('","')]
            if len(parts) >= 2 and parts[1].isdigit():
                pids.add(int(parts[1]))
        return pids
    except Exception:
        return set()


def _kill_spawned(pid):
    """r21：结束本 worker 自己拉起、已卡住的 EXCEL.EXE（仅限自有 PID，绝不碰用户进程）。"""
    if not pid:
        return
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                       capture_output=True, timeout=15)
        print(f"  [兼容读取] 已结束卡住的读取进程 PID {pid}", file=sys.stderr)
    except Exception:
        pass


def _best_effort_close(wb, excel):
    """r21：收尾关闭——短重试（3 次、间隔 1s），不占 _com_call 的完整退避预算；
    失败不阻断（进程残留由超时路径的杀进程树与下轮 _kill_spawned 兜底）。"""
    for _ in range(3):
        if wb is None:
            break
        try:
            wb.Close(False)
            wb = None
        except Exception:
            time.sleep(1.0)
    for _ in range(3):
        if excel is None:
            break
        try:
            excel.Quit()
            excel = None
        except Exception:
            time.sleep(1.0)


def _read_com_once(path, sheet_name, strict):
    """单实例一轮读取（r21 自 _read_com_in_process 拆出）。返回 (df, used_sheet) 或 (None, None)。

    r21 两改：①DispatchEx 直连微软 Excel 本尊 CLSID，起不来再回退 ProgID——免疫 WPS 等
    对 Excel.Application ProgID 的抢注（主力 WPS 机器上该劫持真实存在）；
    ②持续正忙（_ComBusyExhausted）时先结束自己拉起的实例再上抛，交上层重开新实例。
    归属自查：Hwnd 反查 PID 优先；失败回退"派发前后 EXCEL.EXE 差集"（唯一新增才认定；
    理论上存在与用户同时刻手启 Excel 的窄竞争，最坏影响为多杀一个刚启动的空实例）。
    """
    import win32com.client
    pids_before = _excel_pids()
    excel = None
    pid = None
    channel = "直连"
    wb = None
    try:
        try:
            excel = _com_call(win32com.client.DispatchEx, _MS_EXCEL_CLSID)
        except _ComBusyExhausted:
            raise
        except Exception as e_cls:
            # CLSID 通道起不来（如 Office 注册损坏）→ 回退 ProgID 通道
            print(f"  [兼容读取] 直连通道不可用（{type(e_cls).__name__}），改走常规通道",
                  file=sys.stderr)
            channel = "常规"
            excel = _com_call(win32com.client.DispatchEx, "Excel.Application")
        try:
            import win32process
            _tid, pid = win32process.GetWindowThreadProcessId(excel.Hwnd)
            if not pid:
                raise ValueError("empty pid")
        except Exception:
            diff = _excel_pids() - pids_before
            pid = next(iter(diff)) if len(diff) == 1 else None
        # 已有 Excel 实例时 Visible/DisplayAlerts 可能不可设置，失败不阻断（解密读仍可用）
        for attr, val in (("Visible", False), ("DisplayAlerts", False), ("EnableEvents", False)):
            try:
                setattr(excel, attr, val)
            except Exception:
                pass
        t0 = time.time()
        # 全部 COM 呼叫套 _com_call 退避重试（对方 Excel 正忙/有弹窗时 RPC_E_CALL_REJECTED 等）；
        # Workbooks 属性访问一并包进 lambda，防"创建成功但取属性时被拒"漏保护
        wb = _com_call(lambda: excel.Workbooks.Open(
            path, ReadOnly=True, UpdateLinks=0, IgnoreReadOnlyRecommended=True))
        sheet_count = _com_call(lambda: wb.Sheets.Count)
        names = [_com_call(lambda i=i: wb.Sheets(i).Name) for i in range(1, sheet_count + 1)]
        if strict and sheet_name not in names:
            return None, None
        target = sheet_name if strict else resolve_sheet(names, sheet_name)
        ws = _com_call(lambda: wb.Sheets(names.index(target) + 1))
        used = _com_call(lambda: ws.UsedRange)
        data = _com_call(lambda: used.Value)
        rows_n = _com_call(lambda: used.Rows.Count)
        cols_n = _com_call(lambda: used.Columns.Count)
        print(f"  [兼容读取] 打开 {time.time() - t0:.1f}s | sheet='{target}' | "
              f"UsedRange {rows_n}x{cols_n} | 通道={channel}")
        # 归一为二维
        if not isinstance(data, (tuple, list)):
            data = ((data,),)
        rows = list(data)
        # COM 日期单元可能带非标准时区（win32timezone），先逐单元去时区，避免 pandas 推断出
        # 无法迭代/序列化的 datetime64[tz] 列
        rows = [[naive_cell(c) for c in r] for r in rows]
        # 列名去重：COM 表头可能有重复列（如"细分市场（新）"出现两次），重名会使 df[col] 返回 DataFrame
        cols = [str(c) for c in rows[0]]
        seen = {}
        out_cols = []
        for c in cols:
            if c in seen:
                seen[c] += 1
                out_cols.append(f"{c}_{seen[c]}")
            else:
                seen[c] = 0
                out_cols.append(c)
        df = pd.DataFrame([list(r) for r in rows[1:]], columns=out_cols)
        # 清理 COM 幽灵空列/空行
        df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
        return df, target
    except _ComBusyExhausted:
        _kill_spawned(pid)
        raise
    finally:
        _best_effort_close(wb, excel)


def _read_com_in_process(path, sheet_name, strict):
    """子进程/主进程共用的实际 COM 读取入口（r18 ① 抽离，返回值可 pickle）。

    r21 抗忙三段式：单轮内每个呼叫退避重试（_com_call）；整轮持续正忙（_ComBusyExhausted）
    则弃实例（杀自有 PID）重开新实例再试，共 _COM_INSTANCE_ROUNDS 轮；全部耗尽才抛
    RuntimeError（附中性指引）。DSE 加密文件：ReadOnly 打开，读目标 sheet UsedRange，
    首行作列名；strict=True 时 sheet 不存在返回 (None, None)。本函数不处理 UNC
    （父进程已转本地临时副本）。返回 (DataFrame, used_sheet) 或 (None, None)。
    """
    last = None
    for rnd in range(1, _COM_INSTANCE_ROUNDS + 1):
        try:
            return _read_com_once(path, sheet_name, strict)
        except _ComBusyExhausted as e:
            last = e
            print(f"  [兼容读取] 第 {rnd}/{_COM_INSTANCE_ROUNDS} 轮读取持续正忙，"
                  f"弃当前实例后重开", file=sys.stderr)
    raise RuntimeError(
        "对方 Excel 持续正忙（已自动重开读取实例仍失败）——请关闭本机 WPS/Excel 窗口"
        "及未处理的对话框后重试；若仍失败，请在任务管理器结束残留 EXCEL.EXE 后重跑。"
    ) from last


def _com_read_worker_main():
    """子进程入口：`python -m shared.excel_com <path> <sheet> <strict> <out_pkl>`（r18 ①）。

    worker 内自行把 processing 目录加入 sys.path（壳端三层嵌套 spawn 下不依赖调用方 cwd）；
    结果 df 用 pickle 写回（不用 parquet——COM df 的 object 列正是 pyarrow 序列化问题）。
    成功写 (df, used_sheet) 或 (None, None)；异常写 ("error", type, msg) 并 exit 1。
    """
    _PROC = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if _PROC not in sys.path:
        sys.path.insert(0, _PROC)
    path, sheet_str, strict_str, out_pkl = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    sheet = int(sheet_str) if sheet_str.isdigit() else sheet_str
    strict = strict_str.lower() == "true"
    try:
        result = _read_com_in_process(path, sheet, strict)
        with open(out_pkl, "wb") as f:
            pickle.dump(result, f)
    except BaseException as e:  # noqa: BLE001 —— worker 兜底：把错误写回父进程
        try:
            with open(out_pkl, "wb") as f:
                pickle.dump(("error", type(e).__name__, str(e)), f)
        except Exception:
            pass
        sys.exit(1)


def read_encrypted_com(path, sheet_name, strict=False):
    """DSE 加密文件：COM 解密读（r18 ①：COM 读取在子进程执行 + 300s 超时）。

    COM 在独立子进程中执行，超时/非零退出即杀进程树并抛 RuntimeError——
    防 DSE 未登录/Excel 弹窗在主进程内无限阻塞。UNC 源先复制到本地临时文件再 COM
    （mkstemp 唯一名加固保留，finally 清理）；sheet 语义与 _read_com_in_process 一致。
    返回 (DataFrame, used_sheet) 或 (None, None)。
    """
    cleanup = None
    if isinstance(path, str) and path.startswith("\\\\"):
        # r17 gamma 加固保留：mkstemp 唯一名 + 保留扩展名 + copy2 失败删半成品再 raise
        fd, _local = tempfile.mkstemp(prefix="dse_com_",
                                      suffix=os.path.splitext(os.path.basename(path))[1] or ".tmp")
        os.close(fd)
        try:
            shutil.copy2(path, _local)
        except Exception:
            try:
                os.remove(_local)
            except OSError:
                pass
            raise
        path = _local
        cleanup = _local
    out_fd, out_pkl = tempfile.mkstemp(suffix=".pkl", prefix="dse_com_out_")
    os.close(out_fd)
    try:
        _PROC = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        cmd = [sys.executable, "-m", "shared.excel_com",
               path, str(sheet_name), "True" if strict else "False", out_pkl]
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"  # worker stdout/stderr 按 UTF-8 捕获（防 GBK 管道解码错乱）
        # r21：run()→Popen 自管 PID——TimeoutExpired 无 pid 属性，r18 的 str(e.pid) 实为
        # AttributeError 被吞，超时路径此前从未真正杀过进程树
        proc = subprocess.Popen(cmd, cwd=_PROC, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace", env=env)
        try:
            proc_out, proc_err = proc.communicate(timeout=_COM_TIMEOUT)
        except subprocess.TimeoutExpired:
            # 杀进程树：Excel COM 可能已起 EXCEL.EXE 子进程，仅杀 python 会残留
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               capture_output=True, timeout=15)
            except Exception:
                pass
            raise RuntimeError(
                f"兼容通道读取超时（超过 {_COM_TIMEOUT}s），可能系统保护客户端弹窗未处理"
                "或 Excel 异常，请检查本机 Excel 环境后重试。")
        if proc.returncode != 0:
            detail = ""
            try:
                with open(out_pkl, "rb") as f:
                    r = pickle.load(f)
                if isinstance(r, (tuple, list)) and len(r) == 3 and r[0] == "error":
                    detail = f"{r[1]}: {r[2]}"
            except Exception:
                pass
            msg = (f"兼容通道读取失败（exit={proc.returncode}），"
                   f"请检查本机 Excel 环境后重试。")
            if detail:
                msg += f"\n（兼容读取错误: {detail}）"
            # r21：重试痕迹在 stderr，失败时尾部并入报错（此前被吞，排障零可观测）；stdout 尾部补充上下文
            if proc_out and proc_out.strip():
                msg += f"\n{proc_out.strip()[-800:]}"
            if proc_err and proc_err.strip():
                msg += f"\n{proc_err.strip()[-2000:]}"
            raise RuntimeError(msg)
        with open(out_pkl, "rb") as f:
            result = pickle.load(f)
        if isinstance(result, (tuple, list)) and len(result) == 3 and result[0] == "error":
            raise RuntimeError(f"兼容通道读取失败: {result[1]}: {result[2]}")
        if proc_err and proc_err.strip():
            # r21：成功但中途发生过"正忙重试"时透传痕迹（可观测）
            for line in proc_err.splitlines():
                print(line.rstrip())
        if proc_out and proc_out.strip():
            # 透传 worker 的 [兼容读取] 打开行（成功时展示；stdout 已捕获防管道死锁）
            for line in proc_out.splitlines():
                print(line.rstrip())
        return result
    finally:
        if cleanup and os.path.exists(cleanup):
            try:
                os.remove(cleanup)
            except OSError:
                pass
        if os.path.exists(out_pkl):
            try:
                os.remove(out_pkl)
            except OSError:
                pass


def derive_period(df, filename):
    """YYYYMM：优先数据最大月份（发货日期/日期列），回退文件名"财务分析-X月"。"""
    for col in df.columns:
        if "发货日期" in str(col) or "日期" in str(col):
            try:
                d = pd.to_datetime(df[col], errors="coerce").dropna()
                if len(d):
                    return d.max().strftime("%Y%m")
            except Exception:
                pass
            break
    m = re.search(r"(\d{1,2})月", filename)
    if m:
        month = int(m.group(1))
        now = datetime.datetime.now()
        year = now.year if month <= now.month else now.year - 1
        return f"{year}{month:02d}"
    return datetime.datetime.now().strftime("%Y%m")


def coerce_object_columns(df):
    """混合类型 object 列统一为字符串（保留 NaN 为空），保证 pyarrow 可写。

    ERP 原始列如"产品品类（新）"可能是 str 与 int 混排（如数值型品类码），
    pyarrow 无法推断单一类型。仅处理 object 列中的非字符串单元：
    str 原样、NaN/None 留空、其他转 str；不影响 金额/利润/数量 等数值列合计。
    """
    df = df.copy()
    for c in df.columns:
        if df[c].dtype == object:
            mask = ~df[c].map(lambda x: isinstance(x, str))
            if mask.any():
                df[c] = df[c].map(
                    lambda x: x if isinstance(x, str)
                    else (None if x is None or pd.isna(x) else str(x)))
    return df


def coerce_datetime_columns(df):
    """tz-aware datetime64 列 → 字符串（去掉时区、格式化为 naive 时间串），pyarrow 可写。

    COM 返回的日期带 win32timezone 非标准时区，pandas tz_localize / pyarrow 序列化均无法处理；
    strip tzinfo 后转 "YYYY-MM-DD HH:MM:SS" 字符串，pd.to_datetime 可再解析（stage_silver 正是如此）。
    """
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            if getattr(df[c].dtype, "tz", None) is not None:
                df[c] = df[c].map(
                    lambda v: None if pd.isna(v)
                    else v.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S"))
    return df


def coerce_numeric_object_columns(df):
    """r18 ②：COM 路径 df 类型归一（值不变，dtype 对齐 calamine/快照语义）。

    根治"COM 读出 df 的 object 列让 silver parquet 双写失败"：
      1. 先 coerce_object_columns：object 列非 str 单元统一为 str（修 产品品类 等 str/int 混排列，
         与快照路径同款）。
      2. 再对"纯数字串"object 列 pd.to_numeric 转数值（修 单位成本 等："0.0426900000" → 0.04269，
         数值等价——pandas 读 CSV 时本就会把纯数字串推断为数值，故经 golden_diff 读取后
         dtype/合计与基线一致，CSV 零漂移红线不受影响）。
      3. 含非数值的列保持 str（品类码/编号等标识，不做无损之外的值改动）。
    红线：值不变——纯数字列转数值是数值等价（前导零列 pandas 读 CSV 时本就会剥离，与基线一致）。
    """
    df = coerce_object_columns(df)
    for c in df.columns:
        if df[c].dtype != object:
            continue
        non_null = df[c].dropna()
        if non_null.empty:
            continue
        try:
            num = pd.to_numeric(non_null, errors="coerce")
            if num.isna().any():
                continue  # 含非数值（标识/品类码）→ 保持 str
            df[c] = pd.to_numeric(df[c], errors="coerce")
        except Exception:
            continue
    return df


def sha256_head(path, n=_SHA_HEAD):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(n))
    return h.hexdigest()


def sha256_full(path, chunk=1024 * 1024):
    """全量文件 sha256（r17，宪法 R3：8MB 头会漏检文件后部修正，作身份键必须全量）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


# 关键数值列合计：逻辑名 → 源列候选（raw 列名 vs 重命名后列名）
SUM_COLS = {
    "金额": ["金额", "RMB 未税金额小计"],
    "利润": ["利润"],
    "数量": ["数量", "发货数量"],
}


def column_sums(df):
    r"""关键数值列合计（金额/利润/数量），取源列候选第一个存在的列。

    r17：从 scripts\ingest_snapshot.py 迁入共享层，供 ingest 与快照注入复用。
    """
    sums = {}
    for logical, cands in SUM_COLS.items():
        for c in cands:
            if c in df.columns:
                s = pd.to_numeric(df[c], errors="coerce").sum()
                sums[logical] = round(float(s), 2) if pd.notna(s) else None
                break
        else:
            sums[logical] = None
    return sums


def write_erp_snapshot(df, source_path, warehouse_root, sheet_name, read_seconds=None):
    r"""COM 解密成功后按 ingest 同款落仓：写 data_warehouse\<YYYYMM>\erp_snapshot.parquet + manifest（r17 升级）。

    manifest source 写 name+size+sha256_full（身份键，弃 mtime；mtime 仅保留展示/审计），
    并补全 ingest 同款审计字段（columns / columns_hash / sums / read_seconds）。
    保守策略：目标 period 目录已有 manifest 且其 source.name 与当前源不同时不覆盖（避免挤占
    他人快照，如同名周期下的副本）；同名且 sha256_full 相同视为同源允许覆盖更新。
    写入原子化：manifest 先写同目录临时文件再 os.replace。
    返回 parquet 路径；被跳过/无写入返回 None。写仓失败由调用方捕获（仅告警不阻断读取）。
    """
    period = derive_period(df, os.path.basename(source_path))
    out_dir = os.path.join(warehouse_root, period)
    mf_path = os.path.join(out_dir, "manifest.json")
    if os.path.isfile(mf_path):
        try:
            with open(mf_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if existing.get("source", {}).get("name") != os.path.basename(source_path):
                print(f"  [注入跳过] data_warehouse/{period}/manifest.json 已属于其他源"
                      f"（{existing.get('source', {}).get('name')}），不覆盖；本次读取结果直接使用")
                return None
            # 同名：sha256_full 相同视为同源允许覆盖更新（不同则源已变，同样允许覆盖为新版本）
        except (json.JSONDecodeError, OSError):
            pass  # manifest 损坏/不可读 → 覆盖重写
    os.makedirs(out_dir, exist_ok=True)
    pq_path = os.path.join(out_dir, "erp_snapshot.parquet")
    df = coerce_object_columns(df)
    df = coerce_datetime_columns(df)
    df.to_parquet(pq_path, index=False)
    # r21 第三步：同步落加密容器（分发形态；发布侧只上 .kbdat，明文 parquet 不出本机）。
    # best-effort：容器写失败不阻断读取（本地 parquet 快路径仍可用）。
    try:
        from shared.snapshot_container import write_container
        write_container(df, os.path.join(out_dir, "erp_snapshot.kbdat"))
    except Exception as e:
        print(f"  [注入警告] 快照容器写入失败（不影响本地读取）: {type(e).__name__}: {e}")
    st = os.stat(source_path)
    cols_hash = hashlib.sha256("\n".join(str(c) for c in df.columns).encode("utf-8")).hexdigest()
    manifest = {
        "source": {
            "name": os.path.basename(source_path),
            "size": st.st_size,
            "mtime": st.st_mtime,                        # 展示/审计，不作身份键
            "sha256_full": sha256_full(source_path),
        },
        "ingest": {
            "time": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "decrypt_path": "com",
            "sheet": sheet_name,
            "period": period,
            "read_seconds": round(read_seconds, 1) if read_seconds is not None else None,
        },
        "data": {
            "row_count": int(len(df)),
            "column_count": int(len(df.columns)),
            "columns_hash": cols_hash,
            "columns": [str(c) for c in df.columns],
            "sums": column_sums(df),
        },
        "cust_info": {"file": None, "row_count": None},
    }
    # 原子写：先写同目录临时文件再 os.replace（避免半写 manifest 被并发读）
    fd, tmp_mf = tempfile.mkstemp(suffix=".json", prefix="manifest_", dir=out_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        os.replace(tmp_mf, mf_path)
    except Exception:
        try:
            os.remove(tmp_mf)
        except OSError:
            pass
        raise
    print(f"  [注入] 已写 parquet+manifest（period={period}）: {pq_path}")
    return pq_path


if __name__ == "__main__":
    # r18 ①：COM 子进程入口（read_encrypted_com 以 `python -m shared.excel_com ...` spawn）
    _com_read_worker_main()
