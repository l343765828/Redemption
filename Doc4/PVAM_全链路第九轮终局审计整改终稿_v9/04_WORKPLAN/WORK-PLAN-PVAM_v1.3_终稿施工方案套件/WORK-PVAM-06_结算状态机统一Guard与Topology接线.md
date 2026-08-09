# WORK-PVAM-06 全量重算状态机、统一 Guard 与发布分层施工任务书

> 文档定位：来源于待组织批准的 `TASK-PVAM-06`，在取得组织授权后转化为可执行施工说明。本文件不重新决定业务规则；实际结果只能写入执行记录与验证交付报告。

## 0. 填写与执行规则

1. 上游修改任务与本 v1.3 施工套件当前均为 `DRAFT`；没有组织授权前，本任务保持 `BLOCKED`，不得启动代码施工或部署。
2. 当前只实施 `R-009、R-010` 的受控范围。`TOPO-WIRE-01` 仅可由 WORK-08 外部证据触发，并须先更新受控追溯边；任何 `REJECTED / NEEDS_DECISION / DEFERRED / 未获 TASK 授权的 UAT_VERIFY` 只允许登记、验证或阻断，不得扩展代码范围。
3. 基线必须精确等于 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；发现漂移立即登记 `BLOCK-PVAM-06-BASELINE`。
4. 所有新文件/符号已在变更表标为“新增”；其余锚点均来自固定基线。
5. DEV替身不能冒充真实Kafka/Redis/Dask/GPU/MySQL UAT验证。

## 1. 文档信息与追溯关系

| 字段 | 内容 |
|---|---|
| 施工任务编号 | `WORK-PVAM-06` |
| 施工任务名称 | 全量重算状态机、统一 Guard 与发布分层 |
| 所属施工总方案 | `WORK-PLAN-PVAM_v1.3` |
| 来源修改任务 | `TASK-PVAM-06@MODPLAN-PVAM_v1.2`（authorization=PENDING_ORGANIZATIONAL_APPROVAL） |
| 来源问题 | `R-009、R-010` |
| 复核闭环追踪号 | `REM-009、REM-010 / W-009、W-010 / V-009、V-010`；RISK-001/TOPO-WIRE-01 无预登记 REM/W/V，由 WORK-08 AC-05 取证触发 |
| 来源检查项 | `CHK-BIZ-006、CHK-ARCH-002、CHK-EVT-003、CHK-PUB-001` |
| 关联决策 | `DEC-007、DEC-008、DEC-010、DEC-012` |
| 代码基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| SQL基线 | `sql_uat/*@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，仅有效SQL |
| 文档版本 | `v1.3` |
| 负责人 | `待指派 / 实施工程师` |
| 复核人 | `待指派 / 架构与QA` |
| 当前状态 | `BLOCKED` |
| 文档治理状态 | `DRAFT`（`PENDING_ORGANIZATIONAL_APPROVAL`） |
| 前置任务 | WORK-PVAM-01、WORK-PVAM-02、WORK-PVAM-05 DEV_VERIFIED；WORK-08A调用图证据可并行 |
| 功能开关 | `SETTLEMENT_COORDINATOR_V2` |

### 1.1 一对一追溯摘要

```text
CHK-BIZ-006、CHK-ARCH-002、CHK-EVT-003、CHK-PUB-001
  └─ R-009、R-010
       └─ DEC-007、DEC-008、DEC-010、DEC-012
            └─ TASK-PVAM-06 (DRAFT / PENDING_ORGANIZATIONAL_APPROVAL)
                 └─ WORK-PVAM-06
                      ├─ STEP-PVAM-06-01 / STEP-PVAM-06-02 / STEP-PVAM-06-03 / STEP-PVAM-06-04 / STEP-PVAM-06-05 / STEP-PVAM-06-06
                      ├─ TC-PVAM-06-01 / TC-PVAM-06-02 / TC-PVAM-06-03 / TC-PVAM-06-04 / TC-PVAM-06-05 / TC-PVAM-06-06 / TC-PVAM-06-07 / TC-PVAM-06-08 / TC-PVAM-06-09
                      └─ EV-PVAM-06-01...
```

## 2. 施工任务生成依据

### 2.1 上游输入

| 输入 | 编号/版本 | 本任务使用的结论 | 状态 |
|---|---|---|---|
| 复核报告 | `Redemption_PV_Amount_Migration_d74_复核报告_v1.5` | R-009、R-010 的代码事实与严重级别；TOPO-WIRE-01 由 WORK-08 外部证据门禁管理 | CONFIRMED |
| 修改任务书 | `TASK-PVAM-06` | 采用方案、范围、排除项、AC | DRAFT（待组织授权） |
| 检查方案 | `PLAN-PVAM-v1.15` | CHK-BIZ-006、CHK-ARCH-002、CHK-EVT-003、CHK-PUB-001 | CONTROLLED |
| 正式决策 | DEC-007、DEC-008、DEC-010、DEC-012 | 只执行已关闭裁决；开放项阻断 | CLOSED / 按上游登记 |
| 代码/SQL快照 | 3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2 | 唯一施工对象 | FROZEN |
| 施工模板 | 总方案模板/专项模板 | 章节、状态、证据纪律 | CONTROLLED |

### 2.2 开工条件

- [ ] 当前 HEAD 精确为 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，工作树无未登记变更。
- [ ] `TASK-PVAM-06` 的人工批准记录已归档；本 `WORK` 已由施工负责人和复核人签署。
- [ ] 前置关系满足：WORK-PVAM-01、WORK-PVAM-02、WORK-PVAM-05 DEV_VERIFIED；WORK-08A调用图证据可并行。
- [ ] 本任务涉及的接口、单位、精度、兼容和回滚边界已由上游任务固定。
- [ ] DEV测试依赖已安装；UAT项具备WORK-08生成的环境/数据/schema manifest。
- [ ] 功能开关默认关闭，回滚路径已演练。

未满足任一关键项时，本任务状态为 `BLOCKED`；不得用假设替代。

## 3. 问题事实与施工目标

### 3.1 已确认问题

| 项目 | 内容 |
|---|---|
| 预期行为 | 建立唯一SettlementCoordinator/Guard与run manifest，统一Global/Placement/Elite的freeze、drain、recalc、batch-ready、external receipt与失败恢复；任何入口不可绕过。执行已批准的 TOPO-WIRE-01：有现有接线则核验并修补，无接线则把真实拓扑消息入口接入 TopologyMutationService。 |
| 当前行为 | Global、Placement、Elite 各自维护状态键/锁和guard；`UserStatsService.assert_period_settlement_available` 只覆盖Global+Placement。；`GlobalEliteBonusRecalculationService._emit_settlement_done` 可在 `persisted=False` 时仍把本地状态写DONE并发完成事件。；真实消息入口、direct-call和拓扑变更入口没有可证明的同一原子状态快照守卫。；`TopologyMutationService.orchestrate_topology_mutation` 存在；`MessageConsumer/UserConsumer.py::consume_loop` 仍直接执行 `actor.run_update`，没有通过事务编排器修复旧/新链状态。TASK-PVAM-06 已批准条件工作项 TOPO-WIRE-01，固定archive决定核验现有接线或实施缺失接线。 |
| 差异 | 当前实现缺少本任务批准的唯一合同、门禁或原子边界。 |
| 影响 | 金额/PV单位、奖金、并发一致性、发布或可恢复性，具体见来源问题。 |
| 严重级别 | P0 |
| 证据位置 | 固定代码基线 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；来源 `TASK-PVAM-06`；检查项 `CHK-BIZ-006、CHK-ARCH-002、CHK-EVT-003、CHK-PUB-001` |

### 3.2 已确认代码事实

- Global、Placement、Elite 各自维护状态键/锁和guard；`UserStatsService.assert_period_settlement_available` 只覆盖Global+Placement。
- `GlobalEliteBonusRecalculationService._emit_settlement_done` 可在 `persisted=False` 时仍把本地状态写DONE并发完成事件。
- 真实消息入口、direct-call和拓扑变更入口没有可证明的同一原子状态快照守卫。
- `TopologyMutationService.orchestrate_topology_mutation` 存在；`MessageConsumer/UserConsumer.py::consume_loop` 仍直接执行 `actor.run_update`，没有通过事务编排器修复旧/新链状态。TASK-PVAM-06 已批准条件工作项 TOPO-WIRE-01，固定archive决定核验现有接线或实施缺失接线。

### 3.3 本任务目标

建立唯一SettlementCoordinator/Guard与run manifest，统一Global/Placement/Elite的freeze、drain、recalc、batch-ready、external receipt与失败恢复；任何入口不可绕过。执行已批准的 TOPO-WIRE-01：有现有接线则核验并修补，无接线则把真实拓扑消息入口接入 TopologyMutationService。

### 3.4 完成定义

- [ ] 所有 CHG 和 STEP 在批准范围内完成，未触碰排除项。
- [ ] DEV 静态、单元、契约和 mutation 测试全部通过并生成原始证据。
- [ ] UAT 所属用例已执行并回传，或保持 `PENDING_TEST_ENV/BLOCKED`，绝不预标通过。
- [ ] 受影响调用者回归通过，重复执行和失败恢复满足本任务断言。
- [ ] 回滚开关与 `git revert` 路径均可用，回滚后关键读写验证通过。

### 3.5 明确非目标

- 不修改来源 TASK 未批准的业务比例、资格、分母、Country、period、舍入或发布职责。
- 不使用 `_bak`、`_final`、copy、废弃SQL或 `GraphService.run_bfs` 作为施工依据。
- 不把 UAT_VERIFY 风险转化为代码修复；只做验证、证据或阻断。
- 不建设 PB/SFB/GPB/CRB 算法或 Team Bonus units-int 生产服务。

## 4. 修改前调用链与数据流

### 4.1 入口与调用链

| 顺序 | 调用方/入口 | 文件与符号 | 输入契约 | 输出/副作用 | 错误形成点 |
|---|---|---|---|---|---|
| 1 | Global全量 | `GlobalRecalculationService.settle_period` | period | 独立lock/status/DONE | 未统一epoch |
| 2 | Placement全量 | `PlacementRecalculationService.settle_placement_period` | period | 独立状态/哨兵 | 未统一epoch |
| 3 | Elite全量 | `GlobalEliteBonusRecalculationService.settle_period` | period | persisted false也DONE | 假完成 |
| 4 | 增量guard | `UserStatsService.assert_period_settlement_available` | period | global+placement | 遗漏Elite |
| 5 | 拓扑 | `TopologyMutationService.orchestrate_topology_mutation` / `UserConsumer.consume_loop` | cdc_version/change | 测试服务与直接actor更新并存 | 生产归属未证实 |

### 4.2 当前错误形成点

当前链路在上述入口缺少本任务目标合同，导致已确认问题在写入、计算、路由或发布边界形成并传播。修改必须落在表中稳定符号或明确标记为“新增”的边界；不得通过外围日志掩盖。

### 4.3 受影响消费者

| 消费者 | 依赖内容 | 预期影响 | 是否同步修改 | 对应步骤/测试 |
|---|---|---|---|---|
| WORK-02 确认的唯一真实 PV 入口（可能为条件新增 `PvEventConsumer`） | 写入许可/epoch | 入口+核心函数双guard | 是（对象由 WORK-02 调用图裁决） | STEP-06-03/TC-024 |
| 三类全量服务 | state transition/manifest | 统一编排 | 是 | STEP-06-02/04 |
| Elite外部writer | batch receipt | 验证checksum后PUBLISHED | 是 | STEP-06-04/TC-029 |
| Topology入口 | guard/period/version/影响范围重算 | 核验现有接线或实施批准的缺失接线 | 是（条件分支） | STEP-06-05/TC-011/024/030 |
| 业务正式读取 | 不在本仓职责 | 不得建设read switch | 否 | TC-030 |

## 5. 施工设计

### 5.1 采用方案

- 新增 `Settlement/SettlementCoordinator.py`、`SettlementGuard.py`、`SettlementRunManifest.py`。
- 状态固定：OPEN→QUIESCING→DRAINING→RECALCULATING→RECALC_DONE_PENDING_BATCH→BATCH_READY→PUBLISHING_EXTERNAL→PUBLISHED；FAILED/IN_DOUBT为异常态。
- Guard 一次读取统一epoch快照并验证Global/Placement/Elite局部状态、版本、period、锁；消息入口和核心写函数各调用一次。
- freeze后阻止新delivery，等待in-flight归零，冻结topic/partition watermark、config/topology/schema/version；全量使用同一run/generation。
- 外部receipt必须匹配batch id、counts、checksums与run；未回执不能PUBLISHED。
- TOPO-WIRE-01 已由 TASK-PVAM-06 条件性批准：先以固定archive和部署manifest识别真实入口；已有接线则补齐统一Guard/PeriodSnapshot/version/CDC幂等，未接线则修改真实 `UserConsumer.consume_loop` 通过 `TopologyMutationService.orchestrate_topology_mutation` 执行旧链提取→图变更→新链提取→影响节点重算。

选择理由：

- 与有效SQL、已关闭DEC及来源TASK目标一致。
- 采用 additive-first、显式version/manifest/feature flag，支持独立合入和回滚。
- 将纯函数、I/O适配、业务计算、权威提交和证据采集分层，便于DEV替身与UAT真实验证分别取证。

### 5.2 被否决方案

| 方案 | 不采用原因 | 来源 |
|---|---|---|
| persisted=false写DONE | 假完成 | R-009 |
| 保留双guard | 快照不一致/遗漏Elite | R-010 |
| 本仓实现业务DB writer/read switch | 违反DEC-007/008 | DEC-007/008 |
| 仅在service内部guard | direct-call/入口可绕过 | CHK-EVT-003 |
| 绕开TOPO-WIRE-01证据分支直接新造第二个consumer | 会产生双消费与部署歧义 | TASK-PVAM-06/TOPO-WIRE-01 |

### 5.3 修改后调用链与数据契约

| 边界 | 输入 | 处理 | 输出 | 断言/错误行为 | 责任符号 |
|---|---|---|---|---|---|
| 施工入口 | 固定commit + 批准TASK + SETTLEMENT_COORDINATOR_V2 | 先执行基线/前置检查 | 受控diff | 任一前置失败即BLOCK | `Settlement/SettlementRunManifest.py`、`SettlementCoordinator.py` |
| 核心处理 | strict version/type/period/run合同 | 按STEP顺序执行 | 可测试状态/事件/金额 | 非法类型、状态或proof fail-loud | 见CHG表 |
| 证据出口 | 命令、输入、输出、状态前后 | WORK-08 schema封装 | EV包+SHA-256 | 缺原始证据不得PASS | `uat/scripts/*` |

## 6. 文件与符号级变更清单

| 变更编号 | 文件 | 类/函数/字段/表 | 类型 | 修改前行为 | 要求的修改 | 修改后行为 | 禁止行为 |
|---|---|---|---|---|---|---|---|
| CHG-01 | `Settlement/SettlementRunManifest.py` | run/epoch/generation/watermark/checksum | 新增 | 不存在 | 不可变manifest与状态记录 | 统一run合同 | 不得包含敏感payload |
| CHG-02 | `Settlement/SettlementGuard.py` | `assert_write_allowed`/`assert_recalc_allowed` | 新增 | 多个guard | 统一原子快照判定 | 全部入口同规则 | 不得返回模糊bool |
| CHG-03 | `Settlement/SettlementCoordinator.py` | transition/freeze/drain/receipt/recover | 新增 | 不存在 | CAS状态机与审计 | 单调、幂等 | 不得跨Redis/DB声称原子 |
| CHG-04 | `User/UserStatsService.py` | `assert_period_settlement_available` | 修改 | global+placement | deprecated adapter调用SettlementGuard | 不遗漏Elite | 不得独立读状态 |
| CHG-05 | 三个全量服务 | settle入口与完成事件 | 修改 | 各自RUNNING/DONE | 由Coordinator编排并提交manifest/batch | persisted false不DONE | 不得各自打开epoch |
| CHG-06 | WORK-02 确认的唯一真实 PV 入口及三stage核心入口；若为 `MessageConsumer/PvEventConsumer.py`，该文件属于 WORK-02 条件产物且基线不存在 | guard调用 | 条件新增/修改 | 基线无 `PvEventConsumer.py`；现有入口尚待部署调用图确认 | 入口/核心函数双guard | direct call也阻断 | 不得把条件文件写成既有锚点、不得创建第二 Topic/Group |
| CHG-07 | `User/TopologyMutationService.py` / `MessageConsumer/UserConsumer.py` | `orchestrate_topology_mutation` / `consume_loop` | 修改 | 服务无period/统一guard；consumer直接run_update | 加入period/PeriodSnapshot/version/guard并把真实入口接入事务编排；已有等价接线则只修补 | 旧链→图变更→新链→受影响节点重算可恢复 | 不得保留直接run_update绕过路径或创建第二consumer |
| CHG-08 | `User/Test/test_settlement_coordinator.py` / `User/Test/test_settlement_guard.py` | pytest | 新增 | 不存在 | 状态、并发、CAS、receipt、crash | 可自动验证 | 不得冒充真实Kafka UAT |

### 6.1 固定基线锚点复验

| 文件与符号 | 基线事实 | 施工动作 |
|---|---|---|
| `GlobalEliteBonusRecalculationService.settle_period` | 无db_executor时`persisted=False`，仍调用完成收尾 | 分离RECALC_DONE_PENDING_BATCH/BATCH_READY/PUBLISHED |
| `GlobalEliteBonusRecalculationService._emit_settlement_done` | 状态写DONE并发同名事件 | 改由Coordinator合法transition与统一publisher控制 |
| `UserStatsService.assert_period_settlement_available` | 只覆盖Global/Placement语义 | 兼容adapter转调唯一SettlementGuard |
| `GlobalEliteBonusRecalculationService.assert_period_settlement_available` | 独立Elite guard | 转调唯一Guard，保留兼容接口一轮 |
| `TopologyMutationService.orchestrate_topology_mutation` | 真实存在并执行旧链→actor更新→新链→重算 | 作为拓扑事务编排目标 |
| `UserConsumer.consume_loop` | 当前直接`actor.run_update(...)` | 若部署证据确认其为唯一生产入口，改为调用上述编排器 |

附件二声称`TopologyMutationService`存在自身`def run_update`不正确：固定基线只有对`actor.run_update(...)`的调用。终稿不得以不存在的符号施工。

### 6.2 状态转移合同

```text
OPEN -> QUIESCING -> DRAINING -> RECALCULATING
RECALCULATING -> RECALC_DONE_PENDING_BATCH -> BATCH_READY
BATCH_READY -> PUBLISHING_EXTERNAL -> PUBLISHED
任一中间态 -> FAILED 或 IN_DOUBT
```

- Global、Placement、Elite是同一epoch的stage，不能各自宣称全局DONE。
- `persisted=False`只说明Redis重算完成，绝不能进入PUBLISHED。
- transition必须CAS校验`period/epoch/run_id/generation/expected_state`。
- Guard同时用于消息入口、direct call、核心写函数和Topology入口；只在外层检查不构成通过。
- `assert_read_allowed`只用于引擎内部一致性，不建设业务系统正式读门控。

### 6.3 TOPO-WIRE-01唯一分支

1. WORK-08A采集部署进程、Topic/group、启动参数、镜像与import/call graph；
2. 若已存在等价生产编排器：只补Guard、period/version与恢复测试；
3. 若`UserConsumer.consume_loop`是唯一生产入口：把直接`actor.run_update`替换为`TopologyMutationService.orchestrate_topology_mutation`；
4. 若发现第三条未登记入口：停工并回流新R项；
5. 任何分支都禁止创建第二Topic/group或在无证据时改错入口。

> **DEV 执行口径：** `05_CONTROL/check_baseline_preflight.sh` 与 `05_CONTROL/validate_work_dev.sh` 是唯一强制门禁。STEP 中列出的 `py_compile`、`compileall` 或 `pytest` 命令仅是附加局部检查，不得替代 parent-tree、scope、patch、tree-hash 与专属测试门禁。

## 7. 可执行施工步骤

### STEP-PVAM-06-01：定义manifest与状态机

- 目的：定义manifest与状态机，落实 `TASK-PVAM-06` 的已批准目标。
- 前置条件：WORK-01、WORK-02、WORK-05 DEV_VERIFIED
- 修改文件：`Settlement/SettlementRunManifest.py`、`SettlementCoordinator.py`
- 目标符号：状态/transition
- 精确操作：
1. 实现状态枚举、allowed transition、CAS/idempotency和审计字段。
- 必须保持：不实现业务DB写入/读取切换
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Settlement/SettlementRunManifest.py Settlement/SettlementCoordinator.py`
- 本步单元验证：`TC-PVAM-06-01/02`
- 完成证据：`EV-PVAM-06-01`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：状态语义需新增业务决策则BLOCK

### STEP-PVAM-06-02：实现统一Guard

- 目的：实现统一Guard，落实 `TASK-PVAM-06` 的已批准目标。
- 前置条件：STEP-06-01
- 修改文件：`Settlement/SettlementGuard.py`、旧adapter
- 目标符号：guard
- 精确操作：
1. 一次读取统一epoch+三局部状态
2. RUNNING/FAILED/IN_DOUBT/pending状态阻断写。
- 必须保持：不吞Redis错误
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Settlement/SettlementGuard.py User/UserStatsService.py`
- 本步单元验证：`TC-PVAM-06-03`
- 完成证据：`EV-PVAM-06-02`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任何旧guard生产直连残留不合并

### STEP-PVAM-06-03：接入消息与核心写入口

- 目的：接入消息与核心写入口，落实 `TASK-PVAM-06` 的已批准目标。
- 前置条件：STEP-06-02；WORK-02 已完成部署级调用图裁决并固定唯一真实 PV 入口
- 修改文件：WORK-02 已确认的唯一真实 PV 入口（若 WORK-02 条件新增 `MessageConsumer/PvEventConsumer.py`，须引用其提交与证据）及 UserStats/Placement/Elite 核心入口
- 目标符号：guard调用
- 精确操作：
1. 入口先guard
2. 核心函数再次guard，使用同一period/epoch token。
- 必须保持：不只在日志层检查
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m compileall -q MessageConsumer User Settlement`
- 本步单元验证：`TC-PVAM-06-03/04`
- 完成证据：`EV-PVAM-06-03`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：direct-call能绕过即失败

### STEP-PVAM-06-04：编排三类全量与external receipt

- 目的：编排三类全量与external receipt，落实 `TASK-PVAM-06` 的已批准目标。
- 前置条件：STEP-06-01~03/WORK-05
- 修改文件：三个全量服务/Coordinator
- 目标符号：settle/emit/receipt
- 精确操作：
1. freeze→drain→watermark→recalc→batch-ready→receipt→published
2. 异常FAILED/IN_DOUBT。
- 必须保持：persisted=false不得DONE
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m compileall -q User Settlement`
- 本步单元验证：`TC-PVAM-06-05~08`
- 完成证据：`EV-PVAM-06-04`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任一阶段假DONE立即回滚

### STEP-PVAM-06-05：实施TOPO-WIRE-01条件分支

- 目的：实施TOPO-WIRE-01条件分支，落实 `TASK-PVAM-06` 的已批准目标。
- 前置条件：WORK-08固定archive/callgraph初证
- 修改文件：`User/TopologyMutationService.py`、`MessageConsumer/UserConsumer.py`、部署manifest
- 目标符号：验证并修改
- 精确操作：
1. 先确认唯一真实topology topic/group/启动入口
2. 已有编排器调用则补齐period/version/guard
3. 若入口直接run_update或无编排器接线，则把该真实入口改为调用TopologyMutationService
4. 修正服务内部对 `_get_or_init_user` 的period参数传递
5. 补充幂等和失败事件。
- 必须保持：不得把run_mutation_test当生产证据；不得新增第二topic/group或擅改图算法
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python uat/scripts/build_callgraph.py --symbol TopologyMutationService --out evidence/work06/topology-callgraph.json && python -m py_compile User/TopologyMutationService.py MessageConsumer/UserConsumer.py`
- 本步单元验证：`TC-PVAM-06-09`
- 完成证据：`EV-PVAM-06-05`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：无法确定真实topic/group/部署入口，或需改变业务拓扑规则时BLOCK

### STEP-PVAM-06-06：故障恢复与回归测试

- 目的：故障恢复与回归测试，落实 `TASK-PVAM-06` 的已批准目标。
- 前置条件：STEP-06-01~05
- 修改文件：测试
- 目标符号：pytest/UAT
- 精确操作：
1. 覆盖每个transition前后kill、重复CAS、receipt mismatch、空batch、checkpoint豁免标签。
- 必须保持：不得以DEV替代真实中间件
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m pytest -q User/Test/test_settlement_coordinator.py User/Test/test_settlement_guard.py`
- 本步单元验证：`TC-PVAM-06-01~09`
- 完成证据：`EV-PVAM-06-06`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：恢复checksum不一致不得发布

## 8. 数据迁移、兼容与重跑

### 8.1 数据变化

| 对象 | 旧格式/状态 | 新格式/状态 | 转换位置 | 版本识别 | 异常数据策略 |
|---|---|---|---|---|---|
| 结算状态键 | 三个局部状态 | 统一epoch/run manifest+局部映射 | Coordinator | epoch/run/generation | 非法跳转阻断 |

### 8.2 迁移步骤

| 顺序 | 操作 | 批次/范围 | 幂等键或判定 | 校验 | 失败处理 |
|---|---|---|---|---|---|
| 1 | 只读扫描/dry-run | 专用period/fixture或全量key清单 | run_id + 对象唯一键 | 数量、版本、金额/事件汇总 | 不写入并生成BLOCK |
| 2 | 启用shadow/read验证 | 单个隔离run | event/run/generation或feature flag | 新旧输出逐字段比较 | 关闭flag |
| 3 | 受控新写/切换 | 批准的UAT范围 | idempotency key/CAS | 重复执行结果不变 | 停止consumer/回滚代码 |
| 4 | 保留审计与兼容窗口 | 直到Gate关闭 | manifest checksum | 无新旧混读 | 不删除新字段/证据 |

### 8.3 兼容矩阵

| 读取方 | 旧数据 | 新数据 | 混合数据 | 预期行为 |
|---|---|---|---|---|
| 旧代码 | 原合同内支持 | 默认不保证 | 禁止 | 回滚前必须停止新写；不得让旧代码读取v2数据 |
| 新代码 | 仅隔离adapter/审计 | 支持 | 普通计算阻断 | 不能静默换算 |
| 证据/迁移工具 | 只读支持 | 只读支持 | 分类报告 | 不参与奖金计算 |

### 8.4 幂等与重跑断言

- 第一次执行：产生一个可追踪 run/attempt 及确定结果。
- 相同输入重复执行：以本任务定义的 event/run/generation/idempotency 键 no-op 或得到完全相同结果。
- 中断后续跑：从权威状态判断旧/新完整状态，不把半状态当成功。
- 部分旧/部分新：普通计算阻断，输出精确异常对象与证据；不得自动洗白。

## 9. 测试设计

### 9.1 测试用例总表

| 测试编号 | 层级 | 场景 | 固定输入 | 精确预期 | 对应步骤 | 环境 | 状态 |
|---|---|---|---|---|---|---|---|
| TC-PVAM-06-01 | 单元 | 合法状态链 | 标准run | 按允许顺序到BATCH_READY；无跳跃 | STEP-06-01 | DEV | NOT_RUN |
| TC-PVAM-06-02 | 单元 | 非法/重复transition | OPEN→PUBLISHED、重复同transition | 非法阻断；相同CAS幂等 | STEP-06-01 | DEV | NOT_RUN |
| TC-PVAM-06-03 | 契约 | 统一Guard矩阵 | Global/Placement/Elite各RUNNING/FAILED/IN_DOUBT | 任一状态阻断消息与direct-call | STEP-06-02/03 | DEV+UAT | NOT_RUN |
| TC-PVAM-06-04 | 并发 | freeze与in-flight | 1个在途、1个新消息 | 在途按合同排空；新消息不进入冻结epoch | STEP-06-03/04 | DEV+UAT | NOT_RUN |
| TC-PVAM-06-05 | 状态 | persisted=false | Elite重算完成但无receipt | 只能RECALC_DONE_PENDING_BATCH/BATCH_READY，不DONE/PUBLISHED | STEP-06-04 | DEV+UAT | NOT_RUN |
| TC-PVAM-06-06 | receipt | checksum mismatch | batch A + receipt B | 状态IN_DOUBT/失败；不PUBLISHED | STEP-06-04 | DEV+UAT | NOT_RUN |
| TC-PVAM-06-07 | 空批 | 零结果run | 仍生成manifest/batch并等待receipt | STEP-06-04 | DEV+UAT | NOT_RUN |
| TC-PVAM-06-08 | 故障恢复 | 每状态点进程kill | 恢复后checksum等于干净重跑 | STEP-06-06 | UAT | NOT_RUN |
| TC-PVAM-06-09 | 可达性/集成 | Topology生产接线 | 源码+部署archive+change-user隔离topic | 唯一入口调用TopologyMutationService；period/version/guard有效；无直接run_update绕过；失败不产生半状态 | STEP-06-05 | DEV+UAT | NOT_RUN |

受控检查方案用例映射：`TC-011, TC-023, TC-024, TC-025, TC-026, TC-028, TC-029, TC-030, TC-032`。`TC-000` 为 RETIRED，不执行、不计完成率。

### 9.2 开发环境自动验证

```bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_SHA="3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2"
: "${WORK_COMMIT_SHA:?set the implementation commit for WORK-PVAM-06}"
: "${PARENT_COMMIT_SHA:?set the controlled parent commit; root WORK uses BASE_SHA}"
: "${PARENT_TREE_SHA:?set the tree of PARENT_COMMIT_SHA}"
: "${PARENT_PROVENANCE_JSON:?set schema-v2 parent provenance JSON}"
: "${APPROVED_COMMIT_REGISTRY_JSON:?set canonical WORK_APPROVED_COMMIT_REGISTRY.json}"
CONTROL_ROOT="${PVAM_CONTROL_ROOT:?point to the released 05_CONTROL directory}"

# Phase A：只验证固定基线和既有锚点，不要求 Common/Settlement/Ops 等未来目录存在。
bash "$CONTROL_ROOT/check_baseline_preflight.sh" \
  --repo "$REPO_ROOT" --base "$BASE_SHA" --work-id "WORK-PVAM-06"

# Phase B：在由 parent provenance 证明来源的干净 PARENT_COMMIT worktree 应用当前 WORK 的直接 patch，
# 校验 per-WORK scope、applied tree hash，随后只编译本 WORK 实际变更的 Python 文件并执行专属测试命令。
bash "$CONTROL_ROOT/validate_work_dev.sh" \
  --repo "$REPO_ROOT" \
  --base "$BASE_SHA" \
  --parent-commit "$PARENT_COMMIT_SHA" \
  --parent-tree "$PARENT_TREE_SHA" \
  --parent-provenance "$PARENT_PROVENANCE_JSON" \
  --approved-registry "$APPROVED_COMMIT_REGISTRY_JSON" \
  --work-commit "$WORK_COMMIT_SHA" \
  --work-id "WORK-PVAM-06" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --test-command-file "$CONTROL_ROOT/work-test-commands/WORK-PVAM-06.sh" \
  --out "evidence/WORK-PVAM-06/dev"
```

#### 9.2.1 必须落地的关键 `assert` 契约

以下断言骨架必须进入本任务列出的 pytest 文件；fixture 由测试文件实现，不得用复制生产公式的替身替代被测符号。

```python
import pytest
from Settlement.SettlementCoordinator import SettlementCoordinator
from Settlement.SettlementGuard import SettlementGuard


def test_state_and_guard_contract(redis_authority, run_manifest) -> None:
    coordinator = SettlementCoordinator(redis_authority)
    assert coordinator.transition(run_manifest.run_id, expected="OPEN", target="QUIESCING").state == "QUIESCING"
    with pytest.raises(RuntimeError):
        coordinator.transition(run_manifest.run_id, expected="QUIESCING", target="PUBLISHED")
    guard = SettlementGuard(redis_authority)
    redis_authority.set_local_state("ELITE", "RUNNING")
    with pytest.raises(RuntimeError):
        guard.assert_write_allowed(period=run_manifest.period, epoch=run_manifest.epoch)
```

通过标准：所有命令 exit code 0；pytest 无未解释 skip；证据schema校验通过。GPU/Dask/真实Redis/Kafka/MySQL未在DEV执行时必须标注 `NOT_RUN/PENDING_TEST_ENV`。

### 9.3 测试环境手工执行包

#### ENV-TC-PVAM-06-01：Epoch/Guard/重算/receipt/Topology

- 对应受控测试：`TC-011、TC-023、TC-024、TC-025、TC-026、TC-029、TC-030、TC-032`
- 环境版本：由 `uat/environment_manifest.yaml` 固定 Python/CUDA/RAPIDS/Dask/Redis/Kafka/DB/镜像/commit。
- 前置服务与数据：可控Kafka/Redis/Dask；部署archive；外部writer receipt模拟器
- 清理/隔离：必须使用专用 topic/group、Redis前缀、period/run_id；禁止复用生产数据。
- 执行命令：

```bash
RUN_ID=work06-$(date +%Y%m%d%H%M%S)
bash uat/scripts/run_work_uat.sh --work WORK-PVAM-06 --run-id "$RUN_ID" --tc TC-011,TC-023,TC-024,TC-025,TC-026,TC-029,TC-030,TC-032
```

- SQL/数据库证据命令（仅在专用 UAT schema 和 WORK-08 manifest 校验通过后执行；N/A 项只保留说明）：

```bash
mysql --defaults-extra-file="${MYSQL_CNF:?}" --batch --raw <<SQL
SELECT PERIOD_NUM, IS_PERFING, IS_PERFED, IS_CALCING, IS_CALCULATED,
       PERF_STARTED_AT, PERFED_AT, CALCULATE_STARTED_AT, CALCULATED_AT
  FROM AR_PERIOD
 WHERE PERIOD_NUM = ${PERIOD_NUM:?};
SQL
```

- 执行步骤：
1. 启动专用consumer并注入in-flight
2. 执行三类全量，在各状态点kill/restart
3. 发送匹配/不匹配receipt
4. 核验Topology生产入口或生成BLOCK
- 精确预期：
- 新消息不跨freeze；direct-call被guard
- persisted=false/无receipt不PUBLISHED
- 恢复checksum等于干净重跑
- Topology真实入口唯一且通过事务编排器；旧/新链状态正确，失败无半状态
- 必须回传：完整命令、exit code、stdout/stderr、JUnit/JSON、输入fixture SHA-256、代码commit、镜像、环境版本、执行起止时间、Redis/DB/Kafka/Dask前后证据。
- 失败停止与清理：停止专用consumer/job；保留PEL/状态和证据；禁止在未分析前清理失败现场；按第11节回滚。

### 9.4 SQL 对账样例

| 样例 | SQL输入/来源 | SQL预期 | Python预期 | 比较口径 | 允许差异 |
|---|---|---|---|---|---|
| Period状态对照 | AR_PERIOD IV_STEP 2/3/4 | SQL更新perf/calc状态 | Coordinator manifest映射但不改SQL语义 | 状态对照 | N/A |
| 发布证明 | 无外部receipt | SQL侧不构成本仓原子证明 | 状态停BATCH_READY | DEC-008边界 | N/A |

## 10. 验收标准映射

| 验收编号 | 来源TASK验收项 | 实现步骤 | 测试用例 | 所需证据 | 环境 | 通过条件 |
|---|---|---|---|---|---|---|
| AC-01 | 全仓只存在一个公开 SettlementGuard；旧 guard 仅为弃用 adapter 且无生产直连 | STEP-PVAM-06-02/06 | TC-024、TC-030 | EV-PVAM-06-01 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-02 | Global/Placement/Elite 任一 RUNNING/FAILED/IN_DOUBT 阻断所有生产写入口 | STEP-PVAM-06-02/03/06 | TC-024 | EV-PVAM-06-02 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-03 | 真实消息入口和核心写函数都执行 guard，direct-call 不能绕过 | STEP-PVAM-06-03/06 | TC-024、TC-030 | EV-PVAM-06-03 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-04 | `persisted=False` 只能进入 pending/batch-ready 前状态，不能 DONE/PUBLISHED | STEP-PVAM-06-04/06 | TC-029 | EV-PVAM-06-04 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-05 | freeze 后新消息不进入本 epoch；in-flight 归零并有 watermark | STEP-PVAM-06-04/06 | TC-023、TC-024 | EV-PVAM-06-05 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-06 | 全部 stage 的 period/run/epoch/generation/config/topology/version 一致 | STEP-PVAM-06-01/04/06 | TC-025、TC-026 | EV-PVAM-06-06 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-07 | 空结果也生成 manifest/batch 并等待外部 receipt | STEP-PVAM-06-04/06 | TC-029 | EV-PVAM-06-07 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-08 | 每个状态点崩溃后可恢复，最终 checksum 与干净重跑一致 | STEP-PVAM-06-06 | TC-026、TC-028、TC-032 | EV-PVAM-06-08 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-09 | 重复 transition/CAS 幂等；非法跳转阻断并审计 | STEP-PVAM-06-01/06 | TC-024、TC-026 | EV-PVAM-06-09 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-10 | 业务系统未回 receipt 时，正式读保持上一 committed 版本 | STEP-PVAM-06-04/06 | TC-029、TC-032 | EV-PVAM-06-10 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-11 | 测试 checkpoint 豁免有显式标记，生产 Gate C 不被误关闭 | STEP-PVAM-06-01/04/06 | TC-023、TC-026、TC-032 | EV-PVAM-06-11 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-12 | `TOPO-WIRE-01` 有固定 archive/部署证据，并已选择“验证现有接线”或“实施新接线”分支 | STEP-PVAM-06-05/06 | TC-011、TC-024、TC-030、TC-032 | EV-PVAM-06-12 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-13 | 接线后的拓扑变更入口具备 period/version/guard、影响范围重算、失败/回滚证据；测试脚本不作为生产证明 | STEP-PVAM-06-05/06 | TC-011、TC-024、TC-032 | EV-PVAM-06-13 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |

没有 STEP、TC 或 EV 映射的AC不得标记完成。任何含UAT的AC在未回传真实环境证据时只能为 `PENDING_TEST_ENV/BLOCKED`。

## 11. 风险、停工与回滚

### 11.1 风险清单

| 风险 | 触发条件 | 影响 | 预防措施 | 监测/证据 | 处置 |
|---|---|---|---|---|---|
| 状态迁移过度复杂 | 非法/漏transition | 卡死或假完成 | 有限状态表+CAS | transition audit | FAILED/IN_DOUBT |
| 旧guard残留 | 入口读取不同快照 | 并发脏写 | deprecated adapter+AST | callgraph | 回滚v2并冻结 |
| Topology部署信息不完整 | 无法确认真实topic/group/唯一入口 | 可能双消费或改错入口 | 固定archive+部署manifest+唯一入口断言 | callgraph/进程清单 | BLOCK，补齐材料后恢复 |

### 11.2 本任务强制停工条件

- HEAD、SQL blob、模型schema或上游TASK与受控基线不一致。
- 实施必须改变未批准的业务规则、精度、资格、分母、Country或发布职责才能继续。
- 需要修改排除文件/模块或扩大异常白名单才能通过测试。
- 关键mutation存活、SQL黄金样例出现未批准差异、幂等/原子/回滚断言失败。
- UAT权限、schema、数据或隔离条件不足；此时保持 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV`。

### 11.3 部署面与数据面回滚门禁

**当前可执行性：`BLOCKED_EXTERNAL_EVIDENCE`。** 当前材料没有给出真实部署系统、workload/release、镜像、配置对象和健康检查命令，因此不得以本地`export`或通用`git revert`冒充部署回滚。

部署前必须提供并签署`evidence/WORK-PVAM-06/rollback/ROLLBACK-MANIFEST-PVAM-v1.json`，至少包含：

- `deployment_system`、`environment`、`workload_id`、`release_before/after`、`image_before/after`；
- 精确的停止、回滚、恢复、健康检查和重新放量命令；
- Redis/Stream/ledger/run/manifest的备份或快照位置及SHA-256；
- 执行人、复核人、批准时间、允许的数据恢复范围；
- 命令dry-run/隔离演练的退出码和原始日志。

本任务数据面处置：进入QUIESCING/IN_DOUBT；保存epoch/run/coverage；恢复旧镜像前确保无in-flight写；不得删除FAILED/IN_DOUBT状态键或伪造OPEN。

统一执行顺序：

1. 停止新写并完成本任务定义的drain/freeze；
2. 导出任务相关Redis/Stream/ledger/run状态及checksum；
3. 由已签署manifest执行真实部署系统回滚，禁止仅修改当前shell环境变量；
4. 执行数据恢复/重放门禁；
5. 运行健康检查与幂等复验；
6. 保存命令、退出码、stdout/stderr和SHA-256。

缺少manifest、隔离演练或数据恢复证明时，只允许停止工作负载和保留证据，不得执行生产切换或声称“可独立回滚”。

### 11.4 不可逆部分

本任务计划不包含不可逆生产数据删除。若实施中出现清库、物理删除、无法恢复的trim或数据库DDL需求，立即停工并回上游方案审批。

## 12. 交付物与完成证据

| 编号 | 交付物/证据 | 生成步骤 | 位置/格式 | 验收人 | artifact_status |
|---|---|---|---|---|---|
| EV-PVAM-06-01 | AC-01验收证据：全仓只存在一个公开 SettlementGuard；旧 guard 仅为弃用 adapter 且无生产直连 | STEP-PVAM-06-02/06 | evidence/WORK-PVAM-06/attempt-*/ac/AC-01/ | 待指派QA | PENDING |
| EV-PVAM-06-02 | AC-02验收证据：Global/Placement/Elite 任一 RUNNING/FAILED/IN_DOUBT 阻断所有生产写入口 | STEP-PVAM-06-02/03/06 | evidence/WORK-PVAM-06/attempt-*/ac/AC-02/ | 待指派QA | PENDING |
| EV-PVAM-06-03 | AC-03验收证据：真实消息入口和核心写函数都执行 guard，direct-call 不能绕过 | STEP-PVAM-06-03/06 | evidence/WORK-PVAM-06/attempt-*/ac/AC-03/ | 待指派QA | PENDING |
| EV-PVAM-06-04 | AC-04验收证据：`persisted=False` 只能进入 pending/batch-ready 前状态，不能 DONE/PUBLISHED | STEP-PVAM-06-04/06 | evidence/WORK-PVAM-06/attempt-*/ac/AC-04/ | 待指派QA | PENDING |
| EV-PVAM-06-05 | AC-05验收证据：freeze 后新消息不进入本 epoch；in-flight 归零并有 watermark | STEP-PVAM-06-04/06 | evidence/WORK-PVAM-06/attempt-*/ac/AC-05/ | 待指派QA | PENDING |
| EV-PVAM-06-06 | AC-06验收证据：全部 stage 的 period/run/epoch/generation/config/topology/version 一致 | STEP-PVAM-06-01/04/06 | evidence/WORK-PVAM-06/attempt-*/ac/AC-06/ | 待指派QA | PENDING |
| EV-PVAM-06-07 | AC-07验收证据：空结果也生成 manifest/batch 并等待外部 receipt | STEP-PVAM-06-04/06 | evidence/WORK-PVAM-06/attempt-*/ac/AC-07/ | 待指派QA | PENDING |
| EV-PVAM-06-08 | AC-08验收证据：每个状态点崩溃后可恢复，最终 checksum 与干净重跑一致 | STEP-PVAM-06-06 | evidence/WORK-PVAM-06/attempt-*/ac/AC-08/ | 待指派QA | PENDING |
| EV-PVAM-06-09 | AC-09验收证据：重复 transition/CAS 幂等；非法跳转阻断并审计 | STEP-PVAM-06-01/06 | evidence/WORK-PVAM-06/attempt-*/ac/AC-09/ | 待指派QA | PENDING |
| EV-PVAM-06-10 | AC-10验收证据：业务系统未回 receipt 时，正式读保持上一 committed 版本 | STEP-PVAM-06-04/06 | evidence/WORK-PVAM-06/attempt-*/ac/AC-10/ | 待指派QA | PENDING |
| EV-PVAM-06-11 | AC-11验收证据：测试 checkpoint 豁免有显式标记，生产 Gate C 不被误关闭 | STEP-PVAM-06-01/04/06 | evidence/WORK-PVAM-06/attempt-*/ac/AC-11/ | 待指派QA | PENDING |
| EV-PVAM-06-12 | AC-12验收证据：`TOPO-WIRE-01` 有固定 archive/部署证据，并已选择“验证现有接线”或“实施新接线”分支 | STEP-PVAM-06-05/06 | evidence/WORK-PVAM-06/attempt-*/ac/AC-12/ | 待指派QA | PENDING |
| EV-PVAM-06-13 | AC-13验收证据：接线后的拓扑变更入口具备 period/version/guard、影响范围重算、失败/回滚证据；测试脚本不作为生产证明 | STEP-PVAM-06-05/06 | evidence/WORK-PVAM-06/attempt-*/ac/AC-13/ | 待指派QA | PENDING |
| EV-PVAM-06-P01 | SettlementCoordinator/Guard/Manifest源码 | 对应STEP/TC | evidence/WORK-PVAM-06/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-06-P02 | 三类全量与入口接入diff | 对应STEP/TC | evidence/WORK-PVAM-06/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-06-P03 | Topology接线diff、调用图与回滚记录 | 对应STEP/TC | evidence/WORK-PVAM-06/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-06-P04 | DEV状态/CAS测试 | 对应STEP/TC | evidence/WORK-PVAM-06/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-06-P05 | UAT并发/故障/receipt证据 | 对应STEP/TC | evidence/WORK-PVAM-06/attempt-*/package/ | 待指派QA | PENDING |

> 第 12 节交付物表中的 `PENDING` 属于 `artifact_status`，只表示工件尚未生成；环境验证状态必须使用 `validation_status ∈ {NOT_RUN, PASS, FAIL, PENDING_TEST_ENV, BLOCKED}`。

### 12.A 标准补丁与实施 commit 门禁

文档中的 `diff` 均为 `DESIGN_FRAGMENT`，不是预生成补丁。真实代码完成后必须执行受控脚本；不得手工省略 scope、worktree、tree hash 或测试绑定：

```bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_SHA="3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2"
: "${WORK_COMMIT_SHA:?set implementation commit}"
CONTROL_ROOT="${PVAM_CONTROL_ROOT:?point to released 05_CONTROL}"

bash "$CONTROL_ROOT/validate_work_patch.sh" \
  --repo "$REPO_ROOT" \
  --base "$BASE_SHA" \
  --parent-commit "$PARENT_COMMIT_SHA" \
  --parent-tree "$PARENT_TREE_SHA" \
  --parent-provenance "$PARENT_PROVENANCE_JSON" \
  --approved-registry "$APPROVED_COMMIT_REGISTRY_JSON" \
  --work-commit "$WORK_COMMIT_SHA" \
  --work-id "WORK-PVAM-06" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --out "evidence/WORK-PVAM-06/patch"
```

门禁必须证明：

1. `BASE_SHA` 是 `WORK_COMMIT_SHA` 的祖先；
2. 全部新增、修改、删除和 rename 的旧/新路径均落在 `WORK-PVAM-06` 批准 allowlist；
3. patch 非空，由 `git diff --full-index --binary BASE WORK_COMMIT` 生成；
4. 在干净 BASE worktree 上 `git apply --check --index` 与实际 apply 均成功；
5. apply 后 tree hash 与 `WORK_COMMIT_SHA^{tree}` 完全一致；
6. 证据记录 base、work commit、patch SHA-256、applied tree hash、changed paths、命令、退出码和日志；
7. DEV 结果必须在该 applied tree 上重跑，不能用 `HEAD==BASE_SHA` 的预检查冒充实施验证。

无代码变更的 WORK 必须提交受控 `NO_CODE_CHANGE` 裁决，不得生成空 patch 冒充通过。

## 13. 执行记录（实施后填写）

### 13.1 实际修改

| 步骤 | 实际修改文件/符号 | commit | 执行人 | 时间 | 结果 |
|---|---|---|---|---|---|
| STEP-PVAM-06-01 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-06-02 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-06-03 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-06-04 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-06-05 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-06-06 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |

### 13.2 实际验证

| 测试 | 环境 | 命令/版本 | 结果 | 证据 | 执行时间 |
|---|---|---|---|---|---|
| TC-PVAM-06-01 | DEV | 待执行 | NOT_RUN | EV-PVAM-06-* | 待执行 |
| TC-PVAM-06-02 | DEV | 待执行 | NOT_RUN | EV-PVAM-06-* | 待执行 |
| TC-PVAM-06-03 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-06-* | 待执行 |
| TC-PVAM-06-04 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-06-* | 待执行 |
| TC-PVAM-06-05 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-06-* | 待执行 |
| TC-PVAM-06-06 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-06-* | 待执行 |
| TC-PVAM-06-07 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-06-* | 待执行 |
| TC-PVAM-06-08 | UAT | 待执行 | NOT_RUN | EV-PVAM-06-* | 待执行 |
| TC-PVAM-06-09 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-06-* | 待执行 |

### 13.3 未完成项

| 项目 | 原因 | 风险 | 后续动作 | 责任人 | 截止时间 |
|---|---|---|---|---|---|
| UAT/外部材料 | 当前计划阶段未执行 | 不能关闭P0/P1 | 由WORK-08准入后执行 | 待指派 | 待批准 |

## 14. 偏离、发现项与上游回流

| 编号 | 类型 | 发现事实 | 是否影响业务/范围 | 临时动作 | 需要更新 | 最终裁决 |
|---|---|---|---|---|---|---|
| `DEV-PVAM-06-001` | `预留` | 待执行 | 待判断 | 停工/隔离 | WORK/TASK/DEC/REVIEW | 待裁决 |

任何新增缺陷必须回复核报告登记新的 `R-*`；任何业务/架构歧义必须新增或重开 `DEC-*`。

## 15. 任务结论

本任务结论：`BLOCKED`

说明：本项是**执行/验证结论**，不是文档审批结论。本 v1.3 任务书治理状态为 `DRAFT`、执行状态为 `BLOCKED`；未取得组织授权和实施/DEV/UAT/rollback 证据前不得转为 `READY`。

### 15.1 签署

| 角色 | 姓名 | 结论 | 时间 | 备注 |
|---|---|---|---|---|
| 实施 | 待指派 | 待签署 | 待补充 |  |
| 代码复核 | 待指派 | 待签署 | 待补充 |  |
| 测试环境执行 | 待指派 | 待签署 | 待补充 |  |
| 最终验收 | 待指派 | 待签署 | 待补充 |  |

## 16. 版本记录

| 版本 | 日期 | 变更内容 | 变更原因/来源 | 编制人 | 批准状态 |
|---|---|---|---|---|---|
| v1.0 | 2026-08-04 | 初版施工任务书 | `TASK-PVAM-06` + `PLAN-PVAM-v1.15` + 固定代码基线 | AI Agent（编制） | DRAFT |
| v1.1 | 2026-08-05 | 依据二轮核验报告完成定点修订并补齐治理追溯 | F-A/F-B/F-H/F-I/F-J/F-K/F-F/F-E/F-L/F-M/F-N 中适用项 | AI Agent（编制） | DRAFT |
| v1.2 | 2026-08-05 | 闭合 G-1：统一 `RecalcProcessResult` 类名并补齐 `should_ack`；历史版本曾调整施工套件审批状态，不改变 CHK/DEC/TASK/WORK 范围 | 历史会话声明（未形成可独立验证组织授权，现由 v1.3 取代） | AI Agent（编制） | SUPERSEDED |
| v1.3 | 2026-08-05 | 第四轮关闭 F3-01～F3-10：治理回退 DRAFT、Traceability v3、patch/DEV 双阶段、状态枚举及设计边界 | 三轮审查报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r6 | 2026-08-06 | 五轮 F5 定点修订：规范 v3 追溯、parent provenance/DEV CLI、控制状态字段及单一事实源 | 五轮审计报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r7 | 2026-08-06 | 六轮 S6：信任 registry 初版、归档哈希、临时目录与 Decimal finite 防护 | 六轮终局审计报告 | AI Agent（编制） | DRAFT |
| v1.3-r8 | 2026-08-06 | 七轮 B7：registry 发布信任根、四工件摘要、AC 来源保真及当前轮次引用 | 七轮终局审计报告 + B7 处置 | AI Agent（编制） | DRAFT |
