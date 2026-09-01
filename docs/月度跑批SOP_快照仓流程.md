# 月度跑批 SOP · 快照仓流程（T1 流程固化版）

> 目的：DSE/亿赛通加密环境下的月度数据落库流程标准化。核心能力（W1 快照仓）已落地，
> 本文档固化"每月照做"的动作序列。维护人：用户本人。
> 依据：台账未决 #8、PROJECT_CHARTER S8、scripts\ingest_snapshot.py。

## 一、月度流程（每月 ERP 导出新 Excel 后）

| 步骤 | 动作 | 命令/位置 | 验证点 |
|---|---|---|---|
| 1 | 新月度 Excel 投放数据共享目录（或本地 data\） | 数据共享目录（配置见第五节）或 `data\财务分析-<月>.xlsx` | 文件名与月份一致；DSE 加密不影响（读取走 COM 兜底）；流水线自动合并扫描共享盘+本地取最新 |
| 2 | 落快照仓 | `python scripts\ingest_snapshot.py` | 生成 `data_warehouse\<YYYYMM>\erp_snapshot.parquet` + `erp_snapshot.kbdat` 加密容器（r21：明文本机留存，容器随发布分发）；控制台报行数 |
| 3 | 全量跑批 | `python run_chain.py`（自动取共享盘+本地最新；显式 `--data <路径>` 永远优先） | [STAGE 1/6]~[STAGE 6/6] 全过；末尾"全部通过"；看板 `output\dashboard\销售数据分析看板_<yyyy年mm月>.html` 更新（r23 迁出同步树+按月命名） |
| 4 | 数据对拍 | `python scripts\golden_diff.py --baseline baseline\<当前基线>\summary.json --platform-dir sales_analytics_platform` | 漂移数=已登记数（基线 20260827 起重新计，当前 0），**0 待查明** |
| 5 | 测试门禁 | `python scripts\run_all_tests.py` | 全量 93/93 passed（勿只跑子集） |
| 6 | JS 门禁 | `python scripts\check_js_syntax.py` | `JS: ALL OK (N blocks)` |
| 7 | 性能门禁 | `python scripts\perf_smoke.py` | 端到端 <600s、看板段 <180s（实测 ~255s/~76s） |
| 8 | R 面审定 | 人工审定 `dashboard\risk_action_<YYYYMM>.md` 初稿 → 跑批重渲染 | 行动清单与风险摘要反映审定结果 |
| 9 | 发布共享盘 | `powershell -File kanban\tools\publish_to_share.ps1 -Force` | version.txt = `v<本地HEAD短哈希> @ 时间`，非 vnogit；r22 起快照仓（仅 `.kbdat`+manifest）投**数据共享盘** `D1经营分析\data_warehouse\`（财务受控、密文与代码分家；明文 parquet 不出本机），客户端本地仓 miss 后 UNC 直读命中 |
| 10 | 台账记录 | `project_analysis\施工进度台账.md` 追加一行 | 记录跑批结果/漂移数/异常 |

## 二、关键纪律（违反=返工）

1. **快照先行**：Excel 落 data\ 后第一时间转 parquet（步骤 2 不得跳过）——加密 Excel 只能 COM 读（62s/次），快照是明文逃生通道。
2. **门禁全跑**：步骤 4-7 是发版四门禁，缺一不可；"跑过子集"不算跑过（历史教训：7/7 子集掩盖了 3 个失败）。
3. **漂移必归因**：golden_diff 出现未登记漂移 → 停下来查明，禁止"先发再查"。
4. **指纹触发**：改 settings/代码/数据任一都会触发重算（R3），--dashboard-only 会拒绝过期缓存，这是特性不是故障。
5. **容器先行于发布**（r21）：数据文件**内容**更新后必须重新 ingest 再 publish，否则客户端回落本机 COM 通道；文件**改名**不影响命中（按 size+sha256_full 内容身份兜底，容财务侧加日期后缀）。快照分发目的地=数据盘 D1（r22），代码盘零数据。

## 三、异常处置

| 症状 | 原因 | 处置 |
|---|---|---|
| ingest_snapshot 报 COM 超时 | DSE 加密读取慢 | 重跑一次；仍失败用明文窗口（新建 txt 改扩展名）拷贝 |
| golden_diff 新增未知漂移 | 代码变更未登记 | 对照 git diff 定位，登记或回滚 |
| pytest 新失败 | 测试债或真回归 | 先分清（测试侧 monkeypatch vs 产品侧），修完再发 |
| GitHub 推送阻断 | 公司网络间歇 | `git -c http.version=HTTP/1.1 push` 重试；本地提交安全 |
| 共享盘 version.txt=vnogit | 子进程 PATH 无 git | 脚本已内置全路径回落；仍失败检查 Git 安装 |
| 客户端报"对方 Excel 持续正忙" | 本机 WPS/Excel 窗口、未关弹窗或残留 EXCEL.EXE 占用 | 按报错指引关闭窗口/对话框、任务管理器结束残留 EXCEL.EXE 后重跑（r21 已带自动重开实例与重试痕迹）；仍不明用 `kanban\tools\diagnose_excel_com.ps1` 体检 |

## 四、基线管理

- 当前对拍基线：`baseline\20260827\summary.json`（20260825_july 因 r10 期有意变更过期，r14 重冻入库）
- 换基线时机：口径正式变更（如 observed=True 拍板后）→ `python scripts\freeze_baseline.py` 新基线 + 台账登记变更原因
- 基线只增不删（历史可回溯）

## 五、数据源共享盘配置（r14，2026-08-27 拍板）

- **数据共享目录独立于代码更新共享目录**，必须可配置。内置默认值 `\\192.168.8.3\财务部\财务电子档案备份\D1经营分析`（2026-08-27 用户提供；各机可用环境变量/配置覆盖）。
- **开发机配置优先级**（高→低）：环境变量 `SALES_DATA_SHARE_DIR` > `chain_config.json` 的 `data_share_dir`（显式空串 `""` = 禁用共享盘扫描）> 内置默认。ingest_snapshot 用 `--share-dir`（空串禁用）。注意：`chain_config.json` 已去 git 跟踪（r14b），本机路径配置不会入库；**但仍会随 publish 同步到客户端（robocopy 不看 gitignore）——发布机不要在该文件写本机路径，机器级覆盖一律用环境变量**；当前发布内容为通用默认（stages 等，客户端在用，不可从 publish 排除）。
- **客户端（看板壳）**：设置弹层配「数据文件共享目录」（留空 = 代码共享目录下的 data\）；主界面「从共享盘获取最新数据」按钮一键拉取最新 Excel 到本地缓存（`%LOCALAPPDATA%\KanbanRunner\data\`）再跑批，产物全在本地。
- **安全事实**：DSE 密文 Excel 上共享盘后字节级一致（实测文件头 `00 00 5B 00`）；全员电脑有 DSE 客户端+Office，拉到本地后走现有 COM 透明解密读取，链路已验证。
- **快照仓分发（r22）**：发布脚本把 `data_warehouse\`（仅 `.kbdat`+manifest，`/XF *.parquet`）投到数据共享盘 `D1经营分析\data_warehouse\`——密文与代码（含解密钥匙）分家，代码盘不携带任何数据；客户端流水线 `find_snapshot_local_or_share` 本地仓 miss 后 UNC 直读。

---
*创建：2026-08-26（发版评审 r7 迭代，台账 #8 流程固化）；r14 数据源共享盘：2026-08-27*
