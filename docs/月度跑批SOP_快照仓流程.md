# 月度跑批 SOP · 快照仓流程（T1 流程固化版）

> 目的：DSE/亿赛通加密环境下的月度数据落库流程标准化。核心能力（W1 快照仓）已落地，
> 本文档固化"每月照做"的动作序列。维护人：用户本人。
> 依据：台账未决 #8、PROJECT_CHARTER S8、scripts\ingest_snapshot.py。

## 一、月度流程（每月 ERP 导出新 Excel 后）

| 步骤 | 动作 | 命令/位置 | 验证点 |
|---|---|---|---|
| 1 | 新月度 Excel 放入 data\ | `data\财务分析-<月>.xlsx` | 文件名与月份一致；DSE 加密不影响（读取走 COM 兜底） |
| 2 | 落快照仓 | `python scripts\ingest_snapshot.py` | 生成 `data_warehouse\<YYYYMM>\erp_snapshot.parquet`（明文，Python 写不加密）；控制台报行数 |
| 3 | 全量跑批 | `python run_chain.py --data data\财务分析-<月>.xlsx` | [STAGE 1/6]~[STAGE 6/6] 全过；末尾"全部通过"；看板 dashboard_a.html 更新 |
| 4 | 数据对拍 | `python scripts\golden_diff.py --baseline baseline\<当前基线>\summary.json --platform-dir sales_analytics_platform` | 漂移数=已登记数（当前 55：41 F面插拔+2 ASP_AXIS+2 B_LIST_LIMIT+10 提价过滤），**0 待查明** |
| 5 | 测试门禁 | `python scripts\run_all_tests.py` | 全量 93/93 passed（勿只跑子集） |
| 6 | JS 门禁 | `python scripts\check_js_syntax.py` | `JS: ALL OK (N blocks)` |
| 7 | 性能门禁 | `python scripts\perf_smoke.py` | 端到端 <600s、看板段 <180s（实测 ~255s/~76s） |
| 8 | R 面审定 | 人工审定 `dashboard\risk_action_<YYYYMM>.md` 初稿 → 跑批重渲染 | 行动清单与风险摘要反映审定结果 |
| 9 | 发布共享盘 | `powershell -File kanban\tools\publish_to_share.ps1 -Force` | version.txt = `v<本地HEAD短哈希> @ 时间`，非 vnogit |
| 10 | 台账记录 | `project_analysis\施工进度台账.md` 追加一行 | 记录跑批结果/漂移数/异常 |

## 二、关键纪律（违反=返工）

1. **快照先行**：Excel 落 data\ 后第一时间转 parquet（步骤 2 不得跳过）——加密 Excel 只能 COM 读（62s/次），快照是明文逃生通道。
2. **门禁全跑**：步骤 4-7 是发版四门禁，缺一不可；"跑过子集"不算跑过（历史教训：7/7 子集掩盖了 3 个失败）。
3. **漂移必归因**：golden_diff 出现未登记漂移 → 停下来查明，禁止"先发再查"。
4. **指纹触发**：改 settings/代码/数据任一都会触发重算（R3），--dashboard-only 会拒绝过期缓存，这是特性不是故障。

## 三、异常处置

| 症状 | 原因 | 处置 |
|---|---|---|
| ingest_snapshot 报 COM 超时 | DSE 加密读取慢 | 重跑一次；仍失败用明文窗口（新建 txt 改扩展名）拷贝 |
| golden_diff 新增未知漂移 | 代码变更未登记 | 对照 git diff 定位，登记或回滚 |
| pytest 新失败 | 测试债或真回归 | 先分清（测试侧 monkeypatch vs 产品侧），修完再发 |
| GitHub 推送阻断 | 公司网络间歇 | `git -c http.version=HTTP/1.1 push` 重试；本地提交安全 |
| 共享盘 version.txt=vnogit | 子进程 PATH 无 git | 脚本已内置全路径回落；仍失败检查 Git 安装 |

## 四、基线管理

- 当前对拍基线：`baseline\20260825_july\summary.json`
- 换基线时机：口径正式变更（如 observed=True 拍板后）→ `python scripts\freeze_baseline.py` 新基线 + 台账登记变更原因
- 基线只增不删（历史可回溯）

---
*创建：2026-08-26（发版评审 r7 迭代，台账 #8 流程固化）*
