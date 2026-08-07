# WORK-PLAN-PVAM_v1.3 Redemption PV Amount Migration 施工总方案

> 文档定位：基于 `MODPLAN-PVAM_v1.2` 与九份专项修改任务书定义施工顺序、统一技术合同、停工条件、DEV/UAT证据、发布和回滚。当前尚无可核验组织施工授权，本文件不得被解释为开工批准。

## 0. 使用规则

1. 未知的人员、环境、部署对象和证据均显式登记为 `待签署/BLOCKED/PENDING_TEST_ENV`，不得用假设补齐。
2. 本 v1.3 套件治理状态为 `DRAFT`，施工授权为 `PENDING_ORGANIZATIONAL_APPROVAL`；所有 WORK 当前均为 `BLOCKED`。
3. `REJECTED / NEEDS_DECISION / DEFERRED` 不生成代码动作；`UAT_VERIFY` 只生成验证与证据动作。
4. 追溯链固定为 `CHK → R/RISK/UV → DEC → TASK → WORK → STEP → TC → EV`。
5. 实际执行结果必须写入验证与交付报告；本方案中的预期值不得替代实测。

## 1. 文档信息

| 字段 | 内容 |
|---|---|
| 文档编号 | `WORK-PLAN-PVAM_v1.3` |
| 文档名称 | Redemption PV Amount Migration 施工总方案 |
| 所属本轮修改总方案 | `MODPLAN-PVAM_v1.2`（DRAFT / PENDING_ORGANIZATIONAL_APPROVAL） |
| 复核报告 | `Redemption_PV_Amount_Migration_d74_复核报告_v1.5` |
| 检查方案 | `PLAN-PVAM-v1.15` |
| 七轮审查 | `B7-01～B7-06` 独立核验与第八轮定点修订；S6/F5 为历史来源 |
| 九轮治理修补 | `P0-TRACE-CHAIN-09-01`、`P1-WORK-INDEX-09-02`、`P2-DELIVERY-NAME-09-03` 定点闭环；不改变文档业务版本 |
| 项目代码基线 | `l343765828/Redemption@2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` |
| 修改方案套件SHA-256 | `5016812126ac48835f6c54c3a2e7dcdad5623cf8d528bc8d911fd45a37a96876`（对象：`MODPLAN-PVAM_v1.2_终稿修改方案套件.zip`，随本包提供） |
| SQL业务基线 | `sql_uat/*@2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`，排除Skill列明废弃/副本 |
| 编制人 | AI Agent（施工方案编制） |
| 复核人 | 待组织指派（AI Agent 仅完成文档自检，不代签组织审批） |
| 批准人 | 待组织授权人签署 |
| 批准时间 | 待签署 |
| 当前状态 | `DRAFT / GATED` |
| 计划实施窗口 | 未授权开工；仅允许继续修订文档、准备隔离分支和无业务副作用的门禁脚手架 |

### 1.1 权威来源与裁决顺序

1. `PLAN-PVAM-v1.15` 的检查判据与其中已关闭的 `DEC-*`；
2. 本轮受控但待组织授权的 `MODPLAN-PVAM_v1.2`、专项 `TASK-PVAM-*` 和可追溯专项规格；其授权状态以 `AUTHORIZATION_STATUS-PVAM-v2.md` 为准；
3. 已确认有效的 `sql_uat/` 生产结算 SQL——仅在不存在已关闭 DEC/corrected 裁决时作为 Legacy 行为 oracle；
4. `Doc/奖金制度.md` 等制度说明；
5. Python 固定基线实现；
6. 测试、历史报告和第三方评审。

裁决豁免：Python 与有效 SQL 冲突时，默认视为 Python 实现偏差；**已有正式决策改变业务口径时，以已关闭 DEC/批准的 corrected 合同为准**，不得用 Legacy SQL 反向覆盖。SQL 与 corrected 裁决的结果仍须分别登记 `LEGACY_PARITY / CORRECTED_APPROVED`，但双标签仅用于差分、回放与审计，不替代裁决顺位。有效 SQL 之间存在实质冲突且无既有 DEC 可裁决时，新增或重开 DEC 并停工。

### 1.2 文档批准与执行就绪分层

- 文档治理状态：`DRAFT`；授权状态：`PENDING_ORGANIZATIONAL_APPROVAL`。
- 代码审计结论：`REPORT-PVAM-v1.5 = REJECTED`，直至R-001～R-013闭环。
- 施工设计中的代码片段不是补丁；真实patch只在实施commit后生成并执行`git apply --check`。
- 依赖型 WORK 的 parent tree 必须同时通过受信任 `WORK_APPROVED_COMMIT_REGISTRY.json`；provenance 自报的 WORK 标签不构成批准。
- 部署/数据回滚依赖`ROLLBACK-MANIFEST-PVAM-v1`。当前材料未提供真实deployment/release/unit，禁止臆造；没有manifest的WORK不得部署。
- DEC-013和Gate C保持OPEN；依赖UAT的AC保持`PENDING_TEST_ENV`。

## 2. 施工方案生成依据

### 2.1 输入文档

| 输入 | 版本/编号 | 用途 | 治理/事实状态 | 备注 |
|---|---|---|---|---|
| 检查方案 | PLAN-PVAM-v1.15 | CHK/TC/判据 | CONTROLLED_DRAFT | 授权状态见 `AUTHORIZATION_STATUS-PVAM-v2.md` |
| 复核报告 | REPORT-PVAM-v1.5 | R-001~013、RISK、UV | FINAL / 代码结论 REJECTED | 总体 REJECTED 不弱化 |
| 修改总方案 | MODPLAN-PVAM_v1.2 | 范围/状态/依赖 | DRAFT（待组织授权） | 逻辑8组，07拆A/B |
| 专项修改任务书 | TASK-01~06、07A、07B、08 | 目标/排除/AC | DRAFT（待组织授权） | 九份 |
| 正式决策 | DEC-001~018相关项 | 业务/架构裁决 | 按上游CLOSED/OPEN状态 | DEC-013仍是UAT门禁 |
| 代码与SQL快照 | 2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb | 施工对象 | FROZEN | Python/SQL与097cae32一致 |
| 施工模板 | 两份Redemption模板 | 文档结构/状态/证据 | CONTROLLED | 本套件完整套用 |

### 2.2 开工准入门槛

- [x] R-001～R-013 已在修改方案中处置为 `ACCEPTED`。
- [ ] 已取得可核验组织批准人、角色、批准原文/签名、时间、范围和允许 Wave。
- [x] 代码基线完整SHA固定为 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`。
- [x] `AUDIT-WORKPLAN-PVAM-v1.1` 唯一条件 G-1 已闭合：07A 统一 `RecalcProcessResult` 并实现 `should_ack`。
- [ ] 当前工作副本、有效SQL blob、项目Skill和MODPLAN套件SHA由执行脚本复验。
- [ ] 每个WORK由实施/复核签署；feature flag、分支、回滚提交点就绪。
- [ ] DEV依赖可安装且测试可收集。
- [ ] UAT前置：DEC-013正式准入、DEC-009最小schema manifest、固定镜像/配置/数据和隔离权限齐备。
- [ ] WORK-06 的 `TOPO-WIRE-01` 必须先取得固定archive/部署manifest；已有接线则核验并修补，无接线则只修改已确认的唯一真实拓扑入口接入 `TopologyMutationService`，不得创建第二topic/group。
- [ ] GAP-DEC004-2B保持DEFERRED；不得将fixture解释为生产供给链通过。
- [ ] WORK-08A已产出部署级入口清单：订单/退款Topic、group、启动命令、镜像与实际consumer文件；在此之前只允许实现纯schema/normalizer，不得创建第二消费者。
- [ ] Redis Server版本必须由UAT `INFO server`实测，不得用Python redis客户端版本代替。

施工套件当前为 `DRAFT / GATED`。在组织授权完成前所有 WORK 均为 `BLOCKED`；授权后仍须按依赖、patch、DEV、rollback 和 UAT 门禁逐项解锁。

## 3. 本轮施工目标与完成定义

### 3.1 总体目标

在固定基线上建立 micro-units/version/ppm/cents 公共合同、唯一订单/退款和period边界、统一配置/Active、Elite原子账本与外部发布batch、统一Settlement Guard/Epoch、fail-closed事件消费和ACK-aware Stream保留，并形成可重放的DEV/UAT证据链；不改变未批准业务公式。

### 3.2 总体完成定义（DoD）

- [ ] 九份WORK全部达到 `VERIFIED`，或仅保留经正式批准且不含P0/P1的偏离。
- [ ] R-001～R-013均有代码diff、测试、EV及对应CHK关闭证据。
- [ ] 所有金额字段内部为version=2 int64 micro-units，最终金额为integer cents/明确Decimal string，无生产float链。
- [ ] 同一normalized event三stage的identity/revision/hash/delta一致且幂等。
- [ ] Global/Placement/Elite统一guard与状态机，receipt前不PUBLISHED。
- [ ] Recalc未处理消息不ACK；所有producer无固定`maxlen=100000`；>100000多group恢复测试通过。
- [ ] DEV全部通过；UAT真实依赖项全部执行并回传原始证据。未执行不得标通过。
- [ ] 相关CHK与TC-001～032（TC-000 RETIRED）完成状态明确；Gate C在生产材料未齐时保持OPEN。
- [ ] 发布/回滚演练与最终验证交付报告完成。

## 4. 施工范围

### 4.1 专项施工任务索引

| 顺序 | 施工任务 | 来源修改任务 | 来源问题 | 关联决策 | 内容摘要 | 前置任务 | 可否并行 | 状态 |
|---|---|---|---|---|---|---|---|---|
| 1 | `WORK-PVAM-01` | `TASK-PVAM-01` | R-001、R-002 | DEC-002、DEC-008、DEC-014 | 金额编码公共层与基础模型适配器 | 无 | 否 | BLOCKED |
| 2 | `WORK-PVAM-02` | `TASK-PVAM-02` | R-003、R-007 | DEC-002、DEC-005、DEC-006、DEC-007、DEC-010 | 订单/退款入口金额放大与边界转换 | WORK-PVAM-01达到DEV_VERIFIED | 条件 | BLOCKED |
| 3 | `WORK-PVAM-03` | `TASK-PVAM-03` | R-004 | DEC-001、DEC-002、DEC-003、DEC-009、DEC-014 | 配置解析、ppm 与硬编码清理 | WORK-PVAM-01 DEV_VERIFIED | 条件 | BLOCKED |
| 4 | `WORK-PVAM-04` | `TASK-PVAM-04` | R-005、R-006 | DEC-004、DEC-016、DEC-018 | monthActivePV 唯一取值与 Active 同源现算 | WORK-PVAM-01、WORK-PVAM-03 DEV_VERIFIED；真实供给链UAT仍BLOCKED | 否 | BLOCKED |
| 5 | `WORK-PVAM-05` | `TASK-PVAM-05` | R-008、R-011 | DEC-007、DEC-008、DEC-011、DEC-017 | Elite SOURCE 原子性与外部发布证明 | WORK-PVAM-01、02、03 DEV_VERIFIED | 否 | BLOCKED |
| 6 | `WORK-PVAM-06` | `TASK-PVAM-06` | R-009、R-010 | DEC-007、DEC-008、DEC-010、DEC-012 | 全量重算状态机、统一 Guard 与发布分层 | WORK-PVAM-01、WORK-PVAM-02、WORK-PVAM-05 DEV_VERIFIED；WORK-08A调用图证据可并行 | 否 | BLOCKED |
| 7 | `WORK-PVAM-07A` | `TASK-PVAM-07A` | R-012A（parent_issue=R-012） | DEC-010 | Recalc Consumer ACK 紧急 fail-closed 修复 | 无金额域依赖；可与WORK-01并行 | 是 | BLOCKED |
| 8 | `WORK-PVAM-07B` | `TASK-PVAM-07B` | R-012B（parent_issue=R-012）、R-013 | DEC-007、DEC-010 | 事件路由、正式 Handler 与 Stream 保留护栏 | WORK-PVAM-06、WORK-PVAM-07A DEV_VERIFIED | 否 | BLOCKED |
| 9 | `WORK-PVAM-08` | `TASK-PVAM-08` | RISK-001、RISK-002、UV-001～UV-005、OPT-001、OPT-002、GAP-DEC004-2B | DEC-004、DEC-009、DEC-010、DEC-012、DEC-013、DEC-017、DEC-018 | 风险、UAT 准入与机器可读证据包 | 阶段A可与所有DEV任务并行；阶段B依赖DEC-013及WORK-01～07B DEV_VERIFIED | 是 | BLOCKED |

说明：逻辑上仍为 `WORK-PVAM-01～08` 八组；`WORK-PVAM-07` 为降低P0 ACK风险拆成 `07A/07B`，因此交付九份专项文件。

### 4.2 纳入范围

- `Common` 金额、period、配置和Active纯函数/adapter。
- UserStats、Placement、Elite、PE、SE、EAB、Leadership生产可达金额/Active/配置路径。
- 订单/退款normalized事件和三个增量stage。
- Redis权威commit、Settlement Epoch/Guard、outbox consumer/schema/handler/retention。
- 测试、UAT脚本、schema/config/callgraph/traceability/evidence manifest。

### 4.3 明确排除范围

- PB、SFB、GPB、CRB算法；Team Bonus units-int生产服务建设。
- `GAP-DEC004-2B` AR_CONFIG→Delta→Redis生产写入/失效producer。
- RISK/UV自身的代码修复；仅验证、取证和阻断。
- 业务系统MariaDB writer、正式读切换和跨Redis/DB原子保证。
- `_bak/_final/copy`、9个废弃SQL、`GraphService.run_bfs`、demo/print脚本作为生产证明。

### 4.4 禁止顺手修改

不得改变奖金资格、分母、Country/TYPE政策、period/退款规则、截断/舍入点或有效SQL结果；任何必须改变这些内容的发现均停工回上游。

## 5. 施工依赖与顺序

### 5.1 依赖矩阵

| 施工任务 | 依赖对象 | 依赖类型 | 依赖满足条件 | 未满足时处理 |
|---|---|---|---|---|
| WORK-08A | 固定基线/材料 | 治理 | 先交付证据schema、原生命令包装与callgraph工具 | BLOCK外部部分，不阻止无关DEV；但各WORK引用其脚本前必须先完成08A |
| WORK-01 | 代码基线 | 代码 | HEAD精确、TASK批准 | BLOCK |
| WORK-07A | 现有consumer | 代码 | 独立hotfix审批 | 可与01并行 |
| WORK-02 | WORK-01 | 接口 | 公共units/version DEV通过 | 不得开工 |
| WORK-03 | WORK-01 | 接口 | 公共ppm API可用 | 不得开工 |
| WORK-04 | WORK-01/03 | 接口/数据 | units+ConfigSnapshot可用 | 读侧可做；真实供给侧保持BLOCKED |
| WORK-05 | WORK-01/02/03 | 数据/事件 | units/event/config合同稳定 | 不得开工 |
| WORK-06 | WORK-01/02/05 | 架构 | units/period与Elite batch/receipt合同稳定 | 不得开工 |
| WORK-07B | WORK-06/07A | 事件 | 状态/receipt与fail-closed结果稳定 | 不得开工 |
| WORK-08B | DEC-013+全部DEV | 环境 | UAT准入与manifest齐全 | PENDING_TEST_ENV/BLOCKED |

### 5.2 执行批次

| 批次 | 任务 | 开始条件 | 批次完成条件 | 失败影响 |
|---|---|---|---|---|
| Wave 0 | WORK-08 阶段A | 施工方案批准 | 基线/manifest/脚本DEV通过 | 缺外部材料只阻断对应UAT |
| Wave 1 | WORK-01 + WORK-07A | 各自批准 | 公共层与ACK hotfix DEV_VERIFIED | 01失败阻断金额链；07A独立 |
| Wave 2 | WORK-02 + WORK-03 | WORK-01通过 | 边界/period/config DEV_VERIFIED | 阻断04/05 |
| Wave 3 | WORK-04 | 01/03通过 | Active读侧与消费者DEV通过 | 真实2B仍BLOCKED |
| Wave 4 | WORK-05 | 01/02/03通过 | Elite atomic/batch DEV通过 | 阻断06 |
| Wave 5 | WORK-06 | 01/02/05通过；08A调用图可用 | Coordinator/Guard/receipt DEV通过 | 阻断07B |
| Wave 6 | WORK-07B | 06/07A通过 | schema/handler/retention DEV通过 | 阻断全链路 |
| Wave 7 | WORK-08 阶段B | DEC-013+全部DEV | TC-001~032证据包完成 | 任何P0失败总体REJECTED |

### 5.3 强制停工条件

- commit/SQL/blob/schema与基线不一致；
- 发现实施会改变未批准业务结果；
- 必须修改排除项、开放DEC或DEFERRED项才能继续；
- 无法独立回滚，或继续会造成不可恢复的混合编码、trim或发布；
- SQL黄金样例、幂等、原子、guard、ACK或恢复出现未解释差异；
- 只能通过删测试、扩大异常白名单或把UAT写成DEV通过来“完成”。

## 6. 全局技术约束

### 6.1 依赖与架构约束

- 依赖方向：`Common → Model adapters / User / Placement / Bonus`；Common禁止反向导入业务层。
- I/O、纯计算、权威提交、发布/receipt、consumer/retention分层。
- Redis是本仓权威状态；关系库正式writer和读切换属于业务系统。
- GPU/Dask仅消费已经规范化的int64列；禁止金额隐式提升为float。

### 6.2 数据契约

| 对象 | 字段/接口 | 单位与类型 | 空值/默认值 | 兼容规则 | 责任任务 |
|---|---|---|---|---|---|
| UserStats/EliteBonusStats | amount_encoding_version | Optional[int]；新域必须2 | 缺失=legacy unknown | 普通计算阻断 | WORK-01 |
| PV/BV/GPV/1L/2L/结余 | 金额字段 | int64 micro-units | 业务零=0，不用None洗白 | 两处边界转换 | WORK-01/02 |
| 费率 | *_rate_ppm | signed int64 ppm | 由键矩阵决定缺失/0 | raw+canonical checksum | WORK-03 |
| 最终奖金 | *_cents | int64 cents | 0明确 | E/PE/SE/LB/TB截断；EAB最终HALF_UP | WORK-01/02 |
| Active | is_active计算结果 | bool/0\|1派生 | 不物化共享权威 | 同pv+monthActivePV现算 | WORK-04 |
| Period | PeriodSnapshot | immutable typed object | 无默认/猜测 | AR_PERIOD唯一解析 | WORK-02 |
| Normalized event | effective_pv_delta_units | strict int64/version2 | 不可空 | 三stage同hash/revision | WORK-02/06 |
| Settlement event | v2 envelope | JSON object+schema/hash | 必填字段不可缺 | v1兼容仅确定映射 | WORK-07B |

### 6.3 精度与舍入

- 内部PV/金额状态：micro-units整数；费率：ppm整数；最终支付：cents整数。
- E/PE/SE/LB/TB只在有效SQL规定点向零截断；TB_RATE先截断6位；EAB中间不舍入，个人最终一次ROUND_HALF_UP两位。
- 禁止 `float`、`Decimal(str(float))`、`int(round(float))` 和 `/100.0` 输出财务值。
- 示例：1,500.99×15%=225.1485，SQL/目标输出22514 cents（225.14）。

### 6.4 并发、幂等和重跑

- event identity不含period；同identity+hash幂等，不同hash冲突。
- Redis权威提交必须把业务状态/revision/dirty/stage/outbox放同一原子单元。
- Settlement transition以run/epoch/generation CAS；receipt前不PUBLISHED。
- ACK只在handler+postcondition、批准noop或DLQ成功后；retention只按全部登记group安全水位。

### 6.5 可观测性与审计

日志/manifest必须含 work/step/tc/ev、period/run/epoch/generation、event id/hash、schema/version、config/topology/checksum、状态前后和错误类别；禁止密钥、完整敏感payload和无界对象。

## 7. 文件与变更总索引

| 施工任务 | 文件/对象 | 变更类型 | 目标符号/表/配置 | 预期行为 | 对应测试 |
|---|---|---|---|---|---|
| WORK-PVAM-01 | `Common/PvAmount.py` | 新增 | 模块级常量与纯函数 | 唯一公共金额 API | TC-PVAM-01-01; TC-PVAM-01-02 |
| WORK-PVAM-01 | `Common/AmountModelAdapter.py` | 新增 | `AmountRecordState`、`classify_amount_record` | 普通计算只能接收 NEW | TC-PVAM-01-01; TC-PVAM-01-02 |
| WORK-PVAM-01 | `Model/User/UserStats.py` | 修改 | `UserStats.amount_encoding_version` | 新记录显式2，旧记录保持None | TC-PVAM-01-01; TC-PVAM-01-02 |
| WORK-PVAM-01 | `Model/User/EliteBonusStats.py` | 修改 | version、`estimated_bonus_cents` | v2 不写 float | TC-PVAM-01-01; TC-PVAM-01-02 |
| WORK-PVAM-01 | `User/UserStatsService.py` | 修改 | `_get_or_init_user` | 单位可审计 | TC-PVAM-01-01; TC-PVAM-01-02 |
| WORK-PVAM-01 | `User/GlobalRecalculationService.py` | 修改 | `_new_zero_user_stats`、`_mget_users_with_exists` | 全量不混算 | TC-PVAM-01-01; TC-PVAM-01-02 |
| WORK-PVAM-01 | `User/PlacementIncrementalService.py` / `User/PlacementRecalculationService.py` | 修改 | 节点构造与批量读取 | placement全字段同单位 | TC-PVAM-01-01; TC-PVAM-01-02 |
| WORK-PVAM-01 | `User/EliteBonusService.py` / `User/GlobalEliteBonusRecalculationService.py` | 修改 | `_build_blank_node` / `_new_blank_stats` 等 | Elite状态可判编码 | TC-PVAM-01-01; TC-PVAM-01-02 |
| WORK-PVAM-01 | `User/Test/test_pv_amount_common.py` / `test_amount_model_version.py` | 新增 | pytest 用例 | 可自动验证 | TC-PVAM-01-01; TC-PVAM-01-02 |
| WORK-PVAM-02 | `Common/PeriodResolver.py` | 新增 | `PeriodRepository`、`PeriodResolver`、`PeriodSnapshot` | 唯一period合同 | TC-PVAM-02-01; TC-PVAM-02-02 |
| WORK-PVAM-02 | `Model/Order/NormalizedPvEvent.py` | 新增 | 不可变事件模型 | 三stage同一payload | TC-PVAM-02-01; TC-PVAM-02-02 |
| WORK-PVAM-02 | `MessageConsumer/PvEventSchema.py` / `PvEventNormalizer.py` | 新增 | schema与normalize | 非法输入fail-loud | TC-PVAM-02-01; TC-PVAM-02-02 |
| WORK-PVAM-02 | `Order/RefundReversalLedger.py` | 新增 | 原订单冲销CAS | 无二次负delta | TC-PVAM-02-01; TC-PVAM-02-02 |
| WORK-PVAM-02 | `User/UserStatsService.py` | 修改 | `update_elite_performance` | 不再缩放 | TC-PVAM-02-01; TC-PVAM-02-02 |
| WORK-PVAM-02 | `User/PlacementIncrementalService.py` | 修改 | `update_placement_performance`、`_get_prev_period` | 与UserStats同输入 | TC-PVAM-02-01; TC-PVAM-02-02 |
| WORK-PVAM-02 | `User/EliteBonusService.py` | 修改 | `update_elite_bonus_incremental`、bonus字段 | 无float | TC-PVAM-02-01; TC-PVAM-02-02 |
| WORK-PVAM-02 | `User/PlacementRecalculationService.py` | 修改 | `_get_prev_period`、`_process_extract_batch`、`_calculate_placement_pv`、`_write_back_placement_matrix` | 无精度漂移 | TC-PVAM-02-01; TC-PVAM-02-02 |
| WORK-PVAM-02 | `User/PEBonusService.py` / `SuperEliteBonusService.py` / `LeadershipBonusGPUService.py` / `EliteAchievementBonusService.py` | 修改 | 金额计算边界 | writer前明确cents/string | TC-PVAM-02-01; TC-PVAM-02-02 |
| WORK-PVAM-02 | `MessageConsumer/PvEventConsumer.py`（CALLGRAPH_GATED） | 条件新增 | 仅在部署证明确认没有现存PV入口且新消费者获批时创建 | 唯一可追踪入口 | TC-PVAM-02-01; TC-PVAM-02-02 |
| WORK-PVAM-03 | `Common/BonusConfig.py` | 新增 | `ConfigRequirement`/`ConfigSnapshot`/parser | 运行期唯一配置对象 | TC-PVAM-03-01; TC-PVAM-03-02 |
| WORK-PVAM-03 | `Model/Config/ConfigSnapshot.py` | 新增 | 可序列化manifest模型 | 证据可追溯 | TC-PVAM-03-01; TC-PVAM-03-02 |
| WORK-PVAM-03 | `User/PEBonusService.py` | 修改 | `__init__`、`execute_batch` | 无硬编码 | TC-PVAM-03-01; TC-PVAM-03-02 |
| WORK-PVAM-03 | `User/EliteBonusService.py` | 修改 | `__init__` | 无占位默认 | TC-PVAM-03-01; TC-PVAM-03-02 |
| WORK-PVAM-03 | `User/GlobalEliteBonusRecalculationService.py` | 修改 | `__init__` | 全量增量同run | TC-PVAM-03-01; TC-PVAM-03-02 |
| WORK-PVAM-03 | `User/SuperEliteBonusService.py` | 修改 | `_parse_se_rate`、`_parse_country_mapping` | 非法与豁免分开 | TC-PVAM-03-01; TC-PVAM-03-02 |
| WORK-PVAM-03 | `User/EliteAchievementBonusService.py` / `LeadershipBonusGPUService.py` | 修改 | 配置读取接口 | 同run checksum | TC-PVAM-03-01; TC-PVAM-03-02 |
| WORK-PVAM-03 | `User/team_bonus_tb.py` 测试适配 | 修改 | oracle config输入 | SQL parity不变 | TC-PVAM-03-01; TC-PVAM-03-02 |
| WORK-PVAM-03 | `User/Test/test_bonus_config.py` | 新增 | pytest | 配置合同可测 | TC-PVAM-03-01; TC-PVAM-03-02 |
| WORK-PVAM-04 | `Common/MonthActivePvProvider.py` | 新增 | provider/repository协议 | 唯一门槛getter | TC-PVAM-04-01; TC-PVAM-04-02 |
| WORK-PVAM-04 | `Common/ActiveRule.py` | 新增 | `is_active` / vector helpers | 同源纯计算 | TC-PVAM-04-01; TC-PVAM-04-02 |
| WORK-PVAM-04 | `User/PEBonusService.py` | 修改 | `execute_batch` | 同源结果 | TC-PVAM-04-01; TC-PVAM-04-02 |
| WORK-PVAM-04 | `User/SuperEliteBonusService.py` | 修改 | `calculate_se_bonus` | 分母/不发规则保持 | TC-PVAM-04-01; TC-PVAM-04-02 |
| WORK-PVAM-04 | `User/EliteAchievementBonusService.py` | 修改 | `calculate_eab_bonus` | 理论池保持 | TC-PVAM-04-01; TC-PVAM-04-02 |
| WORK-PVAM-04 | `User/LeadershipBonusGPUService.py` | 修改 | `compute_leadership_bonus`输入组装 | 九代/双闸门不变 | TC-PVAM-04-01; TC-PVAM-04-02 |
| WORK-PVAM-04 | `User/run_monthly_bonus_pipeline_v2.py` | 修改 | run manifest组装 | run内冻结 | TC-PVAM-04-01; TC-PVAM-04-02 |
| WORK-PVAM-04 | `User/Test/test_month_active_pv.py` | 新增 | pytest | 可自动验证 | TC-PVAM-04-01; TC-PVAM-04-02 |
| WORK-PVAM-05 | `Model/User/EliteSourceAssignment.py` | 新增 | assignment模型/序列化 | 可重放审计 | TC-PVAM-05-01; TC-PVAM-05-02 |
| WORK-PVAM-05 | `User/EliteBonusService.py` | 修改 | `_track_bonus_source`、`update_elite_bonus_incremental`、`_batch_save` | 全成或全不成 | TC-PVAM-05-01; TC-PVAM-05-02 |
| WORK-PVAM-05 | `User/EliteRedisCommit.py` | 新增 | `commit_incremental_stage` | 单一提交API | TC-PVAM-05-01; TC-PVAM-05-02 |
| WORK-PVAM-05 | `User/EliteBonusCandidateBuilder.py` | 新增 | candidate gate | 不合格阻断 | TC-PVAM-05-01; TC-PVAM-05-02 |
| WORK-PVAM-05 | `User/EliteBonusPublishBatch.py` | 新增 | batch/manifest模型 | external可校验 | TC-PVAM-05-01; TC-PVAM-05-02 |
| WORK-PVAM-05 | `User/GlobalEliteBonusRecalculationService.py` | 修改 | `settle_period`、`_process_parent_batch`、`_emit_settlement_done` | 等待WORK-06 receipt | TC-PVAM-05-01; TC-PVAM-05-02 |
| WORK-PVAM-05 | `User/EliteBonusService.py::snapshot_period_to_db` | 修改 | 旧接口隔离 | 职责边界清晰 | TC-PVAM-05-01; TC-PVAM-05-02 |
| WORK-PVAM-05 | `User/Test/test_elite_atomic_commit.py` / `test_elite_publish_batch.py` | 新增 | pytest | 可重复验证 | TC-PVAM-05-01; TC-PVAM-05-02 |
| WORK-PVAM-06 | `Settlement/SettlementRunManifest.py` | 新增 | run/epoch/generation/watermark/checksum | 统一run合同 | TC-PVAM-06-01; TC-PVAM-06-02 |
| WORK-PVAM-06 | `Settlement/SettlementGuard.py` | 新增 | `assert_write_allowed`/`assert_recalc_allowed` | 全部入口同规则 | TC-PVAM-06-01; TC-PVAM-06-02 |
| WORK-PVAM-06 | `Settlement/SettlementCoordinator.py` | 新增 | transition/freeze/drain/receipt/recover | 单调、幂等 | TC-PVAM-06-01; TC-PVAM-06-02 |
| WORK-PVAM-06 | `User/UserStatsService.py` | 修改 | `assert_period_settlement_available` | 不遗漏Elite | TC-PVAM-06-01; TC-PVAM-06-02 |
| WORK-PVAM-06 | 三个全量服务 | 修改 | settle入口与完成事件 | persisted false不DONE | TC-PVAM-06-01; TC-PVAM-06-02 |
| WORK-PVAM-06 | `MessageConsumer/PvEventConsumer.py`或WORK-08A确认的唯一真实PV入口；三stage核心入口 | 条件修改 | guard调用 | direct call也阻断 | TC-PVAM-06-01; TC-PVAM-06-02 |
| WORK-PVAM-06 | `User/TopologyMutationService.py` / `MessageConsumer/UserConsumer.py` | 修改 | `orchestrate_topology_mutation` / `consume_loop` | 旧链→图变更→新链→受影响节点重算可恢复 | TC-PVAM-06-01; TC-PVAM-06-02 |
| WORK-PVAM-06 | `User/Test/test_settlement_coordinator.py` / `test_settlement_guard.py` | 新增 | pytest | 可自动验证 | TC-PVAM-06-01; TC-PVAM-06-02 |
| WORK-PVAM-07A | `MessageConsumer/RecalcProcessResult.py` | 新增 | 结果枚举 | 可审计 | TC-PVAM-07A-01; TC-PVAM-07A-02 |
| WORK-PVAM-07A | `MessageConsumer/RecalcStreamConsumer.py` | 修改 | `process_event`→`process_entry` | fail-closed | TC-PVAM-07A-01; TC-PVAM-07A-02 |
| WORK-PVAM-07A | 同文件 | 修改 | `start_consuming` | 未处理保PEL | TC-PVAM-07A-01; TC-PVAM-07A-02 |
| WORK-PVAM-07A | 同文件 | 修改 | `_reclaim_stale` | normal/reclaim一致 | TC-PVAM-07A-01; TC-PVAM-07A-02 |
| WORK-PVAM-07A | `MessageConsumer/Test/test_recalc_ack_fail_closed.py` | 新增 | pytest | hotfix可独立验证 | TC-PVAM-07A-01; TC-PVAM-07A-02 |
| WORK-PVAM-07B | `MessageConsumer/RecalcEventSchema.py` | 新增 | v2 envelope/decoder | 唯一可识别 | TC-PVAM-07B-01; TC-PVAM-07B-02 |
| WORK-PVAM-07B | `MessageConsumer/RecalcHandlerRegistry.py` / `RecalcDisposition.py` | 新增 | registry/disposition | 无pass默认 | TC-PVAM-07B-01; TC-PVAM-07B-02 |
| WORK-PVAM-07B | `Settlement/RecalcEventPublisher.py` | 新增 | publisher | 可双写迁移 | TC-PVAM-07B-01; TC-PVAM-07B-02 |
| WORK-PVAM-07B | Global/Elite/Placement producer文件 | 修改 | xadd调用 | 统一事件 | TC-PVAM-07B-01; TC-PVAM-07B-02 |
| WORK-PVAM-07B | `MessageConsumer/RecalcStreamConsumer.py` | 修改 | decoder/dispatch | ACK条件明确 | TC-PVAM-07B-01; TC-PVAM-07B-02 |
| WORK-PVAM-07B | `Ops/RecalcStreamRetention.py` | 新增 | 安全水位/trim/replay | 慢group安全 | TC-PVAM-07B-01; TC-PVAM-07B-02 |
| WORK-PVAM-07B | `MessageConsumer/Test/test_recalc_event_v2.py` / `test_stream_retention.py` | 新增 | pytest | 可验证 | TC-PVAM-07B-01; TC-PVAM-07B-02 |
| WORK-PVAM-08 | `evidence/manifest.schema.json` | 新增 | 证据schema | 统一证据格式 | TC-PVAM-08-01; TC-PVAM-08-02 |
| WORK-PVAM-08 | `uat/*.yaml/json` | 新增 | 环境/schema/config/run/callgraph manifest | 外部材料可审计 | TC-PVAM-08-01; TC-PVAM-08-02 |
| WORK-PVAM-08 | `05_CONTROL/check_baseline_preflight.sh` / `validate_work_patch.sh` / `validate_work_dev.sh`；`uat/scripts/run_work_uat.sh` / `stop_workload.sh` | 受控交付/新增 | DEV 唯一门禁与 UAT 执行器 | DEV 不可绕过控制脚本；UAT 仅在 DEC-013 后运行 | TC-PVAM-08-01; TC-PVAM-08-02 |
| WORK-PVAM-08 | `uat/scripts/run_sql_python_diff.py` | 新增 | 差分器 | Legacy/Corrected分列 | TC-PVAM-08-01; TC-PVAM-08-02 |
| WORK-PVAM-08 | `uat/scripts/redis_stream_probe.py` | 新增 | Stream证据工具 | ACK证据完整 | TC-PVAM-08-01; TC-PVAM-08-02 |
| WORK-PVAM-08 | `uat/scripts/build_callgraph.py` | 新增 | 调用图工具 | Topology与所有P0可达性 | TC-PVAM-08-01; TC-PVAM-08-02 |
| WORK-PVAM-08 | `traceability_manifest.json` / builder | 新增 | 追踪 | 无孤儿编号 | TC-PVAM-08-01; TC-PVAM-08-02 |
| WORK-PVAM-08 | 现有脚本测试包装器 | 新增/修改测试 | pytest entry | OPT-001落地 | TC-PVAM-08-01; TC-PVAM-08-02 |

实际新增未列文件前必须判断是否范围漂移并登记偏离。

## 8. 数据迁移与兼容总策略

### 8.1 迁移对象

| 数据源 | 数据量估计 | 旧格式 | 新格式 | 转换边界 | 校验方式 | 回滚方式 |
|---|---|---|---|---|---|---|
| Redis UserStats/EliteBonusStats | UAT/生产扫描后填写 | 缺version/legacy值 | version=2 units/cents | 受控重建/新写，不自动换算 | 数量/版本/金额汇总 | 停止v2写，读最后committed legacy |
| Kafka/MQ事件 | 按峰值/停机窗口计算 | raw金额/异构payload | normalized v2 event | raw schema边界 | 三stagehash/revision/delta | 关闭v2consumer/dual-read |
| AR_CONFIG快照 | 按run | 服务本地解析 | frozen ConfigSnapshot/ppm | run启动 | raw/canonical/checksum | 关闭snapshot v2 |
| Recalc Stream | 按容量模型 | v1异构/fixed trim | v2 envelope/ACK-aware retention | 统一publisher | 多group/100001/replay | 关闭v2publish，保留事件 |
| 证据包 | 每attempt | 散落日志 | immutable manifest | WORK-08 scripts | schema+SHA | 不删除旧attempt |

### 8.2 兼容窗口

- 旧代码读新数据：禁止；回滚前先停止v2新写。
- 新代码读旧数据：只允许隔离adapter/扫描，普通计算阻断。
- 混合版本运行：只在明确dual-read/dual-publish窗口且event_id幂等时允许；金额状态禁止混合。
- 结束条件：所有UAT、回滚、调用图、版本分布和外部receipt证明通过，且正式批准切换。

### 8.3 迁移安全要求

全部脚本默认dry-run、专用prefix/period、可分批/断点续跑/幂等；输出数量、金额/PV汇总、版本分布、异常和checksum。不可逆操作必须另行批准。

## 9. 验证分层与证据要求

### 9.0 唯一受控 DEV 入口

所有 WORK 必须通过发布包中的 `05_CONTROL/check_baseline_preflight.sh`、`05_CONTROL/validate_parent_provenance.py`、`05_CONTROL/validate_work_patch.sh` 与 `05_CONTROL/validate_work_dev.sh`。后者以签名式 parent provenance 绑定 `PARENT_COMMIT_SHA/PARENT_TREE_SHA` 与允许前置 WORK 的完整 first-parent 累积链，只生成 `PARENT_COMMIT_TREE → WORK_COMMIT_TREE` 的当前 WORK patch，并执行 scope、apply、tree-hash、changed-file `py_compile` 和专属测试。任何文档内直接列出的 `compileall`、`py_compile`、`pytest` 仅为附加局部检查，不得绕过上述唯一门禁。



### 9.1 开发环境验证

| 验证项 | 命令/方法 | 通过标准 | 证据 | 责任任务 |
|---|---|---|---|---|
| 基线/patch/语法 | `05_CONTROL/check_baseline_preflight.sh` + `05_CONTROL/validate_parent_provenance.py` + `05_CONTROL/validate_work_patch.sh` + `05_CONTROL/validate_work_dev.sh` | root baseline、parent provenance、PARENT_COMMIT/PARENT_TREE、WORK commit/tree、scope、patch SHA 与 changed-file `py_compile` 全部一致 | EV-BASE/patch/dev | WORK-08/全部 |
| pytest收集 | `python -m pytest --collect-only -q` | 目标测试真实收集 | JUnit/collect | WORK-08 |
| 公共合同/单元 | 各WORK第9.2节命令 | 全部通过，无未解释skip | JUnit/stdout | WORK-01~07B |
| AST/mutation/callgraph | WORK-08工具 | 反模式0、关键mutation被捕获 | JSON/HTML | 全部 |
| CPU/替身 | repository/Redis fake | 只证明纯逻辑与调用，不冒充UAT | manifest | 对应WORK |

### 9.2 测试环境验证

| 验证包 | 前置条件 | 执行脚本/步骤 | 预期结果 | 必须回传证据 | 状态 |
|---|---|---|---|---|---|
| ENV-01 | 专用 Redis DB/前缀；固定commit；WORK-08 manifest已生成 | 见 `WORK-PVAM-01_金额编码公共层与基础模型适配器.md` §9.3 | version=2 正常；legacy/3阻断且原值不变; 新记录全部显式 version=2; 无旧记录被自动放大 | 命令/exit/log/DB/Redis/Kafka/Dask/manifest SHA | PENDING_TEST_ENV |
| ENV-02 | Kafka/Redis/Dask隔离环境；AR_PERIOD只读；专用topic/group/period | 见 `WORK-PVAM-02_订单退款金额边界与期间解析.md` §9.3 | 同一事件三stage delta/hash一致; 整单退款只冲销一次且归期由批准时间决定; 所有金额列int64；差分为0或已批准标签 | 命令/exit/log/DB/Redis/Kafka/Dask/manifest SHA | PENDING_TEST_ENV |
| ENV-03 | 脱敏AR_CONFIG快照；DB/SQL oracle可用；fixture有checksum | 见 `WORK-PVAM-03_配置解析ppm与硬编码清理.md` §9.3 | PE/Elite无硬编码兜底; 负费率按合同计算；SE exact raw成立; TB missing/0/capping=0与SQL一致 | 命令/exit/log/DB/Redis/Kafka/Dask/manifest SHA | PENDING_TEST_ENV |
| ENV-04 | WORK-08批准fixture；Redis/Delta隔离；真实2B状态标DEFERRED | 见 `WORK-PVAM-04_monthActivePV与Active同源现算.md` §9.3 | 当前run所有消费者Active一致; 最终缺失时整run失败且无奖金发布; fixture证据不关闭2B生产缺口 | 命令/exit/log/DB/Redis/Kafka/Dask/manifest SHA | PENDING_TEST_ENV |
| ENV-05 | Redis隔离；图与PV_PSS fixture；外部writer模拟器非生产 | 见 `WORK-PVAM-05_Elite_SOURCE原子提交与发布批次.md` §9.3 | 无半提交/双计; candidate缺任一proof即阻断; receipt前不PUBLISHED；empty batch可清旧 | 命令/exit/log/DB/Redis/Kafka/Dask/manifest SHA | PENDING_TEST_ENV |
| ENV-06 | 可控Kafka/Redis/Dask；部署archive；外部writer receipt模拟器 | 见 `WORK-PVAM-06_结算状态机统一Guard与Topology接线.md` §9.3 | 新消息不跨freeze；direct-call被guard; persisted=false/无receipt不PUBLISHED; 恢复checksum等于干净重跑; Topology真实入口唯一且通过事务编排器；旧/新链状态正确，失败无半状态 | 命令/exit/log/DB/Redis/Kafka/Dask/manifest SHA | PENDING_TEST_ENV |
| ENV-07A | 隔离Redis Stream/group；不启用WORK-07B schema | 见 `WORK-PVAM-07A_Consumer_ACK紧急修复.md` §9.3 | 未处理消息留PEL; 永久格式错仅DLQ成功后ACK; ghost不ACK并有IN_DOUBT告警 | 命令/exit/log/DB/Redis/Kafka/Dask/manifest SHA | PENDING_TEST_ENV |
| ENV-07B | Redis容量隔离；至少2个consumer groups；durable registry/manifest fixture | 见 `WORK-PVAM-07B_事件路由与Stream保留.md` §9.3 | 未ACK不被trim; 同event_id不重复执行; ghost可恢复或IN_DOUBT; manifest完整且无fixed MAXLEN | 命令/exit/log/DB/Redis/Kafka/Dask/manifest SHA | PENDING_TEST_ENV |
| ENV-08 | DEC-013批准；固定镜像；DEC-009 manifest；专用数据/权限 | 见 `WORK-PVAM-08_UAT准入与证据治理.md` §9.3 | 每个TC有明确validation_status ∈ {NOT_RUN, PASS, FAIL, PENDING_TEST_ENV, BLOCKED}; 所有P0/P1证据可重放; DEC-010豁免与Gate C OPEN分开登记; 无截图/二手报告单独关闭问题 | 命令/exit/log/DB/Redis/Kafka/Dask/manifest SHA | PENDING_TEST_ENV |

### 9.3 回归检查项映射

#### Traceability Manifest v3

- 基线：`2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`
- 统计域：核心缺陷 13 项；R-012 拆为两个施工子项，但不增加核心缺陷总数。

| CHK | R/parent | DEC | TASK | WORK | REM/W/V | STEP | TC | EV |
|---|---|---|---|---|---|---:|---:|---:|
| CHK-DATA-001、CHK-DATA-003、CHK-EVT-002 | R-001 | DEC-002、DEC-008、DEC-014 | TASK-PVAM-01 | WORK-PVAM-01 | REM-001/W-001/V-001 | 5 | 6 | 15 |
| CHK-ARCH-003 | R-002 | DEC-002、DEC-008、DEC-014 | TASK-PVAM-01 | WORK-PVAM-01 | REM-002/W-002/V-002 | 5 | 6 | 15 |
| CHK-DATA-001、CHK-DATA-002、CHK-ARCH-003、CHK-BIZ-011 | R-003 | DEC-002、DEC-005、DEC-006、DEC-007、DEC-010 | TASK-PVAM-02 | WORK-PVAM-02 | REM-003/W-003/V-003 | 7 | 8 | 17 |
| CHK-DATA-004、CHK-BIZ-007、CHK-BIZ-008 | R-004 | DEC-001、DEC-002、DEC-003、DEC-009、DEC-014 | TASK-PVAM-03 | WORK-PVAM-03 | REM-004/W-004/V-004 | 6 | 7 | 15 |
| CHK-DATA-006、CHK-BIZ-007 | R-005 | DEC-004、DEC-016、DEC-018 | TASK-PVAM-04 | WORK-PVAM-04 | REM-005/W-005/V-005 | 5 | 8 | 16 |
| CHK-DATA-006、CHK-BIZ-007、CHK-BIZ-008、CHK-BIZ-009、CHK-BIZ-011 | R-006 | DEC-004、DEC-016、DEC-018 | TASK-PVAM-04 | WORK-PVAM-04 | REM-006/W-006/V-006 | 5 | 8 | 16 |
| CHK-DATA-005 | R-007 | DEC-002、DEC-005、DEC-006、DEC-007、DEC-010 | TASK-PVAM-02 | WORK-PVAM-02 | REM-007/W-007/V-007 | 7 | 8 | 17 |
| CHK-BIZ-006、CHK-EVT-005 | R-008 | DEC-007、DEC-008、DEC-011、DEC-017 | TASK-PVAM-05 | WORK-PVAM-05 | REM-008/W-008/V-008 | 6 | 8 | 16 |
| CHK-BIZ-006、CHK-EVT-003、CHK-PUB-001 | R-009 | DEC-007、DEC-008、DEC-010、DEC-012 | TASK-PVAM-06 | WORK-PVAM-06 | REM-009/W-009/V-009 | 6 | 9 | 18 |
| CHK-ARCH-002、CHK-EVT-003 | R-010 | DEC-007、DEC-008、DEC-010、DEC-012 | TASK-PVAM-06 | WORK-PVAM-06 | REM-010/W-010/V-010 | 6 | 9 | 18 |
| CHK-BIZ-005、CHK-BIZ-006、CHK-PUB-001 | R-011 | DEC-007、DEC-008、DEC-011、DEC-017 | TASK-PVAM-05 | WORK-PVAM-05 | REM-011/W-011/V-011 | 6 | 8 | 16 |
| CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-001、CHK-TEST-003 | R-012A（parent=R-012） | DEC-010 | TASK-PVAM-07A | WORK-PVAM-07A | REM-012A/W-012A/V-012A | 4 | 7 | 13 |
| CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-003 | R-012B（parent=R-012） | DEC-007、DEC-010 | TASK-PVAM-07B | WORK-PVAM-07B | REM-012B/W-012B/V-012B | 6 | 9 | 15 |
| CHK-EVT-007 | R-013 | DEC-007、DEC-010 | TASK-PVAM-07B | WORK-PVAM-07B | REM-013/W-013/V-013 | 6 | 9 | 15 |

## 10. 发布、切换与回滚总策略

### 10.1 发布/切换步骤

| 顺序 | 操作 | 执行人 | 前置检查 | 成功判据 | 失败动作 |
|---|---|---|---|---|---|
| 1 | 固定commit/镜像/配置/schema/data并备份 | 实施+QA | WORK-08准入 | 所有hash一致 | 停止 |
| 2 | 部署additive模型/公共层，flags关闭 | 实施 | WORK-01 DEV/UAT | 旧路径不变 | revert WORK-01 |
| 3 | 启用shadow normalizer/config/Active/Elite batch | 实施 | WORK-02~05通过 | shadow差分为0/批准差异 | 关闭对应flag |
| 4 | 启用Coordinator/Guard并冻结演练 | 架构/运维 | WORK-06通过 | 状态/恢复/receipt正确 | 回滚v2 coordinator |
| 5 | 先启07A fail-closed，再启07B dual-read/publish | 运维 | 07A/07B通过 | 无假ACK/丢事件 | 关闭v2 publisher，保留PEL |
| 6 | 受控切流并观察至少一个完整period | 业务/QA | 全UAT通过 | checksum、金额、事件、lag正常 | 按WORK独立回滚 |
| 7 | 签署验证与交付报告 | 各角色 | 全部EV完整 | ACCEPTED或明确结论 | 不得带P0/P1通过 |

### 10.2 回滚触发条件

- 单位/version混算、int64溢出、SQL差分非0且无批准标签；
- 重复/漏算、半提交、假PUBLISHED、假ACK、不可恢复trim；
- guard可绕过、状态倒退/卡死、receipt/checksum不一致；
- 错误率、lag、Redis内存或Dask资源超过UAT批准阈值；
- 任何证据无法重放或实际commit/配置漂移。

### 10.3 回滚边界

| 对象 | 可否独立回滚 | 回滚步骤所在任务 | 数据恢复点 | 回滚后验证 |
|---|---|---|---|---|
| WORK-PVAM-01代码/flag | 是 | WORK-PVAM-01 §11 | 最后committed旧状态/保留v2审计 | TC-PVAM-01-01 |
| WORK-PVAM-02代码/flag | 是 | WORK-PVAM-02 §11 | 最后committed旧状态/保留v2审计 | TC-PVAM-02-01 |
| WORK-PVAM-03代码/flag | 是 | WORK-PVAM-03 §11 | 最后committed旧状态/保留v2审计 | TC-PVAM-03-01 |
| WORK-PVAM-04代码/flag | 是 | WORK-PVAM-04 §11 | 最后committed旧状态/保留v2审计 | TC-PVAM-04-01 |
| WORK-PVAM-05代码/flag | 是 | WORK-PVAM-05 §11 | 最后committed旧状态/保留v2审计 | TC-PVAM-05-01 |
| WORK-PVAM-06代码/flag | 是 | WORK-PVAM-06 §11 | 最后committed旧状态/保留v2审计 | TC-PVAM-06-01 |
| WORK-PVAM-07A代码/flag | 是 | WORK-PVAM-07A §11 | 最后committed旧状态/保留v2审计 | TC-PVAM-07A-01 |
| WORK-PVAM-07B代码/flag | 是 | WORK-PVAM-07B §11 | 最后committed旧状态/保留v2审计 | TC-PVAM-07B-01 |
| WORK-PVAM-08代码/flag | 是 | WORK-PVAM-08 §11 | 最后committed旧状态/保留v2审计 | TC-PVAM-08-01 |

## 11. 交付物清单

| 编号 | 交付物 | 责任任务 | 格式/位置 | 完成条件 | artifact_status |
|---|---|---|---|---|---|
| D-01 | 生产代码修改 | WORK-01~07B | commit/diff | 全部CHG完成且复核 | PENDING |
| D-02 | 单元/契约/mutation测试 | 全部 | JUnit/JSON/log | DEV全通过 | PENDING |
| D-03 | 迁移/回滚/安全脚本 | WORK-08+各WORK | uat/scripts | dry-run/幂等/回滚验证 | PENDING |
| D-04 | UAT执行包 | WORK-08 | evidence/attempt-* | TC-001~032状态完整 | PENDING |
| D-05 | 验证与交付报告 | 施工负责人/QA | Markdown+manifest | 正式结论/签署 | PENDING |

## 12. 偏离与变更控制

任何改变业务口径、单位、精度、资格、分母、接口、数据格式、范围或关键测试的偏离必须回TASK/MODPLAN/DEC；不能只在执行记录中批准。

| 偏离编号 | 原施工要求 | 实际需要 | 原因与证据 | 是否改变业务/范围 | 批准人 | 处置 |
|---|---|---|---|---|---|---|
| DEV-PVAM-001 | 待执行 | 待发现 | 待提供 | 待判断 | 待批准 | 更新WORK/回TASK/新增DEC/拒绝 |

## 13. 最终验收与签署

### 13.1 当前施工方案结论

本施工方案套件当前结论：`DRAFT / GATED`。B7-01～B7-04 的包内文档与控制程序问题已定点修订并执行正/负向自测；B7-05 组织授权与 B7-06 真实实施/DEV/UAT/回滚门禁仍未满足：

1. 可识别组织批准人、角色、批准原文/签名、批准范围和允许 Wave；
2. 每个代码 WORK 的真实实施 commit、标准 patch、scope 与 applied-tree 证明；
3. 与实施 commit 绑定的 DEV 原始日志；
4. 真实部署对象及隔离环境 rollback manifest/演练；
5. DEC-013 所需 UAT 环境和 Gate C 关闭证据。

在上述条件满足前，不得按本文件启动正式代码施工、部署或生产发布；仅允许继续准备隔离分支、无业务副作用的控制脚本和文档证据。

### 13.2 签署表

| 角色 | 姓名 | 结论 | 时间 | 备注 |
|---|---|---|---|---|
| 编制 | AI Agent（文档修订角色） | DRAFT | 2026-08-05 | 仅完成第四轮文档修订 |
| 技术复核 | 待组织指派 | 待签署 | 待补充 | 不得由编制者代签 |
| 测试验收 | 待组织指派 | 待签署 | 待补充 | DEV/UAT 尚未执行 |
| 业务/架构批准 | 待组织授权人 | 待签署 | 待补充 | 需附批准原文/签名与范围 |

## 14. 版本记录

| 版本 | 日期 | 变更内容 | 变更来源 | 编制人 | 批准状态 |
|---|---|---|---|---|---|
| v1.0 | 2026-08-04 | 初版完整施工方案套件 | MODPLAN-PVAM_v1.2 + 九份TASK + 两份施工模板 + PLAN-PVAM-v1.15 | AI Agent | DRAFT |
| v1.1 | 2026-08-05 | 依据二轮核验报告定点修复 F-A/F-B/F-H/F-I/F-J/F-K/F-F/F-E/F-L/F-M/F-N；不改变上游范围 | AUDIT-WORKPLAN-PVAM-v1.0 | AI Agent | DRAFT |
| v1.2 | 2026-08-05 | 历史版本曾自述无条件批准；因缺少可独立验证组织授权而由 v1.3 取代 | 历史会话声明（UNVERIFIED） | AI Agent | SUPERSEDED |
| v1.3 | 2026-08-05 | 第四轮关闭 F3-01～F3-10：Traceability v3、治理回退、patch/DEV 双阶段、状态枚举与设计边界 | 三轮审查报告 + 当前文档修订指令 | AI Agent | DRAFT |
| v1.3-r6 | 2026-08-06 | 五轮 F5-01～F5-07：五层双向追溯、TC-020、单一 v3 控制身份、parent provenance、无 `/dev/fd` DEV 门禁与状态字段解耦 | 五轮审计报告 + 当前文档修订指令 | AI Agent | DRAFT |
| v1.3-r7 | 2026-08-06 | 六轮 S6：duplicate-shadow、registry 初版、归档哈希、临时目录与 Decimal finite 防护 | 六轮终局审计报告 | AI Agent | DRAFT |
| v1.3-r8 | 2026-08-06 | 七轮 B7：registry 发布信任根和四类工件实哈希、独立临时目录、AC 来源保真、当前轮次/版本引用 | 七轮终局审计报告 + B7 处置 | AI Agent | DRAFT |
| v1.3-r9 | 2026-08-06 | 九轮 P0-TRACE-CHAIN-09-01 / P1-WORK-INDEX-09-02：跨层权威等价与 §4.1 索引全量同步 | 九轮终局审计报告 + 定点修补 | AI Agent | DRAFT |


## 附录 A：推荐目录结构

```text
04_施工方案/
├── WORK-PLAN-PVAM_v1.3_施工总方案.md
├── WORK-PVAM-01_金额编码公共层与基础模型适配器.md
├── WORK-PVAM-02_订单退款金额边界与期间解析.md
├── WORK-PVAM-03_配置解析ppm与硬编码清理.md
├── WORK-PVAM-04_monthActivePV与Active同源现算.md
├── WORK-PVAM-05_Elite_SOURCE原子提交与发布批次.md
├── WORK-PVAM-06_结算状态机统一Guard与Topology接线.md
├── WORK-PVAM-07A_Consumer_ACK紧急修复.md
├── WORK-PVAM-07B_事件路由与Stream保留.md
├── WORK-PVAM-08_UAT准入与证据治理.md
├── WORK-PVAM_v1.3_完整套件全文.md
├── DOCUMENT_MANIFEST.json
├── SHA256SUMS.txt
└── README.md
```

拆分原则：逻辑上保持 `WORK-PVAM-01～08` 八组；`WORK-PVAM-07` 因紧急 ACK fail-closed 与最终 schema/retention 可独立施工、验证和回滚而物理拆分为 07A/07B。不得将 RISK/UV/DEFERRED 项转成未获批准的生产代码修改。

## 附录 B：追溯编号约定与本轮绑定

| 层级 | 示例 | 本轮含义 |
|---|---|---|
| 检查项 | `CHK-DATA-001` | `PLAN-PVAM-v1.15` 中不可在施工阶段改写的判据 |
| 复核问题 | `R-001` | 复核报告 v1.5 已证实问题 |
| 修改方案闭环 | `REM-001` | 复核报告附录 B 预登记的本轮修改方案编号 |
| 施工闭环 | `W-001` | 复核报告附录 B 预登记的施工编号；通过本套件 WORK 映射承接 |
| 验证闭环 | `V-001` | 复核报告附录 B 预登记的验证编号；由 TC/EV 证据关闭 |
| 正式决策 | `DEC-008` | 已关闭业务/架构裁决；优先于无裁决的 Legacy SQL oracle |
| 修改任务 | `TASK-PVAM-02` | 既定且受控的修复方向、范围、排除项和 AC |
| 施工任务 | `WORK-PVAM-02` | 文件/符号/步骤/测试/回滚的执行说明 |
| 施工步骤 | `STEP-PVAM-02-01` | 可立即检查的最小施工动作 |
| 测试用例 | `TC-PVAM-02-01` | WORK 级用例；另映射受控 TC-001～032 |
| 验证证据 | `EV-PVAM-02-01` | 原始命令、退出码、日志、状态快照和 SHA-256 |
| 阻断项 | `BLOCK-PVAM-02-*` | 必须停工、回上游或等待环境/材料的条件 |

| WORK | R / RISK / UV | REM | W | V / UAT |
|---|---|---|---|---|
| WORK-01 | R-001、R-002 | REM-001、REM-002 | W-001、W-002 | V-001、V-002 |
| WORK-02 | R-003、R-007 | REM-003、REM-007 | W-003、W-007 | V-003、V-007 |
| WORK-03 | R-004 | REM-004 | W-004 | V-004 |
| WORK-04 | R-005、R-006 | REM-005、REM-006 | W-005、W-006 | V-005、V-006 |
| WORK-05 | R-008、R-011 | REM-008、REM-011 | W-008、W-011 | V-008、V-011 |
| WORK-06 | R-009、R-010；RISK-001 条件分支 | REM-009、REM-010 | W-009、W-010 | V-009、V-010；RISK-001 由 WORK-08 AC-05 取证 |
| WORK-07A | R-012A（parent_issue=R-012） | REM-012A | W-012A | V-012A |
| WORK-07B | R-012B（parent_issue=R-012）、R-013 | REM-012B、REM-013 | W-012B、W-013 | V-012B、V-013 |
| WORK-08 | RISK-001/002、UV-001～005、OPT-001/002 | 无预登记 REM | 无预登记 W | UV-002 对应 UAT-011；其余由 AC-11 追踪 manifest 管理 |



## 附录 C：统一状态枚举

- 文档：`DRAFT / APPROVED / SUPERSEDED`
- 实施：`NOT_STARTED / READY / IN_PROGRESS / DEV_VERIFIED / BLOCKED / ROLLED_BACK`
- 验证：`NOT_RUN / PASS / FAIL / PENDING_TEST_ENV / BLOCKED`
- 工件：`PENDING / GENERATED / VERIFIED / REJECTED`（仅用于 patch、日志、EV 文件是否生成，不得用于环境验证）
- 禁止使用：`TEST_ENV_PENDING`、以`APPROVED`代替测试结果。

## 附录 D：Patch与Rollback阶段边界

1. 施工方案负责规定patch生成和验收方法，不在代码尚未实现时伪造标准patch。
2. 每个代码WORK完成前必须交付可在`2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`干净树通过`git apply --check`的真实patch。
3. 每个部署WORK在切换前必须有签名的`ROLLBACK-MANIFEST-PVAM-v1`，包含部署系统、workload/release/config、前后镜像、精确命令、健康检查和数据恢复动作。
4. 缺少外部部署信息时状态为`BLOCKED_EXTERNAL_EVIDENCE`，而不是由文档编制者猜测命令。
