# WORK-PVAM v1.3 完整套件全文


---

<!-- BEGIN WORK-PLAN-PVAM_v1.3_施工总方案.md -->

# WORK-PLAN-PVAM_v1.3 Redemption PV Amount Migration 施工总方案

> 文档定位：基于 `MODPLAN-PVAM_v1.2` 与十份专项修改任务书定义施工顺序、统一技术合同、停工条件、DEV/UAT证据、发布和回滚。当前尚无可核验组织施工授权，本文件不得被解释为开工批准。

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
| 项目代码基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| 修改方案套件SHA-256 | `6b6c45fc5d52339cae2ab7fe4cbbc1ff2e179fe45b4ef3aef08cd23410d05c97`（对象：`MODPLAN-PVAM_v1.2_终稿修改方案套件.zip`，随本包提供） |
| SQL业务基线 | `sql_uat/*@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，排除Skill列明废弃/副本 |
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
| 专项修改任务书 | TASK-01、01C、02~06、07A、07B、08 | 目标/排除/AC | DRAFT（待组织授权） | 十份 |
| 正式决策 | DEC-001~018相关项 | 业务/架构裁决 | 按上游CLOSED/OPEN状态 | DEC-013仍是UAT门禁 |
| 代码与SQL快照 | 3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2 | 施工对象 | FROZEN | Python/SQL与097cae32一致 |
| 施工模板 | 两份Redemption模板 | 文档结构/状态/证据 | CONTROLLED | 本套件完整套用 |

### 2.2 开工准入门槛

- [x] R-001～R-013 已在修改方案中处置为 `ACCEPTED`。
- [ ] 已取得可核验组织批准人、角色、批准原文/签名、时间、范围和允许 Wave。
- [x] 代码基线完整SHA固定为 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`。
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

- [ ] 十份WORK全部达到 `VERIFIED`，或仅保留经正式批准且不含P0/P1的偏离。
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
| 1A | `WORK-PVAM-01C` | `TASK-PVAM-01C` | GAP-PVAM-FLAG-CONTRACT | DEC-019 | Redis flag Provider、原子 MANUAL_BOOTSTRAP、run-freeze 与 admission | 无（Phase A）；组合 factory 测试在 WORK-01 后执行 | 是 | BLOCKED |
| 1B | `WORK-PVAM-01` | `TASK-PVAM-01` | R-001、R-002 | DEC-002、DEC-008、DEC-014、DEC-019 | 金额编码公共层与基础模型适配器及条件化 factory/version gate | WORK-PVAM-01C Phase A DEV_VERIFIED | 否 | BLOCKED |
| 2 | `WORK-PVAM-03` | `TASK-PVAM-03` | R-004 | DEC-001、DEC-002、DEC-003、DEC-009、DEC-014 | 配置解析、ppm 与硬编码清理 | WORK-PVAM-01 DEV_VERIFIED | 条件 | BLOCKED |
| 3 | `WORK-PVAM-02` | `TASK-PVAM-02` | R-003、R-007 | DEC-002、DEC-005、DEC-006、DEC-007、DEC-010 | 订单/退款入口金额放大与边界转换 | WORK-PVAM-01、WORK-PVAM-03 均达到 DEV_VERIFIED | 否 | BLOCKED |
| 4 | `WORK-PVAM-04` | `TASK-PVAM-04` | R-005、R-006 | DEC-004、DEC-016、DEC-018 | monthActivePV 唯一取值与 Active 同源现算 | WORK-PVAM-01、WORK-PVAM-03 DEV_VERIFIED；真实供给链UAT仍BLOCKED | 否 | BLOCKED |
| 5 | `WORK-PVAM-05` | `TASK-PVAM-05` | R-008、R-011 | DEC-007、DEC-008、DEC-011、DEC-017 | Elite SOURCE 原子性与外部发布证明 | WORK-PVAM-01、02、03 DEV_VERIFIED | 否 | BLOCKED |
| 6 | `WORK-PVAM-06` | `TASK-PVAM-06` | R-009、R-010 | DEC-007、DEC-008、DEC-010、DEC-012 | 全量重算状态机、统一 Guard 与发布分层 | WORK-PVAM-01、WORK-PVAM-02、WORK-PVAM-05 DEV_VERIFIED；WORK-08A调用图证据可并行 | 否 | BLOCKED |
| 7 | `WORK-PVAM-07A` | `TASK-PVAM-07A` | R-012A（parent_issue=R-012） | DEC-010 | Recalc Consumer ACK 紧急 fail-closed 修复 | 无金额域依赖；可与WORK-01并行 | 是 | BLOCKED |
| 8 | `WORK-PVAM-07B` | `TASK-PVAM-07B` | R-012B（parent_issue=R-012）、R-013 | DEC-007、DEC-010 | 事件路由、正式 Handler 与 Stream 保留护栏 | WORK-PVAM-06、WORK-PVAM-07A DEV_VERIFIED | 否 | BLOCKED |
| 9 | `WORK-PVAM-08` | `TASK-PVAM-08` | RISK-001、RISK-002、UV-001～UV-005、OPT-001、OPT-002、GAP-DEC004-2B | DEC-004、DEC-009、DEC-010、DEC-012、DEC-013、DEC-017、DEC-018 | 风险、UAT 准入与机器可读证据包 | 阶段A可与所有DEV任务并行；阶段B依赖DEC-013及WORK-01～07B DEV_VERIFIED | 是 | BLOCKED |

说明：原 `WORK-PVAM-01～08` 八组保持不变；DEC-019 另增独立配置组 `WORK-PVAM-01C`，且 `WORK-PVAM-07` 仍拆为 `07A/07B`，因此当前交付十份专项文件。

### 4.2 纳入范围

- `Common` 金额、period、配置和Active纯函数/adapter。
- UserStats、Placement、Elite、PE、SE、EAB、Leadership生产可达金额/Active/配置路径。
- 订单/退款normalized事件和三个增量stage。
- Redis权威commit、Settlement Epoch/Guard、outbox consumer/schema/handler/retention。
- 测试、UAT脚本、schema/config/callgraph/traceability/evidence manifest。

### 4.3 明确排除范围

- PB、SFB、GPB、CRB算法；Team Bonus units-int生产服务建设。
- `GAP-DEC004-2B` AR_CONFIG→Delta→Redis生产写入/失效producer；DEC-019 只批准 MANUAL_BOOTSTRAP，不批准自动同步。
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
| WORK-01C | 代码基线/Redis helper | 配置接口 | HEAD精确、TASK批准；Phase A Provider/bootstrap 可独立DEV | BLOCK |
| WORK-07A | 现有consumer | 代码 | 独立hotfix审批 | 可与01并行 |
| WORK-02 | WORK-01/03 | 接口 | 公共units/version与ConfigSnapshot配置API均DEV通过 | 不得开工 |
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
| Wave 1A | WORK-01C Phase A + WORK-07A | 各自批准 | Provider/bootstrap与ACK hotfix DEV_VERIFIED | 01C失败阻断WORK-01；07A独立 |
| Wave 2 | WORK-03 | WORK-01通过 | ConfigSnapshot与配置API DEV_VERIFIED | 阻断02/04/05 |
| Wave 3 | WORK-02 | WORK-01/03通过 | 边界/period/float金额链 DEV_VERIFIED | 阻断05/06 |
| Wave 4 | WORK-04 | 01/03通过 | Active读侧与消费者DEV通过 | 真实2B仍BLOCKED |
| Wave 5 | WORK-05 | 01/02/03通过 | Elite atomic/batch DEV通过 | 阻断06 |
| Wave 6 | WORK-06 | 01/02/05通过；08A调用图可用 | Coordinator/Guard/receipt DEV通过 | 阻断07B |
| Wave 7 | WORK-07B | 06/07A通过 | schema/handler/retention DEV通过 | 阻断全链路 |
| Wave 8 | WORK-08 阶段B | DEC-013+全部DEV | TC-001~032证据包完成 | 任何P0失败总体REJECTED |

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
- Redis是本仓权威状态且是 PV amount flag 唯一 runtime Provider；AR_CONFIG 仍为业务 Source of Truth；关系库正式writer和读切换属于业务系统。
- GPU/Dask仅消费已经规范化的int64列；禁止金额隐式提升为float。

### 6.2 数据契约

| 对象 | 字段/接口 | 单位与类型 | 空值/默认值 | 兼容规则 | 责任任务 |
|---|---|---|---|---|---|
| UserStats/EliteBonusStats | amount_encoding_version | Optional[int]；完整V2域必须2 | 缺失=legacy unknown | 00/01 Legacy path不无条件gate且不stamping2；获批11 V2 entry阻断 | WORK-01 |
| PV amount flag | `PVAmountRunConfig` | frozen bool/bool/non-negative config_version | 无默认 | Redis atomic snapshot；00/01允许、10拒绝、未批准11拒绝；run途中不refresh | WORK-01C/01 |
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
| WORK-PVAM-01C | `Redishelper/PVAmountConfigProvider.py` | 新增 | run config/provider/admission | Redis唯一runtime Provider、fail-loud、run-freeze | TC-FLAG-01～11; TC-FLAG-13 |
| WORK-PVAM-01C | `Redishelper/PVAmountConfigBootstrap.py` | 新增 | MANUAL_BOOTSTRAP/Lua CAS | 原子发布01、stale/lost-update保护 | TC-FLAG-12; TC-FLAG-22; TC-FLAG-23 |
| WORK-PVAM-01C | `tests/pvam/WORK-PVAM-01C/` | 新增 | provider/bootstrap tests | fake DEV与真实Redis UAT分层 | TC-FLAG-01～13; TC-FLAG-22; TC-FLAG-23 |
| WORK-PVAM-01 | `Common/PvAmount.py` | 新增 | 模块级常量与纯函数 | 唯一公共金额 API | TC-PVAM-01-01; TC-PVAM-01-02 |
| WORK-PVAM-01 | `Common/AmountModelAdapter.py` | 新增 | `AmountRecordState`、`classify_amount_record` | 普通计算只能接收 NEW | TC-PVAM-01-01; TC-PVAM-01-02 |
| WORK-PVAM-01 | `Model/User/UserStats.py` | 修改 | `UserStats.amount_encoding_version` | 仅获批 V2 domain record 显式2；00/01共享-key Legacy record不写2 | TC-PVAM-01-01; TC-PVAM-01-02 |
| WORK-PVAM-01 | `Model/User/EliteBonusStats.py` | 修改 | version、`estimated_bonus_cents` | 仅V2 blank/init允许cents=0；禁止legacy float→cents与00/01 stamping2 | TC-PVAM-01-01; TC-PVAM-01-02 |
| WORK-PVAM-01 | `User/UserStatsService.py` | 修改 | `_get_or_init_user` | factory按冻结run config条件化且单位可审计 | TC-PVAM-01-01; TC-PVAM-01-02 |
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
| WORK-PVAM-02 | `Common/PvAmount.py` | 修改 | signed dtype 守卫、公共 units→cents helper | unsigned/溢出 fail-loud | TC-PVAM-02-01; TC-PVAM-02-02 |
| WORK-PVAM-02 | `User/EliteBonusService.py` / `User/GlobalEliteBonusRecalculationService.py` | 修改 | 增量与全量 bonus/threshold/snapshot | 同一 `estimated_bonus_cents` 合同 | TC-PVAM-02-01; TC-PVAM-02-02 |
| WORK-PVAM-02 | `User/PlacementRecalculationService.py` | 修改 | `_get_prev_period`、`_process_extract_batch`、`_calculate_placement_pv`、`_write_back_placement_matrix` | 无精度漂移 | TC-PVAM-02-01; TC-PVAM-02-02 |
| WORK-PVAM-02 | `User/PEBonusService.py` / `PEBonusService_Main.py` / `SuperEliteBonusService.py` / `LeadershipBonusGPUService.py` / `EliteAchievementBonusService.py` | 修改/核验 | 金额计算与受影响调用边界 | writer/人工入口明确cents/string | TC-PVAM-02-01; TC-PVAM-02-02 |
| WORK-PVAM-02 | `User/Test/PEBonusServiceTest.py` / `test_amount_dtype_migration.py` / `test_pv_amount_common.py` | 修改 | GPU UAT 与公共/迁移回归 | units/ppm/cents、ConfigSnapshot、signed dtype 可验证 | TC-PVAM-02-01; TC-PVAM-02-02 |
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
| 公共合同/单元 | 各WORK第9.2节命令 | 全部通过，无未解释skip | JUnit/stdout | WORK-01C、01~07B |
| AST/mutation/callgraph | WORK-08工具 | 反模式0、关键mutation被捕获 | JSON/HTML | 全部 |
| CPU/替身 | repository/Redis fake | 只证明纯逻辑与调用，不冒充UAT | manifest | 对应WORK |

### 9.2 测试环境验证

| 验证包 | 前置条件 | 执行脚本/步骤 | 预期结果 | 必须回传证据 | 状态 |
|---|---|---|---|---|---|
| ENV-01C | 隔离 Redis；AR_CONFIG 批准值已确认；不得使用生产 key | 见 `WORK-PVAM-01C_Flag_Runtime_Contract与Redis原子配置.md` §9.2 | 原子加载/发布01；00/01/10/11 admission、stale/concurrent CAS、run-freeze全部符合DEC-019；fake证据不冒充本行 | 命令/exit/log/Redis前后snapshot/config_version/checksum/manifest SHA | PENDING_TEST_ENV |
| ENV-01 | 专用 Redis DB/前缀；固定commit；WORK-08 manifest已生成 | 见 `WORK-PVAM-01_金额编码公共层与基础模型适配器.md` §9.3 | 00/01共享-key Legacy record不写2；获批/test-only V2 factory写2；Legacy path不无条件gate；无旧记录被放大或float→cents | 命令/exit/log/DB/Redis/Kafka/Dask/manifest SHA | PENDING_TEST_ENV |
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

- 基线：`3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`
- 统计域：核心缺陷 13 项；R-012 拆为两个施工子项，但不增加核心缺陷总数。

| CHK | R/parent | DEC | TASK | WORK | REM/W/V | STEP | TC | EV |
|---|---|---|---|---|---|---:|---:|---:|
| CHK-DATA-001、CHK-DATA-003、CHK-EVT-002 | R-001 | DEC-002、DEC-008、DEC-014、DEC-019 | TASK-PVAM-01 | WORK-PVAM-01 | REM-001/W-001/V-001 | 5 | 14 | 15 |
| CHK-ARCH-003 | R-002 | DEC-002、DEC-008、DEC-014 | TASK-PVAM-01 | WORK-PVAM-01 | REM-002/W-002/V-002 | 5 | 14 | 15 |
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
| CHK-ARCH-001、CHK-ARCH-003、CHK-DATA-003、CHK-EVT-003、CHK-TEST-003、CHK-TEST-004 | GAP-PVAM-FLAG-CONTRACT | DEC-019 | TASK-PVAM-01C | WORK-PVAM-01C | REM-014/W-014/V-014 | 4 | 15 | 5 |

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
| WORK-PVAM-01C config Provider/bootstrap | 是 | WORK-PVAM-01C §11 | 保留versioned snapshot；发布更高version合法00/01 | TC-FLAG-01/12/22/23 |
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
| D-01 | 生产代码修改 | WORK-01C、01~07B | commit/diff | 全部CHG完成且复核 | PENDING |
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
| v1.3-r10 | 2026-08-08 | 接入 DEC-019、GAP/TASK/WORK-PVAM-01C；条件化 WORK-01，更新 scope/test/traceability/version/hash 治理链 | PVAM USER-DECISION FINAL | AI Agent | DRAFT |
| v1.3-r11 | 2026-08-12 | 同步 WORK-PVAM-02 实施期治理扩围：公共守卫、全量 Elite、PE 人工入口与 GPU UAT 回归 | WORK-PVAM-02 终审发现与治理依赖修订 | AI Agent | DRAFT |


## 附录 A：推荐目录结构

```text
04_施工方案/
├── WORK-PLAN-PVAM_v1.3_施工总方案.md
├── WORK-PVAM-01_金额编码公共层与基础模型适配器.md
├── WORK-PVAM-01C_Flag_Runtime_Contract与Redis原子配置.md
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

拆分原则：原 `WORK-PVAM-01～08` 八组保持；DEC-019 新增独立配置卡 01C，07 仍物理拆分 07A/07B。01C 不扩张 WORK-01 production allowlist，不得把 RISK/UV/DEFERRED 项转成未获批准修改。

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
| WORK-01C | GAP-PVAM-FLAG-CONTRACT | REM-014 | W-014 | V-014 |
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
2. 每个代码WORK完成前必须交付可在`3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`干净树通过`git apply --check`的真实patch。
3. 每个部署WORK在切换前必须有签名的`ROLLBACK-MANIFEST-PVAM-v1`，包含部署系统、workload/release/config、前后镜像、精确命令、健康检查和数据恢复动作。
4. 缺少外部部署信息时状态为`BLOCKED_EXTERNAL_EVIDENCE`，而不是由文档编制者猜测命令。

<!-- END WORK-PLAN-PVAM_v1.3_施工总方案.md -->

---

<!-- BEGIN WORK-PVAM-01_金额编码公共层与基础模型适配器.md -->

# WORK-PVAM-01 金额编码公共层与基础模型适配器施工任务书

> 文档定位：来源于待组织批准的 `TASK-PVAM-01`，在取得组织授权后转化为可执行施工说明。本文件不重新决定业务规则；实际结果只能写入执行记录与验证交付报告。

## 0. 填写与执行规则

1. 上游修改任务与本 v1.3 施工套件当前均为 `DRAFT`；没有组织授权前，本任务保持 `BLOCKED`，不得启动代码施工或部署。
2. 只实施 `R-001、R-002` 中已 `ACCEPTED` 或由来源 TASK 明确批准的条件代码事项。任何 `REJECTED / NEEDS_DECISION / DEFERRED / 未获 TASK 授权的 UAT_VERIFY` 只允许登记、验证或阻断，不得扩展代码范围。
3. 基线必须精确等于 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；发现漂移立即登记 `BLOCK-PVAM-01-BASELINE`。
4. 所有新文件/符号已在变更表标为“新增”；其余锚点均来自固定基线。
5. DEV替身不能冒充真实Kafka/Redis/Dask/GPU/MySQL UAT验证。

## 1. 文档信息与追溯关系

| 字段 | 内容 |
|---|---|
| 施工任务编号 | `WORK-PVAM-01` |
| 施工任务名称 | 金额编码公共层与基础模型适配器 |
| 所属施工总方案 | `WORK-PLAN-PVAM_v1.3` |
| 来源修改任务 | `TASK-PVAM-01@MODPLAN-PVAM_v1.2`（authorization=PENDING_ORGANIZATIONAL_APPROVAL） |
| 来源问题 | `R-001、R-002` |
| 复核闭环追踪号 | `REM-001、REM-002 / W-001、W-002 / V-001、V-002` |
| 来源检查项 | `CHK-ARCH-003、CHK-DATA-001、CHK-DATA-003、CHK-EVT-002` |
| 关联决策 | `DEC-002、DEC-008、DEC-014、DEC-019` |
| 代码基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| SQL基线 | `sql_uat/*@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，仅有效SQL |
| 文档版本 | `v1.3` |
| 负责人 | `待指派 / 实施工程师` |
| 复核人 | `待指派 / 架构与QA` |
| 当前状态 | `BLOCKED` |
| 文档治理状态 | `DRAFT`（`PENDING_ORGANIZATIONAL_APPROVAL`） |
| 前置任务 | `WORK-PVAM-01C` Phase A Provider/bootstrap 接口 DEV_VERIFIED |
| 功能开关 | `PV_AMOUNT_V2_READ / PV_AMOUNT_V2_WRITE` |

### 1.1 一对一追溯摘要

```text
CHK-ARCH-003、CHK-DATA-001、CHK-DATA-003、CHK-EVT-002
  └─ R-001、R-002
       └─ DEC-002、DEC-008、DEC-014、DEC-019
            └─ TASK-PVAM-01 (DRAFT / PENDING_ORGANIZATIONAL_APPROVAL)
                 └─ WORK-PVAM-01
                      ├─ STEP-PVAM-01-01 / STEP-PVAM-01-02 / STEP-PVAM-01-03 / STEP-PVAM-01-04 / STEP-PVAM-01-05
                      ├─ TC-PVAM-01-01 / TC-PVAM-01-02 / TC-PVAM-01-03 / TC-PVAM-01-04 / TC-PVAM-01-05 / TC-PVAM-01-06
                      └─ EV-PVAM-01-01...
```

## 2. 施工任务生成依据

### 2.1 上游输入

| 输入 | 编号/版本 | 本任务使用的结论 | 状态 |
|---|---|---|---|
| 复核报告 | `Redemption_PV_Amount_Migration_d74_复核报告_v1.5` | R-001、R-002 的代码事实与严重级别 | CONFIRMED |
| 修改任务书 | `TASK-PVAM-01` | 采用方案、范围、排除项、AC | DRAFT（待组织授权） |
| 检查方案 | `PLAN-PVAM-v1.15` | CHK-ARCH-003、CHK-DATA-001、CHK-DATA-003、CHK-EVT-002 | CONTROLLED |
| 正式决策 | DEC-002、DEC-008、DEC-014、DEC-019 | int64、Redis authority、Final 合同与 flag runtime 条件化语义 | CLOSED / 按上游登记 |
| 代码/SQL快照 | 3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2 | 唯一施工对象 | FROZEN |
| 施工模板 | 总方案模板/专项模板 | 章节、状态、证据纪律 | CONTROLLED |

### 2.2 开工条件

- [ ] 当前 HEAD 精确为 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，工作树无未登记变更。
- [ ] `TASK-PVAM-01` 的人工批准记录已归档；本 `WORK` 已由施工负责人和复核人签署。
- [ ] 前置关系满足：WORK-PVAM-01C Phase A Provider/bootstrap 接口已 DEV_VERIFIED。
- [ ] 本任务涉及的接口、单位、精度、兼容和回滚边界已由上游任务固定。
- [ ] DEV测试依赖已安装；UAT项具备WORK-08生成的环境/数据/schema manifest。
- [ ] Redis 已由 MANUAL_BOOTSTRAP 原子发布当前批准01；缺失配置必须 fail-loud；回滚通过更高 config_version 的合法00/01 snapshot。

未满足任一关键项时，本任务状态为 `BLOCKED`；不得用假设替代。

## 3. 问题事实与施工目标

### 3.1 已确认问题

| 项目 | 内容 |
|---|---|
| 预期行为 | 新增最低层公共金额合同与 additive version 字段；只有真正进入获批 V2 domain 且全部共享金额字段满足 V2 合同的记录才写2。00/01 共享-key Legacy record 不写2；legacy/unknown 只在 V2 calculation entry 阻断。 |
| 当前行为 | `Model/User/UserStats.py::UserStats` 的 `pv/gpv/gpv_real/gpv_unreal/contrib` 及 1L/2L/结余字段均为 `Optional[int]`，基线没有 `amount_encoding_version`。；`Model/User/EliteBonusStats.py::EliteBonusStats` 没有编码版本，且 `estimated_bonus: Optional[float] = 0.0`。；`Redishelper/BaseRedisModel.py::BaseRedisModel` 仅绑定 Redis OM 连接，没有金额版本后置校验。；固定提交中 `Common/PvAmount.py` 不存在；金额缩放、ppm、cents、截断与溢出校验分散在奖金服务。 |
| 差异 | 当前实现缺少本任务批准的唯一合同、门禁或原子边界。 |
| 影响 | 金额/PV单位、奖金、并发一致性、发布或可恢复性，具体见来源问题。 |
| 严重级别 | P0 / P1 |
| 证据位置 | 固定代码基线 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；来源 `TASK-PVAM-01`；检查项 `CHK-ARCH-003、CHK-DATA-001、CHK-DATA-003、CHK-EVT-002` |

### 3.2 已确认代码事实

- `Model/User/UserStats.py::UserStats` 的 `pv/gpv/gpv_real/gpv_unreal/contrib` 及 1L/2L/结余字段均为 `Optional[int]`，基线没有 `amount_encoding_version`。
- `Model/User/EliteBonusStats.py::EliteBonusStats` 没有编码版本，且 `estimated_bonus: Optional[float] = 0.0`。
- `Redishelper/BaseRedisModel.py::BaseRedisModel` 仅绑定 Redis OM 连接，没有金额版本后置校验。
- 固定提交中 `Common/PvAmount.py` 不存在；金额缩放、ppm、cents、截断与溢出校验分散在奖金服务。

### 3.3 本任务目标

新增最低层公共金额合同与 additive version 字段；按 DEC-019 接收同一 frozen run config，条件化全部真实 factory/version gate；当前01的共享-key Legacy record 不写2，获批11 V2 domain 才显式写2。

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
| 1 | Redis OM 反序列化 | `Redishelper/BaseRedisModel.py::BaseRedisModel` | 旧 JSON 可能不含 version | 直接构造业务模型 | 无统一版本门禁 |
| 2 | UserStats 新建 | `User/UserStatsService.py::_get_or_init_user` | period/user_id | 创建无 version 的 `UserStats` | 后续服务无法识别单位 |
| 3 | 全量零节点 | `User/GlobalRecalculationService.py::_new_zero_user_stats` | period/uid | 创建无 version 的 `UserStats` | 混合编码不可判定 |
| 4 | Elite 新建 | `User/EliteBonusService.py::_get_or_create_node` / `_build_blank_node` | period/user_id | 创建无 version 的 `EliteBonusStats` | 奖金 float 与 PV 单位不可审计 |

### 4.2 当前错误形成点

当前链路在上述入口缺少本任务目标合同，导致已确认问题在写入、计算、路由或发布边界形成并传播。修改必须落在表中稳定符号或明确标记为“新增”的边界；不得通过外围日志掩盖。

### 4.3 受影响消费者

| 消费者 | 依赖内容 | 预期影响 | 是否同步修改 | 对应步骤/测试 |
|---|---|---|---|---|
| UserStats/Global | 金额字段和版本 | 读写需同步修改 | 是 | STEP-PVAM-01-03/TC-003 |
| Placement | UserStats 精确 1L/2L/结余共享字段 | 00/01 Legacy factory 不写2；V2 entry 才 gate/stamping | 是 | STEP-PVAM-01-03/TC-003 |
| Elite | pv_pcs/gpv/gpv_real/contrib_to_parent + legacy estimated_bonus | 00/01 不写2且不做 float→cents；V2 blank cents=0 不代表 parity | 是 | STEP-PVAM-01-04/TC-003 |
| UserPeriodHighestRank | 无金额字段 | 保持不变 | 否 | TC-003 |

## 5. 施工设计

### 5.1 采用方案

- 新增 `Common/PvAmount.py`，公开 `parse_external_decimal_to_units`、`parse_db_amount_to_units`、`require_units_int`、`require_amount_version` 与受控整数乘除API；只依赖 Python 标准库与可选 NumPy/CuPy 类型探测，不导入 `User`、`Model.User` 或奖金模块。
- 常量固定：`PV_SCALE=1_000_000`、`RATE_PPM_SCALE=1_000_000`、`BONUS_CENT_SCALE=100`、`AMOUNT_ENCODING_VERSION_V2=2`。
- `require_units_int` 先拒绝 `bool`，再接受受控 signed integer，最后检查 int64 范围；内部域不接受 `str/Decimal/float`。
- 模型字段采用 `Optional[int] = None`；所有 v2 工厂显式传 `2`，绝不把默认值设为 2。
- legacy 记录仅允许通过 `Common/AmountModelAdapter.py`（新增）进入扫描、报表或受控重建；普通计算入口调用 `require_amount_version` 后 fail-loud。

选择理由：

- 与有效SQL、已关闭DEC及来源TASK目标一致。
- 采用 additive-first、显式version/manifest/feature flag，支持独立合入和回滚。
- 将纯函数、I/O适配、业务计算、权威提交和证据采集分层，便于DEV替身与UAT真实验证分别取证。

### 5.2 被否决方案

| 方案 | 不采用原因 | 来源 |
|---|---|---|
| version 默认值设为2 | 旧 JSON 缺字段会被静默伪装成新编码 | TASK-PVAM-01/CHK-DATA-003 |
| 服务内复制 parser | 继续产生多套 scale | R-002 |
| 接受 float 后再 Decimal | 精度损失已经发生 | CHK-DATA-001/002 |
| 给 UserPeriodHighestRank 加 version | 该模型不持有金额 | TASK-PVAM-01 |

### 5.3 修改后调用链与数据契约

| 边界 | 输入 | 处理 | 输出 | 断言/错误行为 | 责任符号 |
|---|---|---|---|---|---|
| 施工入口 | 固定commit + 批准TASK + PV_AMOUNT_V2_READ / PV_AMOUNT_V2_WRITE | 先执行基线/前置检查 | 受控diff | 任一前置失败即BLOCK | `Common/PvAmount.py` |
| 核心处理 | strict version/type/period/run合同 | 按STEP顺序执行 | 可测试状态/事件/金额 | 非法类型、状态或proof fail-loud | 见CHG表 |
| 证据出口 | 命令、输入、输出、状态前后 | WORK-08 schema封装 | EV包+SHA-256 | 缺原始证据不得PASS | `uat/scripts/*` |

## 6. 文件与符号级变更清单

| 变更编号 | 文件 | 类/函数/字段/表 | 类型 | 修改前行为 | 要求的修改 | 修改后行为 | 禁止行为 |
|---|---|---|---|---|---|---|---|
| CHG-01 | `Common/PvAmount.py` | 模块级常量与纯函数 | 新增 | 不存在 | 实现上述命名 parser、units/ppm/cents、int64/dtype 守卫 | 唯一公共金额 API | 不得导入业务层 |
| CHG-02 | `Common/AmountModelAdapter.py` | `AmountRecordState`、`classify_amount_record` | 新增 | 不存在 | 隔离 NEW/LEGACY_UNKNOWN/INCOMPATIBLE | 普通计算只能接收 NEW | 不得自动乘 scale |
| CHG-03 | `Model/User/UserStats.py` | `UserStats.amount_encoding_version` | 修改 | 无字段 | 增加 `Optional[int]=None` 与 units 注释 | 新记录显式2，旧记录保持None | 不得默认2 |
| CHG-04 | `Model/User/EliteBonusStats.py` | version、`estimated_bonus_cents` | 修改 | 无version；bonus float | additive 增加 version 与 integer cents；旧 float 只读兼容 | v2 不写 float | 不得删除旧字段 |
| CHG-05 | `User/UserStatsService.py` | `_get_or_init_user` 及 public run/batch 入口 | 修改 | 新节点无version | 每次 run/batch 加载一次 immutable config；00/01 factory 不写2；获批11 V2 factory 写2并 gate | Legacy/V2 作用域可审计 | 不得 refresh、fallback 或转换旧值 |
| CHG-06 | `User/GlobalRecalculationService.py` | `settle_period`、`_new_zero_user_stats`、`_mget_users_with_exists` | 修改 | 无 run config/version scope | settle 前加载一次并冻结；00/01 不写2且不无条件 gate；获批11 V2 entry 才写2/阻断旧未知 | 当前 run 不见中途 flag 变化 | 不得把缺失补2 |
| CHG-07 | `User/PlacementIncrementalService.py` / `User/PlacementRecalculationService.py` | public run/batch、节点构造与批量读取 | 修改 | 无 run config/version scope | 每个 batch/run 冻结一次；00/01 Legacy 结余照旧且不写2；获批11 V2 entry 才 gate/stamping | placement 全字段域一致 | 不得在01重解释 legacy 结余 |
| CHG-08 | `User/EliteBonusService.py` / `User/GlobalEliteBonusRecalculationService.py` | public run/batch、`_build_blank_node` / `_new_blank_stats` 等全部真实构造点 | 修改 | 无 run config/version scope | 每个 batch/run 冻结一次；00/01 不写2且禁止 legacy float→cents；获批11 V2 blank 写2且 cents=0 仅为 init | Elite 状态可判编码 | 不得自动重建或声称 bonus parity |
| CHG-09 | `User/Test/test_pv_amount_common.py` / `User/Test/test_amount_model_version.py` | pytest 用例 | 新增 | 不存在 | 覆盖类型、边界、序列化、mutation | 可自动验证 | 不得依赖GPU |

### 6.0A DEC-019 条件化合同

- Provider：只从 `PVAmountConfigProvider.load_run_config()` 获取 Redis snapshot；所有 production entry 使用同一 immutable run config，禁止直接 Redis flag GET、env/default/fallback 或途中 refresh。
- 00：Legacy authoritative，factory 不写2。
- 01：当前批准状态；UserStats/EliteBonusStats 仍为共享 key + Legacy authoritative，全部 production factory 为 `V2_WRITE_NOT_AVAILABLE`，不得写2、不得原地放大、不得 legacy float→cents。
- 10：production admission `INVALID_STATE`。
- 11：只有正式 approval 才可 production admission；当前无 approval 必须 `V2_STATE_NOT_AUTHORIZED`。
- TEST-ONLY 11：测试可直接构造 snapshot 调用 private factory/domain，但不能进入 production admission。
- UserStats 静态字段必须精确覆盖 `pv/gpv/gpv_real/gpv_unreal/contrib/pv_1l/pv_2l/pre_surplus_1l/pre_surplus_2l/total_1l/total_2l/remain_surplus_1l/remain_surplus_2l`。
- EliteBonusStats 静态字段必须精确覆盖 `pv_pcs/gpv/gpv_real/contrib_to_parent`；`estimated_bonus_cents=0` 只表示 blank/init。
- factory 测试通过 AST 发现全部真实 `UserStats(...)` / `EliteBonusStats(...)` 构造点，不使用预写函数数量作为覆盖证明。
### 6.1 固定基线锚点复验

| 文件与符号 | 基线事实 | 施工动作 |
|---|---|---|
| `Model/User/UserStats.py::UserStats` | 金额字段为`Optional[int]`，无`amount_encoding_version` | additive增加`Optional[int]=None`；所有v2工厂显式传2 |
| `Model/User/EliteBonusStats.py::EliteBonusStats` | 无version；`estimated_bonus`为`Optional[float]` | additive增加version与`estimated_bonus_cents`；legacy float只读兼容 |
| `User/GlobalRecalculationService.py::_new_zero_user_stats` | 新节点未写编码版本 | 显式写2，并在批量读取后统一校验 |
| `User/EliteBonusService.py::_build_blank_node`、`User/GlobalEliteBonusRecalculationService.py::_new_blank_stats` | 新Elite节点未写编码版本 | 显式写2；未知版本不得进入计算 |
| `Common/PvAmount.py` | 基线不存在 | 本任务新增；不得反向依赖User/Bonus |

### 6.2 规范补丁片段

以下片段是施工合同，不代替实施后的完整`git diff`：

> **补丁性质：`DESIGN_FRAGMENT`（非逐字可应用补丁）。真实patch须在实施commit后按§12.A生成并校验。**

```diff
--- a/Model/User/UserStats.py
+++ b/Model/User/UserStats.py
@@
 class UserStats(BaseRedisModel, index=True):
+    # None/缺失表示legacy或未知；只有显式2可进入micro-units计算域。
+    amount_encoding_version: Optional[int] = None
     id: str
```

> **补丁性质：`DESIGN_FRAGMENT`（非逐字可应用补丁）。真实patch须在实施commit后按§12.A生成并校验。**

```diff
--- a/Model/User/EliteBonusStats.py
+++ b/Model/User/EliteBonusStats.py
@@
 class EliteBonusStats(BaseRedisModel, index=True):
+    amount_encoding_version: Optional[int] = None
@@
     estimated_bonus: Optional[float] = 0.0
+    # v2权威写字段；legacy float字段仅用于兼容读取与对账。
+    estimated_bonus_cents: Optional[int] = 0
```

`Common/PvAmount.py`最低实现合同：

```python
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from numbers import Integral
from typing import Final

PV_SCALE: Final[int] = 1_000_000
RATE_PPM_SCALE: Final[int] = 1_000_000
BONUS_CENT_SCALE: Final[int] = 100
AMOUNT_ENCODING_VERSION_V2: Final[int] = 2
# 仅供隔离 legacy adapter 返回；不得写入模型或事件。
LEGACY_ADAPTER_VERSION: Final[int] = 0
INT64_MIN: Final[int] = -(2**63)
INT64_MAX: Final[int] = 2**63 - 1
_CANONICAL_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")


def require_int64(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{field_name} must be an integer, got {type(value).__name__}")
    result = int(value)
    if result < INT64_MIN or result > INT64_MAX:
        raise OverflowError(f"{field_name} is outside signed int64")
    return result


def require_units_int(value: object, field_name: str = "amount_units") -> int:
    return require_int64(value, field_name=field_name)


def _require_max_decimals(max_decimals: int) -> int:
    if isinstance(max_decimals, bool) or not isinstance(max_decimals, int) or max_decimals < 0:
        raise ValueError("max_decimals must be a non-negative integer")
    return max_decimals


def _decimal_to_units(
    value: Decimal,
    *,
    max_decimals: int,
    field_name: str,
) -> int:
    max_decimals = _require_max_decimals(max_decimals)
    decimal_places = max(0, -value.as_tuple().exponent)
    if decimal_places > max_decimals:
        raise ValueError(
            f"{field_name} has {decimal_places} decimal places; maximum is {max_decimals}"
        )
    scaled = value * PV_SCALE
    if scaled != scaled.to_integral_value():
        raise ValueError(f"{field_name} has precision finer than micro-units")
    return require_int64(int(scaled), field_name=field_name)


def parse_external_decimal_to_units(
    raw: str,
    *,
    max_decimals: int = 2,
) -> int:
    if not isinstance(raw, str) or not _CANONICAL_DECIMAL.fullmatch(raw):
        raise TypeError("external amount must be a canonical decimal string")
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("external amount is not a decimal") from exc
    return _decimal_to_units(
        value,
        max_decimals=max_decimals,
        field_name="external_amount",
    )


def parse_db_amount_to_units(
    raw: Decimal | str,
    *,
    max_decimals: int = 2,
) -> int:
    if isinstance(raw, Decimal):
        value = raw
    elif isinstance(raw, str) and _CANONICAL_DECIMAL.fullmatch(raw):
        try:
            value = Decimal(raw)
        except InvalidOperation as exc:
            raise ValueError("DB amount is not a decimal") from exc
    else:
        raise TypeError("DB amount must be Decimal or canonical decimal string")
    if not value.is_finite():
        raise ValueError("DB amount must be finite")
    return _decimal_to_units(value, max_decimals=max_decimals, field_name="db_amount")


def require_amount_version(
    value: object,
    *,
    allow_legacy: bool = False,
) -> int:
    if value is None:
        if allow_legacy:
            return LEGACY_ADAPTER_VERSION
        raise ValueError("amount_encoding_version is missing/legacy")
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError("amount_encoding_version must be an integer")
    normalized = int(value)
    if normalized != AMOUNT_ENCODING_VERSION_V2:
        raise ValueError(f"unsupported amount_encoding_version={normalized}")
    return normalized


def trunc_div_zero(numerator: int, denominator: int) -> int:
    """整数除法向零截断；支持任意非零分母。"""
    if denominator == 0:
        raise ZeroDivisionError("denominator must not be zero")
    quotient = abs(numerator) // abs(denominator)
    return -quotient if (numerator < 0) ^ (denominator < 0) else quotient
```

禁止把上述parser用于内部units再次放大；禁止把缺失version补成2后继续计算。

> **DEV 执行口径：** `05_CONTROL/check_baseline_preflight.sh` 与 `05_CONTROL/validate_work_dev.sh` 是唯一强制门禁。STEP 中列出的 `py_compile`、`compileall` 或 `pytest` 命令仅是附加局部检查，不得替代 parent-tree、scope、patch、tree-hash 与专属测试门禁。

## 7. 可执行施工步骤

### STEP-PVAM-01-01：建立公共金额模块

- 目的：建立公共金额模块，落实 `TASK-PVAM-01` 的已批准目标。
- 前置条件：无
- 修改文件：`Common/PvAmount.py`
- 目标符号：模块 API
- 精确操作：
1. 按 TASK 定义常量和类型标注
2. 实现向零整数除法、溢出检查和外部/DB 两类 parser
3. 对异常使用明确 `TypeError/ValueError/OverflowError`。
- 必须保持：不选择具体奖项舍入；不导入业务层
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Common/PvAmount.py`
- 本步单元验证：`TC-PVAM-01-01/02`
- 完成证据：`EV-PVAM-01-01`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任何 parser 接受 float/bool 时停工

### STEP-PVAM-01-02：建立版本适配器

- 目的：建立版本适配器，落实 `TASK-PVAM-01` 的已批准目标。
- 前置条件：STEP-01-01
- 修改文件：`Common/AmountModelAdapter.py`
- 目标符号：版本分类函数
- 精确操作：
1. 实现 `version=2`、legacy unknown、incompatible 三态
2. 普通入口默认不允许 legacy。
- 必须保持：不写数据、不自动转换
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Common/AmountModelAdapter.py`
- 本步单元验证：`TC-PVAM-01-03`
- 完成证据：`EV-PVAM-01-02`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：无法区分旧新记录时停工

### STEP-PVAM-01-03：扩展 UserStats 与工厂

- 目的：扩展 UserStats 与工厂，落实 `TASK-PVAM-01` 的已批准目标。
- 前置条件：STEP-01-02
- 修改文件：`Model/User/UserStats.py`、三个 User/Placement 服务
- 目标符号：字段与节点工厂
- 精确操作：
1. additive 增加 version
2. 按 frozen run config 条件化全部 AST 扫描所得构造点：00/01 不写2，获批11 V2 factory 显式2
3. 批量读与跨期读调用门禁。
- 必须保持：保持字段名/Redis key/业务公式不变
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Model/User/UserStats.py User/UserStatsService.py User/GlobalRecalculationService.py User/PlacementIncrementalService.py User/PlacementRecalculationService.py`
- 本步单元验证：`TC-PVAM-01-03/04`
- 完成证据：`EV-PVAM-01-03`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：旧记录被静默写回2时立即回滚

### STEP-PVAM-01-04：扩展 EliteBonusStats 与工厂

- 目的：扩展 EliteBonusStats 与工厂，落实 `TASK-PVAM-01` 的已批准目标。
- 前置条件：STEP-01-02
- 修改文件：`Model/User/EliteBonusStats.py`、Elite两服务
- 目标符号：version与cents additive字段
- 精确操作：
1. 新增 `estimated_bonus_cents`
2. 00/01 Legacy factory 不写2；获批11 V2 factory 写2并执行 version gate
3. 保留 `estimated_bonus` 供旧读。
- 必须保持：不在本步骤改Elite公式
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Model/User/EliteBonusStats.py User/EliteBonusService.py User/GlobalEliteBonusRecalculationService.py`
- 本步单元验证：`TC-PVAM-01-03/05`
- 完成证据：`EV-PVAM-01-04`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：旧字段被删除或重新解释时停工

### STEP-PVAM-01-05：补齐自动测试与静态扫描

- 目的：补齐自动测试与静态扫描，落实 `TASK-PVAM-01` 的已批准目标。
- 前置条件：STEP-01-01~04
- 修改文件：`User/Test/test_pv_amount_common.py` 等
- 目标符号：测试
- 精确操作：
1. 加入固定样例、旧JSON、int64、dtype、import graph与反mutation。
- 必须保持：测试不得复制生产算法
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m pytest -q User/Test/test_pv_amount_common.py User/Test/test_amount_model_version.py`
- 本步单元验证：`TC-PVAM-01-01~06`
- 完成证据：`EV-PVAM-01-05`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任一mutation存活不得合并

## 8. 数据迁移、兼容与重跑

### 8.1 数据变化

| 对象 | 旧格式/状态 | 新格式/状态 | 转换位置 | 版本识别 | 异常数据策略 |
|---|---|---|---|---|---|
| Redis UserStats/EliteBonusStats | 无version/legacy共享字段 | 00/01 保持 Legacy authoritative；获批11才产生完整 version=2 V2 record | 条件化节点工厂/后续受控重建 | amount_encoding_version + frozen config | Legacy path 不无条件 gate；V2 entry 阻断未知 |

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
| TC-PVAM-01-01 | 单元 | 外部金额字符串 | `"30.00"`,`"-100.25"` | `30_000_000`、`-100_250_000` | STEP-01-01 | DEV | NOT_RUN |
| TC-PVAM-01-02 | 单元 | 非法输入 | `0.1`,`True`,`"1e2"`,`"NaN"`,`"Infinity"`, `Decimal("NaN")`, `Decimal("sNaN")`, `Decimal("Infinity")`, `Decimal("-Infinity")` | 分别抛受控异常；无返回units | STEP-01-01 | DEV | NOT_RUN |
| TC-PVAM-01-03 | 契约 | version隔离 | None/1/2/3/`"2"` | 仅整数2进入新域；None归LEGACY_UNKNOWN；其余阻断 | STEP-01-02~04 | DEV+UAT | NOT_RUN |
| TC-PVAM-01-04 | 迁移 | 旧UserStats JSON | 缺version且pv=100 | 可反序列化；计算入口抛版本错误；值不被乘scale | STEP-01-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-01-05 | 边界 | int64乘法 | 接近INT64_MAX的units*ppm | 溢出前结果精确；越界抛OverflowError | STEP-01-01 | DEV | NOT_RUN |
| TC-PVAM-01-06 | 静态 | 依赖/反模式 | AST全仓 | Common不导入User；新增代码无Decimal(str(float))/int(round(float)) | STEP-01-05 | DEV | NOT_RUN |

| TC-FLAG-14 | 契约 | READ=false audit read | Legacy result + read-only V2 fixture | 审计读取不改变业务返回、version或写副作用 | STEP-01-02/05 | DEV | NOT_RUN |
| TC-FLAG-15 | factory | 00 Legacy factory | AST发现的全部UserStats/Elite构造点 | 不stamping2 | STEP-01-03/04/05 | DEV | NOT_RUN |
| TC-FLAG-16 | factory | 01共享-key Legacy factory | AST发现的全部生产构造点 | 不stamping2、不原地放大 | STEP-01-03/04/05 | DEV | NOT_RUN |
| TC-FLAG-17 | 静态 | 精确共享字段 | DEC-019字段清单 | UserStats 13项与Elite 4项逐项覆盖 | STEP-01-05 | DEV | NOT_RUN |
| TC-FLAG-18 | 静态/单元 | legacy float→cents | estimated_bonus float样本 | 不存在洗白路径 | STEP-01-04/05 | DEV | NOT_RUN |
| TC-FLAG-19 | 单元 | cents blank/init | estimated_bonus_cents=0 | 只证明初始化，不声称bonus parity | STEP-01-04/05 | DEV | NOT_RUN |
| TC-FLAG-20 | 单元 | test-only 11 | 直接构造测试snapshot | V2 factory写2但不能进入production admission | STEP-01-03/04/05 | DEV | NOT_RUN |
| TC-FLAG-21 | 静态/单元 | test-only bypass | production AST/callgraph | production code无法启用测试旁路 | STEP-01-05 | DEV | NOT_RUN |
受控检查方案用例映射：`TC-001, TC-002, TC-003, TC-008, TC-030, TC-031, TC-032`。`TC-000` 为 RETIRED，不执行、不计完成率。

### 9.2 开发环境自动验证

```bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_SHA="3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2"
: "${WORK_COMMIT_SHA:?set the implementation commit for WORK-PVAM-01}"
: "${PARENT_COMMIT_SHA:?set the controlled parent commit; root WORK uses BASE_SHA}"
: "${PARENT_TREE_SHA:?set the tree of PARENT_COMMIT_SHA}"
: "${PARENT_PROVENANCE_JSON:?set schema-v2 parent provenance JSON}"
: "${APPROVED_COMMIT_REGISTRY_JSON:?set canonical WORK_APPROVED_COMMIT_REGISTRY.json}"
CONTROL_ROOT="${PVAM_CONTROL_ROOT:?point to the released 05_CONTROL directory}"

# Phase A：只验证固定基线和既有锚点，不要求 Common/Settlement/Ops 等未来目录存在。
bash "$CONTROL_ROOT/check_baseline_preflight.sh" \
  --repo "$REPO_ROOT" --base "$BASE_SHA" --work-id "WORK-PVAM-01"

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
  --work-id "WORK-PVAM-01" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --test-command-file "$CONTROL_ROOT/work-test-commands/WORK-PVAM-01.sh" \
  --out "evidence/WORK-PVAM-01/dev"
```

#### 9.2.1 必须落地的关键 `assert` 契约

以下断言骨架必须进入本任务列出的 pytest 文件；fixture 由测试文件实现，不得用复制生产公式的替身替代被测符号。

```python
import pytest
from Common.PvAmount import (
    parse_external_decimal_to_units,
    require_amount_version,
    require_units_int,
)


def test_pv_amount_contract() -> None:
    assert parse_external_decimal_to_units("30.00") == 30_000_000
    assert parse_external_decimal_to_units("-100.25") == -100_250_000
    assert require_units_int(30_000_000, field_name="pv") == 30_000_000
    assert require_amount_version(2) == 2
    with pytest.raises(TypeError):
        parse_external_decimal_to_units(30.0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        require_units_int(True, field_name="pv")
    with pytest.raises(ValueError):
        require_amount_version(None)
```

通过标准：所有命令 exit code 0；pytest 无未解释 skip；证据schema校验通过。GPU/Dask/真实Redis/Kafka/MySQL未在DEV执行时必须标注 `NOT_RUN/PENDING_TEST_ENV`。

### 9.3 测试环境手工执行包

#### ENV-TC-PVAM-01-01：混合编码 Redis 读取

- 对应受控测试：`TC-003、TC-008、TC-031`
- 环境版本：由 `uat/environment_manifest.yaml` 固定 Python/CUDA/RAPIDS/Dask/Redis/Kafka/DB/镜像/commit。
- 前置服务与数据：专用 Redis DB/前缀；固定commit；WORK-08 manifest已生成
- 清理/隔离：必须使用专用 topic/group、Redis前缀、period/run_id；禁止复用生产数据。
- 执行命令：

```bash
RUN_ID=work01-$(date +%Y%m%d%H%M%S)
bash uat/scripts/run_work_uat.sh --work WORK-PVAM-01 --run-id "$RUN_ID" --tc TC-003,TC-008,TC-031
```

- SQL/数据库证据命令（仅在专用 UAT schema 和 WORK-08 manifest 校验通过后执行；N/A 项只保留说明）：

```bash
# N/A：本任务以 Redis JSON/version 与 Python 类型证据为准，不执行关系库写操作。
```

- 执行步骤：
1. 插入 legacy 缺version、version=2、version=3 三类记录
2. 运行批量读取与新节点构造
3. 导出前后JSON和异常日志
- 精确预期：
- version=2 正常；legacy/3阻断且原值不变
- 00/01 下全部共享-key Legacy 新记录不 stamping2；仅 test-only/获批11 V2 factory 显式2
- 无旧记录被自动放大
- 必须回传：完整命令、exit code、stdout/stderr、JUnit/JSON、输入fixture SHA-256、代码commit、镜像、环境版本、执行起止时间、Redis/DB/Kafka/Dask前后证据。
- 失败停止与清理：停止专用consumer/job；保留PEL/状态和证据；禁止在未分析前清理失败现场；按第11节回滚。

### 9.4 SQL 对账样例

| 样例 | SQL输入/来源 | SQL预期 | Python预期 | 比较口径 | 允许差异 |
|---|---|---|---|---|---|
| 金额编码样例 | `30.00 PV` | N/A（公共层不改SQL） | `30_000_000 units` | 1 PV=1,000,000 units | 0 |

## 10. 验收标准映射

| 验收编号 | 来源TASK验收项 | 实现步骤 | 测试用例 | 所需证据 | 环境 | 通过条件 |
|---|---|---|---|---|---|---|
| AC-01 | `Common/PvAmount.py` 存在，import graph 无循环，公共层无业务模块 import | STEP-PVAM-01-01/05 | TC-002、TC-031 | EV-PVAM-01-01 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-02 | 只有真正进入获批 V2 domain 且全部共享金额字段满足 V2 编码合同的 UserStats/EliteBonusStats record 才显式写 version=2；00/01 共享-key Legacy record 不得 stamping 2 | STEP-PVAM-01-03/04 | TC-003、TC-FLAG-15/16/20/21 | EV-PVAM-01-02 | DEV+UAT | 来源AC全部断言满足；真实 factory AST 扫描全覆盖；命令exit code 0；证据齐全 |
| AC-03 | 旧 JSON 缺 version 可反序列化；legacy/unknown version 仅在进入 v2 计算入口时必定阻断，READ=false 的 Legacy authoritative path 不得无条件 require version=2 | STEP-PVAM-01-02/03/04 | TC-003、TC-FLAG-14/15/16/20 | EV-PVAM-01-03 | DEV+UAT | 来源AC全部断言满足；00/01 与 V2 entry 分支均有反向测试；证据齐全 |
| AC-04 | version=1、3、字符串2、bool 等非法值全部阻断 | STEP-PVAM-01-02/05 | TC-003 | EV-PVAM-01-04 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-05 | 外部/DB 边界 parser 与内部 `require_units_int` 职责分离 | STEP-PVAM-01-01/05 | TC-001、TC-002 | EV-PVAM-01-05 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-06 | `0.1` float、`True`、NaN、Infinity、指数文本均被相应用例拒绝 | STEP-PVAM-01-01/05 | TC-001、TC-002 | EV-PVAM-01-06 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-07 | 正负边界、int64 最大值、乘法溢出测试通过 | STEP-PVAM-01-01/05 | TC-008 | EV-PVAM-01-07 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-08 | 只有持久化金额模型新增 version；无金额模型零误加 | STEP-PVAM-01-03/04/05 | TC-003、TC-030 | EV-PVAM-01-08 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-09 | 全仓新增代码没有 `Decimal(str(float))`、`int(round(float))` 等洗白模式 | STEP-PVAM-01-05 | TC-002、TC-031 | EV-PVAM-01-09 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-10 | TASK-01 独立回滚测试通过，旧代码在不写 v2 新数据时可启动 | STEP-PVAM-01-05 | TC-031、TC-032 | EV-PVAM-01-10 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |

### 10.1 AC-06 实施细化 / 派生测试

本小节只细化 `AC-06` 的实现测试边界，不改写上游 TASK 的来源验收文本，也不增加新的业务规则。来源 AC 仍严格限定为：`0.1` float、`True`、NaN、Infinity、指数文本均被相应用例拒绝。

| 类型 | 派生输入 | 预期异常合同 | TC 映射 | EV 映射 | 环境 |
|---|---|---|---|---|---|
| Decimal 非数扩展 | `Decimal("sNaN")` | 在缩放、指数或整数转换前显式抛 `ValueError("DB amount must be finite")` | `TC-PVAM-01-02` | `EV-PVAM-01-06` | DEV |
| Decimal 正无穷扩展 | `Decimal("Infinity")` | 在缩放、指数或整数转换前显式抛 `ValueError("DB amount must be finite")` | `TC-PVAM-01-02` | `EV-PVAM-01-06` | DEV |
| Decimal 负无穷扩展 | `Decimal("-Infinity")` | 在缩放、指数或整数转换前显式抛 `ValueError("DB amount must be finite")` | `TC-PVAM-01-02` | `EV-PVAM-01-06` | DEV |

派生输入只允许出现在本小节及其 `TC-PVAM-01-02` / `EV-PVAM-01-06` 映射中；不得回填到 AC 来源文本，不得据此把 DEV 结果解释为 UAT 或生产通过。

没有 STEP、TC 或 EV 映射的AC不得标记完成。任何含UAT的AC在未回传真实环境证据时只能为 `PENDING_TEST_ENV/BLOCKED`。

## 11. 风险、停工与回滚

### 11.1 风险清单

| 风险 | 触发条件 | 影响 | 预防措施 | 监测/证据 | 处置 |
|---|---|---|---|---|---|
| 旧记录被默认成v2 | 模型默认值或反序列化补值 | 历史金额按错误倍率参与 | 字段默认None；入口强校验 | version扫描 | 停工并回滚reader enforcement |
| int64越界 | 极大聚合/乘ppm | wrap导致财务错误 | checked_add/mul | 异常与上界报告 | 阻断该run |

### 11.2 本任务强制停工条件

- HEAD、SQL blob、模型schema或上游TASK与受控基线不一致。
- 实施必须改变未批准的业务规则、精度、资格、分母、Country或发布职责才能继续。
- 需要修改排除文件/模块或扩大异常白名单才能通过测试。
- 关键mutation存活、SQL黄金样例出现未批准差异、幂等/原子/回滚断言失败。
- UAT权限、schema、数据或隔离条件不足；此时保持 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV`。

### 11.3 部署面与数据面回滚门禁

**当前可执行性：`BLOCKED_EXTERNAL_EVIDENCE`。** 当前材料没有给出真实部署系统、workload/release、镜像、配置对象和健康检查命令，因此不得以本地`export`或通用`git revert`冒充部署回滚。

部署前必须提供并签署`evidence/WORK-PVAM-01/rollback/ROLLBACK-MANIFEST-PVAM-v1.json`，至少包含：

- `deployment_system`、`environment`、`workload_id`、`release_before/after`、`image_before/after`；
- 精确的停止、回滚、恢复、健康检查和重新放量命令；
- Redis/Stream/ledger/run/manifest的备份或快照位置及SHA-256；
- 执行人、复核人、批准时间、允许的数据恢复范围；
- 命令dry-run/隔离演练的退出码和原始日志。

本任务数据面处置：停止v2新写；保留amount version与适配器；禁止把v2数据降级伪装成legacy；恢复旧镜像后仅允许读取旧数据，v2记录继续隔离。

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
| EV-PVAM-01-01 | AC-01验收证据：`Common/PvAmount.py` 存在，import graph 无循环，公共层无业务模块 import | STEP-PVAM-01-01/05 | evidence/WORK-PVAM-01/attempt-*/ac/AC-01/ | 待指派QA | PENDING |
| EV-PVAM-01-02 | AC-02验收证据：00/01共享-key Legacy record不写2；test-only/获批11完整V2 factory写2 | STEP-PVAM-01-03/04 | evidence/WORK-PVAM-01/attempt-*/ac/AC-02/ | 待指派QA | PENDING |
| EV-PVAM-01-03 | AC-03验收证据：Legacy path不无条件gate；进入V2计算入口必阻断legacy/unknown | STEP-PVAM-01-02/03/04 | evidence/WORK-PVAM-01/attempt-*/ac/AC-03/ | 待指派QA | PENDING |
| EV-PVAM-01-04 | AC-04验收证据：version=1、3、字符串2、bool 等非法值全部阻断 | STEP-PVAM-01-02/05 | evidence/WORK-PVAM-01/attempt-*/ac/AC-04/ | 待指派QA | PENDING |
| EV-PVAM-01-05 | AC-05验收证据：外部/DB 边界 parser 与内部 `require_units_int` 职责分离 | STEP-PVAM-01-01/05 | evidence/WORK-PVAM-01/attempt-*/ac/AC-05/ | 待指派QA | PENDING |
| EV-PVAM-01-06 | AC-06验收证据：`0.1` float、`True`、NaN、sNaN、±Infinity（字符串与 Decimal）、指数文本均被相应用例拒绝 | STEP-PVAM-01-01/05 | evidence/WORK-PVAM-01/attempt-*/ac/AC-06/ | 待指派QA | PENDING |
| EV-PVAM-01-07 | AC-07验收证据：正负边界、int64 最大值、乘法溢出测试通过 | STEP-PVAM-01-01/05 | evidence/WORK-PVAM-01/attempt-*/ac/AC-07/ | 待指派QA | PENDING |
| EV-PVAM-01-08 | AC-08验收证据：只有持久化金额模型新增 version；无金额模型零误加 | STEP-PVAM-01-03/04/05 | evidence/WORK-PVAM-01/attempt-*/ac/AC-08/ | 待指派QA | PENDING |
| EV-PVAM-01-09 | AC-09验收证据：全仓新增代码没有 `Decimal(str(float))`、`int(round(float))` 等洗白模式 | STEP-PVAM-01-05 | evidence/WORK-PVAM-01/attempt-*/ac/AC-09/ | 待指派QA | PENDING |
| EV-PVAM-01-10 | AC-10验收证据：TASK-01 独立回滚测试通过，旧代码在不写 v2 新数据时可启动 | STEP-PVAM-01-05 | evidence/WORK-PVAM-01/attempt-*/ac/AC-10/ | 待指派QA | PENDING |
| EV-PVAM-01-P01 | 公共金额模块与版本适配器 diff | 对应STEP/TC | evidence/WORK-PVAM-01/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-01-P02 | 模型/工厂 additive diff | 对应STEP/TC | evidence/WORK-PVAM-01/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-01-P03 | DEV pytest/JUnit与AST报告 | 对应STEP/TC | evidence/WORK-PVAM-01/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-01-P04 | UAT混合编码证据包 | 对应STEP/TC | evidence/WORK-PVAM-01/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-01-P05 | 字段编码矩阵与回滚记录 | 对应STEP/TC | evidence/WORK-PVAM-01/attempt-*/package/ | 待指派QA | PENDING |

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
  --work-id "WORK-PVAM-01" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --out "evidence/WORK-PVAM-01/patch"
```

门禁必须证明：

1. `BASE_SHA` 是 `WORK_COMMIT_SHA` 的祖先；
2. 全部新增、修改、删除和 rename 的旧/新路径均落在 `WORK-PVAM-01` 批准 allowlist；
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
| STEP-PVAM-01-01 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-01-02 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-01-03 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-01-04 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-01-05 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |

### 13.2 实际验证

| 测试 | 环境 | 命令/版本 | 结果 | 证据 | 执行时间 |
|---|---|---|---|---|---|
| TC-PVAM-01-01 | DEV | 待执行 | NOT_RUN | EV-PVAM-01-* | 待执行 |
| TC-PVAM-01-02 | DEV | 待执行 | NOT_RUN | EV-PVAM-01-* | 待执行 |
| TC-PVAM-01-03 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-01-* | 待执行 |
| TC-PVAM-01-04 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-01-* | 待执行 |
| TC-PVAM-01-05 | DEV | 待执行 | NOT_RUN | EV-PVAM-01-* | 待执行 |
| TC-PVAM-01-06 | DEV | 待执行 | NOT_RUN | EV-PVAM-01-* | 待执行 |

### 13.3 未完成项

| 项目 | 原因 | 风险 | 后续动作 | 责任人 | 截止时间 |
|---|---|---|---|---|---|
| UAT/外部材料 | 当前计划阶段未执行 | 不能关闭P0/P1 | 由WORK-08准入后执行 | 待指派 | 待批准 |

## 14. 偏离、发现项与上游回流

| 编号 | 类型 | 发现事实 | 是否影响业务/范围 | 临时动作 | 需要更新 | 最终裁决 |
|---|---|---|---|---|---|---|
| `DEV-PVAM-01-001` | `预留` | 待执行 | 待判断 | 停工/隔离 | WORK/TASK/DEC/REVIEW | 待裁决 |

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
| v1.0 | 2026-08-04 | 初版施工任务书 | `TASK-PVAM-01` + `PLAN-PVAM-v1.15` + 固定代码基线 | AI Agent（编制） | DRAFT |
| v1.1 | 2026-08-05 | 依据二轮核验报告完成定点修订并补齐治理追溯 | F-A/F-B/F-H/F-I/F-J/F-K/F-F/F-E/F-L/F-M/F-N 中适用项 | AI Agent（编制） | DRAFT |
| v1.2 | 2026-08-05 | 闭合 G-1：统一 `RecalcProcessResult` 类名并补齐 `should_ack`；历史版本曾调整施工套件审批状态，不改变 CHK/DEC/TASK/WORK 范围 | 历史会话声明（未形成可独立验证组织授权，现由 v1.3 取代） | AI Agent（编制） | SUPERSEDED |
| v1.3 | 2026-08-05 | 第四轮关闭 F3-01～F3-10：治理回退 DRAFT、Traceability v3、patch/DEV 双阶段、状态枚举及设计边界 | 三轮审查报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r6 | 2026-08-06 | 五轮 F5 定点修订：规范 v3 追溯、parent provenance/DEV CLI、控制状态字段及单一事实源 | 五轮审计报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r7 | 2026-08-06 | 六轮 S6：信任 registry 初版、归档哈希、临时目录与 Decimal finite 防护 | 六轮终局审计报告 | AI Agent（编制） | DRAFT |
| v1.3-r8 | 2026-08-06 | 七轮 B7：registry 发布信任根、四工件摘要、AC 来源保真及当前轮次引用 | 七轮终局审计报告 + B7 处置 | AI Agent（编制） | DRAFT |
| v1.3-r10 | 2026-08-08 | 依据 DEC-019 条件化 AC-02/03、CHG-05～08、factory/version gate 与 TEST-ONLY 域；新增 TC-FLAG-14～21 | PVAM USER-DECISION FINAL | AI Agent（编制） | DRAFT |

<!-- END WORK-PVAM-01_金额编码公共层与基础模型适配器.md -->

---

<!-- BEGIN WORK-PVAM-01C_Flag_Runtime_Contract与Redis原子配置.md -->

# WORK-PVAM-01C Flag Runtime Contract 与 Redis 原子配置施工任务书

> 本文档来源于待组织批准的 `TASK-PVAM-01C`；技术合同已由 DEC-019 固化，但组织施工授权、真实 UAT 与 Gate C 仍保持独立。

## 0. 填写与执行规则

1. 基线必须精确等于 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`。
2. 治理 validator 未全部 0 退出前，禁止编辑本卡 production 文件。
3. 只允许修改 §6 与 `WORK_SCOPE_ALLOWLIST.json` 登记的路径。
4. fake/stub 只形成 DEV 证据，真实 Redis UAT 继续由 WORK-PVAM-08/DEC-013 控制。

## 1. 文档信息与追溯关系

| 项目 | 内容 |
|---|---|
| 施工任务编号 | `WORK-PVAM-01C` |
| 来源修改任务 | `TASK-PVAM-01C` |
| 来源检查项 | `CHK-ARCH-001、CHK-ARCH-003、CHK-DATA-003、CHK-EVT-003、CHK-TEST-003、CHK-TEST-004` |
| 来源问题 | `GAP-PVAM-FLAG-CONTRACT` |
| 关联决策 | `DEC-019` |
| 复核闭环追踪号 | `REM-014 / W-014 / V-014` |
| 代码基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| 文档版本 | `v1.3` |
| 文档状态 | `DRAFT` |
| 实施状态 | `BLOCKED` |
| 验证状态 | `NOT_RUN / PENDING_TEST_ENV` |

## 2. 施工目标与完成定义

- 在 `Redishelper` 建立唯一 Provider 和 MANUAL_BOOTSTRAP，不在 Common 或业务 Service 内复制配置 I/O。
- Provider 单次 Lua 原子读取 active pointer 与 versioned snapshot，严格解析 immutable run config。
- production admission 明确实现 00/01/10/11；当前不存在 11 production approval。
- run session 在开始时加载一次并冻结；无 refresh、无 stale cache。
- Bootstrap 使用 Lua/CAS 完成 strictly monotonic version 判断、snapshot 写入和 pointer 切换，并 read-after-write verify。

完成必须同时满足：TC-FLAG-01～13、22、23 在相应 DEV/UAT 边界有真实结果；不存在 fallback；scope 与治理 validator 通过。TC-FLAG-14～21 由条件化后的 WORK-PVAM-01 承接。

## 3. 当前事实与复用决定

| 检查对象 | 事实 | 决定 |
|---|---|---|
| `Redishelper/BaseRedisModel.py` | 已有项目 Redis 连接 | Provider 延迟复用该连接，并允许测试注入 fake client |
| ConfigService/revision/CAS | 未发现适用实现 | 本卡只为 PV amount flag 定义 versioned snapshot，不建立第二套通用配置框架 |
| run context | 未发现统一实现 | 在 Provider 文件内提供 frozen run session/admission；后续 WORK-PVAM-01 入口传递同一 config |
| Redis transaction helpers | pipeline/lock 存在，但无配置 CAS | 使用 Redis Lua 单原子边界，避免 GET→SET TOCTOU |

## 4. Redis 合同

### 4.1 Key 与 schema

| Key | 类型 | 内容 |
|---|---|---|
| `pvam:amount_config:active` | string | `config_version:checksum` |
| `pvam:amount_config:snapshot:<config_version>` | hash | READ、WRITE、config_version、load_mode、source、checksum |

canonical payload 至少为：

```json
{
  "PV_AMOUNT_V2_READ": "false",
  "PV_AMOUNT_V2_WRITE": "true",
  "config_version": "1",
  "load_mode": "MANUAL_BOOTSTRAP",
  "source": "AR_CONFIG"
}
```

### 4.2 原子读取与发布

- load Lua 在一个 Redis 执行边界内读取 pointer 与对应 hash；pointer/version/checksum 任一不一致即 fail-loud。
- publish Lua 在同一执行边界校验 active version、创建不可变 snapshot、切 pointer；`new_version <= active_version` 为 `STALE_CONFIG_VERSION`。
- 第一次发布只允许 active 不存在的 explicit initial-create；version 仍必须是非负整数。
- Provider/Bootstrap 不接受 env、常量默认、AR_CONFIG 直查或 cached stale fallback。

### 4.3 State admission 与 run-freeze

| 状态 | production admission |
|---|---|
| 00 | 允许，Legacy authoritative |
| 01 | 允许，当前批准配置；Legacy authoritative |
| 10 | `INVALID_STATE` |
| 11 | 当前 `V2_STATE_NOT_AUTHORIZED` |

`PVAmountRunSession.start(provider)` 是 production admission 边界；返回对象及其 config 均 immutable，不公开 refresh。运行期间 Provider 变化只影响下一次 start。

## 5. 分阶段依赖

- Phase A：本卡 Provider/bootstrap 与 TC-FLAG-01～13/22/23，无前置 production WORK。
- WORK-PVAM-01：在 Phase A 接口可用后，条件化 AC-02/AC-03 与 CHG-05～08，接入同一 run config。
- Phase B：在组合树执行 TC-FLAG-14～21 和全量 factory 扫描；这不是新的 production scope。

## 6. 文件与符号级变更清单

| 变更编号 | 文件 | 符号 | 类型 | 合同 |
|---|---|---|---|---|
| CHG-01C-01 | `Redishelper/PVAmountConfigProvider.py` | `PVAmountRunConfig`、`PVAmountConfigProvider.load_run_config` | 新增 | immutable、atomic load、strict parse、fail-loud |
| CHG-01C-02 | `Redishelper/PVAmountConfigProvider.py` | `PVAmountRunSession.start`、production admission | 新增 | 00/01允许、10拒绝、未批准11拒绝、run-freeze |
| CHG-01C-03 | `Redishelper/PVAmountConfigBootstrap.py` | `publish_manual_bootstrap`、CLI | 新增 | 原子发布01、stale protection、read-after-write、失败非零 |
| CHG-01C-04 | `tests/pvam/WORK-PVAM-01C/` | provider/bootstrap tests | 新增 | fake/in-memory DEV；真实 Redis 不伪造 |

禁止修改：`Common/PvAmount.py`、现有业务 Service、共享 Redis model 字段、奖金公式、AR_CONFIG→Delta producer。

## 7. 可执行施工步骤

### STEP-PVAM-01C-01：实现 snapshot 解析与 Provider

- 新建 frozen dataclass、错误类型、canonical bool/version/checksum 校验。
- 单次 Lua 读取 pointer + hash；Redis 异常统一 fail-loud，保留 cause。
- 禁止任何 fallback 或直接 AR_CONFIG/env 读取。

### STEP-PVAM-01C-02：实现 admission 与 run-freeze

- 实现 00/01/10/11 状态机。
- `PVAmountRunSession.start` 只调用 Provider 一次；session 无 refresh。
- 当前 production admission 不提供 test-only 或 11 approval bypass。

### STEP-PVAM-01C-03：实现 MANUAL_BOOTSTRAP

- CLI 接受显式 `config_version`，固定当前批准 READ=false/WRITE=true。
- Lua/CAS 原子发布 versioned snapshot + pointer；stale/conflict 失败。
- Provider read-after-write verify；任一失败非零退出。

### STEP-PVAM-01C-04：补齐 DEV/UAT 分层测试

- fake client 覆盖结构、异常、状态、冻结、stale、并发。
- AST 扫描 production consumer 无直接 flag GET/env/default。
- 隔离 Redis 未提供时，相关真实环境项保持 PENDING_TEST_ENV。

## 8. 数据与回滚

- Snapshot append-only；不删除已发布 version。
- 回滚通过发布更高 version 的合法 00/01 snapshot，不倒拨 config_version。
- 不允许部分字段更新或直接改 active snapshot。
- 任何需要新 V2 carrier 的行为以 `V2_CARRIER_NOT_APPROVED` 停工。

## 9. 测试设计

### 9.1 测试用例总表

| 测试编号 | 场景 | 精确预期 | 环境 | 状态 |
|---|---|---|---|---|
| TC-FLAG-01 | 合法01 load | immutable config 为 false/true/version | DEV+UAT | NOT_RUN |
| TC-FLAG-02 | snapshot 缺失 | fail-loud | DEV | NOT_RUN |
| TC-FLAG-03 | READ 缺失 | fail-loud | DEV | NOT_RUN |
| TC-FLAG-04 | WRITE 缺失 | fail-loud | DEV | NOT_RUN |
| TC-FLAG-05 | version 缺失 | fail-loud | DEV | NOT_RUN |
| TC-FLAG-06 | 非法bool | fail-loud | DEV | NOT_RUN |
| TC-FLAG-07 | 状态10 | `INVALID_STATE` | DEV | NOT_RUN |
| TC-FLAG-08 | Provider exception | 无 AR_CONFIG/env/default fallback | DEV | NOT_RUN |
| TC-FLAG-09 | run中途01→11 | 当前 run 保持01 | DEV | NOT_RUN |
| TC-FLAG-10 | 下一 run 读未批准11 | `V2_STATE_NOT_AUTHORIZED` | DEV | NOT_RUN |
| TC-FLAG-11 | pointer/snapshot 跨version | fail-loud | DEV | NOT_RUN |
| TC-FLAG-12 | bootstrap发布01 | 单一原子提交并校验 | DEV+UAT | NOT_RUN |
| TC-FLAG-13 | consumer静态扫描 | 无直接 Redis flag GET | DEV | NOT_RUN |
| TC-FLAG-22 | stale publish | N/N-1 均失败 | DEV+UAT | NOT_RUN |
| TC-FLAG-23 | 并发 publish | 至多一个成功且 active 为较新合法 version | DEV+UAT | NOT_RUN |

受控检查方案用例映射：`TC-003, TC-024, TC-031, TC-032`。`TC-FLAG` 为本决策局部测试编号。

### 9.2 开发环境自动验证

```bash
set -euo pipefail
BASE_SHA="3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2"
: "${WORK_COMMIT_SHA:?set WORK-PVAM-01C implementation commit}"
: "${PARENT_COMMIT_SHA:?set controlled parent}"
: "${PARENT_TREE_SHA:?set controlled parent tree}"
: "${PARENT_PROVENANCE_JSON:?set parent provenance}"
bash 05_CONTROL/check_baseline_preflight.sh --repo "$PWD" --base "$BASE_SHA" --work-id WORK-PVAM-01C
bash 05_CONTROL/validate_work_dev.sh \
  --repo "$PWD" --base "$BASE_SHA" \
  --parent-commit "$PARENT_COMMIT_SHA" \
  --parent-tree "$PARENT_TREE_SHA" \
  --parent-provenance "$PARENT_PROVENANCE_JSON" \
  --approved-registry "$APPROVED_COMMIT_REGISTRY_JSON" \
  --work-commit "$WORK_COMMIT_SHA" --work-id WORK-PVAM-01C \
  --scope "$PVAM_CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --test-command-file "$PVAM_CONTROL_ROOT/work-test-commands/WORK-PVAM-01C.sh" \
  --out evidence/WORK-PVAM-01C/dev
```

## 10. 验收标准映射

| 验收编号 | 来源TASK验收项 | 实现步骤 | 测试用例 | 所需证据 | 环境 | 通过条件 |
|---|---|---|---|---|---|---|
| AC-01 | 合法 01 snapshot 原子加载成功并返回 immutable run config | STEP-PVAM-01C-01 | TC-FLAG-01 | EV-PVAM-01C-01 | DEV+UAT | 精确值、原子读取与不可变性成立 |
| AC-02 | active snapshot 缺失时 fail-loud | STEP-PVAM-01C-01 | TC-FLAG-02 | EV-PVAM-01C-01 | DEV | 无返回 config |
| AC-03 | READ 缺失时 fail-loud | STEP-PVAM-01C-01 | TC-FLAG-03 | EV-PVAM-01C-01 | DEV | 无 fallback |
| AC-04 | WRITE 缺失时 fail-loud | STEP-PVAM-01C-01 | TC-FLAG-04 | EV-PVAM-01C-01 | DEV | 无 fallback |
| AC-05 | config_version 缺失时 fail-loud | STEP-PVAM-01C-01 | TC-FLAG-05 | EV-PVAM-01C-01 | DEV | 无默认 version |
| AC-06 | 非 canonical bool 时 fail-loud | STEP-PVAM-01C-01 | TC-FLAG-06 | EV-PVAM-01C-01 | DEV | 非法值拒绝 |
| AC-07 | 状态 10 在 production admission 抛 `INVALID_STATE` | STEP-PVAM-01C-02 | TC-FLAG-07 | EV-PVAM-01C-02 | DEV | 不自动修正 |
| AC-08 | Provider 异常时不存在 AR_CONFIG/env/default fallback | STEP-PVAM-01C-01 | TC-FLAG-08 | EV-PVAM-01C-02 | DEV | 原异常链可审计 |
| AC-09 | run 加载 01 后 Redis 变 11，当前 run 仍固定 01 | STEP-PVAM-01C-02 | TC-FLAG-09 | EV-PVAM-01C-02 | DEV | Provider 仅调用一次 |
| AC-10 | 下一 production run 加载 11 且无正式 approval 时抛 `V2_STATE_NOT_AUTHORIZED` | STEP-PVAM-01C-02 | TC-FLAG-10 | EV-PVAM-01C-02 | DEV | test-only 不旁路 |
| AC-11 | active pointer 与 snapshot 跨 version 或 checksum 不一致时 fail-loud | STEP-PVAM-01C-01 | TC-FLAG-11 | EV-PVAM-01C-01 | DEV | 无部分 snapshot |
| AC-12 | bootstrap 以单一原子操作发布完整 01 并 read-after-write verify | STEP-PVAM-01C-03 | TC-FLAG-12 | EV-PVAM-01C-03 | DEV+UAT | 失败非零 |
| AC-13 | production consumer 无直接 Redis flag GET | STEP-PVAM-01C-04 | TC-FLAG-13 | EV-PVAM-01C-04 | DEV | AST 扫描零命中 |
| AC-14 | 当前 version=N 时发布 N 或 N-1 均抛 `STALE_CONFIG_VERSION` | STEP-PVAM-01C-03 | TC-FLAG-22 | EV-PVAM-01C-03 | DEV+UAT | active 不变 |
| AC-15 | 两个并发 bootstrap 至多一个成功，active version 为较新合法版本且无 lost update | STEP-PVAM-01C-03/04 | TC-FLAG-23 | EV-PVAM-01C-03 | DEV+UAT | CAS 结果确定 |

## 11. 风险、停工与回滚

- Redis client 不支持 Lua/EVAL 或无法证明 server-side atomicity：停工。
- 发现适用的既有统一 config revision/CAS：回到治理卡评估复用，禁止并存竞争版本机制。
- 需要独立 V2 carrier/keyspace：`V2_CARRIER_NOT_APPROVED`。
- 真实 Redis 不可用：DEV 可继续，UAT 保持 `PENDING_TEST_ENV`。

## 12. 交付物与完成证据

| 证据编号 | 内容 | 状态 |
|---|---|---|
| EV-PVAM-01C-01 | snapshot schema、atomic load 与 fail-loud 测试 | PENDING |
| EV-PVAM-01C-02 | 00/01/10/11 admission 与 run-freeze 测试 | PENDING |
| EV-PVAM-01C-03 | bootstrap stale/CAS/concurrency 测试 | PENDING |
| EV-PVAM-01C-04 | direct GET/fallback/static scan 与 DEV 报告 | PENDING |
| EV-PVAM-01C-P01 | scope、patch、parent provenance、命令/exit/SHA 包 | PENDING |

## 13. 执行记录

| 项目 | 当前状态 |
|---|---|
| 实际修改 | 待执行 |
| DEV | NOT_RUN |
| 真实 Redis UAT | PENDING_TEST_ENV |
| Gate C | OPEN |

## 14. 版本记录

| 版本 | 日期 | 变更内容 | 变更原因/来源 | 编制人 | 批准状态 |
|---|---|---|---|---|---|
| v1.3-r10 | 2026-08-08 | 新建 flag runtime Provider、atomic bootstrap、admission 与 run-freeze 施工卡 | `DEC-019 / TASK-PVAM-01C` | AI Agent（编制） | DRAFT |

<!-- END WORK-PVAM-01C_Flag_Runtime_Contract与Redis原子配置.md -->

---

<!-- BEGIN WORK-PVAM-02_订单退款金额边界与期间解析.md -->

# WORK-PVAM-02 订单/退款入口金额放大与边界转换施工任务书

> 文档定位：来源于待组织批准的 `TASK-PVAM-02`，在取得组织授权后转化为可执行施工说明。本文件不重新决定业务规则；实际结果只能写入执行记录与验证交付报告。

## 0. 填写与执行规则

1. 上游修改任务与本 v1.3 施工套件当前均为 `DRAFT`；没有组织授权前，本任务保持 `BLOCKED`，不得启动代码施工或部署。
2. 只实施 `R-003、R-007` 中已 `ACCEPTED` 或由来源 TASK 明确批准的条件代码事项。任何 `REJECTED / NEEDS_DECISION / DEFERRED / 未获 TASK 授权的 UAT_VERIFY` 只允许登记、验证或阻断，不得扩展代码范围。
3. 基线必须精确等于 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；发现漂移立即登记 `BLOCK-PVAM-02-BASELINE`。
4. 所有新文件/符号已在变更表标为“新增”；其余锚点均来自固定基线。
5. DEV替身不能冒充真实Kafka/Redis/Dask/GPU/MySQL UAT验证。

## 1. 文档信息与追溯关系

| 字段 | 内容 |
|---|---|
| 施工任务编号 | `WORK-PVAM-02` |
| 施工任务名称 | 订单/退款入口金额放大与边界转换 |
| 所属施工总方案 | `WORK-PLAN-PVAM_v1.3` |
| 来源修改任务 | `TASK-PVAM-02@MODPLAN-PVAM_v1.2`（authorization=PENDING_ORGANIZATIONAL_APPROVAL） |
| 来源问题 | `R-003、R-007` |
| 复核闭环追踪号 | `REM-003、REM-007 / W-003、W-007 / V-003、V-007` |
| 来源检查项 | `CHK-DATA-001、CHK-DATA-002、CHK-ARCH-003、CHK-BIZ-011、CHK-DATA-005` |
| 关联决策 | `DEC-002、DEC-005、DEC-006、DEC-007、DEC-010` |
| 代码基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| SQL基线 | `sql_uat/*@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，仅有效SQL |
| 文档版本 | `v1.3` |
| 负责人 | `待指派 / 实施工程师` |
| 复核人 | `待指派 / 架构与QA` |
| 当前状态 | `BLOCKED` |
| 文档治理状态 | `DRAFT`（`PENDING_ORGANIZATIONAL_APPROVAL`） |
| 前置任务 | WORK-PVAM-01、WORK-PVAM-03 均达到 DEV_VERIFIED；WORK-PVAM-03 配置 API 在奖金切换前必须可用 |
| 功能开关 | `PV_NORMALIZER_V2 / PERIOD_RESOLVER_V2` |

### 1.1 一对一追溯摘要

```text
CHK-DATA-001、CHK-DATA-002、CHK-ARCH-003、CHK-BIZ-011、CHK-DATA-005
  └─ R-003、R-007
       └─ DEC-002、DEC-005、DEC-006、DEC-007、DEC-010
            └─ TASK-PVAM-02 (DRAFT / PENDING_ORGANIZATIONAL_APPROVAL)
                 └─ WORK-PVAM-02
                      ├─ STEP-PVAM-02-01 / STEP-PVAM-02-02 / STEP-PVAM-02-03 / STEP-PVAM-02-04 / STEP-PVAM-02-05 / STEP-PVAM-02-06 / STEP-PVAM-02-07
                      ├─ TC-PVAM-02-01 / TC-PVAM-02-02 / TC-PVAM-02-03 / TC-PVAM-02-04 / TC-PVAM-02-05 / TC-PVAM-02-06 / TC-PVAM-02-07 / TC-PVAM-02-08
                      └─ EV-PVAM-02-01...
```

## 2. 施工任务生成依据

### 2.1 上游输入

| 输入 | 编号/版本 | 本任务使用的结论 | 状态 |
|---|---|---|---|
| 复核报告 | `Redemption_PV_Amount_Migration_d74_复核报告_v1.5` | R-003、R-007 的代码事实与严重级别 | CONFIRMED |
| 修改任务书 | `TASK-PVAM-02` | 采用方案、范围、排除项、AC | DRAFT（待组织授权） |
| 检查方案 | `PLAN-PVAM-v1.15` | CHK-DATA-001、CHK-DATA-002、CHK-ARCH-003、CHK-BIZ-011、CHK-DATA-005 | CONTROLLED |
| 正式决策 | DEC-002、DEC-005、DEC-006、DEC-007、DEC-010 | 只执行已关闭裁决；开放项阻断 | CLOSED / 按上游登记 |
| 代码/SQL快照 | 3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2 | 唯一施工对象 | FROZEN |
| 施工模板 | 总方案模板/专项模板 | 章节、状态、证据纪律 | CONTROLLED |

### 2.2 开工条件

- [ ] 当前 HEAD 精确为 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，工作树无未登记变更。
- [ ] `TASK-PVAM-02` 的人工批准记录已归档；本 `WORK` 已由施工负责人和复核人签署。
- [ ] 前置关系满足：WORK-PVAM-01、WORK-PVAM-03 均达到 DEV_VERIFIED；WORK-PVAM-03 配置 API 在奖金切换前必须可用。
- [ ] 本任务涉及的接口、单位、精度、兼容和回滚边界已由上游任务固定。
- [ ] DEV测试依赖已安装；UAT项具备WORK-08生成的环境/数据/schema manifest。
- [ ] 功能开关默认关闭，回滚路径已演练。

未满足任一关键项时，本任务状态为 `BLOCKED`；不得用假设替代。

## 3. 问题事实与施工目标

### 3.1 已确认问题

| 项目 | 内容 |
|---|---|
| 预期行为 | 实现唯一 raw→normalized PV 入口和唯一 PeriodResolver；三条增量链只消费同一 strict units-int delta；清除生产可达金额链中的 float/round 中转。 |
| 当前行为 | `User/PEBonusService.py::_apply_truncate` 使用 `cp.round` 并通过 `/100.0` 产生奖金 float。；`User/LeadershipBonusGPUService.py::_truncate_gpu` 将金额转为 `float64` 后使用 `nextafter/trunc`。；`User/PlacementRecalculationService.py::_process_extract_batch` 从 Redis 调用 `float(...)`，空表构造 `float64` PV 列，回写包含 `int(round(float(...)))`。；`GlobalRecalculationService._get_previous_period`、`PlacementIncrementalService._get_prev_period` 和 `PlacementRecalculationService._get_prev_period` 存在本地 period 算术/首期硬编码。；`Order/OrderService.py` 是 Dask/BFS 演示，`MessageConsumer/UserConsumer.py` 是拓扑变更 consumer；二者都不是受控金额入口。 |
| 差异 | 当前实现缺少本任务批准的唯一合同、门禁或原子边界。 |
| 影响 | 金额/PV单位、奖金、并发一致性、发布或可恢复性，具体见来源问题。 |
| 严重级别 | P0 |
| 证据位置 | 固定代码基线 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；来源 `TASK-PVAM-02`；检查项 `CHK-DATA-001、CHK-DATA-002、CHK-ARCH-003、CHK-BIZ-011、CHK-DATA-005` |

### 3.2 已确认代码事实

- `User/PEBonusService.py::_apply_truncate` 使用 `cp.round` 并通过 `/100.0` 产生奖金 float。
- `User/LeadershipBonusGPUService.py::_truncate_gpu` 将金额转为 `float64` 后使用 `nextafter/trunc`。
- `User/PlacementRecalculationService.py::_process_extract_batch` 从 Redis 调用 `float(...)`，空表构造 `float64` PV 列，回写包含 `int(round(float(...)))`。
- `User/SuperEliteBonusService.py:404`（基线稳定语句）以 `(orders['pv'] * 1000).round().astype('int64')` 生成 `pv_mills`，属于 R-003 登记的本地放大/round 链，必须改由公共金额边界与整数列合同承接。
- `Model/User/EliteBonusStats.py::estimated_bonus` 的 float 持久化字段由 WORK-PVAM-01 的 `estimated_bonus_cents` 兼容改造承接，本任务只负责入口和计算链不再继续制造 float。
- `GlobalRecalculationService._get_previous_period`、`PlacementIncrementalService._get_prev_period` 和 `PlacementRecalculationService._get_prev_period` 存在本地 period 算术/首期硬编码。
- `Order/OrderService.py` 是 Dask/BFS 演示，`MessageConsumer/UserConsumer.py` 是拓扑变更 consumer；二者都不是受控金额入口。

### 3.3 本任务目标

实现唯一 raw→normalized PV 入口和唯一 PeriodResolver；三条增量链只消费同一 strict units-int delta；清除生产可达金额链中的 float/round 中转。

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
| 1 | 用户变更消息 | `MessageConsumer/UserConsumer.py::consume_loop` | ChangeUserMsg | 直接 `actor.run_update` | 不是PV入口 |
| 2 | 订单演示 | `Order/OrderService.py::main` | OrderPayload示例 | 打印BFS结果 | 没有schema/幂等/period |
| 3 | 增量UserStats | `User/UserStatsService.py::update_elite_performance` | `bv` 后 `int(bv)` | 更新Redis | 原单位不可证明 |
| 4 | Placement全量 | `User/PlacementRecalculationService.py::_process_extract_batch` | Redis JSON | float转换/round回写 | 精度漂移 |
| 5 | Period | 三个本地 `_get_prev*` | 字符串/整数 | 本地减一或YYYYMM推导 | 绕过AR_PERIOD |

### 4.2 当前错误形成点

当前链路在上述入口缺少本任务目标合同，导致已确认问题在写入、计算、路由或发布边界形成并传播。修改必须落在表中稳定符号或明确标记为“新增”的边界；不得通过外围日志掩盖。

### 4.3 受影响消费者

| 消费者 | 依赖内容 | 预期影响 | 是否同步修改 | 对应步骤/测试 |
|---|---|---|---|---|
| UserStatsService | effective delta | 改为接收NormalizedPvEvent/strict units | 是 | STEP-02-04/TC-023 |
| PlacementIncrementalService | 同上 | 同一delta，不再转换 | 是 | STEP-02-04/TC-012/023 |
| EliteBonusService | 同上 | 同一delta，不再转换 | 是 | STEP-02-04/TC-015/023 |
| GlobalEliteBonusRecalculationService | `EliteBonusStats` 全量状态与奖金快照 | 与增量链共用 scaled threshold 和 `estimated_bonus_cents` | 是 | STEP-02-06/TC-007/008 |
| PEBonusService_Main / PEBonusServiceTest | PE 输出 schema 与 ConfigSnapshot | 改用显式快照、micro-units、ppm、cents | 是 | STEP-02-06/TC-007/008 |
| 批量全量服务 | DB金额/period snapshot | DB boundary转换一次 | 是 | STEP-02-03/05 |
| 奖金服务 | units/cents | 移除float中转 | 是 | STEP-02-06 |

## 5. 施工设计

### 5.1 采用方案

- 新增 `Common/PeriodResolver.py`，以可注入 repository 查询 AR_PERIOD；输出不可变 `PeriodSnapshot(period_num, calc_year, calc_month, first_period_num, previous_period_num, source_checksum)`。
- 新增 `Model/Order/NormalizedPvEvent.py`、`MessageConsumer/PvEventSchema.py`、`PvEventNormalizer.py`；raw 金额字段只接受 canonical JSON string。
- 事件身份不含 period；normalized event 固化 source identity、hash、business revision、previous revision、effective_pv_delta_units、version=2 和 resolved period snapshot。
- 退款用 `Order/RefundReversalLedger.py`（新增 Redis authority接口）保证同一原订单只产生一次整单负delta；批准时间按 GMT+8 映射。
- PE/SE/LB/Elite/Placement 的金额列改用 int64 units/cents；EAB 保留最终一次 HALF_UP，但入口统一使用公共units。

选择理由：

- 与有效SQL、已关闭DEC及来源TASK目标一致。
- 采用 additive-first、显式version/manifest/feature flag，支持独立合入和回滚。
- 将纯函数、I/O适配、业务计算、权威提交和证据采集分层，便于DEV替身与UAT真实验证分别取证。

### 5.2 被否决方案

| 方案 | 不采用原因 | 来源 |
|---|---|---|
| 入口 `int(bv)` | 会截断/误收原始单位 | R-003 |
| 内部再次乘1e6 | 双放大 | CHK-DATA-001 |
| YYYYMM猜period | PERIOD_NUM不是日历值 | DEC-006/CHK-DATA-005 |
| 到达时间定退款期 | 违反批准时间裁决 | DEC-006 |
| 部署OrderService demo | 没有生产合同 | CHK-ARCH-002 |

### 5.3 修改后调用链与数据契约

| 边界 | 输入 | 处理 | 输出 | 断言/错误行为 | 责任符号 |
|---|---|---|---|---|---|
| 施工入口 | 固定commit + 批准TASK + PV_NORMALIZER_V2 / PERIOD_RESOLVER_V2 | 先执行基线/前置检查 | 受控diff | 任一前置失败即BLOCK | `Common/PeriodResolver.py` |
| 核心处理 | strict version/type/period/run合同 | 按STEP顺序执行 | 可测试状态/事件/金额 | 非法类型、状态或proof fail-loud | 见CHG表 |
| 证据出口 | 命令、输入、输出、状态前后 | WORK-08 schema封装 | EV包+SHA-256 | 缺原始证据不得PASS | `uat/scripts/*` |

## 6. 文件与符号级变更清单

| 变更编号 | 文件 | 类/函数/字段/表 | 类型 | 修改前行为 | 要求的修改 | 修改后行为 | 禁止行为 |
|---|---|---|---|---|---|---|---|
| CHG-01 | `Common/PeriodResolver.py` | `PeriodRepository`、`PeriodResolver`、`PeriodSnapshot` | 新增 | 不存在 | 从AR_PERIOD解析current/first/previous/approval-time period | 唯一period合同 | 不得本地减一猜测 |
| CHG-02 | `Model/Order/NormalizedPvEvent.py` | 不可变事件模型 | 新增 | 不存在 | 定义identity/revision/delta/version/period | 三stage同一payload | 不得含float |
| CHG-03 | `MessageConsumer/PvEventSchema.py` / `MessageConsumer/PvEventNormalizer.py` | schema与normalize | 新增 | 无受控金额入口 | canonical string→units一次，生成hash/delta | 非法输入fail-loud | 不得trim/指数/number洗白 |
| CHG-04 | `Order/RefundReversalLedger.py` | 原订单冲销CAS | 新增 | 不存在 | 一次整单冲销、重复no-op、冲突阻断 | 无二次负delta | 不得决定人工override |
| CHG-05 | `User/UserStatsService.py` | `update_elite_performance` | 修改 | 接收bv并int转换 | 改接收strict units/int + identity/revision；保留兼容adapter为非生产 | 不再缩放 | 不得绕过guard |
| CHG-06 | `User/PlacementIncrementalService.py` | `update_placement_performance`、`_get_prev_period` | 修改 | bv int、本地period | 接收同一delta；注入PeriodSnapshot | 与UserStats同输入 | 不得period算术 |
| CHG-07 | `User/EliteBonusService.py` / `User/GlobalEliteBonusRecalculationService.py` | 增量入口、全量 `_evaluate_node`、bonus字段 | 修改 | 增量/全量可能使用不同阈值或 float/cents 字段 | strict units/version；全量与增量统一写 `estimated_bonus_cents` | 同一快照无 stale/missing cents | 不得改资格公式 |
| CHG-08 | `User/PlacementRecalculationService.py` | `_get_prev_period`、`_process_extract_batch`、`_calculate_placement_pv`、`_write_back_placement_matrix` | 修改 | float读取/float64/round | int64 units与PeriodSnapshot | 无精度漂移 | 不得改闭包腿逻辑 |
| CHG-09 | `User/PEBonusService.py` / `User/SuperEliteBonusService.py` / `User/LeadershipBonusGPUService.py` / `User/EliteAchievementBonusService.py` | 金额计算边界 | 修改/核验 | 多处float/本地scale | 接公共units/ppm/cents；整数运算；已符合合同的 EAB 仅核验不强制造成 diff | writer前明确cents/string | 不得改变SQL公式 |
| CHG-09A | `Common/PvAmount.py` | `assert_integer_amount_dtype`、公共 units→cents helper | 修改 | unsigned dtype 可在后续 cast 回绕；服务可能重复本地换算 | 公共入口只接受 signed integer dtype，并提供统一溢出/舍入合同 | 所有奖金链共用 fail-loud 边界 | 不得为单一奖项增加无依据业务上限 |
| CHG-09B | `User/PEBonusService_Main.py` / `User/Test/PEBonusServiceTest.py` / `User/Test/test_amount_dtype_migration.py` / `User/Test/test_pv_amount_common.py` | PE 人工入口、GPU UAT、公共/迁移回归 | 修改 | 旧调用方读取 `BONUS_PE`/`PE_RATE` 或无参构造配置消费者 | 显式注入 ConfigSnapshot，fixture/assert 使用 units/ppm/cents；公共守卫覆盖 unsigned | 受影响调用方与公共合同可回归 | GPU 未执行时不得宣称 UAT PASS |
| CHG-10 | `MessageConsumer/PvEventConsumer.py`或WORK-08A证明的现有部署入口 | 生产消费编排 | 条件新增/修改 | 当前仓库未证明订单PV入口 | normalize一次后分发三stage；先guard后权威提交 | 唯一可追踪入口 | 无callgraph不得创建第二consumer/topic/group |

> 实施期治理扩围依据：`Common/PvAmount.py` 是所有 Step 06 链共享的 signed-int64 信任边界；`GlobalEliteBonusRecalculationService.py` 与增量 Elite 共用 `EliteBonusStats` 和 snapshot，不能留下 legacy float/旧阈值；`PEBonusService_Main.py` 与 `PEBonusServiceTest.py` 已由检查方案 S-008 列为 PE 受影响调用方；`test_pv_amount_common.py` 必须随公共 API 合同同步。以上路径只修复已确认的单位、字段和调用合同，不新增业务公式。

### 6.1 固定基线锚点与生产入口门禁

| 文件与符号 | 基线事实 | 裁决 |
|---|---|---|
| `Order/OrderService.py::main` | 构造`OrderPayload`后调用Dask图演示并打印，非生产金额入口 | 不得直接改造成生产consumer |
| `MessageConsumer/UserConsumer.py::consume_loop` | 消费`change-user`并直接调用`graph_actor.run_update` | 这是拓扑入口候选，不得当作订单PV入口 |
| `User/PlacementRecalculationService.py::_extract_period_data/_process_extract_batch` | 使用`float64`、`float(...)`和`int(round(float(...)))`链 | 改为严格int64/version读取 |
| `User/GlobalRecalculationService.py::_get_previous_period` | 以1为首期并做period-1 | 改为注入的`PeriodResolver` |
| `User/PEBonusService.py::_apply_truncate` | `cp.round(...*100)`与`/100.0` | 改为units/ppm/cents整数公式 |

`MessageConsumer/PvEventConsumer.py`是上游TASK允许的候选新文件，不是当前基线事实。施工分支必须由WORK-08A部署证据选择：

1. 已存在唯一订单/退款consumer：修改该真实文件并保留原Topic/group；
2. 没有现存consumer且部署方案明确批准新入口：才新增`PvEventConsumer.py`；
3. 证据不完整：只完成schema、normalizer、repository和单测，生产接线步骤标记`BLOCKED_CALLGRAPH`。

### 6.2 Period与Normalized事件接口合同

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

@dataclass(frozen=True)
class PeriodSnapshot:
    period_num: int
    calc_year: int
    calc_month: int
    previous_period_num: int | None
    source_checksum: str

class PeriodRepository(Protocol):
    def resolve_current(self, period_num: int) -> PeriodSnapshot: ...
    def resolve_approved_at(self, approved_at: datetime) -> PeriodSnapshot: ...
```

Normalized delivery必须冻结：`source_system/source_event_id/payload_hash/business_revision/previous_business_revision/effective_pv_delta_units/amount_encoding_version=2/period_snapshot`。三个stage只能消费该delta，不得重新解析raw金额、再次乘scale或自行钳制。

### 6.3 金额改造公式纪律

- GPU/CPU中间列保持signed int64；join后立即断言dtype。
- 比例计算使用`trunc_div_zero(base_units * rate_ppm, 1_000_000)`；最终支付转换到cents时按对应SQL截断点执行。
- EAB保留批准的“中间不舍入、个人最终一次HALF_UP”；本任务只替换输入/输出单位适配，不改变模式。
- 任何需要猜测真实Topic、group、退款字段名或DB loader位置的施工都必须停止并登记`BLOCK-PVAM-02-CALLGRAPH`。

> **DEV 执行口径：** `05_CONTROL/check_baseline_preflight.sh` 与 `05_CONTROL/validate_work_dev.sh` 是唯一强制门禁。STEP 中列出的 `py_compile`、`compileall` 或 `pytest` 命令仅是附加局部检查，不得替代 parent-tree、scope、patch、tree-hash 与专属测试门禁。

## 7. 可执行施工步骤

### STEP-PVAM-02-01：实现PeriodResolver

- 目的：实现PeriodResolver，落实 `TASK-PVAM-02` 的已批准目标。
- 前置条件：WORK-01 DEV_VERIFIED
- 修改文件：`Common/PeriodResolver.py`
- 目标符号：resolver/repository
- 精确操作：
1. 按AR_PERIOD唯一性、MIN首期、真实前期行和GMT+8批准时间实现
2. repository接口不绑定具体ORM。
- 必须保持：不猜YYYYMM；不固定首期1
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Common/PeriodResolver.py`
- 本步单元验证：`TC-PVAM-02-01/02`
- 完成证据：`EV-PVAM-02-01`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：缺少AR_PERIOD字段合同则BLOCK

### STEP-PVAM-02-02：定义normalized事件与raw schema

- 目的：定义normalized事件与raw schema，落实 `TASK-PVAM-02` 的已批准目标。
- 前置条件：STEP-02-01
- 修改文件：`Model/Order/NormalizedPvEvent.py`、`MessageConsumer/PvEventSchema.py`
- 目标符号：数据类/校验
- 精确操作：
1. 严格字符串金额、identity/hash/revision
2. 模型冻结不可变。
- 必须保持：不接受JSON number/bool/null/指数
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Model/Order/NormalizedPvEvent.py MessageConsumer/PvEventSchema.py`
- 本步单元验证：`TC-PVAM-02-03`
- 完成证据：`EV-PVAM-02-02`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：外部真实schema未确认则只做adapter不接生产

### STEP-PVAM-02-03：实现Normalizer和退款ledger

- 目的：实现Normalizer和退款ledger，落实 `TASK-PVAM-02` 的已批准目标。
- 前置条件：STEP-02-02
- 修改文件：`MessageConsumer/PvEventNormalizer.py`、`Order/RefundReversalLedger.py`
- 目标符号：normalize/CAS
- 精确操作：
1. 只在raw或DB边界转换
2. 计算effective delta
3. 退款whole-order CAS。
- 必须保持：不得部分退款；不得自行定义迟到cutoff
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile MessageConsumer/PvEventNormalizer.py Order/RefundReversalLedger.py`
- 本步单元验证：`TC-PVAM-02-03~05`
- 完成证据：`EV-PVAM-02-03`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：原订单权威状态不可取时BLOCK

### STEP-PVAM-02-04：改造三stage增量入口

- 目的：改造三stage增量入口，落实 `TASK-PVAM-02` 的已批准目标。
- 前置条件：STEP-02-03
- 修改文件：UserStats/Placement/Elite服务
- 目标符号：三个入口函数
- 精确操作：
1. 接收同一normalized payload或严格字段
2. 校验version/revision/hash
3. 删除本地转换。
- 必须保持：保持业务传播/锁/幂等公式
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile User/UserStatsService.py User/PlacementIncrementalService.py User/EliteBonusService.py`
- 本步单元验证：`TC-PVAM-02-06`
- 完成证据：`EV-PVAM-02-04`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：三路hash不一致立即停工

### STEP-PVAM-02-05：替换本地period算术

- 目的：替换本地period算术，落实 `TASK-PVAM-02` 的已批准目标。
- 前置条件：STEP-02-01
- 修改文件：Global/Placement/奖金入口
- 目标符号：`_get_previous_period`/`_get_prev_period`调用点
- 精确操作：
1. 改为注入PeriodSnapshot
2. 旧方法只做deprecated adapter并禁止生产直连。
- 必须保持：保留Redis key格式
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile User/GlobalRecalculationService.py User/PlacementIncrementalService.py User/PlacementRecalculationService.py`
- 本步单元验证：`TC-PVAM-02-01/02`
- 完成证据：`EV-PVAM-02-05`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任一生产入口仍本地算period不合并

### STEP-PVAM-02-06：清除生产float金额链

- 目的：清除生产float金额链，落实 `TASK-PVAM-02` 的已批准目标。
- 前置条件：WORK-PVAM-01与WORK-PVAM-03均达到DEV_VERIFIED，且WORK-PVAM-03配置接口可用
- 修改文件：`Common/PvAmount.py`、PE/SE/LB/Elite/GlobalElite/EAB/Placement文件、`User/PEBonusService_Main.py`、`User/Test/PEBonusServiceTest.py`、`User/Test/test_amount_dtype_migration.py`、`User/Test/test_pv_amount_common.py`
- 目标符号：金额符号
- 精确操作：
1. 逐字段换成units/ppm/cents
2. merge/groupby前后dtype断言。
- 必须保持：保持各奖项SQL舍入点
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m compileall -q User Model Common MessageConsumer Order`
- 本步单元验证：`TC-PVAM-02-07/08`
- 完成证据：`EV-PVAM-02-06`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：SQL黄金样例差1分立即停止

### STEP-PVAM-02-07：建立生产入口与回归测试

- 目的：建立生产入口与回归测试，落实 `TASK-PVAM-02` 的已批准目标。
- 前置条件：STEP-02-02~06
- 修改文件：由WORK-08A选定的唯一真实部署入口；仅在“无现存入口且新consumer获批”分支新增`MessageConsumer/PvEventConsumer.py`，并同步测试/部署文件
- 目标符号：consumer/pytest
- 精确操作：
1. 接入实际配置通过依赖注入
2. 先guard、后normalize、后stage提交、最后ACK由事件任务处理。
- 必须保持：不得写真实地址/密钥
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m pytest -q User/Test/test_pv_event_normalizer.py User/Test/test_period_resolver.py User/Test/test_amount_dtype_migration.py`
- 本步单元验证：`TC-PVAM-02-01~08`
- 完成证据：`EV-PVAM-02-07`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：部署入口未获确认时保持BLOCKED

## 8. 数据迁移、兼容与重跑

### 8.1 数据变化

| 对象 | 旧格式/状态 | 新格式/状态 | 转换位置 | 版本识别 | 异常数据策略 |
|---|---|---|---|---|---|
| Kafka/MQ raw amount | 字符串/number混杂风险 | canonical string→units的NormalizedPvEvent | Normalizer唯一边界 | schema_version=2 | 非法输入DLQ/拒绝 |
| Redis金额状态 | 旧单位/float路径 | version=2 int64 units | 三stage/全量入口 | amount_encoding_version | legacy阻断/重建 |

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
| TC-PVAM-02-01 | 单元 | Period首期/前期 | fixture period 40(2025/12),41(2026/01) | first=40,current=41,previous=40 | STEP-02-01 | DEV | NOT_RUN |
| TC-PVAM-02-02 | 单元/集成 | 批准时间GMT+8 | `2026-01-31T16:00:00Z` | 转换为GMT+8的2026-02-01 00:00并匹配唯一二月period | STEP-02-01 | DEV+UAT | NOT_RUN |
| TC-PVAM-02-03 | 契约 | raw金额类型 | `"30.00"`与JSON number 30.0 | 字符串→30,000,000；number受控失败 | STEP-02-02/03 | DEV | NOT_RUN |
| TC-PVAM-02-04 | 幂等 | 整单退款重复 | 原订单100.25，两次退款请求 | 首个delta=-100,250,000；第二个duplicate/no-op，累计仍-100,250,000 | STEP-02-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-02-05 | 冲突 | 同identity不同hash | 同source id两payload | 阻断并记录冲突；无stage写入 | STEP-02-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-02-06 | 集成 | 三stage同delta | 同normalized event | UserStats/Placement/Elite输入hash、revision、delta完全相同 | STEP-02-04 | DEV+UAT | NOT_RUN |
| TC-PVAM-02-07 | 差分 | PE截断样例 | 1,500.99 BV、15% | 1,500,990,000 units；奖金22514 cents=225.14 | STEP-02-06 | DEV+UAT | NOT_RUN |
| TC-PVAM-02-08 | 静态/mutation | float清除 | AST与dtype mutation | 生产金额路径无float64/round洗白；mutation被捕获 | STEP-02-06/07 | DEV | NOT_RUN |

受控检查方案用例映射：`TC-001, TC-002, TC-006, TC-008, TC-010, TC-012, TC-017, TC-018, TC-019, TC-021, TC-022, TC-023, TC-024, TC-026, TC-030, TC-031, TC-032`。`TC-000` 为 RETIRED，不执行、不计完成率。

### 9.2 开发环境自动验证

```bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_SHA="3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2"
: "${WORK_COMMIT_SHA:?set the implementation commit for WORK-PVAM-02}"
: "${PARENT_COMMIT_SHA:?set the controlled parent commit; root WORK uses BASE_SHA}"
: "${PARENT_TREE_SHA:?set the tree of PARENT_COMMIT_SHA}"
: "${PARENT_PROVENANCE_JSON:?set schema-v2 parent provenance JSON}"
: "${APPROVED_COMMIT_REGISTRY_JSON:?set canonical WORK_APPROVED_COMMIT_REGISTRY.json}"
CONTROL_ROOT="${PVAM_CONTROL_ROOT:?point to the released 05_CONTROL directory}"

# Phase A：只验证固定基线和既有锚点，不要求 Common/Settlement/Ops 等未来目录存在。
bash "$CONTROL_ROOT/check_baseline_preflight.sh" \
  --repo "$REPO_ROOT" --base "$BASE_SHA" --work-id "WORK-PVAM-02"

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
  --work-id "WORK-PVAM-02" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --test-command-file "$CONTROL_ROOT/work-test-commands/WORK-PVAM-02.sh" \
  --out "evidence/WORK-PVAM-02/dev"
```

#### 9.2.1 必须落地的关键 `assert` 契约

以下断言骨架必须进入本任务列出的 pytest 文件；fixture 由测试文件实现，不得用复制生产公式的替身替代被测符号。

```python
import pytest
from datetime import datetime, timezone
from Common.PeriodResolver import PeriodResolver
from MessageConsumer.PvEventNormalizer import PvEventNormalizer


def test_period_and_refund_contract(period_repository, event_registry, refund_ledger) -> None:
    resolver = PeriodResolver(period_repository)
    snap = resolver.resolve_approval_time(datetime(2026, 1, 31, 16, 0, tzinfo=timezone.utc))
    assert snap.calc_year == 2026
    assert snap.calc_month == 2
    normalizer = PvEventNormalizer(resolver, event_registry, refund_ledger)
    first = normalizer.normalize_refund({"source_event_id": "R-1", "original_order_id": "O-1", "amount": "100.25", "approved_at": "2026-01-31T16:00:00Z"})
    second = normalizer.normalize_refund({"source_event_id": "R-2", "original_order_id": "O-1", "amount": "100.25", "approved_at": "2026-01-31T16:00:00Z"})
    assert first.effective_pv_delta_units == -100_250_000
    assert second.disposition == "DUPLICATE_NOOP"
    assert second.effective_pv_delta_units == 0
    with pytest.raises((TypeError, ValueError)):
        normalizer.normalize_order({"source_event_id": "O-X", "amount": 30.0})
```

通过标准：所有命令 exit code 0；pytest 无未解释 skip；证据schema校验通过。GPU/Dask/真实Redis/Kafka/MySQL未在DEV执行时必须标注 `NOT_RUN/PENDING_TEST_ENV`。

### 9.3 测试环境手工执行包

#### ENV-TC-PVAM-02-01：真实订单/退款/period与三stage

- 对应受控测试：`TC-001、TC-006、TC-008、TC-010、TC-022、TC-023`
- 环境版本：由 `uat/environment_manifest.yaml` 固定 Python/CUDA/RAPIDS/Dask/Redis/Kafka/DB/镜像/commit。
- 前置服务与数据：Kafka/Redis/Dask隔离环境；AR_PERIOD只读；专用topic/group/period
- 清理/隔离：必须使用专用 topic/group、Redis前缀、period/run_id；禁止复用生产数据。
- 执行命令：

```bash
RUN_ID=work02-$(date +%Y%m%d%H%M%S)
bash uat/scripts/run_work_uat.sh --work WORK-PVAM-02 --run-id "$RUN_ID" --tc TC-001,TC-006,TC-008,TC-010,TC-022,TC-023
```

- SQL/数据库证据命令（仅在专用 UAT schema 和 WORK-08 manifest 校验通过后执行；N/A 项只保留说明）：

```bash
test "${UAT_SCHEMA_ISOLATED:?must equal 1}" = "1"
mysql --defaults-extra-file="${MYSQL_CNF:?}" --batch --raw <<SQL
SELECT PERIOD_NUM, CALC_MONTH, IS_PERFING, IS_PERFED, IS_CALCING, IS_CALCULATED
  FROM AR_PERIOD
 ORDER BY PERIOD_NUM;
CALL CALC_BE_PE(${PERIOD_NUM:?}, ${CALC_MONTH:?});
SELECT PERIOD_NUM, CALC_MONTH, USER_ID, GPV_REAL, PE_RATE, BONUS_PE, IS_ACTIVE
  FROM AR_CALC_BONUS_PE
 WHERE PERIOD_NUM = ${PERIOD_NUM}
 ORDER BY USER_ID;
SQL
```

- 执行步骤：
1. 导入固定AR_PERIOD和原订单fixture
2. 发布正常订单、重复订单、首次/第二次退款和冲突事件
3. 导出normalized、三stage输入及Redis前后状态
4. 运行SQL-Python金额差分
- 精确预期：
- 同一事件三stage delta/hash一致
- 整单退款只冲销一次且归期由批准时间决定
- 所有金额列int64；差分为0或已批准标签
- 必须回传：完整命令、exit code、stdout/stderr、JUnit/JSON、输入fixture SHA-256、代码commit、镜像、环境版本、执行起止时间、Redis/DB/Kafka/Dask前后证据。
- 失败停止与清理：停止专用consumer/job；保留PEL/状态和证据；禁止在未分析前清理失败现场；按第11节回滚。

### 9.4 SQL 对账样例

| 样例 | SQL输入/来源 | SQL预期 | Python预期 | 比较口径 | 允许差异 |
|---|---|---|---|---|---|
| PE截断 | `GPV_REAL+GPV_UNREAL=1500.99`, `proEliteRate=15` | `TRUNCATE(1500.99*0.15,2)=225.14` | `22514 cents` | SQL两位向零截断 | 0 cents |
| 退款 | 原订单100.25 | SQL/approved contract整单反向 | `-100_250_000 units`一次 | signed units | 0 |

## 10. 验收标准映射

| 验收编号 | 来源TASK验收项 | 实现步骤 | 测试用例 | 所需证据 | 环境 | 通过条件 |
|---|---|---|---|---|---|---|
| AC-01 | 全仓只有两个批准的放大调用点；生产内部无第三处 `*1_000_000` | STEP-PVAM-02-02/03/04/06/07 | TC-001、TC-002、TC-023 | EV-PVAM-02-01 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-02 | JSON number/float/bool/null/指数/NaN/Infinity 全部拒绝并进入明确错误处置 | STEP-PVAM-02-02/03/07 | TC-001 | EV-PVAM-02-02 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-03 | 同一 normalized event 三路收到相同 int delta、version、revision 和 identity | STEP-PVAM-02-02/03/04/07 | TC-023、TC-026 | EV-PVAM-02-03 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-04 | PE/SE/Elite/LB/Placement 生产金额列无 float dtype；EAB scale 不与公共 units 混用 | STEP-PVAM-02-04/06/07 | TC-002、TC-012、TC-017、TC-018、TC-021 | EV-PVAM-02-04 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-05 | 最终奖金不以 float 输出，外部只输出两位 Decimal string 或 integer cents | STEP-PVAM-02-06/07 | TC-008、TC-017、TC-018、TC-019、TC-021 | EV-PVAM-02-05 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-06 | PeriodResolver 不接受 YYYYMM 推导；首期来自 MIN(AR_PERIOD) | STEP-PVAM-02-01/05 | TC-006 | EV-PVAM-02-06 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-07 | current/previous period 缺失、多行或不连续时 fail-loud | STEP-PVAM-02-01/05 | TC-006 | EV-PVAM-02-07 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-08 | 退款批准时间经 GMT+8 在月界前后映射正确；到达时间不影响归期 | STEP-PVAM-02-01/03 | TC-006、TC-022 | EV-PVAM-02-08 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-09 | 整单退款重复和第二次冲销不产生第二个负 delta | STEP-PVAM-02-03/07 | TC-010、TC-022 | EV-PVAM-02-09 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-10 | SQL-Python 边界、极值、负值、跨分区差分符合 Legacy/Corrected 标签 | STEP-PVAM-02-06/07 | TC-008、TC-012、TC-017、TC-018、TC-019、TC-021 | EV-PVAM-02-10 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-11 | demo/图 consumer 未被冒充金额入口；真实启动/部署接线有证据 | STEP-PVAM-02-07 | TC-024、TC-030、TC-032 | EV-PVAM-02-11 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-12 | 本任务 feature flag 关闭后，不影响 TASK-01 模型/API | STEP-PVAM-02-07 | TC-031 | EV-PVAM-02-12 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |

没有 STEP、TC 或 EV 映射的AC不得标记完成。任何含UAT的AC在未回传真实环境证据时只能为 `PENDING_TEST_ENV/BLOCKED`。

## 11. 风险、停工与回滚

### 11.1 风险清单

| 风险 | 触发条件 | 影响 | 预防措施 | 监测/证据 | 处置 |
|---|---|---|---|---|---|
| 真实入口不明 | 只有demo/拓扑consumer | 新代码不可达 | WORK-08 call graph与部署manifest | 入口trace | BLOCK并回上游 |
| period字段合同缺失 | 无批准schema | 错误归期 | repository adapter+manifest | resolver查询证据 | BLOCK |
| 双写期间单位混用 | 旧/新consumer并行 | 金额放大 | event version+feature flag | 三stage hash | 停止v2写 |

### 11.2 本任务强制停工条件

- HEAD、SQL blob、模型schema或上游TASK与受控基线不一致。
- 实施必须改变未批准的业务规则、精度、资格、分母、Country或发布职责才能继续。
- 需要修改排除文件/模块或扩大异常白名单才能通过测试。
- 关键mutation存活、SQL黄金样例出现未批准差异、幂等/原子/回滚断言失败。
- UAT权限、schema、数据或隔离条件不足；此时保持 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV`。

### 11.3 部署面与数据面回滚门禁

**当前可执行性：`BLOCKED_EXTERNAL_EVIDENCE`。** 当前材料没有给出真实部署系统、workload/release、镜像、配置对象和健康检查命令，因此不得以本地`export`或通用`git revert`冒充部署回滚。

部署前必须提供并签署`evidence/WORK-PVAM-02/rollback/ROLLBACK-MANIFEST-PVAM-v1.json`，至少包含：

- `deployment_system`、`environment`、`workload_id`、`release_before/after`、`image_before/after`；
- 精确的停止、回滚、恢复、健康检查和重新放量命令；
- Redis/Stream/ledger/run/manifest的备份或快照位置及SHA-256；
- 执行人、复核人、批准时间、允许的数据恢复范围；
- 命令dry-run/隔离演练的退出码和原始日志。

本任务数据面处置：停止订单/退款consumer并完成in-flight drain；保存normalized event与reversal ledger；恢复旧镜像后按event_id/revision受控重放，禁止重复冲销。

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
| EV-PVAM-02-01 | AC-01验收证据：全仓只有两个批准的放大调用点；生产内部无第三处 `*1_000_000` | STEP-PVAM-02-02/03/04/06/07 | evidence/WORK-PVAM-02/attempt-*/ac/AC-01/ | 待指派QA | PENDING |
| EV-PVAM-02-02 | AC-02验收证据：JSON number/float/bool/null/指数/NaN/Infinity 全部拒绝并进入明确错误处置 | STEP-PVAM-02-02/03/07 | evidence/WORK-PVAM-02/attempt-*/ac/AC-02/ | 待指派QA | PENDING |
| EV-PVAM-02-03 | AC-03验收证据：同一 normalized event 三路收到相同 int delta、version、revision 和 identity | STEP-PVAM-02-02/03/04/07 | evidence/WORK-PVAM-02/attempt-*/ac/AC-03/ | 待指派QA | PENDING |
| EV-PVAM-02-04 | AC-04验收证据：PE/SE/Elite/LB/Placement 生产金额列无 float dtype；EAB scale 不与公共 units 混用 | STEP-PVAM-02-04/06/07 | evidence/WORK-PVAM-02/attempt-*/ac/AC-04/ | 待指派QA | PENDING |
| EV-PVAM-02-05 | AC-05验收证据：最终奖金不以 float 输出，外部只输出两位 Decimal string 或 integer cents | STEP-PVAM-02-06/07 | evidence/WORK-PVAM-02/attempt-*/ac/AC-05/ | 待指派QA | PENDING |
| EV-PVAM-02-06 | AC-06验收证据：PeriodResolver 不接受 YYYYMM 推导；首期来自 MIN(AR_PERIOD) | STEP-PVAM-02-01/05 | evidence/WORK-PVAM-02/attempt-*/ac/AC-06/ | 待指派QA | PENDING |
| EV-PVAM-02-07 | AC-07验收证据：current/previous period 缺失、多行或不连续时 fail-loud | STEP-PVAM-02-01/05 | evidence/WORK-PVAM-02/attempt-*/ac/AC-07/ | 待指派QA | PENDING |
| EV-PVAM-02-08 | AC-08验收证据：退款批准时间经 GMT+8 在月界前后映射正确；到达时间不影响归期 | STEP-PVAM-02-01/03 | evidence/WORK-PVAM-02/attempt-*/ac/AC-08/ | 待指派QA | PENDING |
| EV-PVAM-02-09 | AC-09验收证据：整单退款重复和第二次冲销不产生第二个负 delta | STEP-PVAM-02-03/07 | evidence/WORK-PVAM-02/attempt-*/ac/AC-09/ | 待指派QA | PENDING |
| EV-PVAM-02-10 | AC-10验收证据：SQL-Python 边界、极值、负值、跨分区差分符合 Legacy/Corrected 标签 | STEP-PVAM-02-06/07 | evidence/WORK-PVAM-02/attempt-*/ac/AC-10/ | 待指派QA | PENDING |
| EV-PVAM-02-11 | AC-11验收证据：demo/图 consumer 未被冒充金额入口；真实启动/部署接线有证据 | STEP-PVAM-02-07 | evidence/WORK-PVAM-02/attempt-*/ac/AC-11/ | 待指派QA | PENDING |
| EV-PVAM-02-12 | AC-12验收证据：本任务 feature flag 关闭后，不影响 TASK-01 模型/API | STEP-PVAM-02-07 | evidence/WORK-PVAM-02/attempt-*/ac/AC-12/ | 待指派QA | PENDING |
| EV-PVAM-02-P01 | PeriodResolver与测试 | 对应STEP/TC | evidence/WORK-PVAM-02/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-02-P02 | normalized schema/normalizer/退款ledger | 对应STEP/TC | evidence/WORK-PVAM-02/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-02-P03 | 三stage入口与float清理diff | 对应STEP/TC | evidence/WORK-PVAM-02/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-02-P04 | DEV测试/mutation报告 | 对应STEP/TC | evidence/WORK-PVAM-02/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-02-P05 | UAT订单退款/SQL差分证据 | 对应STEP/TC | evidence/WORK-PVAM-02/attempt-*/package/ | 待指派QA | PENDING |

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
  --work-id "WORK-PVAM-02" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --out "evidence/WORK-PVAM-02/patch"
```

门禁必须证明：

1. `BASE_SHA` 是 `WORK_COMMIT_SHA` 的祖先；
2. 全部新增、修改、删除和 rename 的旧/新路径均落在 `WORK-PVAM-02` 批准 allowlist；
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
| STEP-PVAM-02-01 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-02-02 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-02-03 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-02-04 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-02-05 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-02-06 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-02-07 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |

### 13.2 实际验证

| 测试 | 环境 | 命令/版本 | 结果 | 证据 | 执行时间 |
|---|---|---|---|---|---|
| TC-PVAM-02-01 | DEV | 待执行 | NOT_RUN | EV-PVAM-02-* | 待执行 |
| TC-PVAM-02-02 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-02-* | 待执行 |
| TC-PVAM-02-03 | DEV | 待执行 | NOT_RUN | EV-PVAM-02-* | 待执行 |
| TC-PVAM-02-04 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-02-* | 待执行 |
| TC-PVAM-02-05 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-02-* | 待执行 |
| TC-PVAM-02-06 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-02-* | 待执行 |
| TC-PVAM-02-07 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-02-* | 待执行 |
| TC-PVAM-02-08 | DEV | 待执行 | NOT_RUN | EV-PVAM-02-* | 待执行 |

### 13.3 未完成项

| 项目 | 原因 | 风险 | 后续动作 | 责任人 | 截止时间 |
|---|---|---|---|---|---|
| UAT/外部材料 | 当前计划阶段未执行 | 不能关闭P0/P1 | 由WORK-08准入后执行 | 待指派 | 待批准 |

## 14. 偏离、发现项与上游回流

| 编号 | 类型 | 发现事实 | 是否影响业务/范围 | 临时动作 | 需要更新 | 最终裁决 |
|---|---|---|---|---|---|---|
| `DEV-PVAM-02-001` | `预留` | 待执行 | 待判断 | 停工/隔离 | WORK/TASK/DEC/REVIEW | 待裁决 |

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
| v1.0 | 2026-08-04 | 初版施工任务书 | `TASK-PVAM-02` + `PLAN-PVAM-v1.15` + 固定代码基线 | AI Agent（编制） | DRAFT |
| v1.1 | 2026-08-05 | 依据二轮核验报告完成定点修订并补齐治理追溯 | F-A/F-B/F-H/F-I/F-J/F-K/F-F/F-E/F-L/F-M/F-N 中适用项 | AI Agent（编制） | DRAFT |
| v1.2 | 2026-08-05 | 闭合 G-1：统一 `RecalcProcessResult` 类名并补齐 `should_ack`；历史版本曾调整施工套件审批状态，不改变 CHK/DEC/TASK/WORK 范围 | 历史会话声明（未形成可独立验证组织授权，现由 v1.3 取代） | AI Agent（编制） | SUPERSEDED |
| v1.3 | 2026-08-05 | 第四轮关闭 F3-01～F3-10：治理回退 DRAFT、Traceability v3、patch/DEV 双阶段、状态枚举及设计边界 | 三轮审查报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r6 | 2026-08-06 | 五轮 F5 定点修订：规范 v3 追溯、parent provenance/DEV CLI、控制状态字段及单一事实源 | 五轮审计报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r7 | 2026-08-06 | 六轮 S6：信任 registry 初版、归档哈希、临时目录与 Decimal finite 防护 | 六轮终局审计报告 | AI Agent（编制） | DRAFT |
| v1.3-r8 | 2026-08-06 | 七轮 B7：registry 发布信任根、四工件摘要、AC 来源保真及当前轮次引用 | 七轮终局审计报告 + B7 处置 | AI Agent（编制） | DRAFT |
| v1.3-r11 | 2026-08-12 | 实施期扩围公共 signed-int64 守卫、全量 Elite 共享状态与 S-008 PE 调用方，并同步测试范围 | WORK-PVAM-02 终审发现与用户批准的治理依赖修订 | AI Agent（编制） | DRAFT |

<!-- END WORK-PVAM-02_订单退款金额边界与期间解析.md -->

---

<!-- BEGIN WORK-PVAM-03_配置解析ppm与硬编码清理.md -->

# WORK-PVAM-03 配置解析、ppm 与硬编码清理施工任务书

> 文档定位：来源于待组织批准的 `TASK-PVAM-03`，在取得组织授权后转化为可执行施工说明。本文件不重新决定业务规则；实际结果只能写入执行记录与验证交付报告。

## 0. 填写与执行规则

1. 上游修改任务与本 v1.3 施工套件当前均为 `DRAFT`；没有组织授权前，本任务保持 `BLOCKED`，不得启动代码施工或部署。
2. 只实施 `R-004` 中已 `ACCEPTED` 或由来源 TASK 明确批准的条件代码事项。任何 `REJECTED / NEEDS_DECISION / DEFERRED / 未获 TASK 授权的 UAT_VERIFY` 只允许登记、验证或阻断，不得扩展代码范围。
3. 基线必须精确等于 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；发现漂移立即登记 `BLOCK-PVAM-03-BASELINE`。
4. 所有新文件/符号已在变更表标为“新增”；其余锚点均来自固定基线。
5. DEV替身不能冒充真实Kafka/Redis/Dask/GPU/MySQL UAT验证。

## 1. 文档信息与追溯关系

| 字段 | 内容 |
|---|---|
| 施工任务编号 | `WORK-PVAM-03` |
| 施工任务名称 | 配置解析、ppm 与硬编码清理 |
| 所属施工总方案 | `WORK-PLAN-PVAM_v1.3` |
| 来源修改任务 | `TASK-PVAM-03@MODPLAN-PVAM_v1.2`（authorization=PENDING_ORGANIZATIONAL_APPROVAL） |
| 来源问题 | `R-004` |
| 复核闭环追踪号 | `REM-004 / W-004 / V-004` |
| 来源检查项 | `CHK-DATA-004、CHK-BIZ-007、CHK-BIZ-008` |
| 关联决策 | `DEC-001、DEC-002、DEC-003、DEC-009、DEC-014` |
| 代码基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| SQL基线 | `sql_uat/*@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，仅有效SQL |
| 文档版本 | `v1.3` |
| 负责人 | `待指派 / 实施工程师` |
| 复核人 | `待指派 / 架构与QA` |
| 当前状态 | `BLOCKED` |
| 文档治理状态 | `DRAFT`（`PENDING_ORGANIZATIONAL_APPROVAL`） |
| 前置任务 | WORK-PVAM-01 DEV_VERIFIED |
| 功能开关 | `BONUS_CONFIG_SNAPSHOT_V2` |

### 1.1 一对一追溯摘要

```text
CHK-DATA-004、CHK-BIZ-007、CHK-BIZ-008
  └─ R-004
       └─ DEC-001、DEC-002、DEC-003、DEC-009、DEC-014
            └─ TASK-PVAM-03 (DRAFT / PENDING_ORGANIZATIONAL_APPROVAL)
                 └─ WORK-PVAM-03
                      ├─ STEP-PVAM-03-01 / STEP-PVAM-03-02 / STEP-PVAM-03-03 / STEP-PVAM-03-04 / STEP-PVAM-03-05 / STEP-PVAM-03-06
                      ├─ TC-PVAM-03-01 / TC-PVAM-03-02 / TC-PVAM-03-03 / TC-PVAM-03-04 / TC-PVAM-03-05 / TC-PVAM-03-06 / TC-PVAM-03-07
                      └─ EV-PVAM-03-01...
```

## 2. 施工任务生成依据

### 2.1 上游输入

| 输入 | 编号/版本 | 本任务使用的结论 | 状态 |
|---|---|---|---|
| 复核报告 | `Redemption_PV_Amount_Migration_d74_复核报告_v1.5` | R-004 的代码事实与严重级别 | CONFIRMED |
| 修改任务书 | `TASK-PVAM-03` | 采用方案、范围、排除项、AC | DRAFT（待组织授权） |
| 检查方案 | `PLAN-PVAM-v1.15` | CHK-DATA-004、CHK-BIZ-007、CHK-BIZ-008 | CONTROLLED |
| 正式决策 | DEC-001、DEC-002、DEC-003、DEC-009、DEC-014 | 只执行已关闭裁决；开放项阻断 | CLOSED / 按上游登记 |
| 代码/SQL快照 | 3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2 | 唯一施工对象 | FROZEN |
| 施工模板 | 总方案模板/专项模板 | 章节、状态、证据纪律 | CONTROLLED |

### 2.2 开工条件

- [ ] 当前 HEAD 精确为 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，工作树无未登记变更。
- [ ] `TASK-PVAM-03` 的人工批准记录已归档；本 `WORK` 已由施工负责人和复核人签署。
- [ ] 前置关系满足：WORK-PVAM-01 DEV_VERIFIED。
- [ ] 本任务涉及的接口、单位、精度、兼容和回滚边界已由上游任务固定。
- [ ] DEV测试依赖已安装；UAT项具备WORK-08生成的环境/数据/schema manifest。
- [ ] 功能开关默认关闭，回滚路径已演练。

未满足任一关键项时，本任务状态为 `BLOCKED`；不得用假设替代。

## 3. 问题事实与施工目标

### 3.1 已确认问题

| 项目 | 内容 |
|---|---|
| 预期行为 | 建立不可变、可审计的 ConfigSnapshot 和逐奖项 ConfigRequirementMatrix；费率只以 signed ppm 进入计算，移除生产硬编码默认并保持各奖项独立的 raw/TYPE/requiredness 规则。 |
| 当前行为 | `PEBonusService.__init__` 固定 `_pro_elite_rate_ppm = 150000`。；`EliteBonusService.__init__` 在未提供 loader 时告警后使用 `Decimal('0.15')`。；`SuperEliteBonusService._parse_se_rate` 对 name/type 执行 strip/lower，要求 rate>0；这与 signed ppm、exact raw SE 合同不一致。；当前各奖项 requiredness、0/负值/重复/非法值处理不集中，run 也没有统一配置 checksum。 |
| 差异 | 当前实现缺少本任务批准的唯一合同、门禁或原子边界。 |
| 影响 | 金额/PV单位、奖金、并发一致性、发布或可恢复性，具体见来源问题。 |
| 严重级别 | P0 |
| 证据位置 | 固定代码基线 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；来源 `TASK-PVAM-03`；检查项 `CHK-DATA-004、CHK-BIZ-007、CHK-BIZ-008` |

### 3.2 已确认代码事实

- `PEBonusService.__init__` 固定 `_pro_elite_rate_ppm = 150000`。
- `EliteBonusService.__init__` 在未提供 loader 时告警后使用 `Decimal('0.15')`。
- `SuperEliteBonusService._parse_se_rate` 对 name/type 执行 strip/lower，要求 rate>0；这与 signed ppm、exact raw SE 合同不一致。
- 当前各奖项 requiredness、0/负值/重复/非法值处理不集中，run 也没有统一配置 checksum。

### 3.3 本任务目标

建立不可变、可审计的 ConfigSnapshot 和逐奖项 ConfigRequirementMatrix；费率只以 signed ppm 进入计算，移除生产硬编码默认并保持各奖项独立的 raw/TYPE/requiredness 规则。

### 3.4 完成定义

- [ ] 所有 CHG 和 STEP 在批准范围内完成，未触碰排除项。
- [ ] DEV 静态、单元、契约和 mutation 测试全部通过并生成原始证据。
- [ ] UAT 所属用例已执行并回传，或保持 `PENDING_TEST_ENV/BLOCKED`，绝不预标通过。
- [ ] 受影响调用者回归通过，重复执行和失败恢复满足本任务断言。
- [ ] 回滚开关与 `git revert` 路径均可用，回滚后关键读写验证通过。

本任务不存在附件二提出的新增`BLOCK-PVAM-03`；逐键missing/duplicate/exact规则已由上游TASK固定。

### 3.5 明确非目标

- 不修改来源 TASK 未批准的业务比例、资格、分母、Country、period、舍入或发布职责。
- 不使用 `_bak`、`_final`、copy、废弃SQL或 `GraphService.run_bfs` 作为施工依据。
- 不把 UAT_VERIFY 风险转化为代码修复；只做验证、证据或阻断。
- 不建设 PB/SFB/GPB/CRB 算法或 Team Bonus units-int 生产服务。

## 4. 修改前调用链与数据流

### 4.1 入口与调用链

| 顺序 | 调用方/入口 | 文件与符号 | 输入契约 | 输出/副作用 | 错误形成点 |
|---|---|---|---|---|---|
| 1 | PE初始化 | `User/PEBonusService.py::PEBonusService.__init__` | 无配置参数 | 固定150000ppm | 绕过AR_CONFIG |
| 2 | Elite初始化 | `User/EliteBonusService.py::EliteBonusService.__init__` | 可选loader | 缺失时0.15 | 假成功 |
| 3 | SE配置 | `User/SuperEliteBonusService.py::_parse_se_rate` | DataFrame config | strip/lower、rate<=0阻断 | 误改raw/负值 |
| 4 | TB oracle | `User/team_bonus_tb.py` 配置函数 | AR_CONFIG fixture | 按SQL模拟 | 必须保持oracle |

### 4.2 当前错误形成点

当前链路在上述入口缺少本任务目标合同，导致已确认问题在写入、计算、路由或发布边界形成并传播。修改必须落在表中稳定符号或明确标记为“新增”的边界；不得通过外围日志掩盖。

### 4.3 受影响消费者

| 消费者 | 依赖内容 | 预期影响 | 是否同步修改 | 对应步骤/测试 |
|---|---|---|---|---|
| PE | proEliteRate | 从snapshot读signed ppm | 是 | STEP-03-03/TC-004 |
| Elite | eliteRate | 删除0.15 fallback | 是 | STEP-03-03/TC-014 |
| SE | superEliteRate/Country* | exact raw TYPE与signed ppm | 是 | STEP-03-04/TC-005/018 |
| EAB/LB | 各自配置 | 使用同一snapshot但独立矩阵 | 是 | STEP-03-04/TC-019/021 |
| TB oracle | teamBisectRate/TouchRate/Capping | 保持SQL忠实，仅接snapshot fixture | 测试调整 | TC-004/013 |

## 5. 施工设计

### 5.1 采用方案

- 新增 `Common/BonusConfig.py`，定义 `ConfigRequirement`、`ConfigSnapshot`、`ConfigSnapshotLoader` 和 `parse_signed_percent_to_ppm`。
- snapshot 保留 raw 行、canonical 值、row count、source/version/checksum；run 启动后冻结。
- 矩阵逐键声明 missing/zero/negative/duplicate/invalid/type/country 行为，不将 SE exact raw 规则套给 EAB/LB。
- 负费率允许为 signed ppm；最大值/专项上限由上游系统保证，本仓不二次决定。
- DEC-004 2B 写入侧不在本任务建设，配置 snapshot 可由UAT受控fixture或现有只读加载适配器提供。

选择理由：

- 与有效SQL、已关闭DEC及来源TASK目标一致。
- 采用 additive-first、显式version/manifest/feature flag，支持独立合入和回滚。
- 将纯函数、I/O适配、业务计算、权威提交和证据采集分层，便于DEV替身与UAT真实验证分别取证。

### 5.2 被否决方案

| 方案 | 不采用原因 | 来源 |
|---|---|---|
| 硬编码15%兜底 | 缺配置应fail-loud或按矩阵为0 | R-004 |
| 统一strip/lower所有配置 | 改变SE exact raw | DEC-003 |
| rate<=0一律阻断 | 负费率已允许，0按键矩阵 | DEC-001/002 |
| 重写TB生产服务 | 超出范围 | EX-005 |

### 5.3 修改后调用链与数据契约

| 边界 | 输入 | 处理 | 输出 | 断言/错误行为 | 责任符号 |
|---|---|---|---|---|---|
| 施工入口 | 固定commit + 批准TASK + BONUS_CONFIG_SNAPSHOT_V2 | 先执行基线/前置检查 | 受控diff | 任一前置失败即BLOCK | `Common/BonusConfig.py`、`Model/Config/ConfigSnapshot.py` |
| 核心处理 | strict version/type/period/run合同 | 按STEP顺序执行 | 可测试状态/事件/金额 | 非法类型、状态或proof fail-loud | 见CHG表 |
| 证据出口 | 命令、输入、输出、状态前后 | WORK-08 schema封装 | EV包+SHA-256 | 缺原始证据不得PASS | `uat/scripts/*` |

## 6. 文件与符号级变更清单

| 变更编号 | 文件 | 类/函数/字段/表 | 类型 | 修改前行为 | 要求的修改 | 修改后行为 | 禁止行为 |
|---|---|---|---|---|---|---|---|
| CHG-01 | `Common/BonusConfig.py` | `ConfigRequirement`/`ConfigSnapshot`/parser | 新增 | 不存在 | 建立矩阵、raw/canonical/checksum和signed ppm | 运行期唯一配置对象 | 不得包含业务默认 |
| CHG-02 | `Model/Config/ConfigSnapshot.py` | 可序列化manifest模型 | 新增 | 不存在 | 记录period/run/source/raw checksum | 证据可追溯 | 不得含密钥 |
| CHG-03 | `User/PEBonusService.py` | `__init__`、`execute_batch` | 修改 | 固定150000 | 强制注入snapshot/ppm | 无硬编码 | 不得改PE base公式 |
| CHG-04 | `User/EliteBonusService.py` | `__init__` | 修改 | loader缺失用0.15 | 生产模式缺snapshot fail-loud；测试显式fixture | 无占位默认 | 不得改资格 |
| CHG-05 | `User/GlobalEliteBonusRecalculationService.py` | `__init__` | 修改 | 默认elite_rate=0.15 | 改显式ConfigSnapshot/ppm | 全量增量同run | 不得保留生产默认 |
| CHG-06 | `User/SuperEliteBonusService.py` | `_parse_se_rate`、`_parse_country_mapping` | 修改 | strip/lower与正值限制 | 按SE矩阵exact raw、signed ppm | 非法与豁免分开 | 不得把EAB/LB规则套入 |
| CHG-07 | `User/EliteAchievementBonusService.py` / `User/LeadershipBonusGPUService.py` | 配置读取接口 | 修改 | 各自解析 | 接snapshot与公共ppm，保留专项规则 | 同run checksum | 不得改业务公式 |
| CHG-08 | `User/team_bonus_tb.py` 测试适配 | oracle config输入 | 修改 | DataFrame直接读 | 接受受控snapshot导出的等价fixture | SQL parity不变 | 不得生产接线 |
| CHG-09 | `User/Test/test_bonus_config.py` | pytest | 新增 | 不存在 | 矩阵、checksum、freeze、mutation | 配置合同可测 | 不得依赖真实DB |

### 6.1 固定基线锚点复验

| 文件与符号 | 基线事实 | 施工动作 |
|---|---|---|
| `User/PEBonusService.py::PEBonusService.__init__` | `_pro_elite_rate_ppm=150000` | 改为必传冻结ConfigSnapshot |
| `User/EliteBonusService.py::EliteBonusService.__init__` | loader缺失时回退`Decimal('0.15')` | 生产路径缺配置必须fail-loud |
| `User/GlobalEliteBonusRecalculationService.py::__init__` | `elite_rate: float=0.15` | 改为signed ppm或受控Decimal/string，不接受float默认 |
| `User/SuperEliteBonusService.py::_parse_se_rate` | strip/lower并拒绝`rate<=0` | 按逐键矩阵解析；负值不因负号被拒绝 |
| `User/SuperEliteBonusService.py::_normalize_id_series` | strip/upper/删除`.0` | exact-raw字段先校验原值，禁止洗白 |
| `User/team_bonus_tb.py` | SQL faithful oracle | 只补配置矩阵测试，不接入生产 |

### 6.2 ConfigRequirementMatrix合同

```python
from dataclasses import dataclass
from enum import Enum

class MissingPolicy(str, Enum):
    ZERO = "ZERO"
    ERROR = "ERROR"

@dataclass(frozen=True)
class ConfigRequirement:
    config_name: str
    type_exact: str | None
    missing_policy: MissingPolicy
    duplicate_is_error: bool
    exact_raw_name: bool = False
    exact_raw_type: bool = False
    allow_negative: bool = True
```

`missing_policy`不得由施工人员重新决定，必须来自TASK-03已批准的逐奖项矩阵和有效SQL：SQL/DEC定义缺失为0的键使用ZERO；正式required键使用ERROR；重复、TYPE、Country规则按奖项独立处理。附件二提出的新`BLOCK-PVAM-03`不成立，本终稿不新增DEC。

### 6.3 费率转换约束

- raw只允许Decimal或canonical decimal string；float、NaN、Infinity和科学计数法阻断。
- 百分数转ppm必须证明乘法结果为整数；显式0保留为0，负值保留符号。
- 同一run只加载一次ConfigSnapshot，并记录raw rows、source、version、checksum和canonical checksum。
- 不因上游负责的最大值/Country空值/EAB或LB非bonus TYPE而新增二次业务阻断；SE exact TYPE规则仍独立执行。

> **DEV 执行口径：** `05_CONTROL/check_baseline_preflight.sh` 与 `05_CONTROL/validate_work_dev.sh` 是唯一强制门禁。STEP 中列出的 `py_compile`、`compileall` 或 `pytest` 命令仅是附加局部检查，不得替代 parent-tree、scope、patch、tree-hash 与专属测试门禁。

## 7. 可执行施工步骤

### STEP-PVAM-03-01：建立配置矩阵与snapshot

- 目的：建立配置矩阵与snapshot，落实 `TASK-PVAM-03` 的已批准目标。
- 前置条件：WORK-01 DEV_VERIFIED
- 修改文件：`Common/BonusConfig.py`、`Model/Config/ConfigSnapshot.py`
- 目标符号：新模块
- 精确操作：
1. 编码每个配置键的requiredness/0/负值/重复/exact规则
2. 计算稳定SHA-256。
- 必须保持：不读取MySQL；不内置比例
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Common/BonusConfig.py Model/Config/ConfigSnapshot.py`
- 本步单元验证：`TC-PVAM-03-01/02`
- 完成证据：`EV-PVAM-03-01`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：矩阵与DEC冲突时BLOCK

### STEP-PVAM-03-02：实现signed ppm解析

- 目的：实现signed ppm解析，落实 `TASK-PVAM-03` 的已批准目标。
- 前置条件：STEP-03-01
- 修改文件：`Common/BonusConfig.py`
- 目标符号：parser
- 精确操作：
1. 只接受Decimal/string
2. 15→150000、-15→-150000、0→0
3. 拒绝float/NaN。
- 必须保持：不设业务最大值
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m pytest -q User/Test/test_bonus_config.py -k ppm`
- 本步单元验证：`TC-PVAM-03-01`
- 完成证据：`EV-PVAM-03-02`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：出现float中转立即停工

### STEP-PVAM-03-03：移除PE/Elite硬编码

- 目的：移除PE/Elite硬编码，落实 `TASK-PVAM-03` 的已批准目标。
- 前置条件：STEP-03-01/02
- 修改文件：PE与Elite两套服务
- 目标符号：构造器与执行入口
- 精确操作：
1. 强制显式snapshot
2. 生产缺失fail-loud
3. 测试传fixture。
- 必须保持：保持公式/资格/表结构
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile User/PEBonusService.py User/EliteBonusService.py User/GlobalEliteBonusRecalculationService.py`
- 本步单元验证：`TC-PVAM-03-03`
- 完成证据：`EV-PVAM-03-03`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任何生产fallback残留不合并

### STEP-PVAM-03-04：改造SE/EAB/LB配置入口

- 目的：改造SE/EAB/LB配置入口，落实 `TASK-PVAM-03` 的已批准目标。
- 前置条件：STEP-03-01/02
- 修改文件：三个奖金服务
- 目标符号：parse/compute入口
- 精确操作：
1. 接snapshot
2. SE exact raw
3. EAB/LB按自身矩阵
4. 负ppm可计算。
- 必须保持：不新增上游合法性校验
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m compileall -q User Common Model`
- 本步单元验证：`TC-PVAM-03-04/05`
- 完成证据：`EV-PVAM-03-04`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：合法SQL样例变化则停工

### STEP-PVAM-03-05：保护TB oracle并补回归

- 目的：保护TB oracle并补回归，落实 `TASK-PVAM-03` 的已批准目标。
- 前置条件：STEP-03-01
- 修改文件：`User/team_bonus_tb.py`与测试
- 目标符号：配置fixture
- 精确操作：
1. 保持SQL的missing/0/capping=0/重复行为
2. snapshot仅做输入适配。
- 必须保持：不把oracle接生产
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m pytest -q User/Test/test_team_bonus_tb.py User/Test/test_bonus_config.py`
- 本步单元验证：`TC-PVAM-03-06`
- 完成证据：`EV-PVAM-03-05`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：oracle结果变化阻断

### STEP-PVAM-03-06：建立run冻结与manifest测试

- 目的：建立run冻结与manifest测试，落实 `TASK-PVAM-03` 的已批准目标。
- 前置条件：STEP-03-01~05
- 修改文件：测试与run入口
- 目标符号：manifest
- 精确操作：
1. 同一run各奖项使用相同snapshot id/checksum
2. 中途源变化不影响当前run。
- 必须保持：不实现DEC-004 2B producer
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m pytest -q User/Test/test_bonus_config.py`
- 本步单元验证：`TC-PVAM-03-02/07`
- 完成证据：`EV-PVAM-03-06`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：checksum不稳定不得合并

## 8. 数据迁移、兼容与重跑

### 8.1 数据变化

| 对象 | 旧格式/状态 | 新格式/状态 | 转换位置 | 版本识别 | 异常数据策略 |
|---|---|---|---|---|---|
| AR_CONFIG快照 | 原始行由各服务解析 | ConfigSnapshot + signed ppm | run启动适配 | snapshot_id/checksum | 缺失按矩阵fail-loud |

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
| TC-PVAM-03-01 | 单元 | signed ppm | `15`,`0`,`-15`,`float(15)` | 150000、0、-150000；float拒绝 | STEP-03-02 | DEV | NOT_RUN |
| TC-PVAM-03-02 | 单元 | snapshot checksum/freeze | 同一行集不同输入顺序；run中改源 | canonical checksum相同；已冻结对象不变 | STEP-03-01/06 | DEV | NOT_RUN |
| TC-PVAM-03-03 | 回归 | 硬编码清理 | PE/Elite缺配置 | 生产模式抛明确错误；无150000/0.15 fallback | STEP-03-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-03-04 | 契约 | SE exact TYPE | `bonus`,` BONUS `,`Bonus` | 只按已批准exact raw接受；变体不被strip/lower救回 | STEP-03-04 | DEV+UAT | NOT_RUN |
| TC-PVAM-03-05 | 差分 | 负费率 | 合法输入1000 BV、-15% | 产生signed结果并与专项SQL/oracle口径比较；不因负号阻断 | STEP-03-04 | DEV+UAT | NOT_RUN |
| TC-PVAM-03-06 | oracle | TB capping=0 | touch=600,rate=10%,capping=0 | TOUCH_BASE=60 | STEP-03-05 | DEV+UAT | NOT_RUN |
| TC-PVAM-03-07 | 集成 | 多服务同snapshot | PE/SE/EAB/LB同run | manifest中的snapshot id/checksum一致 | STEP-03-06 | DEV+UAT | NOT_RUN |

受控检查方案用例映射：`TC-004, TC-005, TC-013, TC-018, TC-031, TC-032`。`TC-000` 为 RETIRED，不执行、不计完成率。

### 9.2 开发环境自动验证

```bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_SHA="3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2"
: "${WORK_COMMIT_SHA:?set the implementation commit for WORK-PVAM-03}"
: "${PARENT_COMMIT_SHA:?set the controlled parent commit; root WORK uses BASE_SHA}"
: "${PARENT_TREE_SHA:?set the tree of PARENT_COMMIT_SHA}"
: "${PARENT_PROVENANCE_JSON:?set schema-v2 parent provenance JSON}"
: "${APPROVED_COMMIT_REGISTRY_JSON:?set canonical WORK_APPROVED_COMMIT_REGISTRY.json}"
CONTROL_ROOT="${PVAM_CONTROL_ROOT:?point to the released 05_CONTROL directory}"

# Phase A：只验证固定基线和既有锚点，不要求 Common/Settlement/Ops 等未来目录存在。
bash "$CONTROL_ROOT/check_baseline_preflight.sh" \
  --repo "$REPO_ROOT" --base "$BASE_SHA" --work-id "WORK-PVAM-03"

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
  --work-id "WORK-PVAM-03" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --test-command-file "$CONTROL_ROOT/work-test-commands/WORK-PVAM-03.sh" \
  --out "evidence/WORK-PVAM-03/dev"
```

#### 9.2.1 必须落地的关键 `assert` 契约

以下断言骨架必须进入本任务列出的 pytest 文件；fixture 由测试文件实现，不得用复制生产公式的替身替代被测符号。

```python
import pytest
from Common.BonusConfig import ConfigSnapshot, parse_signed_percent_to_ppm


def test_signed_ppm_and_snapshot_contract() -> None:
    assert parse_signed_percent_to_ppm("15") == 150_000
    assert parse_signed_percent_to_ppm("0") == 0
    assert parse_signed_percent_to_ppm("-15") == -150_000
    with pytest.raises(TypeError):
        parse_signed_percent_to_ppm(15.0)  # type: ignore[arg-type]
    a = ConfigSnapshot.from_rows([{"config_name": "proEliteRate", "type": "bonus", "value": "15"}])
    b = ConfigSnapshot.from_rows([{"value": "15", "type": "bonus", "config_name": "proEliteRate"}])
    assert a.checksum == b.checksum
    assert a.require_ppm("proEliteRate") == 150_000
```

通过标准：所有命令 exit code 0；pytest 无未解释 skip；证据schema校验通过。GPU/Dask/真实Redis/Kafka/MySQL未在DEV执行时必须标注 `NOT_RUN/PENDING_TEST_ENV`。

### 9.3 测试环境手工执行包

#### ENV-TC-PVAM-03-01：真实配置快照与SQL/oracle差分

- 对应受控测试：`TC-004、TC-005、TC-013、TC-017、TC-018、TC-021`
- 环境版本：由 `uat/environment_manifest.yaml` 固定 Python/CUDA/RAPIDS/Dask/Redis/Kafka/DB/镜像/commit。
- 前置服务与数据：脱敏AR_CONFIG快照；DB/SQL oracle可用；fixture有checksum
- 清理/隔离：必须使用专用 topic/group、Redis前缀、period/run_id；禁止复用生产数据。
- 执行命令：

```bash
RUN_ID=work03-$(date +%Y%m%d%H%M%S)
bash uat/scripts/run_work_uat.sh --work WORK-PVAM-03 --run-id "$RUN_ID" --tc TC-004,TC-005,TC-013,TC-017,TC-018,TC-021
```

- SQL/数据库证据命令（仅在专用 UAT schema 和 WORK-08 manifest 校验通过后执行；N/A 项只保留说明）：

```bash
mysql --defaults-extra-file="${MYSQL_CNF:?}" --batch --raw <<'SQL'
SELECT CONFIG_NAME, TYPE, VALUE
  FROM AR_CONFIG
 WHERE CONFIG_NAME IN ('eliteRate','proEliteRate','superEliteRate','teamBisectRate')
    OR CONFIG_NAME LIKE 'teamTouchRate%'
    OR CONFIG_NAME LIKE 'teamTouchCapping%'
 ORDER BY CONFIG_NAME, TYPE, VALUE;
SQL
```

- 执行步骤：
1. 导出配置原始行及checksum
2. 执行各奖项配置矩阵和TB oracle
3. 导出manifest、解析ppm和SQL/Python差分
- 精确预期：
- PE/Elite无硬编码兜底
- 负费率按合同计算；SE exact raw成立
- TB missing/0/capping=0与SQL一致
- 必须回传：完整命令、exit code、stdout/stderr、JUnit/JSON、输入fixture SHA-256、代码commit、镜像、环境版本、执行起止时间、Redis/DB/Kafka/Dask前后证据。
- 失败停止与清理：停止专用consumer/job；保留PEL/状态和证据；禁止在未分析前清理失败现场；按第11节回滚。

### 9.4 SQL 对账样例

| 样例 | SQL输入/来源 | SQL预期 | Python预期 | 比较口径 | 允许差异 |
|---|---|---|---|---|---|
| PE 15% | AR_CONFIG proEliteRate=15 | `MIN(VALUE)/100=0.15` | `150000 ppm` | signed ppm | 0 |
| TB capping=0 | touch=600,rate=10%,capping=0 | TOUCH_BASE=60 | 60 units-domain equivalent | SQL capping semantics | 0 |

## 10. 验收标准映射

| 验收编号 | 来源TASK验收项 | 实现步骤 | 测试用例 | 所需证据 | 环境 | 通过条件 |
|---|---|---|---|---|---|---|
| AC-01 | PE 和 Elite 生产路径无硬编码 15%/150000 默认 | STEP-PVAM-03-03 | TC-004、TC-031 | EV-PVAM-03-01 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-02 | 所有生产奖金费率使用同一 signed ppm parser | STEP-PVAM-03-01/02/03/04 | TC-004 | EV-PVAM-03-02 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-03 | 缺失、0、负值、重复、非法文本、float、exact raw 的逐奖项矩阵通过 | STEP-PVAM-03-01/02/04/05 | TC-004、TC-005 | EV-PVAM-03-03 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-04 | 负费率不因负号被拒绝，结果按既有有符号公式计算 | STEP-PVAM-03-02/04 | TC-004 | EV-PVAM-03-04 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-05 | SE raw TYPE/name 的空格和大小写变体不会被静默修复 | STEP-PVAM-03-01/04 | TC-005、TC-018 | EV-PVAM-03-05 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-06 | DEC-003 豁免项不被错误判失败；SE 独立规则不被豁免覆盖 | STEP-PVAM-03-01/04 | TC-005、TC-018 | EV-PVAM-03-06 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-07 | run manifest 含 raw/canonical checksum，同一 run 各服务一致 | STEP-PVAM-03-01/06 | TC-004、TC-032 | EV-PVAM-03-07 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-08 | 配置运行中变化不影响已启动 run；下一个 run 使用新 snapshot | STEP-PVAM-03-06 | TC-004、TC-032 | EV-PVAM-03-08 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-09 | TB oracle 的 missing/0/capping=0 测试保持 SQL parity | STEP-PVAM-03-05 | TC-004、TC-013 | EV-PVAM-03-09 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-10 | ConfigRequirementMatrix 可机器读取并覆盖当前范围内所有配置键 | STEP-PVAM-03-01/06 | TC-031、TC-032 | EV-PVAM-03-10 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |

没有 STEP、TC 或 EV 映射的AC不得标记完成。任何含UAT的AC在未回传真实环境证据时只能为 `PENDING_TEST_ENV/BLOCKED`。

## 11. 风险、停工与回滚

### 11.1 风险清单

| 风险 | 触发条件 | 影响 | 预防措施 | 监测/证据 | 处置 |
|---|---|---|---|---|---|
| 配置矩阵误合并奖项 | 一套规则套所有奖项 | 合法输入被拒/脏值被洗白 | 逐奖项矩阵 | TC-004/005差分 | 回滚相关consumer |
| snapshot不稳定 | 源顺序影响hash | 同run不一致 | canonical排序与hash | manifest | 停工 |
| 2B链不存在 | UAT误把fixture当生产 | 虚假PASS | 显式DEFERRED标签 | evidence manifest | 保持BLOCKED |

### 11.2 本任务强制停工条件

- HEAD、SQL blob、模型schema或上游TASK与受控基线不一致。
- 实施必须改变未批准的业务规则、精度、资格、分母、Country或发布职责才能继续。
- 需要修改排除文件/模块或扩大异常白名单才能通过测试。
- 关键mutation存活、SQL黄金样例出现未批准差异、幂等/原子/回滚断言失败。
- UAT权限、schema、数据或隔离条件不足；此时保持 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV`。

### 11.3 部署面与数据面回滚门禁

**当前可执行性：`BLOCKED_EXTERNAL_EVIDENCE`。** 当前材料没有给出真实部署系统、workload/release、镜像、配置对象和健康检查命令，因此不得以本地`export`或通用`git revert`冒充部署回滚。

部署前必须提供并签署`evidence/WORK-PVAM-03/rollback/ROLLBACK-MANIFEST-PVAM-v1.json`，至少包含：

- `deployment_system`、`environment`、`workload_id`、`release_before/after`、`image_before/after`；
- 精确的停止、回滚、恢复、健康检查和重新放量命令；
- Redis/Stream/ledger/run/manifest的备份或快照位置及SHA-256；
- 执行人、复核人、批准时间、允许的数据恢复范围；
- 命令dry-run/隔离演练的退出码和原始日志。

本任务数据面处置：冻结配置snapshot与run checksum；恢复旧镜像和上一个已批准配置对象；保留新snapshot审计，不删除负ppm或raw证据。

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
| EV-PVAM-03-01 | AC-01验收证据：PE 和 Elite 生产路径无硬编码 15%/150000 默认 | STEP-PVAM-03-03 | evidence/WORK-PVAM-03/attempt-*/ac/AC-01/ | 待指派QA | PENDING |
| EV-PVAM-03-02 | AC-02验收证据：所有生产奖金费率使用同一 signed ppm parser | STEP-PVAM-03-01/02/03/04 | evidence/WORK-PVAM-03/attempt-*/ac/AC-02/ | 待指派QA | PENDING |
| EV-PVAM-03-03 | AC-03验收证据：缺失、0、负值、重复、非法文本、float、exact raw 的逐奖项矩阵通过 | STEP-PVAM-03-01/02/04/05 | evidence/WORK-PVAM-03/attempt-*/ac/AC-03/ | 待指派QA | PENDING |
| EV-PVAM-03-04 | AC-04验收证据：负费率不因负号被拒绝，结果按既有有符号公式计算 | STEP-PVAM-03-02/04 | evidence/WORK-PVAM-03/attempt-*/ac/AC-04/ | 待指派QA | PENDING |
| EV-PVAM-03-05 | AC-05验收证据：SE raw TYPE/name 的空格和大小写变体不会被静默修复 | STEP-PVAM-03-01/04 | evidence/WORK-PVAM-03/attempt-*/ac/AC-05/ | 待指派QA | PENDING |
| EV-PVAM-03-06 | AC-06验收证据：DEC-003 豁免项不被错误判失败；SE 独立规则不被豁免覆盖 | STEP-PVAM-03-01/04 | evidence/WORK-PVAM-03/attempt-*/ac/AC-06/ | 待指派QA | PENDING |
| EV-PVAM-03-07 | AC-07验收证据：run manifest 含 raw/canonical checksum，同一 run 各服务一致 | STEP-PVAM-03-01/06 | evidence/WORK-PVAM-03/attempt-*/ac/AC-07/ | 待指派QA | PENDING |
| EV-PVAM-03-08 | AC-08验收证据：配置运行中变化不影响已启动 run；下一个 run 使用新 snapshot | STEP-PVAM-03-06 | evidence/WORK-PVAM-03/attempt-*/ac/AC-08/ | 待指派QA | PENDING |
| EV-PVAM-03-09 | AC-09验收证据：TB oracle 的 missing/0/capping=0 测试保持 SQL parity | STEP-PVAM-03-05 | evidence/WORK-PVAM-03/attempt-*/ac/AC-09/ | 待指派QA | PENDING |
| EV-PVAM-03-10 | AC-10验收证据：ConfigRequirementMatrix 可机器读取并覆盖当前范围内所有配置键 | STEP-PVAM-03-01/06 | evidence/WORK-PVAM-03/attempt-*/ac/AC-10/ | 待指派QA | PENDING |
| EV-PVAM-03-P01 | BonusConfig/ConfigSnapshot源码 | 对应STEP/TC | evidence/WORK-PVAM-03/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-03-P02 | PE/Elite/SE/EAB/LB接入diff | 对应STEP/TC | evidence/WORK-PVAM-03/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-03-P03 | ConfigRequirementMatrix机器文件 | 对应STEP/TC | evidence/WORK-PVAM-03/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-03-P04 | DEV矩阵与TB oracle报告 | 对应STEP/TC | evidence/WORK-PVAM-03/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-03-P05 | UAT配置快照/SQL差分包 | 对应STEP/TC | evidence/WORK-PVAM-03/attempt-*/package/ | 待指派QA | PENDING |

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
  --work-id "WORK-PVAM-03" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --out "evidence/WORK-PVAM-03/patch"
```

门禁必须证明：

1. `BASE_SHA` 是 `WORK_COMMIT_SHA` 的祖先；
2. 全部新增、修改、删除和 rename 的旧/新路径均落在 `WORK-PVAM-03` 批准 allowlist；
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
| STEP-PVAM-03-01 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-03-02 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-03-03 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-03-04 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-03-05 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-03-06 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |

### 13.2 实际验证

| 测试 | 环境 | 命令/版本 | 结果 | 证据 | 执行时间 |
|---|---|---|---|---|---|
| TC-PVAM-03-01 | DEV | 待执行 | NOT_RUN | EV-PVAM-03-* | 待执行 |
| TC-PVAM-03-02 | DEV | 待执行 | NOT_RUN | EV-PVAM-03-* | 待执行 |
| TC-PVAM-03-03 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-03-* | 待执行 |
| TC-PVAM-03-04 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-03-* | 待执行 |
| TC-PVAM-03-05 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-03-* | 待执行 |
| TC-PVAM-03-06 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-03-* | 待执行 |
| TC-PVAM-03-07 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-03-* | 待执行 |

### 13.3 未完成项

| 项目 | 原因 | 风险 | 后续动作 | 责任人 | 截止时间 |
|---|---|---|---|---|---|
| UAT/外部材料 | 当前计划阶段未执行 | 不能关闭P0/P1 | 由WORK-08准入后执行 | 待指派 | 待批准 |

## 14. 偏离、发现项与上游回流

| 编号 | 类型 | 发现事实 | 是否影响业务/范围 | 临时动作 | 需要更新 | 最终裁决 |
|---|---|---|---|---|---|---|
| `DEV-PVAM-03-001` | `预留` | 待执行 | 待判断 | 停工/隔离 | WORK/TASK/DEC/REVIEW | 待裁决 |

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
| v1.0 | 2026-08-04 | 初版施工任务书 | `TASK-PVAM-03` + `PLAN-PVAM-v1.15` + 固定代码基线 | AI Agent（编制） | DRAFT |
| v1.1 | 2026-08-05 | 依据二轮核验报告完成定点修订并补齐治理追溯 | F-A/F-B/F-H/F-I/F-J/F-K/F-F/F-E/F-L/F-M/F-N 中适用项 | AI Agent（编制） | DRAFT |
| v1.2 | 2026-08-05 | 闭合 G-1：统一 `RecalcProcessResult` 类名并补齐 `should_ack`；历史版本曾调整施工套件审批状态，不改变 CHK/DEC/TASK/WORK 范围 | 历史会话声明（未形成可独立验证组织授权，现由 v1.3 取代） | AI Agent（编制） | SUPERSEDED |
| v1.3 | 2026-08-05 | 第四轮关闭 F3-01～F3-10：治理回退 DRAFT、Traceability v3、patch/DEV 双阶段、状态枚举及设计边界 | 三轮审查报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r6 | 2026-08-06 | 五轮 F5 定点修订：规范 v3 追溯、parent provenance/DEV CLI、控制状态字段及单一事实源 | 五轮审计报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r7 | 2026-08-06 | 六轮 S6：信任 registry 初版、归档哈希、临时目录与 Decimal finite 防护 | 六轮终局审计报告 | AI Agent（编制） | DRAFT |
| v1.3-r8 | 2026-08-06 | 七轮 B7：registry 发布信任根、四工件摘要、AC 来源保真及当前轮次引用 | 七轮终局审计报告 + B7 处置 | AI Agent（编制） | DRAFT |

<!-- END WORK-PVAM-03_配置解析ppm与硬编码清理.md -->

---

<!-- BEGIN WORK-PVAM-04_monthActivePV与Active同源现算.md -->

# WORK-PVAM-04 monthActivePV 唯一取值与 Active 同源现算施工任务书

> 文档定位：来源于待组织批准的 `TASK-PVAM-04`，在取得组织授权后转化为可执行施工说明。本文件不重新决定业务规则；实际结果只能写入执行记录与验证交付报告。

## 0. 填写与执行规则

1. 上游修改任务与本 v1.3 施工套件当前均为 `DRAFT`；没有组织授权前，本任务保持 `BLOCKED`，不得启动代码施工或部署。
2. 只实施 `R-005、R-006` 中已 `ACCEPTED` 或由来源 TASK 明确批准的条件代码事项。任何 `REJECTED / NEEDS_DECISION / DEFERRED / 未获 TASK 授权的 UAT_VERIFY` 只允许登记、验证或阻断，不得扩展代码范围。
3. 基线必须精确等于 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；发现漂移立即登记 `BLOCK-PVAM-04-BASELINE`。
4. 所有新文件/符号已在变更表标为“新增”；其余锚点均来自固定基线。
5. DEV替身不能冒充真实Kafka/Redis/Dask/GPU/MySQL UAT验证。

## 1. 文档信息与追溯关系

| 字段 | 内容 |
|---|---|
| 施工任务编号 | `WORK-PVAM-04` |
| 施工任务名称 | monthActivePV 唯一取值与 Active 同源现算 |
| 所属施工总方案 | `WORK-PLAN-PVAM_v1.3` |
| 来源修改任务 | `TASK-PVAM-04@MODPLAN-PVAM_v1.2`（authorization=PENDING_ORGANIZATIONAL_APPROVAL） |
| 来源问题 | `R-005、R-006` |
| 复核闭环追踪号 | `REM-005、REM-006 / W-005、W-006 / V-005、V-006` |
| 来源检查项 | `CHK-DATA-006、CHK-BIZ-007、CHK-BIZ-008、CHK-BIZ-009、CHK-BIZ-011` |
| 关联决策 | `DEC-004、DEC-016、DEC-018` |
| 代码基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| SQL基线 | `sql_uat/*@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，仅有效SQL |
| 文档版本 | `v1.3` |
| 负责人 | `待指派 / 实施工程师` |
| 复核人 | `待指派 / 架构与QA` |
| 当前状态 | `BLOCKED` |
| 文档治理状态 | `DRAFT`（`PENDING_ORGANIZATIONAL_APPROVAL`） |
| 前置任务 | WORK-PVAM-01、WORK-PVAM-03 DEV_VERIFIED；真实供给链UAT仍BLOCKED |
| 功能开关 | `ACTIVE_RULE_V2` |

### 1.1 一对一追溯摘要

```text
CHK-DATA-006、CHK-BIZ-007、CHK-BIZ-008、CHK-BIZ-009、CHK-BIZ-011
  └─ R-005、R-006
       └─ DEC-004、DEC-016、DEC-018
            └─ TASK-PVAM-04 (DRAFT / PENDING_ORGANIZATIONAL_APPROVAL)
                 └─ WORK-PVAM-04
                      ├─ STEP-PVAM-04-01 / STEP-PVAM-04-02 / STEP-PVAM-04-03 / STEP-PVAM-04-04 / STEP-PVAM-04-05
                      ├─ TC-PVAM-04-01 / TC-PVAM-04-02 / TC-PVAM-04-03 / TC-PVAM-04-04 / TC-PVAM-04-05 / TC-PVAM-04-06 / TC-PVAM-04-07 / TC-PVAM-04-08
                      └─ EV-PVAM-04-01...
```

## 2. 施工任务生成依据

### 2.1 上游输入

| 输入 | 编号/版本 | 本任务使用的结论 | 状态 |
|---|---|---|---|
| 复核报告 | `Redemption_PV_Amount_Migration_d74_复核报告_v1.5` | R-005、R-006 的代码事实与严重级别 | CONFIRMED |
| 修改任务书 | `TASK-PVAM-04` | 采用方案、范围、排除项、AC | DRAFT（待组织授权） |
| 检查方案 | `PLAN-PVAM-v1.15` | CHK-DATA-006、CHK-BIZ-007、CHK-BIZ-008、CHK-BIZ-009、CHK-BIZ-011 | CONTROLLED |
| 正式决策 | DEC-004、DEC-016、DEC-018 | 只执行已关闭裁决；开放项阻断 | CLOSED / 按上游登记 |
| 代码/SQL快照 | 3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2 | 唯一施工对象 | FROZEN |
| 施工模板 | 总方案模板/专项模板 | 章节、状态、证据纪律 | CONTROLLED |

### 2.2 开工条件

- [ ] 当前 HEAD 精确为 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，工作树无未登记变更。
- [ ] `TASK-PVAM-04` 的人工批准记录已归档；本 `WORK` 已由施工负责人和复核人签署。
- [ ] 前置关系满足：WORK-PVAM-01、WORK-PVAM-03 DEV_VERIFIED；真实供给链UAT仍BLOCKED。
- [ ] 本任务涉及的接口、单位、精度、兼容和回滚边界已由上游任务固定。
- [ ] DEV测试依赖已安装；UAT项具备WORK-08生成的环境/数据/schema manifest。
- [ ] 功能开关默认关闭，回滚路径已演练。

未满足任一关键项时，本任务状态为 `BLOCKED`；不得用假设替代。

## 3. 问题事实与施工目标

### 3.1 已确认问题

| 项目 | 内容 |
|---|---|
| 预期行为 | 实现唯一 monthActivePV getter 和纯函数 ActiveRule；PE/SE/EAB/LB及适用TB消费者每次从同一 v2 UserStats.pv 现算，外部IS_ACTIVE仅用于审计；本轮不建设延期的2B写入侧。 |
| 当前行为 | `PEBonusService.execute_batch` 在 `ddf_user_perf is None` 时直接以 `UserStats.pv >= 30` 派生。；PE、SE、EAB 等服务可接受外部 `IS_ACTIVE` 表/列并用于发奖，形成多权威源。；固定基线不存在唯一 monthActivePV getter，也不存在可证明的 AR_CONFIG→Delta→Redis 2B producer。；DEC-018 要求不物化共享Active snapshot，各消费方用同一pv源和同一门槛规则各自现算。 |
| 差异 | 当前实现缺少本任务批准的唯一合同、门禁或原子边界。 |
| 影响 | 金额/PV单位、奖金、并发一致性、发布或可恢复性，具体见来源问题。 |
| 严重级别 | P0 / P1 |
| 证据位置 | 固定代码基线 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；来源 `TASK-PVAM-04`；检查项 `CHK-DATA-006、CHK-BIZ-007、CHK-BIZ-008、CHK-BIZ-009、CHK-BIZ-011` |

### 3.2 已确认代码事实

- `PEBonusService.execute_batch` 在 `ddf_user_perf is None` 时直接以 `UserStats.pv >= 30` 派生。
- PE、SE、EAB 等服务可接受外部 `IS_ACTIVE` 表/列并用于发奖，形成多权威源。
- 固定基线不存在唯一 monthActivePV getter，也不存在可证明的 AR_CONFIG→Delta→Redis 2B producer。
- DEC-018 要求不物化共享Active snapshot，各消费方用同一pv源和同一门槛规则各自现算。

### 3.3 本任务目标

实现唯一 monthActivePV getter 和纯函数 ActiveRule；PE/SE/EAB/LB及适用TB消费者每次从同一 v2 UserStats.pv 现算，外部IS_ACTIVE仅用于审计；本轮不建设延期的2B写入侧。

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
| 1 | PE执行 | `User/PEBonusService.py::execute_batch` | ddf_user_perf可空 | 空时pv>=30；非空时外部权威 | 裸值/双权威 |
| 2 | SE执行 | `User/SuperEliteBonusService.py::calculate_se_bonus` | ddf_user_perf必需 | 直接使用外部is_active | 来源不可追溯 |
| 3 | EAB执行 | `User/EliteAchievementBonusService.py::calculate_eab_bonus` | ddf_user_perf | 外部is_active决定实际发放 | 来源不可追溯 |
| 4 | LB执行 | `LeadershipBonusGPUService`输入快照 | active字段/上游 | 无统一门槛manifest | 跨奖项漂移 |

### 4.2 当前错误形成点

当前链路在上述入口缺少本任务目标合同，导致已确认问题在写入、计算、路由或发布边界形成并传播。修改必须落在表中稳定符号或明确标记为“新增”的边界；不得通过外围日志掩盖。

### 4.3 受影响消费者

| 消费者 | 依赖内容 | 预期影响 | 是否同步修改 | 对应步骤/测试 |
|---|---|---|---|---|
| PE | UserStats.pv + threshold | 替换裸30和外部权威 | 是 | STEP-04-03/TC-007/017 |
| SE | 同源现算 | 外部字段改audit | 是 | STEP-04-03/TC-018 |
| EAB | 同源现算 | 理论行保留，不活跃实际0 | 是 | STEP-04-03/TC-019 |
| LB | 同源现算 | 理论/实际语义不变 | 是 | STEP-04-03/TC-021 |
| Elite | Active=N/A | 不改 | 否 | TC-014 |
| TB oracle/未来consumer | 适用时同规则 | 只适配测试，不建生产服务 | 测试 | TC-007/013 |

## 5. 施工设计

### 5.1 采用方案

- 新增 `Common/MonthActivePvProvider.py`：读取顺序 Redis→sleep(2s)→Redis→Delta→fail-loud；依赖通过接口注入，便于DEV替身。
- 门槛原始值按 INTEGER_BV_ONLY scale=100 解析：30/30.00可规范，30.1阻断；随后转换为30,000,000 micro-units。
- 新增 `Common/ActiveRule.py::is_active(pv_units, threshold_units) -> bool`，先校验version/units，比较结果不持久化。
- run启动时取值一次并写 `threshold_raw/canonical/source/version/checksum` 到run manifest。
- `GAP-DEC004-2B` 保持DEFERRED：不得新增AR_CONFIG同步、Redis失效或Delta生产writer；UAT通过fixture只验证getter读侧。

选择理由：

- 与有效SQL、已关闭DEC及来源TASK目标一致。
- 采用 additive-first、显式version/manifest/feature flag，支持独立合入和回滚。
- 将纯函数、I/O适配、业务计算、权威提交和证据采集分层，便于DEV替身与UAT真实验证分别取证。

### 5.2 被否决方案

| 方案 | 不采用原因 | 来源 |
|---|---|---|
| 共享Active表/snapshot | 违反DEC-018 | DEC-018 |
| 硬编码30 | 配置变更无法生效 | R-005 |
| 最终失败回退30/全员活跃 | 违反DEC-004 fail-loud | DEC-004 |
| 本轮顺手建设2B producer | DEFERRED，无批准 | GAP-DEC004-2B |
| 外部IS_ACTIVE作为权威 | R-006 | R-006 |

### 5.3 修改后调用链与数据契约

| 边界 | 输入 | 处理 | 输出 | 断言/错误行为 | 责任符号 |
|---|---|---|---|---|---|
| 施工入口 | 固定commit + 批准TASK + ACTIVE_RULE_V2 | 先执行基线/前置检查 | 受控diff | 任一前置失败即BLOCK | `Common/MonthActivePvProvider.py` |
| 核心处理 | strict version/type/period/run合同 | 按STEP顺序执行 | 可测试状态/事件/金额 | 非法类型、状态或proof fail-loud | 见CHG表 |
| 证据出口 | 命令、输入、输出、状态前后 | WORK-08 schema封装 | EV包+SHA-256 | 缺原始证据不得PASS | `uat/scripts/*` |

## 6. 文件与符号级变更清单

| 变更编号 | 文件 | 类/函数/字段/表 | 类型 | 修改前行为 | 要求的修改 | 修改后行为 | 禁止行为 |
|---|---|---|---|---|---|---|---|
| CHG-01 | `Common/MonthActivePvProvider.py` | provider/repository协议 | 新增 | 不存在 | 实现严格读取顺序与manifest | 唯一门槛getter | 不得写配置 |
| CHG-02 | `Common/ActiveRule.py` | `is_active` / vector helpers | 新增 | 不存在 | 以strict units比较 | 同源纯计算 | 不得物化结果 |
| CHG-03 | `User/PEBonusService.py` | `execute_batch` | 修改 | 裸30或外部perf | 注入threshold+从stats.pv现算；perf仅audit | 同源结果 | 不得改base/资格 |
| CHG-04 | `User/SuperEliteBonusService.py` | `calculate_se_bonus` | 修改 | 外部is_active权威 | 接UserStats pv与threshold现算 | 分母/不发规则保持 | 不得重分配份额 |
| CHG-05 | `User/EliteAchievementBonusService.py` | `calculate_eab_bonus` | 修改 | 外部is_active权威 | 现算；仅实际奖金受影响 | 理论池保持 | 不得改HALF_UP |
| CHG-06 | `User/LeadershipBonusGPUService.py` | `compute_leadership_bonus`输入组装 | 修改 | 上游active | 现算并审计差异 | 九代/双闸门不变 | 不得改Country政策 |
| CHG-07 | `User/run_monthly_bonus_pipeline_v2.py` | run manifest组装 | 修改 | 无统一threshold | 启动一次取值并传各消费者 | run内冻结 | 不得实现2B写侧 |
| CHG-08 | `User/Test/test_month_active_pv.py` | pytest | 新增 | 不存在 | provider顺序、阈值、跨奖项一致性 | 可自动验证 | 不得伪造生产供给链PASS |

### 6.1 固定基线锚点复验

| 文件与符号 | 基线事实 | 施工动作 |
|---|---|---|
| `User/PEBonusService.py::execute_batch` | `ddf_user_perf is None`时按`pv>=30`派生 | 删除裸30与外部Active权威输入 |
| `User/SuperEliteBonusService.py` | 要求注入`ddf_user_perf.is_active` | 改为同run UserStats PV + threshold现算 |
| EAB/LB消费者 | 各自存在Active输入/组装路径 | 接入同一ActiveRule，不改变理论池/分母规则 |
| AR_CONFIG→Delta→Redis写入侧 | 固定基线无完整生产实现 | 保持`GAP-DEC004-2B / DEFERRED`，本任务不建设 |

### 6.2 读取侧参考接口

```python
from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, Sequence

@dataclass(frozen=True)
class MonthActivePv:
    raw_value: str
    threshold_units: int
    source: str
    source_version: str
    checksum: str

class ConfigRowsReader(Protocol):
    def read_redis_rows(self, config_name: str) -> Sequence[dict]: ...
    def read_delta_rows(self, config_name: str) -> Sequence[dict]: ...

class MonthActivePvProvider:
    def __init__(self, reader: ConfigRowsReader, sleep_fn=time.sleep):
        self._reader = reader
        self._sleep = sleep_fn

    def load_for_run(self) -> MonthActivePv:
        rows = list(self._reader.read_redis_rows("monthActivePV"))
        source = "redis"
        if not rows:
            self._sleep(2)
            rows = list(self._reader.read_redis_rows("monthActivePV"))
        if not rows:
            rows = list(self._reader.read_delta_rows("monthActivePV"))
            source = "delta"
        if not rows:
            raise RuntimeError("monthActivePV missing from Redis and Delta")
        # 重复时按DEC-016取真实行之一；不得使用内置默认值。
        raw = str(rows[0]["value"])
        value = Decimal(raw)
        if value != value.to_integral_value():
            raise ValueError("monthActivePV must be INTEGER_BV_ONLY")
        threshold_units = int(value) * 1_000_000
        source_version = rows[0].get("source_version")
        checksum = rows[0].get("checksum")
        if not source_version or not checksum:
            raise RuntimeError("monthActivePV source_version/checksum missing")
        return MonthActivePv(raw, threshold_units, source,
                             str(source_version), str(checksum))


def derive_active(*, user_pv_units: int, threshold_units: int) -> bool:
    return user_pv_units >= threshold_units
```

实际实现必须由WORK-03公共parser校验类型/checksum；source_version或checksum缺失必须fail-loud，示例不授权自造排序规则。30与30.00规范到相同整数阈值；30.1因非INTEGER_BV阻断。

### 6.3 供给链边界

UAT可由DBA受控注入Redis/Delta fixture验证读取顺序，但证据必须记录来源、注入人、有效期和SHA-256；fixture通过不得把2B生产写入/失效链改为CLOSED或VERIFIED。

> **DEV 执行口径：** `05_CONTROL/check_baseline_preflight.sh` 与 `05_CONTROL/validate_work_dev.sh` 是唯一强制门禁。STEP 中列出的 `py_compile`、`compileall` 或 `pytest` 命令仅是附加局部检查，不得替代 parent-tree、scope、patch、tree-hash 与专属测试门禁。

## 7. 可执行施工步骤

### STEP-PVAM-04-01：实现provider读侧

- 目的：实现provider读侧，落实 `TASK-PVAM-04` 的已批准目标。
- 前置条件：WORK-01/03 DEV_VERIFIED
- 修改文件：`Common/MonthActivePvProvider.py`
- 目标符号：provider接口
- 精确操作：
1. 实现Redis两读间隔2秒、Delta兜底和最终异常
2. 返回值含source/version/checksum。
- 必须保持：不新增写入/失效producer
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Common/MonthActivePvProvider.py`
- 本步单元验证：`TC-PVAM-04-01/02`
- 完成证据：`EV-PVAM-04-01`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：无法证明读源字段时BLOCK UAT，不猜

### STEP-PVAM-04-02：实现ActiveRule

- 目的：实现ActiveRule，落实 `TASK-PVAM-04` 的已批准目标。
- 前置条件：STEP-04-01
- 修改文件：`Common/ActiveRule.py`
- 目标符号：纯函数/vector helper
- 精确操作：
1. 门槛scale=100规范后转units
2. pv/version严格校验。
- 必须保持：不写共享snapshot
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Common/ActiveRule.py`
- 本步单元验证：`TC-PVAM-04-03`
- 完成证据：`EV-PVAM-04-02`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：30.1未阻断则停工

### STEP-PVAM-04-03：改造奖金消费者

- 目的：改造奖金消费者，落实 `TASK-PVAM-04` 的已批准目标。
- 前置条件：STEP-04-02
- 修改文件：PE/SE/EAB/LB服务
- 目标符号：执行入口
- 精确操作：
1. 移除外部active权威
2. 从同run stats.pv+threshold现算
3. 外部列只做audit mismatch。
- 必须保持：保持资格/分母/理论/实际业务语义
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m compileall -q User Common`
- 本步单元验证：`TC-PVAM-04-04~07`
- 完成证据：`EV-PVAM-04-03`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任何奖项结果非Active部分变化则停工

### STEP-PVAM-04-04：冻结门槛manifest

- 目的：冻结门槛manifest，落实 `TASK-PVAM-04` 的已批准目标。
- 前置条件：STEP-04-01
- 修改文件：`User/run_monthly_bonus_pipeline_v2.py`
- 目标符号：run启动
- 精确操作：
1. 取一次threshold，记录manifest并显式传入全部消费者。
- 必须保持：不在run中热刷新
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile User/run_monthly_bonus_pipeline_v2.py`
- 本步单元验证：`TC-PVAM-04-08`
- 完成证据：`EV-PVAM-04-04`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：同run出现两个checksum即失败

### STEP-PVAM-04-05：补齐fixture纪律与测试

- 目的：补齐fixture纪律与测试，落实 `TASK-PVAM-04` 的已批准目标。
- 前置条件：STEP-04-01~04
- 修改文件：测试/uat fixture manifest
- 目标符号：pytest与manifest
- 精确操作：
1. DEV用repository替身
2. UAT fixture必须标记人工注入、来源/checksum/有效期，真实2B仍BLOCKED。
- 必须保持：不得把fixture当生产链
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m pytest -q User/Test/test_month_active_pv.py`
- 本步单元验证：`TC-PVAM-04-01~08`
- 完成证据：`EV-PVAM-04-05`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：证据标签缺失不得验收

## 8. 数据迁移、兼容与重跑

### 8.1 数据变化

| 对象 | 旧格式/状态 | 新格式/状态 | 转换位置 | 版本识别 | 异常数据策略 |
|---|---|---|---|---|---|
| monthActivePV配置 | 裸30/外部Active | 门槛units + 每消费方现算 | run启动getter | threshold checksum | 最终缺失阻断 |
| 外部IS_ACTIVE | 权威输入 | 仅审计字段 | 奖金入口 | audit flag | 不参与裁决 |

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
| TC-PVAM-04-01 | 单元 | Redis首读命中 | Redis=30,Delta=空 | 不sleep/不读Delta；返回30,000,000及Redis来源 | STEP-04-01 | DEV | NOT_RUN |
| TC-PVAM-04-02 | 故障 | Redis空→2s→空→Delta/空 | 受控clock与repositories | Delta有30则成功；Delta空抛明确错误且无奖金结果 | STEP-04-01 | DEV+UAT | NOT_RUN |
| TC-PVAM-04-03 | 边界 | 阈值与PV | threshold 30/30.00/30.1；pv29.99/30 | 30.1阻断；29.99 inactive；30 active | STEP-04-02 | DEV | NOT_RUN |
| TC-PVAM-04-04 | 差分 | 跨奖项同源 | 同user/period/run pv=30 | PE/SE/EAB/LB active均1 | STEP-04-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-04-05 | 审计 | 外部active冲突 | 现算1、外部0 | 奖金按1裁决；产生audit mismatch | STEP-04-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-04-06 | 回归 | Elite不受Active | 同Elite输入，active切换 | Elite候选/奖金完全相同 | STEP-04-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-04-07 | 业务回归 | inactive语义 | qualified但pv29.99 | PE/SE/EAB/LB实际不发；理论/分母按各自SQL合同 | STEP-04-03 | UAT | NOT_RUN |
| TC-PVAM-04-08 | 集成 | run冻结 | 启动后源从30改40 | 当前run仍30/checksum不变；下一run40 | STEP-04-04 | DEV+UAT | NOT_RUN |

受控检查方案用例映射：`TC-007, TC-013, TC-014, TC-017, TC-018, TC-019, TC-021, TC-030, TC-031, TC-032`。`TC-000` 为 RETIRED，不执行、不计完成率。

### 9.2 开发环境自动验证

```bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_SHA="3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2"
: "${WORK_COMMIT_SHA:?set the implementation commit for WORK-PVAM-04}"
: "${PARENT_COMMIT_SHA:?set the controlled parent commit; root WORK uses BASE_SHA}"
: "${PARENT_TREE_SHA:?set the tree of PARENT_COMMIT_SHA}"
: "${PARENT_PROVENANCE_JSON:?set schema-v2 parent provenance JSON}"
: "${APPROVED_COMMIT_REGISTRY_JSON:?set canonical WORK_APPROVED_COMMIT_REGISTRY.json}"
CONTROL_ROOT="${PVAM_CONTROL_ROOT:?point to the released 05_CONTROL directory}"

# Phase A：只验证固定基线和既有锚点，不要求 Common/Settlement/Ops 等未来目录存在。
bash "$CONTROL_ROOT/check_baseline_preflight.sh" \
  --repo "$REPO_ROOT" --base "$BASE_SHA" --work-id "WORK-PVAM-04"

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
  --work-id "WORK-PVAM-04" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --test-command-file "$CONTROL_ROOT/work-test-commands/WORK-PVAM-04.sh" \
  --out "evidence/WORK-PVAM-04/dev"
```

#### 9.2.1 必须落地的关键 `assert` 契约

以下断言骨架必须进入本任务列出的 pytest 文件；fixture 由测试文件实现，不得用复制生产公式的替身替代被测符号。

```python
import pytest
from Common.ActiveRule import is_active
from Common.MonthActivePvProvider import MonthActivePvProvider


def test_active_threshold_contract(redis_repo, delta_repo, fake_clock) -> None:
    provider = MonthActivePvProvider(redis_repo=redis_repo, delta_repo=delta_repo, clock=fake_clock)
    threshold = provider.get_for_run(period="41", run_id="r1")
    assert threshold.units == 30_000_000
    assert is_active(29_990_000, threshold.units) is False
    assert is_active(30_000_000, threshold.units) is True
    redis_repo.clear()
    delta_repo.clear()
    with pytest.raises(RuntimeError):
        provider.get_for_run(period="42", run_id="r2")
```

通过标准：所有命令 exit code 0；pytest 无未解释 skip；证据schema校验通过。GPU/Dask/真实Redis/Kafka/MySQL未在DEV执行时必须标注 `NOT_RUN/PENDING_TEST_ENV`。

### 9.3 测试环境手工执行包

#### ENV-TC-PVAM-04-01：Active同源与读链故障

- 对应受控测试：`TC-007、TC-013、TC-017、TC-018、TC-019、TC-021`
- 环境版本：由 `uat/environment_manifest.yaml` 固定 Python/CUDA/RAPIDS/Dask/Redis/Kafka/DB/镜像/commit。
- 前置服务与数据：WORK-08批准fixture；Redis/Delta隔离；真实2B状态标DEFERRED
- 清理/隔离：必须使用专用 topic/group、Redis前缀、period/run_id；禁止复用生产数据。
- 执行命令：

```bash
RUN_ID=work04-$(date +%Y%m%d%H%M%S)
bash uat/scripts/run_work_uat.sh --work WORK-PVAM-04 --run-id "$RUN_ID" --tc TC-007,TC-013,TC-017,TC-018,TC-019,TC-021
```

- SQL/数据库证据命令（仅在专用 UAT schema 和 WORK-08 manifest 校验通过后执行；N/A 项只保留说明）：

```bash
mysql --defaults-extra-file="${MYSQL_CNF:?}" --batch --raw <<SQL
SELECT CONFIG_NAME, TYPE, VALUE
  FROM AR_CONFIG
 WHERE CONFIG_NAME = 'monthActivePV';
SELECT PERIOD_NUM, USER_ID, PV_PCS, IS_ACTIVE
  FROM AR_PERF_MONTH
 WHERE PERIOD_NUM = ${PERIOD_NUM:?}
 ORDER BY USER_ID;
SQL
```

- 执行步骤：
1. 分别注入Redis命中、Redis空Delta命中、两者皆空
2. 以pv=29.99/30执行PE/SE/EAB/LB与TB oracle
3. 运行中改变fixture并启动下一run
- 精确预期：
- 当前run所有消费者Active一致
- 最终缺失时整run失败且无奖金发布
- fixture证据不关闭2B生产缺口
- 必须回传：完整命令、exit code、stdout/stderr、JUnit/JSON、输入fixture SHA-256、代码commit、镜像、环境版本、执行起止时间、Redis/DB/Kafka/Dask前后证据。
- 失败停止与清理：停止专用consumer/job；保留PEL/状态和证据；禁止在未分析前清理失败现场；按第11节回滚。

### 9.4 SQL 对账样例

| 样例 | SQL输入/来源 | SQL预期 | Python预期 | 比较口径 | 允许差异 |
|---|---|---|---|---|---|
| Active边界 | monthActivePV=30; pv=29.99/30 | SQL legacy active对照 | 0/1 | micro-units比较 | 0 |
| PE inactive | qualified, pv<30 | 理论金额存在但IS_ACTIVE=0不发（按当前合同） | 实际0 cents | Active仅最终拦截 | 0 |

## 10. 验收标准映射

| 验收编号 | 来源TASK验收项 | 实现步骤 | 测试用例 | 所需证据 | 环境 | 通过条件 |
|---|---|---|---|---|---|---|
| AC-01 | 全仓生产路径不再出现裸 `>=30` Active 判定 | STEP-PVAM-04-03/05 | TC-007、TC-031 | EV-PVAM-04-01 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-02 | 唯一 getter 的 Redis→2秒→Redis→Delta→fail 顺序有单测和故障测试 | STEP-PVAM-04-01/05 | TC-007 | EV-PVAM-04-02 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-03 | 30、30.00 可规范；30.1 阻断；29.99PV不活跃，30PV活跃 | STEP-PVAM-04-01/02/05 | TC-007 | EV-PVAM-04-03 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-04 | PE/SE/EAB/LB 在同一 user/period/run 下 Active 结果逐行一致 | STEP-PVAM-04-03/05 | TC-007、TC-017、TC-018、TC-019、TC-021 | EV-PVAM-04-04 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-05 | 各服务不读取持久化 Active 表或共享 snapshot 作为权威 | STEP-PVAM-04-03/05 | TC-007、TC-030 | EV-PVAM-04-05 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-06 | 外部 `IS_ACTIVE` 修改不改变奖金裁决，只产生审计差异 | STEP-PVAM-04-03/05 | TC-007 | EV-PVAM-04-06 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-07 | Elite Bonus 结果不因 Active 变化而变化 | STEP-PVAM-04-03/05 | TC-007、TC-014 | EV-PVAM-04-07 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-08 | SE 分母、EAB理论行、LB理论计算和TB结余语义不被改写 | STEP-PVAM-04-03/05 | TC-007、TC-013、TC-018、TC-019、TC-021 | EV-PVAM-04-08 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-09 | run manifest 包含 threshold raw/canonical/source/version/checksum | STEP-PVAM-04-04/05 | TC-007、TC-032 | EV-PVAM-04-09 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-10 | 配置在运行中变化不造成 run 内结果分裂 | STEP-PVAM-04-04/05 | TC-007 | EV-PVAM-04-10 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-11 | UAT fixture 明确标记来源与 checksum；不得据 fixture 将 2B 生产供给链标为 PASS | STEP-PVAM-04-05 | TC-007、TC-032 | EV-PVAM-04-11 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |

没有 STEP、TC 或 EV 映射的AC不得标记完成。任何含UAT的AC在未回传真实环境证据时只能为 `PENDING_TEST_ENV/BLOCKED`。

## 11. 风险、停工与回滚

### 11.1 风险清单

| 风险 | 触发条件 | 影响 | 预防措施 | 监测/证据 | 处置 |
|---|---|---|---|---|---|
| fixture误判生产链 | UAT只测读侧 | 虚假关闭CHK-DATA-006 | manifest标DEFERRED | evidence review | 保持BLOCKED |
| 多消费者接口不齐 | 任一继续用外部active | 结果漂移 | 全仓AST/callgraph | mismatch trace | 停工 |
| 门槛中途变化 | 重复getter | 同run分裂 | run冻结 | checksum | 回滚到旧run |

### 11.2 本任务强制停工条件

- HEAD、SQL blob、模型schema或上游TASK与受控基线不一致。
- 实施必须改变未批准的业务规则、精度、资格、分母、Country或发布职责才能继续。
- 需要修改排除文件/模块或扩大异常白名单才能通过测试。
- 关键mutation存活、SQL黄金样例出现未批准差异、幂等/原子/回滚断言失败。
- UAT权限、schema、数据或隔离条件不足；此时保持 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV`。

### 11.3 部署面与数据面回滚门禁

**当前可执行性：`BLOCKED_EXTERNAL_EVIDENCE`。** 当前材料没有给出真实部署系统、workload/release、镜像、配置对象和健康检查命令，因此不得以本地`export`或通用`git revert`冒充部署回滚。

部署前必须提供并签署`evidence/WORK-PVAM-04/rollback/ROLLBACK-MANIFEST-PVAM-v1.json`，至少包含：

- `deployment_system`、`environment`、`workload_id`、`release_before/after`、`image_before/after`；
- 精确的停止、回滚、恢复、健康检查和重新放量命令；
- Redis/Stream/ledger/run/manifest的备份或快照位置及SHA-256；
- 执行人、复核人、批准时间、允许的数据恢复范围；
- 命令dry-run/隔离演练的退出码和原始日志。

本任务数据面处置：停止奖金run；固定回滚前threshold checksum；恢复旧镜像后对受影响period干净重跑；不得物化共享Active结果或把fixture当生产供给链。

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
| EV-PVAM-04-01 | AC-01验收证据：全仓生产路径不再出现裸 `>=30` Active 判定 | STEP-PVAM-04-03/05 | evidence/WORK-PVAM-04/attempt-*/ac/AC-01/ | 待指派QA | PENDING |
| EV-PVAM-04-02 | AC-02验收证据：唯一 getter 的 Redis→2秒→Redis→Delta→fail 顺序有单测和故障测试 | STEP-PVAM-04-01/05 | evidence/WORK-PVAM-04/attempt-*/ac/AC-02/ | 待指派QA | PENDING |
| EV-PVAM-04-03 | AC-03验收证据：30、30.00 可规范；30.1 阻断；29.99PV不活跃，30PV活跃 | STEP-PVAM-04-01/02/05 | evidence/WORK-PVAM-04/attempt-*/ac/AC-03/ | 待指派QA | PENDING |
| EV-PVAM-04-04 | AC-04验收证据：PE/SE/EAB/LB 在同一 user/period/run 下 Active 结果逐行一致 | STEP-PVAM-04-03/05 | evidence/WORK-PVAM-04/attempt-*/ac/AC-04/ | 待指派QA | PENDING |
| EV-PVAM-04-05 | AC-05验收证据：各服务不读取持久化 Active 表或共享 snapshot 作为权威 | STEP-PVAM-04-03/05 | evidence/WORK-PVAM-04/attempt-*/ac/AC-05/ | 待指派QA | PENDING |
| EV-PVAM-04-06 | AC-06验收证据：外部 `IS_ACTIVE` 修改不改变奖金裁决，只产生审计差异 | STEP-PVAM-04-03/05 | evidence/WORK-PVAM-04/attempt-*/ac/AC-06/ | 待指派QA | PENDING |
| EV-PVAM-04-07 | AC-07验收证据：Elite Bonus 结果不因 Active 变化而变化 | STEP-PVAM-04-03/05 | evidence/WORK-PVAM-04/attempt-*/ac/AC-07/ | 待指派QA | PENDING |
| EV-PVAM-04-08 | AC-08验收证据：SE 分母、EAB理论行、LB理论计算和TB结余语义不被改写 | STEP-PVAM-04-03/05 | evidence/WORK-PVAM-04/attempt-*/ac/AC-08/ | 待指派QA | PENDING |
| EV-PVAM-04-09 | AC-09验收证据：run manifest 包含 threshold raw/canonical/source/version/checksum | STEP-PVAM-04-04/05 | evidence/WORK-PVAM-04/attempt-*/ac/AC-09/ | 待指派QA | PENDING |
| EV-PVAM-04-10 | AC-10验收证据：配置在运行中变化不造成 run 内结果分裂 | STEP-PVAM-04-04/05 | evidence/WORK-PVAM-04/attempt-*/ac/AC-10/ | 待指派QA | PENDING |
| EV-PVAM-04-11 | AC-11验收证据：UAT fixture 明确标记来源与 checksum；不得据 fixture 将 2B 生产供给链标为 PASS | STEP-PVAM-04-05 | evidence/WORK-PVAM-04/attempt-*/ac/AC-11/ | 待指派QA | PENDING |
| EV-PVAM-04-P01 | MonthActivePvProvider/ActiveRule源码 | 对应STEP/TC | evidence/WORK-PVAM-04/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-04-P02 | PE/SE/EAB/LB接入diff | 对应STEP/TC | evidence/WORK-PVAM-04/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-04-P03 | run threshold manifest | 对应STEP/TC | evidence/WORK-PVAM-04/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-04-P04 | DEV provider/Active测试 | 对应STEP/TC | evidence/WORK-PVAM-04/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-04-P05 | UAT跨奖项/失败链证据与2B缺口登记 | 对应STEP/TC | evidence/WORK-PVAM-04/attempt-*/package/ | 待指派QA | PENDING |

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
  --work-id "WORK-PVAM-04" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --out "evidence/WORK-PVAM-04/patch"
```

门禁必须证明：

1. `BASE_SHA` 是 `WORK_COMMIT_SHA` 的祖先；
2. 全部新增、修改、删除和 rename 的旧/新路径均落在 `WORK-PVAM-04` 批准 allowlist；
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
| STEP-PVAM-04-01 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-04-02 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-04-03 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-04-04 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-04-05 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |

### 13.2 实际验证

| 测试 | 环境 | 命令/版本 | 结果 | 证据 | 执行时间 |
|---|---|---|---|---|---|
| TC-PVAM-04-01 | DEV | 待执行 | NOT_RUN | EV-PVAM-04-* | 待执行 |
| TC-PVAM-04-02 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-04-* | 待执行 |
| TC-PVAM-04-03 | DEV | 待执行 | NOT_RUN | EV-PVAM-04-* | 待执行 |
| TC-PVAM-04-04 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-04-* | 待执行 |
| TC-PVAM-04-05 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-04-* | 待执行 |
| TC-PVAM-04-06 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-04-* | 待执行 |
| TC-PVAM-04-07 | UAT | 待执行 | NOT_RUN | EV-PVAM-04-* | 待执行 |
| TC-PVAM-04-08 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-04-* | 待执行 |

### 13.3 未完成项

| 项目 | 原因 | 风险 | 后续动作 | 责任人 | 截止时间 |
|---|---|---|---|---|---|
| UAT/外部材料 | 当前计划阶段未执行 | 不能关闭P0/P1 | 由WORK-08准入后执行 | 待指派 | 待批准 |

## 14. 偏离、发现项与上游回流

| 编号 | 类型 | 发现事实 | 是否影响业务/范围 | 临时动作 | 需要更新 | 最终裁决 |
|---|---|---|---|---|---|---|
| `DEV-PVAM-04-001` | `预留` | 待执行 | 待判断 | 停工/隔离 | WORK/TASK/DEC/REVIEW | 待裁决 |

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
| v1.0 | 2026-08-04 | 初版施工任务书 | `TASK-PVAM-04` + `PLAN-PVAM-v1.15` + 固定代码基线 | AI Agent（编制） | DRAFT |
| v1.1 | 2026-08-05 | 依据二轮核验报告完成定点修订并补齐治理追溯 | F-A/F-B/F-H/F-I/F-J/F-K/F-F/F-E/F-L/F-M/F-N 中适用项 | AI Agent（编制） | DRAFT |
| v1.2 | 2026-08-05 | 闭合 G-1：统一 `RecalcProcessResult` 类名并补齐 `should_ack`；历史版本曾调整施工套件审批状态，不改变 CHK/DEC/TASK/WORK 范围 | 历史会话声明（未形成可独立验证组织授权，现由 v1.3 取代） | AI Agent（编制） | SUPERSEDED |
| v1.3 | 2026-08-05 | 第四轮关闭 F3-01～F3-10：治理回退 DRAFT、Traceability v3、patch/DEV 双阶段、状态枚举及设计边界 | 三轮审查报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r6 | 2026-08-06 | 五轮 F5 定点修订：规范 v3 追溯、parent provenance/DEV CLI、控制状态字段及单一事实源 | 五轮审计报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r7 | 2026-08-06 | 六轮 S6：信任 registry 初版、归档哈希、临时目录与 Decimal finite 防护 | 六轮终局审计报告 | AI Agent（编制） | DRAFT |
| v1.3-r8 | 2026-08-06 | 七轮 B7：registry 发布信任根、四工件摘要、AC 来源保真及当前轮次引用 | 七轮终局审计报告 + B7 处置 | AI Agent（编制） | DRAFT |

<!-- END WORK-PVAM-04_monthActivePV与Active同源现算.md -->

---

<!-- BEGIN WORK-PVAM-05_Elite_SOURCE原子提交与发布批次.md -->

# WORK-PVAM-05 Elite SOURCE 原子性与外部发布证明施工任务书

> 文档定位：来源于待组织批准的 `TASK-PVAM-05`，在取得组织授权后转化为可执行施工说明。本文件不重新决定业务规则；实际结果只能写入执行记录与验证交付报告。

## 0. 填写与执行规则

1. 上游修改任务与本 v1.3 施工套件当前均为 `DRAFT`；没有组织授权前，本任务保持 `BLOCKED`，不得启动代码施工或部署。
2. 只实施 `R-008、R-011` 中已 `ACCEPTED` 或由来源 TASK 明确批准的条件代码事项。任何 `REJECTED / NEEDS_DECISION / DEFERRED / 未获 TASK 授权的 UAT_VERIFY` 只允许登记、验证或阻断，不得扩展代码范围。
3. 基线必须精确等于 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；发现漂移立即登记 `BLOCK-PVAM-05-BASELINE`。
4. 所有新文件/符号已在变更表标为“新增”；其余锚点均来自固定基线。
5. DEV替身不能冒充真实Kafka/Redis/Dask/GPU/MySQL UAT验证。

## 1. 文档信息与追溯关系

| 字段 | 内容 |
|---|---|
| 施工任务编号 | `WORK-PVAM-05` |
| 施工任务名称 | Elite SOURCE 原子性与外部发布证明 |
| 所属施工总方案 | `WORK-PLAN-PVAM_v1.3` |
| 来源修改任务 | `TASK-PVAM-05@MODPLAN-PVAM_v1.2`（authorization=PENDING_ORGANIZATIONAL_APPROVAL） |
| 来源问题 | `R-008、R-011` |
| 复核闭环追踪号 | `REM-008、REM-011 / W-008、W-011 / V-008、V-011` |
| 来源检查项 | `CHK-BIZ-005、CHK-BIZ-006、CHK-EVT-005、CHK-PUB-001` |
| 关联决策 | `DEC-007、DEC-008、DEC-011、DEC-017` |
| 代码基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| SQL基线 | `sql_uat/*@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，仅有效SQL |
| 文档版本 | `v1.3` |
| 负责人 | `待指派 / 实施工程师` |
| 复核人 | `待指派 / 架构与QA` |
| 当前状态 | `BLOCKED` |
| 文档治理状态 | `DRAFT`（`PENDING_ORGANIZATIONAL_APPROVAL`） |
| 前置任务 | WORK-PVAM-01、02、03 DEV_VERIFIED |
| 功能开关 | `ELITE_ATOMIC_LEDGER_V2` |

### 1.1 一对一追溯摘要

```text
CHK-BIZ-005、CHK-BIZ-006、CHK-EVT-005、CHK-PUB-001
  └─ R-008、R-011
       └─ DEC-007、DEC-008、DEC-011、DEC-017
            └─ TASK-PVAM-05 (DRAFT / PENDING_ORGANIZATIONAL_APPROVAL)
                 └─ WORK-PVAM-05
                      ├─ STEP-PVAM-05-01 / STEP-PVAM-05-02 / STEP-PVAM-05-03 / STEP-PVAM-05-04 / STEP-PVAM-05-05 / STEP-PVAM-05-06
                      ├─ TC-PVAM-05-01 / TC-PVAM-05-02 / TC-PVAM-05-03 / TC-PVAM-05-04 / TC-PVAM-05-05 / TC-PVAM-05-06 / TC-PVAM-05-07 / TC-PVAM-05-08
                      └─ EV-PVAM-05-01...
```

## 2. 施工任务生成依据

### 2.1 上游输入

| 输入 | 编号/版本 | 本任务使用的结论 | 状态 |
|---|---|---|---|
| 复核报告 | `Redemption_PV_Amount_Migration_d74_复核报告_v1.5` | R-008、R-011 的代码事实与严重级别 | CONFIRMED |
| 修改任务书 | `TASK-PVAM-05` | 采用方案、范围、排除项、AC | DRAFT（待组织授权） |
| 检查方案 | `PLAN-PVAM-v1.15` | CHK-BIZ-005、CHK-BIZ-006、CHK-EVT-005、CHK-PUB-001 | CONTROLLED |
| 正式决策 | DEC-007、DEC-008、DEC-011、DEC-017 | 只执行已关闭裁决；开放项阻断 | CLOSED / 按上游登记 |
| 代码/SQL快照 | 3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2 | 唯一施工对象 | FROZEN |
| 施工模板 | 总方案模板/专项模板 | 章节、状态、证据纪律 | CONTROLLED |

### 2.2 开工条件

- [ ] 当前 HEAD 精确为 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，工作树无未登记变更。
- [ ] `TASK-PVAM-05` 的人工批准记录已归档；本 `WORK` 已由施工负责人和复核人签署。
- [ ] 前置关系满足：WORK-PVAM-01、02、03 DEV_VERIFIED。
- [ ] 本任务涉及的接口、单位、精度、兼容和回滚边界已由上游任务固定。
- [ ] DEV测试依赖已安装；UAT项具备WORK-08生成的环境/数据/schema manifest。
- [ ] 功能开关默认关闭，回滚路径已演练。

未满足任一关键项时，本任务状态为 `BLOCKED`；不得用假设替代。

## 3. 问题事实与施工目标

### 3.1 已确认问题

| 项目 | 内容 |
|---|---|
| 预期行为 | 把 Elite stats、source assignment、revision/dirty、idempotency与outbox写入同一Redis权威提交；全量只在通过八项candidate gate后产生带checksum的ELITE_BONUS_BATCH_READY，等待外部receipt。 |
| 当前行为 | `EliteBonusService._track_bonus_source` 直接执行独立 `HSET` 与 `EXPIRE`。；`EliteBonusService.update_elite_bonus_incremental` 最后才通过 `_batch_save` 保存 stats；source 与 stats 不在同一权威提交。；`GlobalEliteBonusRecalculationService` 可在未提供 `db_executor` 时完成Redis重算并发 persisted=false 哨兵；正式candidate gate、PV_PSS、version、coverage及external receipt证明不完整。；DEC-008 已把关系库写入职责转给业务系统，本仓只能发布可验证的 batch/manifest，不能声称跨Redis/DB原子。 |
| 差异 | 当前实现缺少本任务批准的唯一合同、门禁或原子边界。 |
| 影响 | 金额/PV单位、奖金、并发一致性、发布或可恢复性，具体见来源问题。 |
| 严重级别 | P0 |
| 证据位置 | 固定代码基线 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；来源 `TASK-PVAM-05`；检查项 `CHK-BIZ-005、CHK-BIZ-006、CHK-EVT-005、CHK-PUB-001` |

### 3.2 已确认代码事实

- `EliteBonusService._track_bonus_source` 直接执行独立 `HSET` 与 `EXPIRE`。
- `EliteBonusService.update_elite_bonus_incremental` 最后才通过 `_batch_save` 保存 stats；source 与 stats 不在同一权威提交。
- `GlobalEliteBonusRecalculationService` 可在未提供 `db_executor` 时完成Redis重算并发 persisted=false 哨兵；正式candidate gate、PV_PSS、version、coverage及external receipt证明不完整。
- DEC-008 已把关系库写入职责转给业务系统，本仓只能发布可验证的 batch/manifest，不能声称跨Redis/DB原子。

### 3.3 本任务目标

把 Elite stats、source assignment、revision/dirty、idempotency与outbox写入同一Redis权威提交；全量只在通过八项candidate gate后产生带checksum的ELITE_BONUS_BATCH_READY，等待外部receipt。

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
| 1 | Elite增量 | `EliteBonusService.update_elite_bonus_incremental` | user_id/pv_delta | 调用_track_bonus_source后_batch_save | source可能先落 |
| 2 | SOURCE | `EliteBonusService._track_bonus_source` | source/bonus/layer | HSET+EXPIRE | 独立写 |
| 3 | stats | `EliteBonusService._batch_save` | models | Redis OM pipeline | 不含source/outbox |
| 4 | 全量 | `GlobalEliteBonusRecalculationService.settle_period` | period | 可选db_executor或persisted=false | gate/proof不足 |

### 4.2 当前错误形成点

当前链路在上述入口缺少本任务目标合同，导致已确认问题在写入、计算、路由或发布边界形成并传播。修改必须落在表中稳定符号或明确标记为“新增”的边界；不得通过外围日志掩盖。

### 4.3 受影响消费者

| 消费者 | 依赖内容 | 预期影响 | 是否同步修改 | 对应步骤/测试 |
|---|---|---|---|---|
| Elite增量重放 | assignment ledger | 需幂等revision | 是 | STEP-05-02/TC-015/016 |
| Global Elite全量 | candidate/manifest | 需gate与空batch | 是 | STEP-05-03/04 |
| 外部业务writer | ELITE_BONUS_BATCH_READY | 本仓只发batch，不写DB | 接口 | TC-029 |
| SettlementCoordinator | receipt/state | WORK-06承接 | 后续 | TC-024/029 |

## 5. 施工设计

### 5.1 采用方案

- 新增 `Model/User/EliteSourceAssignment.py`，唯一键 `(period_num, source_user_id)`，记录chosen bonus user、minimal layer、accepted revision、event hash、status。
- 将 `_track_bonus_source` 改成纯 mutation intent，不执行Redis命令；统一由 Redis Function/Lua 或经证明的 WATCH/MULTI/EXEC 提交。
- 权威提交包含 stats JSON、assignment、revision/dirty、idempotency/stage marker、outbox；任一点失败全不成。
- 新增 `User/EliteBonusCandidateBuilder.py` 和 `User/EliteBonusPublishBatch.py`，验证 PV_PSS、version、资格/gpv_real、source-clean、run/revision/coverage/config/topology八项证明。
- 空candidate也产生显式batch，external receipt前状态只能READY_FOR_EXTERNAL_PUBLISH。

选择理由：

- 与有效SQL、已关闭DEC及来源TASK目标一致。
- 采用 additive-first、显式version/manifest/feature flag，支持独立合入和回滚。
- 将纯函数、I/O适配、业务计算、权威提交和证据采集分层，便于DEV替身与UAT真实验证分别取证。

### 5.2 被否决方案

| 方案 | 不采用原因 | 来源 |
|---|---|---|
| 继续独立HSET | R-008仍存在 | R-008 |
| Python直接写MariaDB | 违反DEC-008职责边界 | DEC-008 |
| estimated_bonus>0即视为资格proof | 缺PV_PSS/version/source-clean | R-011 |
| 空结果不发batch | 外部无法清旧期 | CHK-PUB-001 |
| 声称Redis+DB原子 | 跨存储虚假保证 | DEC-008 |

### 5.3 修改后调用链与数据契约

| 边界 | 输入 | 处理 | 输出 | 断言/错误行为 | 责任符号 |
|---|---|---|---|---|---|
| 施工入口 | 固定commit + 批准TASK + ELITE_ATOMIC_LEDGER_V2 | 先执行基线/前置检查 | 受控diff | 任一前置失败即BLOCK | 新增三个模型/模块 |
| 核心处理 | strict version/type/period/run合同 | 按STEP顺序执行 | 可测试状态/事件/金额 | 非法类型、状态或proof fail-loud | 见CHG表 |
| 证据出口 | 命令、输入、输出、状态前后 | WORK-08 schema封装 | EV包+SHA-256 | 缺原始证据不得PASS | `uat/scripts/*` |

## 6. 文件与符号级变更清单

| 变更编号 | 文件 | 类/函数/字段/表 | 类型 | 修改前行为 | 要求的修改 | 修改后行为 | 禁止行为 |
|---|---|---|---|---|---|---|---|
| CHG-01 | `Model/User/EliteSourceAssignment.py` | assignment模型/序列化 | 新增 | 不存在 | 定义唯一归属与revision状态 | 可重放审计 | 不得直接当正式DB行 |
| CHG-02 | `User/EliteBonusService.py` | `_track_bonus_source`、`update_elite_bonus_incremental`、`_batch_save` | 修改 | source独立HSET | 生成intent并统一权威提交 | 全成或全不成 | 不得吞WatchError |
| CHG-03 | `User/EliteRedisCommit.py` | `commit_incremental_stage` | 新增 | 不存在 | 封装Function/Lua或WATCH事务 | 单一提交API | 不得调用MariaDB |
| CHG-04 | `User/EliteBonusCandidateBuilder.py` | candidate gate | 新增 | 不存在 | 执行八项proof与reconciliation | 不合格阻断 | 不得用金额代替资格 |
| CHG-05 | `User/EliteBonusPublishBatch.py` | batch/manifest模型 | 新增 | 不存在 | 生成nonempty/empty batch、counts/checksum | external可校验 | 不得标persisted=true |
| CHG-06 | `User/GlobalEliteBonusRecalculationService.py` | `settle_period`、`_process_parent_batch`、`_emit_settlement_done` | 修改 | 重算后DONE/可选db_executor | 构建candidate/batch并发ready事件 | 等待WORK-06 receipt | 不得生产调用db_executor |
| CHG-07 | `User/EliteBonusService.py::snapshot_period_to_db` | 旧接口隔离 | 修改 | 本仓可调用DB executor | 标legacy/test-only并从生产调用图移除 | 职责边界清晰 | 不得删除历史测试入口 |
| CHG-08 | `User/Test/test_elite_atomic_commit.py` / `User/Test/test_elite_publish_batch.py` | pytest | 新增 | 不存在 | 命令点故障、revision、空batch、gate | 可重复验证 | 不得用mock证明跨存储原子 |

### 6.1 固定基线锚点复验

| 文件与符号 | 基线事实 | 施工动作 |
|---|---|---|
| `EliteBonusService._track_bonus_source` | 独立`hget/hset/expire`，立即写Redis | 改为生成assignment命令，不在函数内提交 |
| `EliteBonusService._batch_save` | 单独pipeline保存stats | 扩展为唯一原子提交入口 |
| `GlobalEliteBonusRecalculationService._track_bonus_source` | 全量路径可在传入pipeline中写SOURCE | 与增量共享统一assignment/序列化合同 |
| `snapshot_period_to_db`/`db_executor` | 当前代码宣称本仓可写关系库 | 生产路径隔离；本仓输出batch/manifest，业务系统回receipt |

### 6.2 原子实现选择

本终稿固化使用`WATCH/MULTI/EXEC`，而不是直接用Lua重写redis-om JSON。理由是基线已使用`model.save(pipeline=pipe)`，该路径能保持redis-om序列化兼容；SOURCE最小layer读取、幂等marker和冲突检查放在WATCH阶段，stats JSON、SOURCE HSET/EXPIRE、revision、dirty、stage marker和outbox在同一MULTI内排队。发生`WatchError`必须整单重读并有限重试，禁止只补写SOURCE或只补写stats。

伪代码合同：

```python
for attempt in range(max_retries):
    with redis_conn.pipeline(transaction=True) as pipe:
        try:
            pipe.watch(*watched_keys)
            current = load_and_validate_under_watch(pipe)
            commands = build_complete_commit(current, event)
            pipe.multi()
            for model in commands.models:
                model.save(pipeline=pipe)
            queue_source_assignment(pipe, commands.assignment)
            queue_revision_dirty_stage(pipe, commands)
            queue_outbox(pipe, commands.outbox_event)
            pipe.execute()
            break
        except WatchError:
            if attempt + 1 == max_retries:
                raise
```

### 6.3 Candidate与receipt门禁

- Candidate必须独立证明PV_PSS、七条Elite gate、version=2、source-clean、revision/dirty、row/key/amount/checksum。
- 缺PV_PSS权威来源时状态为`BLOCKED_CANDIDATE_PROOF`；不得以`gpv_real>0`近似。
- 空candidate也生成batch，明确表达清空该period旧结果。
- 本仓只发`BATCH_READY`及manifest；业务系统返回签名/可校验receipt后，WORK-06才能转PUBLISHED。

> **DEV 执行口径：** `05_CONTROL/check_baseline_preflight.sh` 与 `05_CONTROL/validate_work_dev.sh` 是唯一强制门禁。STEP 中列出的 `py_compile`、`compileall` 或 `pytest` 命令仅是附加局部检查，不得替代 parent-tree、scope、patch、tree-hash 与专属测试门禁。

## 7. 可执行施工步骤

### STEP-PVAM-05-01：定义assignment与batch模型

- 目的：定义assignment与batch模型，落实 `TASK-PVAM-05` 的已批准目标。
- 前置条件：WORK-01/02/03完成
- 修改文件：新增三个模型/模块
- 目标符号：数据合同
- 精确操作：
1. 字段含period/run/generation/source/revision/hash/layer/status/counts/checksum
2. 类型均严格。
- 必须保持：不设计业务DB表
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Model/User/EliteSourceAssignment.py User/EliteBonusPublishBatch.py User/EliteBonusCandidateBuilder.py`
- 本步单元验证：`TC-PVAM-05-01/02`
- 完成证据：`EV-PVAM-05-01`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：唯一键/字段与TASK不一致则BLOCK

### STEP-PVAM-05-02：实现Redis原子提交

- 目的：实现Redis原子提交，落实 `TASK-PVAM-05` 的已批准目标。
- 前置条件：STEP-05-01
- 修改文件：`User/EliteRedisCommit.py`、`EliteBonusService.py`
- 目标符号：commit API/_track/_batch
- 精确操作：
1. 把source改为intent
2. 通过单一原子单元写stats/assignment/revision/dirty/idempotency/outbox。
- 必须保持：不允许先source后stats
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile User/EliteRedisCommit.py User/EliteBonusService.py`
- 本步单元验证：`TC-PVAM-05-03/04`
- 完成证据：`EV-PVAM-05-02`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任一故障产生半状态立即停工

### STEP-PVAM-05-03：实现candidate八项gate

- 目的：实现candidate八项gate，落实 `TASK-PVAM-05` 的已批准目标。
- 前置条件：STEP-05-01/WORK-01~04接口
- 修改文件：`User/EliteBonusCandidateBuilder.py`
- 目标符号：build/validate
- 精确操作：
1. 逐条校验PV_PSS、version、资格、gpv_real、source-clean、run/revision/coverage/config/topology
2. 生成reconciliation。
- 必须保持：不得只看bonus>0
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile User/EliteBonusCandidateBuilder.py`
- 本步单元验证：`TC-PVAM-05-05/06`
- 完成证据：`EV-PVAM-05-03`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：权威PV_PSS不可得则BLOCK

### STEP-PVAM-05-04：重构全量为batch-ready

- 目的：重构全量为batch-ready，落实 `TASK-PVAM-05` 的已批准目标。
- 前置条件：STEP-05-02/03
- 修改文件：`GlobalEliteBonusRecalculationService.py`
- 目标符号：settle/emit
- 精确操作：
1. 移除生产db_executor路径
2. 构建非空/空batch，写manifest与outbox
3. 状态交WORK-06。
- 必须保持：不写PUBLISHED/DONE persisted true
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile User/GlobalEliteBonusRecalculationService.py`
- 本步单元验证：`TC-PVAM-05-06/07`
- 完成证据：`EV-PVAM-05-04`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：无batch却标完成立即回滚

### STEP-PVAM-05-05：隔离旧writer并补扫描

- 目的：隔离旧writer并补扫描，落实 `TASK-PVAM-05` 的已批准目标。
- 前置条件：STEP-05-04
- 修改文件：`EliteBonusService.py`与调用图测试
- 目标符号：snapshot接口
- 精确操作：
1. 保留测试兼容但加显式legacy/test-only标记
2. 生产入口扫描不得调用。
- 必须保持：不删除历史对账能力
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`grep -R "snapshot_period_to_db" -n --include="*.py" .`
- 本步单元验证：`TC-PVAM-05-08`
- 完成证据：`EV-PVAM-05-05`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：发现生产调用则BLOCK

### STEP-PVAM-05-06：故障/重放/空批测试

- 目的：故障/重放/空批测试，落实 `TASK-PVAM-05` 的已批准目标。
- 前置条件：STEP-05-02~05
- 修改文件：新增测试
- 目标符号：pytest
- 精确操作：
1. 在每个Redis命令点注错
2. 重复revision、hash冲突、退款、reassign、empty candidate。
- 必须保持：测试不得跳过
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m pytest -q User/Test/test_elite_atomic_commit.py User/Test/test_elite_publish_batch.py`
- 本步单元验证：`TC-PVAM-05-01~08`
- 完成证据：`EV-PVAM-05-06`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：mutation存活或半状态不得合并

## 8. 数据迁移、兼容与重跑

### 8.1 数据变化

| 对象 | 旧格式/状态 | 新格式/状态 | 转换位置 | 版本识别 | 异常数据策略 |
|---|---|---|---|---|---|
| Elite source hash | 独立HSET | revisioned assignment ledger | Redis权威提交 | event/revision/hash | 冲突阻断 |
| Elite发布 | 可选DB writer/DONE | batch+manifest+external receipt | 全量收尾 | batch/run/generation | receipt前不PUBLISHED |

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
| TC-PVAM-05-01 | 契约 | assignment唯一键 | 同period/source两候选layer3/1 | 最终仅layer1，revision/hash可审计 | STEP-05-01 | DEV | NOT_RUN |
| TC-PVAM-05-02 | 契约 | batch checksum | 固定bonus/source行集 | 排序无关checksum稳定，counts精确 | STEP-05-01 | DEV | NOT_RUN |
| TC-PVAM-05-03 | 故障注入 | stats后source前失败 | 任一Redis命令异常 | stats/source/revision/outbox均无新状态 | STEP-05-02 | DEV+UAT | NOT_RUN |
| TC-PVAM-05-04 | 幂等 | 同event/revision重放 | 相同hash重复/不同hash | 相同no-op；不同hash fail-loud | STEP-05-02 | DEV+UAT | NOT_RUN |
| TC-PVAM-05-05 | gate | PV_PSS=0或version缺失 | 有estimated bonus脏值 | candidate阻断且产生明确proof failure | STEP-05-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-05-06 | SOURCE重归属 | 旧upline→新upline | 同source仅最新accepted归属；总SOURCE_PV不双计 | STEP-05-03/04 | DEV+UAT | NOT_RUN |
| TC-PVAM-05-07 | 空快照 | 本期无候选，外部旧行存在fixture | 产生empty batch，外部模拟器清旧行 | STEP-05-04 | DEV+UAT | NOT_RUN |
| TC-PVAM-05-08 | 静态 | DB writer边界 | 全仓调用图 | 生产无db_executor/snapshot_period_to_db调用；事件persisted=false | STEP-05-05 | DEV | NOT_RUN |

受控检查方案用例映射：`TC-009, TC-010, TC-014, TC-015, TC-016, TC-023, TC-025, TC-026, TC-029, TC-030, TC-031`。`TC-000` 为 RETIRED，不执行、不计完成率。

### 9.2 开发环境自动验证

```bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_SHA="3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2"
: "${WORK_COMMIT_SHA:?set the implementation commit for WORK-PVAM-05}"
: "${PARENT_COMMIT_SHA:?set the controlled parent commit; root WORK uses BASE_SHA}"
: "${PARENT_TREE_SHA:?set the tree of PARENT_COMMIT_SHA}"
: "${PARENT_PROVENANCE_JSON:?set schema-v2 parent provenance JSON}"
: "${APPROVED_COMMIT_REGISTRY_JSON:?set canonical WORK_APPROVED_COMMIT_REGISTRY.json}"
CONTROL_ROOT="${PVAM_CONTROL_ROOT:?point to the released 05_CONTROL directory}"

# Phase A：只验证固定基线和既有锚点，不要求 Common/Settlement/Ops 等未来目录存在。
bash "$CONTROL_ROOT/check_baseline_preflight.sh" \
  --repo "$REPO_ROOT" --base "$BASE_SHA" --work-id "WORK-PVAM-05"

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
  --work-id "WORK-PVAM-05" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --test-command-file "$CONTROL_ROOT/work-test-commands/WORK-PVAM-05.sh" \
  --out "evidence/WORK-PVAM-05/dev"
```

#### 9.2.1 必须落地的关键 `assert` 契约

以下断言骨架必须进入本任务列出的 pytest 文件；fixture 由测试文件实现，不得用复制生产公式的替身替代被测符号。

```python
import pytest
from User.EliteRedisCommit import EliteRedisCommit


def test_elite_authority_commit_is_atomic(fake_redis, elite_commit_payload) -> None:
    commit = EliteRedisCommit(fake_redis)
    before = fake_redis.snapshot()
    fake_redis.inject_failure(command_index=3)
    with pytest.raises(RuntimeError):
        commit.commit_incremental_stage(elite_commit_payload)
    assert fake_redis.snapshot() == before
    fake_redis.clear_failure()
    commit.commit_incremental_stage(elite_commit_payload)
    once = fake_redis.snapshot()
    commit.commit_incremental_stage(elite_commit_payload)
    assert fake_redis.snapshot() == once
```

通过标准：所有命令 exit code 0；pytest 无未解释 skip；证据schema校验通过。GPU/Dask/真实Redis/Kafka/MySQL未在DEV执行时必须标注 `NOT_RUN/PENDING_TEST_ENV`。

### 9.3 测试环境手工执行包

#### ENV-TC-PVAM-05-01：Elite原子/重放/candidate/空批

- 对应受控测试：`TC-014、TC-015、TC-016、TC-026、TC-029`
- 环境版本：由 `uat/environment_manifest.yaml` 固定 Python/CUDA/RAPIDS/Dask/Redis/Kafka/DB/镜像/commit。
- 前置服务与数据：Redis隔离；图与PV_PSS fixture；外部writer模拟器非生产
- 清理/隔离：必须使用专用 topic/group、Redis前缀、period/run_id；禁止复用生产数据。
- 执行命令：

```bash
RUN_ID=work05-$(date +%Y%m%d%H%M%S)
bash uat/scripts/run_work_uat.sh --work WORK-PVAM-05 --run-id "$RUN_ID" --tc TC-014,TC-015,TC-016,TC-026,TC-029
```

- SQL/数据库证据命令（仅在专用 UAT schema 和 WORK-08 manifest 校验通过后执行；N/A 项只保留说明）：

```bash
test "${UAT_SCHEMA_ISOLATED:?must equal 1}" = "1"
mysql --defaults-extra-file="${MYSQL_CNF:?}" --batch --raw <<SQL
CALL CALC_BE_E(${PERIOD_NUM:?}, ${CALC_MONTH:?});
SELECT PERIOD_NUM, CALC_MONTH, USER_ID, GPV_REAL, E_RATE, BONUS_E
  FROM AR_CALC_BONUS_E
 WHERE PERIOD_NUM = ${PERIOD_NUM}
 ORDER BY USER_ID;
SELECT PERIOD_NUM, CALC_MONTH, BONUS_USER_ID, SOURCE_USER_ID, SOURCE_PV, BONUS_LAYER
  FROM AR_CALC_BONUS_E_SOURCE
 WHERE PERIOD_NUM = ${PERIOD_NUM}
 ORDER BY SOURCE_USER_ID, BONUS_LAYER;
SQL
```

- 执行步骤：
1. 构造七条Elite gate正反例
2. 注入Redis提交点故障与重复revision
3. 执行重归属/退款/空candidate
4. 运行外部writer模拟器并回传receipt fixture
- 精确预期：
- 无半提交/双计
- candidate缺任一proof即阻断
- receipt前不PUBLISHED；empty batch可清旧
- 必须回传：完整命令、exit code、stdout/stderr、JUnit/JSON、输入fixture SHA-256、代码commit、镜像、环境版本、执行起止时间、Redis/DB/Kafka/Dask前后证据。
- 失败停止与清理：停止专用consumer/job；保留PEL/状态和证据；禁止在未分析前清理失败现场；按第11节回滚。

### 9.4 SQL 对账样例

| 样例 | SQL输入/来源 | SQL预期 | Python预期 | 比较口径 | 允许差异 |
|---|---|---|---|---|---|
| Elite候选 | PV_PSS=0, PV_PCS=1000 | CALC_BE_E不插入NET | candidate=0 | PV_PSS gate | 0 rows |
| Elite奖金 | GPV_REAL=1000.99, rate=15% | TRUNCATE=150.14 | 15014 cents | 向零两位 | 0 cents |
| SOURCE | 同source多个layer | ROW_NUMBER order BONUS_LAYER取最小 | assignment minimal layer | source唯一 | 0 rows |

## 10. 验收标准映射

| 验收编号 | 来源TASK验收项 | 实现步骤 | 测试用例 | 所需证据 | 环境 | 通过条件 |
|---|---|---|---|---|---|---|
| AC-01 | `_track_bonus_source` 不再直接执行 HSET/EXPIRE | STEP-PVAM-05-02/06 | TC-026、TC-031 | EV-PVAM-05-01 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-02 | 任一 Redis 命令点故障时 stats/SOURCE/revision/outbox 全成或全不成 | STEP-PVAM-05-02/06 | TC-026 | EV-PVAM-05-02 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-03 | 重复 normalized event/revision 幂等，冲突 hash fail-loud | STEP-PVAM-05-02/06 | TC-015、TC-016、TC-023、TC-026 | EV-PVAM-05-03 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-04 | 每个 source 最多一个正式 assignment，minimal layer 可复核 | STEP-PVAM-05-01/02/06 | TC-015、TC-016 | EV-PVAM-05-04 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-05 | candidate 缺 PV_PSS/version/run/revision/coverage 任一字段时阻断 | STEP-PVAM-05-03/06 | TC-014、TC-029 | EV-PVAM-05-05 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-06 | 奖金和 SOURCE counts/checksum 与 manifest 一致 | STEP-PVAM-05-03/04/06 | TC-015、TC-016、TC-029 | EV-PVAM-05-06 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-07 | 空快照生成显式 batch，模拟器可清空旧正式结果 | STEP-PVAM-05-04/06 | TC-029 | EV-PVAM-05-07 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-08 | 生产代码不调用 MariaDB db_executor；旧接口隔离并有扫描证明 | STEP-PVAM-05-05/06 | TC-029、TC-030 | EV-PVAM-05-08 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-09 | receipt 不存在时只到 `READY_FOR_EXTERNAL_PUBLISH`，不标 PUBLISHED | STEP-PVAM-05-04/06 | TC-029 | EV-PVAM-05-09 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-10 | DEC-011 数量变化/输出变化传播测试保持通过 | STEP-PVAM-05-03/06 | TC-009、TC-010 | EV-PVAM-05-10 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-11 | 同一 run/generation 重跑幂等；新 generation 新 batch，不覆盖旧审计 | STEP-PVAM-05-01/02/03/04/06 | TC-015、TC-016、TC-025、TC-029 | EV-PVAM-05-11 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |

没有 STEP、TC 或 EV 映射的AC不得标记完成。任何含UAT的AC在未回传真实环境证据时只能为 `PENDING_TEST_ENV/BLOCKED`。

## 11. 风险、停工与回滚

### 11.1 风险清单

| 风险 | 触发条件 | 影响 | 预防措施 | 监测/证据 | 处置 |
|---|---|---|---|---|---|
| Redis OM序列化与Lua不兼容 | 脚本直写格式偏差 | reader失败 | 先做序列化golden test；可选WATCH方案 | roundtrip证据 | BLOCK并选经批准方案 |
| PV_PSS来源缺失 | candidate gate无权威输入 | 错误发奖 | 硬阻断 | proof failure | BLOCK |
| external receipt伪造 | 事件被当已落库 | 假发布 | WORK-06验证签名/checksum | receipt审计 | IN_DOUBT |

### 11.2 本任务强制停工条件

- HEAD、SQL blob、模型schema或上游TASK与受控基线不一致。
- 实施必须改变未批准的业务规则、精度、资格、分母、Country或发布职责才能继续。
- 需要修改排除文件/模块或扩大异常白名单才能通过测试。
- 关键mutation存活、SQL黄金样例出现未批准差异、幂等/原子/回滚断言失败。
- UAT权限、schema、数据或隔离条件不足；此时保持 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV`。

### 11.3 部署面与数据面回滚门禁

**当前可执行性：`BLOCKED_EXTERNAL_EVIDENCE`。** 当前材料没有给出真实部署系统、workload/release、镜像、配置对象和健康检查命令，因此不得以本地`export`或通用`git revert`冒充部署回滚。

部署前必须提供并签署`evidence/WORK-PVAM-05/rollback/ROLLBACK-MANIFEST-PVAM-v1.json`，至少包含：

- `deployment_system`、`environment`、`workload_id`、`release_before/after`、`image_before/after`；
- 精确的停止、回滚、恢复、健康检查和重新放量命令；
- Redis/Stream/ledger/run/manifest的备份或快照位置及SHA-256；
- 执行人、复核人、批准时间、允许的数据恢复范围；
- 命令dry-run/隔离演练的退出码和原始日志。

本任务数据面处置：冻结Elite写入口；保留revisioned ledger、SOURCE与outbox；若发布批次已产生则进入IN_DOUBT并按receipt决定重放或废弃，不直接删除证据。

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
| EV-PVAM-05-01 | AC-01验收证据：`_track_bonus_source` 不再直接执行 HSET/EXPIRE | STEP-PVAM-05-02/06 | evidence/WORK-PVAM-05/attempt-*/ac/AC-01/ | 待指派QA | PENDING |
| EV-PVAM-05-02 | AC-02验收证据：任一 Redis 命令点故障时 stats/SOURCE/revision/outbox 全成或全不成 | STEP-PVAM-05-02/06 | evidence/WORK-PVAM-05/attempt-*/ac/AC-02/ | 待指派QA | PENDING |
| EV-PVAM-05-03 | AC-03验收证据：重复 normalized event/revision 幂等，冲突 hash fail-loud | STEP-PVAM-05-02/06 | evidence/WORK-PVAM-05/attempt-*/ac/AC-03/ | 待指派QA | PENDING |
| EV-PVAM-05-04 | AC-04验收证据：每个 source 最多一个正式 assignment，minimal layer 可复核 | STEP-PVAM-05-01/02/06 | evidence/WORK-PVAM-05/attempt-*/ac/AC-04/ | 待指派QA | PENDING |
| EV-PVAM-05-05 | AC-05验收证据：candidate 缺 PV_PSS/version/run/revision/coverage 任一字段时阻断 | STEP-PVAM-05-03/06 | evidence/WORK-PVAM-05/attempt-*/ac/AC-05/ | 待指派QA | PENDING |
| EV-PVAM-05-06 | AC-06验收证据：奖金和 SOURCE counts/checksum 与 manifest 一致 | STEP-PVAM-05-03/04/06 | evidence/WORK-PVAM-05/attempt-*/ac/AC-06/ | 待指派QA | PENDING |
| EV-PVAM-05-07 | AC-07验收证据：空快照生成显式 batch，模拟器可清空旧正式结果 | STEP-PVAM-05-04/06 | evidence/WORK-PVAM-05/attempt-*/ac/AC-07/ | 待指派QA | PENDING |
| EV-PVAM-05-08 | AC-08验收证据：生产代码不调用 MariaDB db_executor；旧接口隔离并有扫描证明 | STEP-PVAM-05-05/06 | evidence/WORK-PVAM-05/attempt-*/ac/AC-08/ | 待指派QA | PENDING |
| EV-PVAM-05-09 | AC-09验收证据：receipt 不存在时只到 `READY_FOR_EXTERNAL_PUBLISH`，不标 PUBLISHED | STEP-PVAM-05-04/06 | evidence/WORK-PVAM-05/attempt-*/ac/AC-09/ | 待指派QA | PENDING |
| EV-PVAM-05-10 | AC-10验收证据：DEC-011 数量变化/输出变化传播测试保持通过 | STEP-PVAM-05-03/06 | evidence/WORK-PVAM-05/attempt-*/ac/AC-10/ | 待指派QA | PENDING |
| EV-PVAM-05-11 | AC-11验收证据：同一 run/generation 重跑幂等；新 generation 新 batch，不覆盖旧审计 | STEP-PVAM-05-01/02/03/04/06 | evidence/WORK-PVAM-05/attempt-*/ac/AC-11/ | 待指派QA | PENDING |
| EV-PVAM-05-P01 | Elite assignment/commit/candidate/batch模块 | 对应STEP/TC | evidence/WORK-PVAM-05/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-05-P02 | Elite增量/全量diff | 对应STEP/TC | evidence/WORK-PVAM-05/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-05-P03 | DB writer隔离调用图 | 对应STEP/TC | evidence/WORK-PVAM-05/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-05-P04 | DEV故障/重放测试 | 对应STEP/TC | evidence/WORK-PVAM-05/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-05-P05 | UAT Elite SQL/source/empty batch证据 | 对应STEP/TC | evidence/WORK-PVAM-05/attempt-*/package/ | 待指派QA | PENDING |

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
  --work-id "WORK-PVAM-05" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --out "evidence/WORK-PVAM-05/patch"
```

门禁必须证明：

1. `BASE_SHA` 是 `WORK_COMMIT_SHA` 的祖先；
2. 全部新增、修改、删除和 rename 的旧/新路径均落在 `WORK-PVAM-05` 批准 allowlist；
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
| STEP-PVAM-05-01 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-05-02 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-05-03 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-05-04 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-05-05 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-05-06 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |

### 13.2 实际验证

| 测试 | 环境 | 命令/版本 | 结果 | 证据 | 执行时间 |
|---|---|---|---|---|---|
| TC-PVAM-05-01 | DEV | 待执行 | NOT_RUN | EV-PVAM-05-* | 待执行 |
| TC-PVAM-05-02 | DEV | 待执行 | NOT_RUN | EV-PVAM-05-* | 待执行 |
| TC-PVAM-05-03 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-05-* | 待执行 |
| TC-PVAM-05-04 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-05-* | 待执行 |
| TC-PVAM-05-05 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-05-* | 待执行 |
| TC-PVAM-05-06 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-05-* | 待执行 |
| TC-PVAM-05-07 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-05-* | 待执行 |
| TC-PVAM-05-08 | DEV | 待执行 | NOT_RUN | EV-PVAM-05-* | 待执行 |

### 13.3 未完成项

| 项目 | 原因 | 风险 | 后续动作 | 责任人 | 截止时间 |
|---|---|---|---|---|---|
| UAT/外部材料 | 当前计划阶段未执行 | 不能关闭P0/P1 | 由WORK-08准入后执行 | 待指派 | 待批准 |

## 14. 偏离、发现项与上游回流

| 编号 | 类型 | 发现事实 | 是否影响业务/范围 | 临时动作 | 需要更新 | 最终裁决 |
|---|---|---|---|---|---|---|
| `DEV-PVAM-05-001` | `预留` | 待执行 | 待判断 | 停工/隔离 | WORK/TASK/DEC/REVIEW | 待裁决 |

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
| v1.0 | 2026-08-04 | 初版施工任务书 | `TASK-PVAM-05` + `PLAN-PVAM-v1.15` + 固定代码基线 | AI Agent（编制） | DRAFT |
| v1.1 | 2026-08-05 | 依据二轮核验报告完成定点修订并补齐治理追溯 | F-A/F-B/F-H/F-I/F-J/F-K/F-F/F-E/F-L/F-M/F-N 中适用项 | AI Agent（编制） | DRAFT |
| v1.2 | 2026-08-05 | 闭合 G-1：统一 `RecalcProcessResult` 类名并补齐 `should_ack`；历史版本曾调整施工套件审批状态，不改变 CHK/DEC/TASK/WORK 范围 | 历史会话声明（未形成可独立验证组织授权，现由 v1.3 取代） | AI Agent（编制） | SUPERSEDED |
| v1.3 | 2026-08-05 | 第四轮关闭 F3-01～F3-10：治理回退 DRAFT、Traceability v3、patch/DEV 双阶段、状态枚举及设计边界 | 三轮审查报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r6 | 2026-08-06 | 五轮 F5 定点修订：规范 v3 追溯、parent provenance/DEV CLI、控制状态字段及单一事实源 | 五轮审计报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r7 | 2026-08-06 | 六轮 S6：信任 registry 初版、归档哈希、临时目录与 Decimal finite 防护 | 六轮终局审计报告 | AI Agent（编制） | DRAFT |
| v1.3-r8 | 2026-08-06 | 七轮 B7：registry 发布信任根、四工件摘要、AC 来源保真及当前轮次引用 | 七轮终局审计报告 + B7 处置 | AI Agent（编制） | DRAFT |

<!-- END WORK-PVAM-05_Elite_SOURCE原子提交与发布批次.md -->

---

<!-- BEGIN WORK-PVAM-06_结算状态机统一Guard与Topology接线.md -->

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

<!-- END WORK-PVAM-06_结算状态机统一Guard与Topology接线.md -->

---

<!-- BEGIN WORK-PVAM-07A_Consumer_ACK紧急修复.md -->

# WORK-PVAM-07A Recalc Consumer ACK 紧急 fail-closed 修复施工任务书

> 文档定位：来源于待组织批准的 `TASK-PVAM-07A`，在取得组织授权后转化为可执行施工说明。本文件不重新决定业务规则；实际结果只能写入执行记录与验证交付报告。

## 0. 填写与执行规则

1. 上游修改任务与本 v1.3 施工套件当前均为 `DRAFT`；没有组织授权前，本任务保持 `BLOCKED`，不得启动代码施工或部署。
2. 只实施 `R-012A`（parent=`R-012`，紧急子集） 中已 `ACCEPTED` 或由来源 TASK 明确批准的条件代码事项。任何 `REJECTED / NEEDS_DECISION / DEFERRED / 未获 TASK 授权的 UAT_VERIFY` 只允许登记、验证或阻断，不得扩展代码范围。
3. 基线必须精确等于 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；发现漂移立即登记 `BLOCK-PVAM-07A-BASELINE`。
4. 所有新文件/符号已在变更表标为“新增”；其余锚点均来自固定基线。
5. DEV替身不能冒充真实Kafka/Redis/Dask/GPU/MySQL UAT验证。

## 1. 文档信息与追溯关系

| 字段 | 内容 |
|---|---|
| 施工任务编号 | `WORK-PVAM-07A` |
| 施工任务名称 | Recalc Consumer ACK 紧急 fail-closed 修复 |
| 所属施工总方案 | `WORK-PLAN-PVAM_v1.3` |
| 来源修改任务 | `TASK-PVAM-07A@MODPLAN-PVAM_v1.2`（authorization=PENDING_ORGANIZATIONAL_APPROVAL） |
| 来源问题 | `R-012A`（parent=`R-012`，紧急子集） |
| 复核闭环追踪号 | `REM-012A / W-012A / V-012A`（R-012 紧急子集） |
| 来源检查项 | `CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-001、CHK-TEST-003` |
| 关联决策 | `DEC-010` |
| 代码基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| SQL基线 | `sql_uat/*@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，仅有效SQL |
| 文档版本 | `v1.3` |
| 负责人 | `待指派 / 实施工程师` |
| 复核人 | `待指派 / 架构与QA` |
| 当前状态 | `BLOCKED` |
| 文档治理状态 | `DRAFT`（`PENDING_ORGANIZATIONAL_APPROVAL`） |
| 前置任务 | 无金额域依赖；可与WORK-01并行 |
| 功能开关 | `RECALC_ACK_FAIL_CLOSED_V1` |

### 1.1 一对一追溯摘要

```text
CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-001、CHK-TEST-003
  └─ R-012A（parent=R-012，紧急子集）
       └─ DEC-010
            └─ TASK-PVAM-07A (DRAFT / PENDING_ORGANIZATIONAL_APPROVAL)
                 └─ WORK-PVAM-07A
                      ├─ STEP-PVAM-07A-01 / STEP-PVAM-07A-02 / STEP-PVAM-07A-03 / STEP-PVAM-07A-04
                      ├─ TC-PVAM-07A-01 / TC-PVAM-07A-02 / TC-PVAM-07A-03 / TC-PVAM-07A-04 / TC-PVAM-07A-05 / TC-PVAM-07A-06 / TC-PVAM-07A-07
                      └─ EV-PVAM-07A-01...
```

## 2. 施工任务生成依据

### 2.1 上游输入

| 输入 | 编号/版本 | 本任务使用的结论 | 状态 |
|---|---|---|---|
| 复核报告 | `Redemption_PV_Amount_Migration_d74_复核报告_v1.5` | R-012A（parent=R-012，紧急子集） 的代码事实与严重级别 | CONFIRMED |
| 修改任务书 | `TASK-PVAM-07A` | 采用方案、范围、排除项、AC | DRAFT（待组织授权） |
| 检查方案 | `PLAN-PVAM-v1.15` | CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-001、CHK-TEST-003 | CONTROLLED |
| 正式决策 | DEC-010 | 只执行已关闭裁决；开放项阻断 | CLOSED / 按上游登记 |
| 代码/SQL快照 | 3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2 | 唯一施工对象 | FROZEN |
| 施工模板 | 总方案模板/专项模板 | 章节、状态、证据纪律 | CONTROLLED |

### 2.2 开工条件

- [ ] 当前 HEAD 精确为 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，工作树无未登记变更。
- [ ] `TASK-PVAM-07A` 的人工批准记录已归档；本 `WORK` 已由施工负责人和复核人签署。
- [ ] 前置关系满足：无金额域依赖；可与WORK-01并行。
- [ ] 本任务涉及的接口、单位、精度、兼容和回滚边界已由上游任务固定。
- [ ] DEV测试依赖已安装；UAT项具备WORK-08生成的环境/数据/schema manifest。
- [ ] 功能开关默认关闭，回滚路径已演练。

未满足任一关键项时，本任务状态为 `BLOCKED`；不得用假设替代。

## 3. 问题事实与施工目标

### 3.1 已确认问题

| 项目 | 内容 |
|---|---|
| 预期行为 | 在不修改producer/envelope/retention的前提下，把ACK改为显式结果驱动：只有handler完成、已批准audited no-op或DLQ写成功才ACK；其余保留PEL或进入IN_DOUBT。 |
| 当前行为 | `RecalcStreamConsumer.process_event` 对空payload返回True，调用方随后ACK。；JSON解析后直接 `e.get`，合法JSON array/null/string/number不在受控异常边界。；`_dispatch_business` 的已知分支仅print/pass，未知事件也自然返回成功。；`_reclaim_stale` 遇到empty fields/ghost entry直接加入ack_ids。；DLQ写失败的处置没有独立结果类型，normal read与reclaim逻辑分散。 |
| 差异 | 当前实现缺少本任务批准的唯一合同、门禁或原子边界。 |
| 影响 | 金额/PV单位、奖金、并发一致性、发布或可恢复性，具体见来源问题。 |
| 严重级别 | P0 |
| 证据位置 | 固定代码基线 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；来源 `TASK-PVAM-07A`；检查项 `CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-001、CHK-TEST-003` |

### 3.2 已确认代码事实

- `RecalcStreamConsumer.process_event` 对空payload返回True，调用方随后ACK。
- JSON解析后直接 `e.get`，合法JSON array/null/string/number不在受控异常边界。
- `_dispatch_business` 的已知分支仅print/pass，未知事件也自然返回成功。
- `_reclaim_stale` 遇到empty fields/ghost entry直接加入ack_ids。
- DLQ写失败的处置没有独立结果类型，normal read与reclaim逻辑分散。

### 3.3 本任务目标

在不修改producer/envelope/retention的前提下，把ACK改为显式结果驱动：只有handler完成、已批准audited no-op或DLQ写成功才ACK；其余保留PEL或进入IN_DOUBT。

### 3.4 完成定义

- [ ] 所有 CHG 和 STEP 在批准范围内完成，未触碰排除项。
- [ ] DEV 静态、单元、契约和 mutation 测试全部通过并生成原始证据。
- [ ] UAT 所属用例已执行并回传，或保持 `PENDING_TEST_ENV/BLOCKED`，绝不预标通过。
- [ ] 受影响调用者回归通过，重复执行和失败恢复满足本任务断言。
- [ ] 回滚开关与 `git revert` 路径均可用，回滚后关键读写验证通过。

告警数值未定不阻断fail-closed代码与DEV/UAT；生产切换窗口另由总方案发布门控制。

### 3.5 明确非目标

- 不修改来源 TASK 未批准的业务比例、资格、分母、Country、period、舍入或发布职责。
- 不使用 `_bak`、`_final`、copy、废弃SQL或 `GraphService.run_bfs` 作为施工依据。
- 不把 UAT_VERIFY 风险转化为代码修复；只做验证、证据或阻断。
- 不建设 PB/SFB/GPB/CRB 算法或 Team Bonus units-int 生产服务。

## 4. 修改前调用链与数据流

### 4.1 入口与调用链

| 顺序 | 调用方/入口 | 文件与符号 | 输入契约 | 输出/副作用 | 错误形成点 |
|---|---|---|---|---|---|
| 1 | 新消息读取 | `RecalcStreamConsumer.start_consuming` | Stream entry | process_event True→XACK | 假成功 |
| 2 | payload解析 | `process_event` | payload string | 空直接True；JSON后e.get | 非object异常逃逸 |
| 3 | 分发 | `_dispatch_business` | event_type/dict | print/pass/unknown无错误 | 未处理仍ACK |
| 4 | reclaim | `_reclaim_stale` | XAUTOCLAIM entry | empty fields直接ACK | payload不可恢复 |

### 4.2 当前错误形成点

当前链路在上述入口缺少本任务目标合同，导致已确认问题在写入、计算、路由或发布边界形成并传播。修改必须落在表中稳定符号或明确标记为“新增”的边界；不得通过外围日志掩盖。

### 4.3 受影响消费者

| 消费者 | 依赖内容 | 预期影响 | 是否同步修改 | 对应步骤/测试 |
|---|---|---|---|---|
| start_consuming | 处理结果 | 改用统一process_entry结果 | 是 | STEP-07A-03/TC-027 |
| _reclaim_stale | 同一结果 | 不再独立决定ACK | 是 | STEP-07A-03/TC-028 |
| DLQ stream | 永久无效消息 | DLQ成功后ACK | 是 | STEP-07A-02 |
| producer | 现有payload | 不修改 | 否 | 回滚独立 |

## 5. 施工设计

### 5.1 采用方案

- 新增 `MessageConsumer/RecalcProcessResult.py`，枚举 `HANDLED_ACK`、`DLQ_WRITTEN_ACK`、`RETRY_KEEP_PEL`、`UNHANDLED_KEEP_PEL`、`GHOST_IN_DOUBT`。
- 重构为 `process_entry(message_id, fields) -> RecalcProcessResult`；normal/reclaim只根据结果决定XACK。
- 空 payload 固定返回 `UNHANDLED_KEEP_PEL`，不写 DLQ、不 ACK；非空 payload 的非法 JSON 或合法非 object JSON 才尝试写 DLQ，只有 XADD 成功返回 `DLQ_WRITTEN_ACK`。
- 现有print/pass分支全部视为UNHANDLED_KEEP_PEL，直到WORK-07B提供正式handler；不得虚构audited noop。
- ghost entry不ACK，记录高优先级告警并保留恢复证据。

选择理由：

- 与有效SQL、已关闭DEC及来源TASK目标一致。
- 采用 additive-first、显式version/manifest/feature flag，支持独立合入和回滚。
- 将纯函数、I/O适配、业务计算、权威提交和证据采集分层，便于DEV替身与UAT真实验证分别取证。

### 5.2 被否决方案

| 方案 | 不采用原因 | 来源 |
|---|---|---|
| 未知事件直接ACK | 永久丢失 | R-012 |
| empty fields ACK | deleted-ID不可恢复 | CHK-EVT-007 |
| catch-all后ACK | 掩盖处理失败 | CHK-EVT-006 |
| 本hotfix改producer/schema | 破坏独立回滚 | TASK-07A |
| 把pass当noop | 无批准依据 | TASK-07A |

### 5.3 修改后调用链与数据契约

| 边界 | 输入 | 处理 | 输出 | 断言/错误行为 | 责任符号 |
|---|---|---|---|---|---|
| 施工入口 | 固定commit + 批准TASK + RECALC_ACK_FAIL_CLOSED_V1 | 先执行基线/前置检查 | 受控diff | 任一前置失败即BLOCK | `RecalcProcessResult.py` |
| 核心处理 | strict version/type/period/run合同 | 按STEP顺序执行 | 可测试状态/事件/金额 | 非法类型、状态或proof fail-loud | 见CHG表 |
| 证据出口 | 命令、输入、输出、状态前后 | WORK-08 schema封装 | EV包+SHA-256 | 缺原始证据不得PASS | `uat/scripts/*` |

## 6. 文件与符号级变更清单

| 变更编号 | 文件 | 类/函数/字段/表 | 类型 | 修改前行为 | 要求的修改 | 修改后行为 | 禁止行为 |
|---|---|---|---|---|---|---|---|
| CHG-01 | `MessageConsumer/RecalcProcessResult.py` | 结果枚举 | 新增 | 不存在 | 定义ACK/PEL/IN_DOUBT语义 | 可审计 | 不得用bool |
| CHG-02 | `MessageConsumer/RecalcStreamConsumer.py` | `process_event`→`process_entry` | 修改 | bool结果/空payload成功 | dict校验、结果枚举、DLQ成功门禁 | fail-closed | 不得吞异常 |
| CHG-03 | 同文件 | `start_consuming` | 修改 | True即ACK | 仅两种ACK结果进入ack_ids | 未处理保PEL | 不得批量ACK其他结果 |
| CHG-04 | 同文件 | `_reclaim_stale` | 修改 | ghost直接ACK | 统一process_entry；ghost IN_DOUBT | normal/reclaim一致 | 不得删除PEL占位 |
| CHG-05 | `MessageConsumer/Test/test_recalc_ack_fail_closed.py` | pytest | 新增 | 不存在 | payload/JSON/unknown/pass/DLQ/ghost矩阵 | hotfix可独立验证 | 不得依赖WORK-07B |

### 6.1 固定基线锚点复验

`MessageConsumer/RecalcStreamConsumer.py`当前存在四个确定的假ACK入口：

1. `_reclaim_stale`遇到空`fields`直接加入`ack_ids`；
2. `process_event`遇到空payload返回True；
3. `json.loads`返回array/null/string/number后，`e.get`在统一异常边界之外；
4. `_dispatch_business`对已列事件仅print/pass，unknown也落空，随后返回True。

### 6.2 五态结果与ACK函数

> 规范合同：新增文件、枚举类名、类型标注和测试导入统一使用 `MessageConsumer.RecalcProcessResult.RecalcProcessResult`。以下代码块是该新增文件的规范参考实现，包含 §5.1、CHG-01、STEP-01 与 §9.2.1 共同要求的只读 `should_ack` 属性。

```python
from enum import Enum


class RecalcProcessResult(str, Enum):
    HANDLED_ACK = "HANDLED_ACK"
    DLQ_WRITTEN_ACK = "DLQ_WRITTEN_ACK"
    RETRY_KEEP_PEL = "RETRY_KEEP_PEL"
    UNHANDLED_KEEP_PEL = "UNHANDLED_KEEP_PEL"
    GHOST_IN_DOUBT = "GHOST_IN_DOUBT"

    @property
    def should_ack(self) -> bool:
        """只有业务处理完成或 DLQ 已可靠写入时才允许 XACK。"""
        return self in (
            RecalcProcessResult.HANDLED_ACK,
            RecalcProcessResult.DLQ_WRITTEN_ACK,
        )


ACKABLE = frozenset(
    {
        RecalcProcessResult.HANDLED_ACK,
        RecalcProcessResult.DLQ_WRITTEN_ACK,
    }
)
```

> **补丁性质：`DESIGN_FRAGMENT`（非逐字可应用补丁）。真实patch须在实施commit后按§12.A生成并校验。**

```diff
--- a/MessageConsumer/RecalcStreamConsumer.py
+++ b/MessageConsumer/RecalcStreamConsumer.py
@@
             for message_id, fields in claimed:
                 # region 幽灵消息 消息如果在原 Stream 中被删了，但还在 PEL 里，清掉占位
                 if not fields:
-                    ack_ids.append(message_id)
+                    self._record_ghost_in_doubt(message_id)
                     continue
@@
         # region 验证
         if not payload_str:
-            return True
+            return RecalcProcessResult.UNHANDLED_KEEP_PEL
         # endregion
 
         # region 处理消息 如有异常 加入死信队列 (格式级别毒丸)
         try:
             e = json.loads(payload_str)
         except json.JSONDecodeError as err:
             logger.error(f"解析 JSON 失败: {err}, 扔进死信队列 (DLQ)")
-            self.r.xadd(DLQ_STREAM_KEY, {"original_id": message_id, "raw_payload": payload_str, "error": str(err),
-                                         "type": "JSON_ERROR"})
-            return True
+            return self._write_dlq_or_keep_pel(
+                message_id,
+                payload_str,
+                "JSON_ERROR",
+                error=str(err),
+            )
         # endregion
 
+        if not isinstance(e, dict):
+            return self._write_dlq_or_keep_pel(
+                message_id,
+                payload_str,
+                "NON_OBJECT_JSON",
+            )
+
         et = e.get("event_type")
```

主循环和reclaim必须调用同一个`process_entry`，并且只在 `result.should_ack is True` 时执行 XACK；`ACKABLE` 仅作为等价审计集合，不得形成第二套判定。DLQ XADD异常返回`RETRY_KEEP_PEL`；没有真实handler的现有print/pass分支返回`UNHANDLED_KEEP_PEL`，不得编造副作用。

### 6.3 发布纪律

告警阈值、观察窗和运维容量不是核心代码开工前置；它们只影响生产切换批准。07A的DEV/UAT必须先证明“未完成业务绝不ACK”，不能因阈值未定而延后P0修复。

> **DEV 执行口径：** `05_CONTROL/check_baseline_preflight.sh` 与 `05_CONTROL/validate_work_dev.sh` 是唯一强制门禁。STEP 中列出的 `py_compile`、`compileall` 或 `pytest` 命令仅是附加局部检查，不得替代 parent-tree、scope、patch、tree-hash 与专属测试门禁。

## 7. 可执行施工步骤

### STEP-PVAM-07A-01：定义处理结果

- 目的：定义处理结果，落实 `TASK-PVAM-07A` 的已批准目标。
- 前置条件：无
- 修改文件：`RecalcProcessResult.py`
- 目标符号：Enum
- 精确操作：
1. 实现五个结果和`should_ack`只读属性
2. 只两类返回true。
- 必须保持：不加入事件业务语义
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile MessageConsumer/RecalcProcessResult.py`
- 本步单元验证：`TC-PVAM-07A-01`
- 完成证据：`EV-PVAM-07A-01`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：仍用bool则不合并

### STEP-PVAM-07A-02：重构payload/DLQ边界

- 目的：重构payload/DLQ边界，落实 `TASK-PVAM-07A` 的已批准目标。
- 前置条件：STEP-07A-01
- 修改文件：`MessageConsumer/RecalcStreamConsumer.py::process_entry`（`NEW_SYMBOL`，基线仅有`process_event`）
- 目标符号：处理函数
- 精确操作：
1. fields 缺失/ghost 进入 `GHOST_IN_DOUBT`；空 payload 返回 `UNHANDLED_KEEP_PEL`，不写 DLQ。
2. 非空非法 JSON/非 object JSON 尝试写 DLQ，只有写入成功才可 ACK。
3. unknown/print/pass/handler失败均保留 PEL；DLQ失败返回 `RETRY_KEEP_PEL`。
- 必须保持：unknown/pass不成功
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile MessageConsumer/RecalcStreamConsumer.py`
- 本步单元验证：`TC-PVAM-07A-02~04`
- 完成证据：`EV-PVAM-07A-02`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任一未处理返回ACK即停工

### STEP-PVAM-07A-03：统一normal/reclaim ACK决策

- 目的：统一normal/reclaim ACK决策，落实 `TASK-PVAM-07A` 的已批准目标。
- 前置条件：STEP-07A-02
- 修改文件：`start_consuming`、`_reclaim_stale`
- 目标符号：ACK路由
- 精确操作：
1. 两路径均调用process_entry，按should_ack收集ID
2. ghost告警/IN_DOUBT。
- 必须保持：不改group/key/config
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile MessageConsumer/RecalcStreamConsumer.py`
- 本步单元验证：`TC-PVAM-07A-05/06`
- 完成证据：`EV-PVAM-07A-03`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：行为不一致不得合并

### STEP-PVAM-07A-04：补齐mutation与回归

- 目的：补齐mutation与回归，落实 `TASK-PVAM-07A` 的已批准目标。
- 前置条件：STEP-07A-01~03
- 修改文件：新增测试
- 目标符号：pytest
- 精确操作：
1. 覆盖空/非法/非object/unknown/pass/handler失败/DLQ失败/ghost及reclaim。
- 必须保持：测试不依赖正式handler
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m pytest -q MessageConsumer/Test/test_recalc_ack_fail_closed.py`
- 本步单元验证：`TC-PVAM-07A-01~07`
- 完成证据：`EV-PVAM-07A-04`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：mutation存活不得发布

## 8. 数据迁移、兼容与重跑

### 8.1 数据变化

| 对象 | 旧格式/状态 | 新格式/状态 | 转换位置 | 版本识别 | 异常数据策略 |
|---|---|---|---|---|---|
| PEL/ACK处置 | bool成功 | 显式 `RecalcProcessResult` | consumer两路径 | message_id/result | 未处理保PEL |

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
| TC-PVAM-07A-01 | 单元 | ACK结果矩阵 | 五种enum | 仅HANDLED_ACK/DLQ_WRITTEN_ACK should_ack=True | STEP-07A-01 | DEV | NOT_RUN |
| TC-PVAM-07A-02 | 单元 | 空payload | None/empty | UNHANDLED_KEEP_PEL，不XACK | STEP-07A-02 | DEV+UAT | NOT_RUN |
| TC-PVAM-07A-03 | 单元 | JSON非object | `[]`,`null`,`"x"`,`1` | 写DLQ成功后ACK；DLQ失败KEEP_PEL | STEP-07A-02 | DEV+UAT | NOT_RUN |
| TC-PVAM-07A-04 | 单元 | 未知/pass事件 | unknown/现有pass分支 | UNHANDLED_KEEP_PEL | STEP-07A-02 | DEV+UAT | NOT_RUN |
| TC-PVAM-07A-05 | 集成 | normal/reclaim一致 | 同一entry分别投递 | 结果与ACK决定一致 | STEP-07A-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-07A-06 | 集成 | ghost entry | XAUTOCLAIM empty fields | GHOST_IN_DOUBT、告警、无ACK | STEP-07A-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-07A-07 | mutation | 反转fail-closed | unknown→ACK/ghost→ACK/DLQ失败→ACK | 测试全部失败 | STEP-07A-04 | DEV | NOT_RUN |

受控检查方案用例映射：`TC-027, TC-028, TC-031`。`TC-000` 为 RETIRED，不执行、不计完成率。

### 9.2 开发环境自动验证

```bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_SHA="3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2"
: "${WORK_COMMIT_SHA:?set the implementation commit for WORK-PVAM-07A}"
: "${PARENT_COMMIT_SHA:?set the controlled parent commit; root WORK uses BASE_SHA}"
: "${PARENT_TREE_SHA:?set the tree of PARENT_COMMIT_SHA}"
: "${PARENT_PROVENANCE_JSON:?set schema-v2 parent provenance JSON}"
: "${APPROVED_COMMIT_REGISTRY_JSON:?set canonical WORK_APPROVED_COMMIT_REGISTRY.json}"
CONTROL_ROOT="${PVAM_CONTROL_ROOT:?point to the released 05_CONTROL directory}"

# Phase A：只验证固定基线和既有锚点，不要求 Common/Settlement/Ops 等未来目录存在。
bash "$CONTROL_ROOT/check_baseline_preflight.sh" \
  --repo "$REPO_ROOT" --base "$BASE_SHA" --work-id "WORK-PVAM-07A"

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
  --work-id "WORK-PVAM-07A" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --test-command-file "$CONTROL_ROOT/work-test-commands/WORK-PVAM-07A.sh" \
  --out "evidence/WORK-PVAM-07A/dev"
```

#### 9.2.1 必须落地的关键 `assert` 契约

以下断言骨架必须进入本任务列出的 pytest 文件；fixture 由测试文件实现，不得用复制生产公式的替身替代被测符号。

```python
from MessageConsumer.RecalcProcessResult import RecalcProcessResult


def test_ack_result_contract() -> None:
    assert RecalcProcessResult.HANDLED_ACK.should_ack is True
    assert RecalcProcessResult.DLQ_WRITTEN_ACK.should_ack is True
    assert RecalcProcessResult.RETRY_KEEP_PEL.should_ack is False
    assert RecalcProcessResult.UNHANDLED_KEEP_PEL.should_ack is False
    assert RecalcProcessResult.GHOST_IN_DOUBT.should_ack is False
```

通过标准：所有命令 exit code 0；pytest 无未解释 skip；证据schema校验通过。GPU/Dask/真实Redis/Kafka/MySQL未在DEV执行时必须标注 `NOT_RUN/PENDING_TEST_ENV`。

### 9.3 测试环境手工执行包

#### ENV-TC-PVAM-07A-01：ACK/PEL/DLQ/ghost hotfix

- 对应受控测试：`TC-027、TC-028、TC-031`
- 环境版本：由 `uat/environment_manifest.yaml` 固定 Python/CUDA/RAPIDS/Dask/Redis/Kafka/DB/镜像/commit。
- 前置服务与数据：隔离Redis Stream/group；不启用WORK-07B schema
- 清理/隔离：必须使用专用 topic/group、Redis前缀、period/run_id；禁止复用生产数据。
- 执行命令：

```bash
RUN_ID=work07a-$(date +%Y%m%d%H%M%S)
bash uat/scripts/run_work_uat.sh --work WORK-PVAM-07A --run-id "$RUN_ID" --tc TC-027,TC-028,TC-031
```

- SQL/数据库证据命令（仅在专用 UAT schema 和 WORK-08 manifest 校验通过后执行；N/A 项只保留说明）：

```bash
# N/A：本任务验证 Redis Stream PEL/ACK/DLQ，不执行 SQL。
```

- 执行步骤：
1. 发布空/非法/non-object/unknown/handler失败消息；分别记录 PEL 与 DLQ 变化
2. 模拟DLQ写失败
3. 制造pending后删除stream entry并XAUTOCLAIM
4. 查询XPENDING/XRANGE/DLQ
- 精确预期：
- 未处理消息留PEL
- 空 payload 固定留在 PEL 且不写 DLQ；非法 JSON/非 object JSON 仅在 DLQ 成功后 ACK
- ghost不ACK并有IN_DOUBT告警
- 必须回传：完整命令、exit code、stdout/stderr、JUnit/JSON、输入fixture SHA-256、代码commit、镜像、环境版本、执行起止时间、Redis/DB/Kafka/Dask前后证据。
- 失败停止与清理：停止专用consumer/job；保留PEL/状态和证据；禁止在未分析前清理失败现场；按第11节回滚。

### 9.4 SQL 对账样例

| 样例 | SQL输入/来源 | SQL预期 | Python预期 | 比较口径 | 允许差异 |
|---|---|---|---|---|---|
| N/A | 事件ACK不涉及业务SQL | N/A | N/A | Redis Stream状态 | N/A |

## 10. 验收标准映射

| 验收编号 | 来源TASK验收项 | 实现步骤 | 测试用例 | 所需证据 | 环境 | 通过条件 |
|---|---|---|---|---|---|---|
| AC-01 | 空 payload 不返回成功，不在无处置证据时 ACK | STEP-PVAM-07A-02/04 | TC-027 | EV-PVAM-07A-01 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-02 | 非法 JSON 与合法非 object JSON 均进入统一异常边界，不中断 reclaim 批次 | STEP-PVAM-07A-02/04 | TC-027 | EV-PVAM-07A-02 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-03 | 未知事件、缺 handler、现有 print/pass 分支不得落空成功 | STEP-PVAM-07A-02/04 | TC-027 | EV-PVAM-07A-03 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-04 | handler 失败或后置条件未知时不 ACK，保留 PEL 等待重试/后续合同 | STEP-PVAM-07A-02/03/04 | TC-027 | EV-PVAM-07A-04 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-05 | 永久非法消息只有在 DLQ 写成功后 ACK；DLQ 失败保留 PEL | STEP-PVAM-07A-02/04 | TC-027、TC-028 | EV-PVAM-07A-05 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-06 | normal read 与 xautoclaim 使用同一处理函数，对同一 entry 行为一致 | STEP-PVAM-07A-03/04 | TC-027、TC-028 | EV-PVAM-07A-06 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-07 | deleted-ID/empty fields 不直接 ACK；至少告警并阻断该批恢复链 | STEP-PVAM-07A-03/04 | TC-028 | EV-PVAM-07A-07 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-08 | 本 hotfix 不要求 producer/envelope 变更，能够独立启停和回滚 | STEP-PVAM-07A-01/03/04 | TC-031 | EV-PVAM-07A-08 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-09 | mutation 将 unknown 重新设为成功、ghost 直接 ACK、DLQ 失败仍 ACK 时，测试必失败 | STEP-PVAM-07A-04 | TC-031 | EV-PVAM-07A-09 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |

### 10.1 AC-01 实施细化

来源 AC 原文保持为“空 payload 不返回成功，不在无处置证据时 ACK”。本 WORK 的唯一实施细化为：空 payload 返回 `UNHANDLED_KEEP_PEL`，不写 DLQ、不调用 `XACK`；该细化不得反向改写来源 TASK 的 AC 文本。

没有 STEP、TC 或 EV 映射的AC不得标记完成。任何含UAT的AC在未回传真实环境证据时只能为 `PENDING_TEST_ENV/BLOCKED`。

## 11. 风险、停工与回滚

### 11.1 风险清单

| 风险 | 触发条件 | 影响 | 预防措施 | 监测/证据 | 处置 |
|---|---|---|---|---|---|
| PEL增长 | pass/unknown不再ACK | 积压 | 告警/容量临时提升/WORK-07B尽快接handler | XPENDING | 不回退假ACK |
| ghost不可保留payload | 原stream已trim | 恢复困难 | IN_DOUBT和证据 | ghost指标 | WORK-07B恢复 |
| 下游依赖旧假ACK | 积压暴露 | 运维压力 | 灰度flag | group lag | 停消费者但不ACK |

### 11.2 本任务强制停工条件

- HEAD、SQL blob、模型schema或上游TASK与受控基线不一致。
- 实施必须改变未批准的业务规则、精度、资格、分母、Country或发布职责才能继续。
- 需要修改排除文件/模块或扩大异常白名单才能通过测试。
- 关键mutation存活、SQL黄金样例出现未批准差异、幂等/原子/回滚断言失败。
- UAT权限、schema、数据或隔离条件不足；此时保持 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV`。

### 11.3 部署面与数据面回滚门禁

**当前可执行性：`BLOCKED_EXTERNAL_EVIDENCE`。** 当前材料没有给出真实部署系统、workload/release、镜像、配置对象和健康检查命令，因此不得以本地`export`或通用`git revert`冒充部署回滚。

部署前必须提供并签署`evidence/WORK-PVAM-07A/rollback/ROLLBACK-MANIFEST-PVAM-v1.json`，至少包含：

- `deployment_system`、`environment`、`workload_id`、`release_before/after`、`image_before/after`；
- 精确的停止、回滚、恢复、健康检查和重新放量命令；
- Redis/Stream/ledger/run/manifest的备份或快照位置及SHA-256；
- 执行人、复核人、批准时间、允许的数据恢复范围；
- 命令dry-run/隔离演练的退出码和原始日志。

本任务数据面处置：停止consumer；导出XPENDING和DLQ；恢复旧镜像前证明回滚窗口内没有未处理消息被ACK；保留PEL并由批准的恢复步骤重新消费。

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
| EV-PVAM-07A-01 | AC-01验收证据：空 payload 固定返回 UNHANDLED_KEEP_PEL，不写 DLQ且不 ACK | STEP-PVAM-07A-02/04 | evidence/WORK-PVAM-07A/attempt-*/ac/AC-01/ | 待指派QA | PENDING |
| EV-PVAM-07A-02 | AC-02验收证据：非法 JSON 与合法非 object JSON 均进入统一异常边界，不中断 reclaim 批次 | STEP-PVAM-07A-02/04 | evidence/WORK-PVAM-07A/attempt-*/ac/AC-02/ | 待指派QA | PENDING |
| EV-PVAM-07A-03 | AC-03验收证据：未知事件、缺 handler、现有 print/pass 分支不得落空成功 | STEP-PVAM-07A-02/04 | evidence/WORK-PVAM-07A/attempt-*/ac/AC-03/ | 待指派QA | PENDING |
| EV-PVAM-07A-04 | AC-04验收证据：handler 失败或后置条件未知时不 ACK，保留 PEL 等待重试/后续合同 | STEP-PVAM-07A-02/03/04 | evidence/WORK-PVAM-07A/attempt-*/ac/AC-04/ | 待指派QA | PENDING |
| EV-PVAM-07A-05 | AC-05验收证据：永久非法消息只有在 DLQ 写成功后 ACK；DLQ 失败保留 PEL | STEP-PVAM-07A-02/04 | evidence/WORK-PVAM-07A/attempt-*/ac/AC-05/ | 待指派QA | PENDING |
| EV-PVAM-07A-06 | AC-06验收证据：normal read 与 xautoclaim 使用同一处理函数，对同一 entry 行为一致 | STEP-PVAM-07A-03/04 | evidence/WORK-PVAM-07A/attempt-*/ac/AC-06/ | 待指派QA | PENDING |
| EV-PVAM-07A-07 | AC-07验收证据：deleted-ID/empty fields 不直接 ACK；至少告警并阻断该批恢复链 | STEP-PVAM-07A-03/04 | evidence/WORK-PVAM-07A/attempt-*/ac/AC-07/ | 待指派QA | PENDING |
| EV-PVAM-07A-08 | AC-08验收证据：本 hotfix 不要求 producer/envelope 变更，能够独立启停和回滚 | STEP-PVAM-07A-01/03/04 | evidence/WORK-PVAM-07A/attempt-*/ac/AC-08/ | 待指派QA | PENDING |
| EV-PVAM-07A-09 | AC-09验收证据：mutation 将 unknown 重新设为成功、ghost 直接 ACK、DLQ 失败仍 ACK 时，测试必失败 | STEP-PVAM-07A-04 | evidence/WORK-PVAM-07A/attempt-*/ac/AC-09/ | 待指派QA | PENDING |
| EV-PVAM-07A-P01 | 处理结果枚举与consumer diff | 对应STEP/TC | evidence/WORK-PVAM-07A/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-07A-P02 | DEV fail-closed/mutation测试 | 对应STEP/TC | evidence/WORK-PVAM-07A/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-07A-P03 | UAT PEL/DLQ/ghost证据 | 对应STEP/TC | evidence/WORK-PVAM-07A/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-07A-P04 | 运行告警和回滚说明 | 对应STEP/TC | evidence/WORK-PVAM-07A/attempt-*/package/ | 待指派QA | PENDING |

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
  --work-id "WORK-PVAM-07A" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --out "evidence/WORK-PVAM-07A/patch"
```

门禁必须证明：

1. `BASE_SHA` 是 `WORK_COMMIT_SHA` 的祖先；
2. 全部新增、修改、删除和 rename 的旧/新路径均落在 `WORK-PVAM-07A` 批准 allowlist；
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
| STEP-PVAM-07A-01 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-07A-02 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-07A-03 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-07A-04 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |

### 13.2 实际验证

| 测试 | 环境 | 命令/版本 | 结果 | 证据 | 执行时间 |
|---|---|---|---|---|---|
| TC-PVAM-07A-01 | DEV | 待执行 | NOT_RUN | EV-PVAM-07A-* | 待执行 |
| TC-PVAM-07A-02 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-07A-* | 待执行 |
| TC-PVAM-07A-03 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-07A-* | 待执行 |
| TC-PVAM-07A-04 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-07A-* | 待执行 |
| TC-PVAM-07A-05 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-07A-* | 待执行 |
| TC-PVAM-07A-06 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-07A-* | 待执行 |
| TC-PVAM-07A-07 | DEV | 待执行 | NOT_RUN | EV-PVAM-07A-* | 待执行 |

### 13.3 未完成项

| 项目 | 原因 | 风险 | 后续动作 | 责任人 | 截止时间 |
|---|---|---|---|---|---|
| UAT/外部材料 | 当前计划阶段未执行 | 不能关闭P0/P1 | 由WORK-08准入后执行 | 待指派 | 待批准 |

## 14. 偏离、发现项与上游回流

| 编号 | 类型 | 发现事实 | 是否影响业务/范围 | 临时动作 | 需要更新 | 最终裁决 |
|---|---|---|---|---|---|---|
| `DEV-PVAM-07A-001` | `预留` | 待执行 | 待判断 | 停工/隔离 | WORK/TASK/DEC/REVIEW | 待裁决 |

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
| v1.0 | 2026-08-04 | 初版施工任务书 | `TASK-PVAM-07A` + `PLAN-PVAM-v1.15` + 固定代码基线 | AI Agent（编制） | DRAFT |
| v1.1 | 2026-08-05 | 依据二轮核验报告完成定点修订并补齐治理追溯 | F-A/F-B/F-H/F-I/F-J/F-K/F-F/F-E/F-L/F-M/F-N 中适用项 | AI Agent（编制） | DRAFT |
| v1.2 | 2026-08-05 | 闭合 G-1：§6.2 统一使用 `RecalcProcessResult`，补齐只读 `should_ack`，同步 diff、ACK 判定与测试合同；不改变五态语义、CHK/DEC/TASK/WORK 范围 | 历史会话声明（未形成可独立验证组织授权，现由 v1.3 取代） | AI Agent（编制） | SUPERSEDED |
| v1.3 | 2026-08-05 | 第四轮关闭 F3-01～F3-10：治理回退 DRAFT、Traceability v3、patch/DEV 双阶段、状态枚举及设计边界 | 三轮审查报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r6 | 2026-08-06 | 五轮 F5 定点修订：规范 v3 追溯、parent provenance/DEV CLI、控制状态字段及单一事实源 | 五轮审计报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r7 | 2026-08-06 | 六轮 S6：信任 registry 初版、归档哈希、临时目录与 Decimal finite 防护 | 六轮终局审计报告 | AI Agent（编制） | DRAFT |
| v1.3-r8 | 2026-08-06 | 七轮 B7：registry 发布信任根、四工件摘要、AC 来源保真及当前轮次引用 | 七轮终局审计报告 + B7 处置 | AI Agent（编制） | DRAFT |

<!-- END WORK-PVAM-07A_Consumer_ACK紧急修复.md -->

---

<!-- BEGIN WORK-PVAM-07B_事件路由与Stream保留.md -->

# WORK-PVAM-07B 事件路由、正式 Handler 与 Stream 保留护栏施工任务书

> 文档定位：来源于待组织批准的 `TASK-PVAM-07B`，在取得组织授权后转化为可执行施工说明。本文件不重新决定业务规则；实际结果只能写入执行记录与验证交付报告。

## 0. 填写与执行规则

1. 上游修改任务与本 v1.3 施工套件当前均为 `DRAFT`；没有组织授权前，本任务保持 `BLOCKED`，不得启动代码施工或部署。
2. 只实施 `R-012B`（parent=`R-012`，最终路由）、`R-013` 中已 `ACCEPTED` 或由来源 TASK 明确批准的条件代码事项。任何 `REJECTED / NEEDS_DECISION / DEFERRED / 未获 TASK 授权的 UAT_VERIFY` 只允许登记、验证或阻断，不得扩展代码范围。
3. 基线必须精确等于 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；发现漂移立即登记 `BLOCK-PVAM-07B-BASELINE`。
4. 所有新文件/符号已在变更表标为“新增”；其余锚点均来自固定基线。
5. DEV替身不能冒充真实Kafka/Redis/Dask/GPU/MySQL UAT验证。

## 1. 文档信息与追溯关系

| 字段 | 内容 |
|---|---|
| 施工任务编号 | `WORK-PVAM-07B` |
| 施工任务名称 | 事件路由、正式 Handler 与 Stream 保留护栏 |
| 所属施工总方案 | `WORK-PLAN-PVAM_v1.3` |
| 来源修改任务 | `TASK-PVAM-07B@MODPLAN-PVAM_v1.2`（authorization=PENDING_ORGANIZATIONAL_APPROVAL） |
| 来源问题 | `R-012B`（parent=`R-012`，最终路由）、`R-013` |
| 复核闭环追踪号 | `REM-012B、REM-013 / W-012B、W-013 / V-012B、V-013` |
| 来源检查项 | `CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-003` |
| 关联决策 | `DEC-007、DEC-010` |
| 代码基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| SQL基线 | `sql_uat/*@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，仅有效SQL |
| 文档版本 | `v1.3` |
| 负责人 | `待指派 / 实施工程师` |
| 复核人 | `待指派 / 架构与QA` |
| 当前状态 | `BLOCKED` |
| 文档治理状态 | `DRAFT`（`PENDING_ORGANIZATIONAL_APPROVAL`） |
| 前置任务 | WORK-PVAM-06、WORK-PVAM-07A DEV_VERIFIED |
| 功能开关 | `RECALC_EVENT_SCHEMA_V2 / RECALC_ACK_AWARE_TRIM` |

### 1.1 一对一追溯摘要

```text
CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-003
  └─ R-012B（parent=R-012，最终路由）、R-013
       └─ DEC-007、DEC-010
            └─ TASK-PVAM-07B (DRAFT / PENDING_ORGANIZATIONAL_APPROVAL)
                 └─ WORK-PVAM-07B
                      ├─ STEP-PVAM-07B-01 / STEP-PVAM-07B-02 / STEP-PVAM-07B-03 / STEP-PVAM-07B-04 / STEP-PVAM-07B-05 / STEP-PVAM-07B-06
                      ├─ TC-PVAM-07B-01 / TC-PVAM-07B-02 / TC-PVAM-07B-03 / TC-PVAM-07B-04 / TC-PVAM-07B-05 / TC-PVAM-07B-06 / TC-PVAM-07B-07 / TC-PVAM-07B-08 / TC-PVAM-07B-09
                      └─ EV-PVAM-07B-01...
```

## 2. 施工任务生成依据

### 2.1 上游输入

| 输入 | 编号/版本 | 本任务使用的结论 | 状态 |
|---|---|---|---|
| 复核报告 | `Redemption_PV_Amount_Migration_d74_复核报告_v1.5` | R-012B（parent=R-012，最终路由）、R-013 的代码事实与严重级别 | CONFIRMED |
| 修改任务书 | `TASK-PVAM-07B` | 采用方案、范围、排除项、AC | DRAFT（待组织授权） |
| 检查方案 | `PLAN-PVAM-v1.15` | CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-003 | CONTROLLED |
| 正式决策 | DEC-007、DEC-010 | 只执行已关闭裁决；开放项阻断 | CLOSED / 按上游登记 |
| 代码/SQL快照 | 3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2 | 唯一施工对象 | FROZEN |
| 施工模板 | 总方案模板/专项模板 | 章节、状态、证据纪律 | CONTROLLED |

### 2.2 开工条件

- [ ] 当前 HEAD 精确为 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，工作树无未登记变更。
- [ ] `TASK-PVAM-07B` 的人工批准记录已归档；本 `WORK` 已由施工负责人和复核人签署。
- [ ] 前置关系满足：WORK-PVAM-06、WORK-PVAM-07A DEV_VERIFIED。
- [ ] 本任务涉及的接口、单位、精度、兼容和回滚边界已由上游任务固定。
- [ ] DEV测试依赖已安装；UAT项具备WORK-08生成的环境/数据/schema manifest。
- [ ] 功能开关默认关闭，回滚路径已演练。

未满足任一关键项时，本任务状态为 `BLOCKED`；不得用假设替代。

## 3. 问题事实与施工目标

### 3.1 已确认问题

| 项目 | 内容 |
|---|---|
| 预期行为 | 建立版本化envelope、schema/handler registry和明确disposition；移除producer固定MAXLEN，采用所有已登记group安全水位与durable replay证明驱动的retention。 |
| 当前行为 | 多个producer在同一stream写payload，但事件身份缺稳定schema_version/producer/domain/subtype。；Global与Elite均可使用 `SETTLEMENT_PERIOD_DONE`，payload/后置动作不同。；consumer没有正式handler registry；旧分支print/pass。；Global/Elite/Placement producer多处 `XADD ... maxlen=100000, approximate=True`。；fixed trim可能在所有consumer group ACK前删除payload；ghost恢复源/容量证明缺失。 |
| 差异 | 当前实现缺少本任务批准的唯一合同、门禁或原子边界。 |
| 影响 | 金额/PV单位、奖金、并发一致性、发布或可恢复性，具体见来源问题。 |
| 严重级别 | P0 |
| 证据位置 | 固定代码基线 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；来源 `TASK-PVAM-07B`；检查项 `CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-003` |

### 3.2 已确认代码事实

- 多个producer在同一stream写payload，但事件身份缺稳定schema_version/producer/domain/subtype。
- Global与Elite均可使用 `SETTLEMENT_PERIOD_DONE`，payload/后置动作不同。
- consumer没有正式handler registry；旧分支print/pass。
- Global/Elite/Placement producer多处 `XADD ... maxlen=100000, approximate=True`。
- fixed trim可能在所有consumer group ACK前删除payload；ghost恢复源/容量证明缺失。

### 3.3 本任务目标

建立版本化envelope、schema/handler registry和明确disposition；移除producer固定MAXLEN，采用所有已登记group安全水位与durable replay证明驱动的retention。

### 3.4 完成定义

- [ ] 所有 CHG 和 STEP 在批准范围内完成，未触碰排除项。
- [ ] DEV 静态、单元、契约和 mutation 测试全部通过并生成原始证据。
- [ ] UAT 所属用例已执行并回传，或保持 `PENDING_TEST_ENV/BLOCKED`，绝不预标通过。
- [ ] 受影响调用者回归通过，重复执行和失败恢复满足本任务断言。
- [ ] 回滚开关与 `git revert` 路径均可用，回滚后关键读写验证通过。

retention阈值未签署时仅阻断实际trim，不阻断schema/registry/publisher/handler与dry-run实现；初始无批准no-op。

### 3.5 明确非目标

- 不修改来源 TASK 未批准的业务比例、资格、分母、Country、period、舍入或发布职责。
- 不使用 `_bak`、`_final`、copy、废弃SQL或 `GraphService.run_bfs` 作为施工依据。
- 不把 UAT_VERIFY 风险转化为代码修复；只做验证、证据或阻断。
- 不建设 PB/SFB/GPB/CRB 算法或 Team Bonus units-int 生产服务。

## 4. 修改前调用链与数据流

### 4.1 入口与调用链

| 顺序 | 调用方/入口 | 文件与符号 | 输入契约 | 输出/副作用 | 错误形成点 |
|---|---|---|---|---|---|
| 1 | Global producer | `GlobalRecalculationService` outbox xadd | payload JSON | 固定maxlen100000 | 可能提前trim |
| 2 | Elite producer | `GlobalEliteBonusRecalculationService._emit_settlement_done` | 同名done | 固定maxlen100000 | 同名异构 |
| 3 | Placement producer | Placement两服务 outbox | PLACEMENT_* | 固定maxlen100000 | 无统一envelope |
| 4 | consumer | `RecalcStreamConsumer._dispatch_business` | event_type | print/pass | 无handler/postcondition |
| 5 | reclaim | XAUTOCLAIM | PEL/ghost | 无durable replay合同 | 无法恢复 |

### 4.2 当前错误形成点

当前链路在上述入口缺少本任务目标合同，导致已确认问题在写入、计算、路由或发布边界形成并传播。修改必须落在表中稳定符号或明确标记为“新增”的边界；不得通过外围日志掩盖。

### 4.3 受影响消费者

| 消费者 | 依赖内容 | 预期影响 | 是否同步修改 | 对应步骤/测试 |
|---|---|---|---|---|
| RecalcStreamConsumer | schema/registry/handler | 改为registry驱动 | 是 | STEP-07B-03/TC-027 |
| 所有outbox producer | 统一publisher/envelope | 修改 | 是 | STEP-07B-02 |
| consumer groups | ACK水位 | 纳入retention registry | 运维 | STEP-07B-04/TC-028 |
| durable event/settlement manifest | ghost replay | 读取恢复 | 接口 | STEP-07B-05 |

## 5. 施工设计

### 5.1 采用方案

- 新增 `MessageConsumer/RecalcEventSchema.py` 定义v2 envelope和严格decoder；新增 `RecalcHandlerRegistry.py`/`RecalcDisposition.py`。
- 新增 `Settlement/RecalcEventPublisher.py`，所有producer通过该符号发布；event id/hash幂等。
- 建议唯一变体为 domain+event_type+subtype，例如 GLOBAL/RECALC_DONE、ELITE/BATCH_READY、PLACEMENT/RECALC_DONE；旧done由兼容decoder仅在字段足够时映射，否则DLQ/KEEP_PEL。
- 新增 `Ops/RecalcStreamRetention.py`，读取登记group的last-delivered/PEL/ACK safe watermark，只有durable replay可用且不存在未决消息时执行 `XTRIM MINID`。
- trim前后生成manifest：group水位、PEL、范围、checksum、replay availability、operator/time。

选择理由：

- 与有效SQL、已关闭DEC及来源TASK目标一致。
- 采用 additive-first、显式version/manifest/feature flag，支持独立合入和回滚。
- 将纯函数、I/O适配、业务计算、权威提交和证据采集分层，便于DEV替身与UAT真实验证分别取证。

### 5.2 被否决方案

| 方案 | 不采用原因 | 来源 |
|---|---|---|
| 固定MAXLEN调大 | 仍无ACK安全证明 | R-013 |
| 按event_type猜同名变体 | 可能执行错误handler | R-012 |
| unknown audited noop | 没有批准编号 | CHK-EVT-006 |
| ghost直接ACK | 永久丢事件 | CHK-EVT-007 |
| producer各自拼payload | 继续schema漂移 | TASK-07B |

### 5.3 修改后调用链与数据契约

| 边界 | 输入 | 处理 | 输出 | 断言/错误行为 | 责任符号 |
|---|---|---|---|---|---|
| 施工入口 | 固定commit + 批准TASK + RECALC_EVENT_SCHEMA_V2 / RECALC_ACK_AWARE_TRIM | 先执行基线/前置检查 | 受控diff | 任一前置失败即BLOCK | 新schema/registry/disposition文件 |
| 核心处理 | strict version/type/period/run合同 | 按STEP顺序执行 | 可测试状态/事件/金额 | 非法类型、状态或proof fail-loud | 见CHG表 |
| 证据出口 | 命令、输入、输出、状态前后 | WORK-08 schema封装 | EV包+SHA-256 | 缺原始证据不得PASS | `uat/scripts/*` |

## 6. 文件与符号级变更清单

| 变更编号 | 文件 | 类/函数/字段/表 | 类型 | 修改前行为 | 要求的修改 | 修改后行为 | 禁止行为 |
|---|---|---|---|---|---|---|---|
| CHG-01 | `MessageConsumer/RecalcEventSchema.py` | v2 envelope/decoder | 新增 | 不存在 | 严格schema/discriminator/hash | 唯一可识别 | 不得猜路由 |
| CHG-02 | `MessageConsumer/RecalcHandlerRegistry.py` / `MessageConsumer/RecalcDisposition.py` | registry/disposition | 新增 | 不存在 | schema→handler→postcondition→disposition | 无pass默认 | 不得自动noop |
| CHG-03 | `Settlement/RecalcEventPublisher.py` | publisher | 新增 | producer各自xadd | 统一envelope/event_id/hash；不设fixed maxlen | 可双写迁移 | 不得早trim |
| CHG-04 | Global/Elite/Placement producer文件 | xadd调用 | 修改 | 直接xadd fixed maxlen | 改用publisher | 统一事件 | 不得改变业务提交原子边界 |
| CHG-05 | `MessageConsumer/RecalcStreamConsumer.py` | decoder/dispatch | 修改 | event_type if/pass | registry驱动并校验postcondition | ACK条件明确 | 不得绕过07A结果 |
| CHG-06 | `Ops/RecalcStreamRetention.py` | 安全水位/trim/replay | 新增 | 不存在 | ACK-aware MINID与manifest | 慢group安全 | 不得使用MAXLEN |
| CHG-07 | `MessageConsumer/Test/test_recalc_event_v2.py` / `MessageConsumer/Test/test_stream_retention.py` | pytest | 新增 | 不存在 | 同名消歧、兼容、>100k、多group/ghost | 可验证 | 不得依赖单group假设 |

### 6.1 固定基线锚点复验

固定`maxlen=100000, approximate=True`至少存在于：

- `GlobalRecalculationService._save_recalc_pipeline`；
- `GlobalRecalculationService._emit_settlement_done`；
- `GlobalEliteBonusRecalculationService._emit_settlement_done`；
- `PlacementRecalculationService`的事件/完成写入；
- `PlacementIncrementalService._save_placement_pipeline`。

实际施工以全仓AST/grep结果为准，必须清零所有生产XADD固定裁剪点，不能只改列表示例。

### 6.2 v2路由键与兼容边界

路由主键固定为`(schema_version, producer_domain, event_type, event_subtype)`；同名`SETTLEMENT_PERIOD_DONE`不能只凭可选字段猜测。v1 decoder只接受能够唯一映射的旧事件；无法唯一判别的旧事件必须DLQ或保PEL。

初始registry不得登记任何`LEGAL_NOOP_AUDITED`；以后只有携带正式批准编号的事件才能添加。没有handler的事件维持07A的fail-closed结果。

### 6.3 Publisher与Retention

> **模式示意，非逐字可应用补丁。** 基线六处 XADD 的变量名、缩进与 payload 参数不同；实施时必须依据 §6.1 的固定提交逐处生成真实 diff，并以 AST/grep 证明所有生产固定 MAXLEN 已清零。

> **补丁性质：`DESIGN_FRAGMENT`（非逐字可应用补丁）。真实patch须在实施commit后按§12.A生成并校验。**

```diff
- pipe.xadd(name=OUTBOX_STREAM_KEY, fields=fields,
-           maxlen=100000, approximate=True)
+ pipe.xadd(name=OUTBOX_STREAM_KEY, fields=fields)
```

统一publisher附加event_id、idempotency_key、payload_hash和schema信息。独立retention job计算所有登记group的安全水位、PEL、最小保留窗和重放证明；默认`--dry-run`。容量模型/安全水位未签署时，只禁止实际XTRIM，不阻断schema、registry、publisher、handler和dry-run代码开发。

Ghost/deleted-ID不得ACK：先查权威event registry/outbox ledger恢复payload；无法恢复则写IN_DOUBT证据并阻断相关stage关闭。

> **DEV 执行口径：** `05_CONTROL/check_baseline_preflight.sh` 与 `05_CONTROL/validate_work_dev.sh` 是唯一强制门禁。STEP 中列出的 `py_compile`、`compileall` 或 `pytest` 命令仅是附加局部检查，不得替代 parent-tree、scope、patch、tree-hash 与专属测试门禁。

## 7. 可执行施工步骤

### STEP-PVAM-07B-01：定义v2 envelope/registry

- 目的：定义v2 envelope/registry，落实 `TASK-PVAM-07B` 的已批准目标。
- 前置条件：WORK-06/07A完成
- 修改文件：新schema/registry/disposition文件
- 目标符号：数据与handler合同
- 精确操作：
1. 定义必填字段、变体键、schema validator、handler postcondition与audited noop批准字段。
- 必须保持：不实现业务DBwriter
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile MessageConsumer/RecalcEventSchema.py MessageConsumer/RecalcHandlerRegistry.py MessageConsumer/RecalcDisposition.py`
- 本步单元验证：`TC-PVAM-07B-01/02`
- 完成证据：`EV-PVAM-07B-01`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任一事件无唯一变体则BLOCK

### STEP-PVAM-07B-02：统一publisher并迁移producer

- 目的：统一publisher并迁移producer，落实 `TASK-PVAM-07B` 的已批准目标。
- 前置条件：STEP-07B-01
- 修改文件：`Settlement/RecalcEventPublisher.py`及四类producer
- 目标符号：publish/xadd
- 精确操作：
1. 生成event_id/hash
2. 支持短期dual-publish/dual-read
3. 移除fixed maxlen。
- 必须保持：保持Redis权威事务边界
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`grep -R "maxlen=100000" -n --include="*.py" User MessageConsumer Settlement`
- 本步单元验证：`TC-PVAM-07B-03/04`
- 完成证据：`EV-PVAM-07B-02`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：仍有生产fixed trim不合并

### STEP-PVAM-07B-03：接正式handler与兼容decoder

- 目的：接正式handler与兼容decoder，落实 `TASK-PVAM-07B` 的已批准目标。
- 前置条件：STEP-07B-01/WORK-07A
- 修改文件：`RecalcStreamConsumer.py`
- 目标符号：process/dispatch
- 精确操作：
1. decoder→registry→handler→postcondition→disposition→07A ACK
2. 旧同名无法消歧不猜。
- 必须保持：unknown保持PEL或DLQ
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile MessageConsumer/RecalcStreamConsumer.py`
- 本步单元验证：`TC-PVAM-07B-01/02/05`
- 完成证据：`EV-PVAM-07B-03`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：pass/默认成功残留不合并

### STEP-PVAM-07B-04：实现ACK-aware retention

- 目的：实现ACK-aware retention，落实 `TASK-PVAM-07B` 的已批准目标。
- 前置条件：STEP-07B-02
- 修改文件：`Ops/RecalcStreamRetention.py`
- 目标符号：plan/execute trim
- 精确操作：
1. 枚举登记group，计算最小安全ID，检查PEL/DLQ/replay，dry-run后MINID trim并manifest。
- 必须保持：不得MAXLEN/删除未ACK
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Ops/RecalcStreamRetention.py`
- 本步单元验证：`TC-PVAM-07B-06/07`
- 完成证据：`EV-PVAM-07B-04`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任何group状态不可读时不trim

### STEP-PVAM-07B-05：实现ghost恢复

- 目的：实现ghost恢复，落实 `TASK-PVAM-07B` 的已批准目标。
- 前置条件：STEP-07B-03/04/WORK-06
- 修改文件：consumer/retention
- 目标符号：recover
- 精确操作：
1. 从event registry/settlement manifest重建entry或IN_DOUBT
2. 保持event_id幂等。
- 必须保持：不得直接ACK
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m compileall -q MessageConsumer Settlement Ops`
- 本步单元验证：`TC-PVAM-07B-08`
- 完成证据：`EV-PVAM-07B-05`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：无durable source则IN_DOUBT

### STEP-PVAM-07B-06：容量/兼容/故障测试

- 目的：容量/兼容/故障测试，落实 `TASK-PVAM-07B` 的已批准目标。
- 前置条件：STEP-07B-01~05
- 修改文件：新增测试与UAT脚本
- 目标符号：pytest/UAT
- 精确操作：
1. 发布100001+消息、多group、慢handler、重启、DLQ失败、dual-read/publish。
- 必须保持：不得只测单消费者
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m pytest -q MessageConsumer/Test/test_recalc_event_v2.py MessageConsumer/Test/test_stream_retention.py`
- 本步单元验证：`TC-PVAM-07B-01~09`
- 完成证据：`EV-PVAM-07B-06`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任何不可恢复丢失不得发布

## 8. 数据迁移、兼容与重跑

### 8.1 数据变化

| 对象 | 旧格式/状态 | 新格式/状态 | 转换位置 | 版本识别 | 异常数据策略 |
|---|---|---|---|---|---|
| Stream payload | 无统一schema/同名异构 | v2 envelope | 统一publisher | schema/event_id/hash | v1兼容decoder |
| Stream保留 | MAXLEN~100000 | ACK-aware MINID | retention job | trim manifest | 无证明不trim |

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
| TC-PVAM-07B-01 | 契约 | v2变体唯一 | Global/Elite/Placement完成事件 | 各自映射唯一schema+handler | STEP-07B-01/03 | DEV+UAT | NOT_RUN |
| TC-PVAM-07B-02 | 兼容 | 旧同名done | 字段充分/不足两类 | 充分时确定映射；不足时DLQ/KEEP_PEL，不猜 | STEP-07B-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-07B-03 | 幂等 | dual publish/read | 同event_id v1/v2 | handler只执行一次 | STEP-07B-02/03 | DEV+UAT | NOT_RUN |
| TC-PVAM-07B-04 | 静态 | 固定maxlen清除 | 全仓AST/grep | 生产xadd无maxlen=100000 | STEP-07B-02 | DEV | NOT_RUN |
| TC-PVAM-07B-05 | handler | postcondition失败 | handler返回但proof缺失 | KEEP_PEL/RETRY，不ACK | STEP-07B-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-07B-06 | 容量 | 100001消息+慢group | fast已ACK、slow未ACK | trim点不越slow安全水位；所有payload存在 | STEP-07B-04/06 | UAT | NOT_RUN |
| TC-PVAM-07B-07 | 多group | 三group不同PEL | group状态fixture | 取最小安全水位；任一异常不trim | STEP-07B-04 | DEV+UAT | NOT_RUN |
| TC-PVAM-07B-08 | 恢复 | ghost/deleted ID | durable源有/无 | 有则同event_id恢复；无则IN_DOUBT | STEP-07B-05 | UAT | NOT_RUN |
| TC-PVAM-07B-09 | 重启 | consumer kill/reclaim | handler中途kill | 重启后幂等完成，无丢/重 | STEP-07B-06 | UAT | NOT_RUN |

受控检查方案用例映射：`TC-023, TC-025, TC-026, TC-027, TC-028, TC-029, TC-031, TC-032`。`TC-000` 为 RETIRED，不执行、不计完成率。

### 9.2 开发环境自动验证

```bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_SHA="3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2"
: "${WORK_COMMIT_SHA:?set the implementation commit for WORK-PVAM-07B}"
: "${PARENT_COMMIT_SHA:?set the controlled parent commit; root WORK uses BASE_SHA}"
: "${PARENT_TREE_SHA:?set the tree of PARENT_COMMIT_SHA}"
: "${PARENT_PROVENANCE_JSON:?set schema-v2 parent provenance JSON}"
: "${APPROVED_COMMIT_REGISTRY_JSON:?set canonical WORK_APPROVED_COMMIT_REGISTRY.json}"
CONTROL_ROOT="${PVAM_CONTROL_ROOT:?point to the released 05_CONTROL directory}"

# Phase A：只验证固定基线和既有锚点，不要求 Common/Settlement/Ops 等未来目录存在。
bash "$CONTROL_ROOT/check_baseline_preflight.sh" \
  --repo "$REPO_ROOT" --base "$BASE_SHA" --work-id "WORK-PVAM-07B"

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
  --work-id "WORK-PVAM-07B" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --test-command-file "$CONTROL_ROOT/work-test-commands/WORK-PVAM-07B.sh" \
  --out "evidence/WORK-PVAM-07B/dev"
```

#### 9.2.1 必须落地的关键 `assert` 契约

以下断言骨架必须进入本任务列出的 pytest 文件；fixture 由测试文件实现，不得用复制生产公式的替身替代被测符号。

```python
from MessageConsumer.RecalcEventSchema import decode_recalc_event


def test_event_variant_and_retention_contract(retention_planner) -> None:
    global_event = decode_recalc_event({"schema_version": 2, "domain": "GLOBAL", "event_type": "RECALC_DONE", "subtype": "USER_STATS", "event_id": "e1", "payload": {}})
    elite_event = decode_recalc_event({"schema_version": 2, "domain": "ELITE", "event_type": "BATCH_READY", "subtype": "ELITE_BONUS", "event_id": "e2", "payload": {}})
    assert global_event.variant_key != elite_event.variant_key
    plan = retention_planner.plan(group_safe_ids={"fast": "200-0", "slow": "100-0"}, unresolved_pel_ids=["101-0"])
    assert plan.apply_allowed is False
    assert plan.safe_before_id <= "100-0"
```

通过标准：所有命令 exit code 0；pytest 无未解释 skip；证据schema校验通过。GPU/Dask/真实Redis/Kafka/MySQL未在DEV执行时必须标注 `NOT_RUN/PENDING_TEST_ENV`。

### 9.3 测试环境手工执行包

#### ENV-TC-PVAM-07B-01：事件v2/handler/100001/trim/ghost

- 对应受控测试：`TC-023、TC-025、TC-026、TC-027、TC-028、TC-032`
- 环境版本：由 `uat/environment_manifest.yaml` 固定 Python/CUDA/RAPIDS/Dask/Redis/Kafka/DB/镜像/commit。
- 前置服务与数据：Redis容量隔离；至少2个consumer groups；durable registry/manifest fixture
- 清理/隔离：必须使用专用 topic/group、Redis前缀、period/run_id；禁止复用生产数据。
- 执行命令：

```bash
RUN_ID=work07b-$(date +%Y%m%d%H%M%S)
bash uat/scripts/run_work_uat.sh --work WORK-PVAM-07B --run-id "$RUN_ID" --tc TC-023,TC-025,TC-026,TC-027,TC-028,TC-032
```

- SQL/数据库证据命令（仅在专用 UAT schema 和 WORK-08 manifest 校验通过后执行；N/A 项只保留说明）：

```bash
# N/A：本任务验证 Redis Stream schema/handler/retention，不执行 SQL。
```

- 执行步骤：
1. dual-publish v1/v2并执行handler
2. 制造100001条backlog和多group进度差
3. 执行retention dry-run/commit
4. 删除待处理entry并测试恢复
5. kill/restart consumer
- 精确预期：
- 未ACK不被trim
- 同event_id不重复执行
- ghost可恢复或IN_DOUBT
- manifest完整且无fixed MAXLEN
- 必须回传：完整命令、exit code、stdout/stderr、JUnit/JSON、输入fixture SHA-256、代码commit、镜像、环境版本、执行起止时间、Redis/DB/Kafka/Dask前后证据。
- 失败停止与清理：停止专用consumer/job；保留PEL/状态和证据；禁止在未分析前清理失败现场；按第11节回滚。

### 9.4 SQL 对账样例

| 样例 | SQL输入/来源 | SQL预期 | Python预期 | 比较口径 | 允许差异 |
|---|---|---|---|---|---|
| N/A | 事件/Stream治理 | N/A | N/A | Redis事件合同 | N/A |

## 10. 验收标准映射

| 验收编号 | 来源TASK验收项 | 实现步骤 | 测试用例 | 所需证据 | 环境 | 通过条件 |
|---|---|---|---|---|---|---|
| AC-01 | 所有生产事件变体在 registry 中唯一映射 schema、handler、disposition | STEP-PVAM-07B-01/03/06 | TC-027 | EV-PVAM-07B-01 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-02 | Global/Elite/Placement 完成事件可无歧义区分并执行不同 handler | STEP-PVAM-07B-01/03/06 | TC-027、TC-029 | EV-PVAM-07B-02 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-03 | handler 后置条件不满足时不 ACK；audited no-op 必须有批准编号与审计记录 | STEP-PVAM-07B-01/03/06 | TC-027 | EV-PVAM-07B-03 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-04 | 所有 producer 不再使用固定 `maxlen=100000` | STEP-PVAM-07B-02/06 | TC-028、TC-031 | EV-PVAM-07B-04 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-05 | 多 group 慢消费者场景，未 ACK 消息不被 trim | STEP-PVAM-07B-04/06 | TC-028 | EV-PVAM-07B-05 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-06 | 超过100000消息、长 PEL、DLQ失败、consumer重启均不丢 payload | STEP-PVAM-07B-04/05/06 | TC-027、TC-028 | EV-PVAM-07B-06 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-07 | ghost entry 通过 registry/manifest 恢复或进入 IN_DOUBT，不直接 ACK | STEP-PVAM-07B-05/06 | TC-028 | EV-PVAM-07B-07 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-08 | trim job 生成 group 水位、PEL、范围、checksum 和恢复可用性证明 | STEP-PVAM-07B-04/06 | TC-028、TC-032 | EV-PVAM-07B-08 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-09 | 旧 `SETTLEMENT_PERIOD_DONE` 兼容 decoder 无法消歧时进入 DLQ/重试，不猜测路由 | STEP-PVAM-07B-03/06 | TC-027 | EV-PVAM-07B-09 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-10 | v2 producer/consumer 切换、dual-read/短期 dual-publish 和回滚保持 event_id 幂等 | STEP-PVAM-07B-02/03/06 | TC-023、TC-025、TC-026、TC-032 | EV-PVAM-07B-10 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |

没有 STEP、TC 或 EV 映射的AC不得标记完成。任何含UAT的AC在未回传真实环境证据时只能为 `PENDING_TEST_ENV/BLOCKED`。

## 11. 风险、停工与回滚

### 11.1 风险清单

| 风险 | 触发条件 | 影响 | 预防措施 | 监测/证据 | 处置 |
|---|---|---|---|---|---|
| backlog占内存 | 移除fixed trim | Redis压力 | 容量模型/背压/运维告警 | memory/XLEN/lag | 停producer或扩容，不假trim |
| dual-publish双处理 | compat窗口 | 重复副作用 | event_id幂等 | handler ledger | 关闭v2写回滚 |
| group漏登记 | trim越过未知消费者 | 事件丢失 | group registry+deny trim | XINFO GROUPS diff | BLOCK trim |

### 11.2 本任务强制停工条件

- HEAD、SQL blob、模型schema或上游TASK与受控基线不一致。
- 实施必须改变未批准的业务规则、精度、资格、分母、Country或发布职责才能继续。
- 需要修改排除文件/模块或扩大异常白名单才能通过测试。
- 关键mutation存活、SQL黄金样例出现未批准差异、幂等/原子/回滚断言失败。
- UAT权限、schema、数据或隔离条件不足；此时保持 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV`。

### 11.3 部署面与数据面回滚门禁

**当前可执行性：`BLOCKED_EXTERNAL_EVIDENCE`。** 当前材料没有给出真实部署系统、workload/release、镜像、配置对象和健康检查命令，因此不得以本地`export`或通用`git revert`冒充部署回滚。

部署前必须提供并签署`evidence/WORK-PVAM-07B/rollback/ROLLBACK-MANIFEST-PVAM-v1.json`，至少包含：

- `deployment_system`、`environment`、`workload_id`、`release_before/after`、`image_before/after`；
- 精确的停止、回滚、恢复、健康检查和重新放量命令；
- Redis/Stream/ledger/run/manifest的备份或快照位置及SHA-256；
- 执行人、复核人、批准时间、允许的数据恢复范围；
- 命令dry-run/隔离演练的退出码和原始日志。

本任务数据面处置：停止 producer/consumer；导出 XLEN/XPENDING/group 水位。默认回滚必须保持 producer 无固定 MAXLEN，仅关闭 v2 schema/handler 与 retention job。任何恢复 fixed MAXLEN 的动作都不得由 XLEN 或 ghost 当前值单独授权，只能进入 §11.3A 的运维/架构双签紧急例外门禁；未完整满足六类容量、速率、告警、停止阈值、未 ACK 保护和再升级条件时禁止执行。

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


#### 11.3A 固定 MAXLEN 紧急例外门禁

默认回滚**禁止**恢复已知不安全的 `maxlen=100000`。兼容回退应保持 producer 无固定 MAXLEN，只关闭 v2 schema/handler 与 retention job。

只有运维负责人和架构负责人共同签署紧急例外时，才可临时恢复固定 MAXLEN；签署的 rollback manifest 必须同时给出：

1. 最长临时窗口和强制再升级时间；
2. 期间最大写入速率、容量上界与计算依据；
3. `XLEN`、所有 group 的 `XPENDING`、consumer lag、ghost/`IN_DOUBT` 实时告警；
4. 自动停止写入/回滚的阈值和精确执行命令；
5. 未 ACK 消息保护与完整重放证明；
6. 当班责任人、批准人及监控证据 URI/SHA。

缺任一项，或运行期间任一阈值越界，必须保持无固定 MAXLEN 的 producer 版本，不得执行代码 revert。

## 12. 交付物与完成证据

| 编号 | 交付物/证据 | 生成步骤 | 位置/格式 | 验收人 | artifact_status |
|---|---|---|---|---|---|
| EV-PVAM-07B-01 | AC-01验收证据：所有生产事件变体在 registry 中唯一映射 schema、handler、disposition | STEP-PVAM-07B-01/03/06 | evidence/WORK-PVAM-07B/attempt-*/ac/AC-01/ | 待指派QA | PENDING |
| EV-PVAM-07B-02 | AC-02验收证据：Global/Elite/Placement 完成事件可无歧义区分并执行不同 handler | STEP-PVAM-07B-01/03/06 | evidence/WORK-PVAM-07B/attempt-*/ac/AC-02/ | 待指派QA | PENDING |
| EV-PVAM-07B-03 | AC-03验收证据：handler 后置条件不满足时不 ACK；audited no-op 必须有批准编号与审计记录 | STEP-PVAM-07B-01/03/06 | evidence/WORK-PVAM-07B/attempt-*/ac/AC-03/ | 待指派QA | PENDING |
| EV-PVAM-07B-04 | AC-04验收证据：所有 producer 不再使用固定 `maxlen=100000` | STEP-PVAM-07B-02/06 | evidence/WORK-PVAM-07B/attempt-*/ac/AC-04/ | 待指派QA | PENDING |
| EV-PVAM-07B-05 | AC-05验收证据：多 group 慢消费者场景，未 ACK 消息不被 trim | STEP-PVAM-07B-04/06 | evidence/WORK-PVAM-07B/attempt-*/ac/AC-05/ | 待指派QA | PENDING |
| EV-PVAM-07B-06 | AC-06验收证据：超过100000消息、长 PEL、DLQ失败、consumer重启均不丢 payload | STEP-PVAM-07B-04/05/06 | evidence/WORK-PVAM-07B/attempt-*/ac/AC-06/ | 待指派QA | PENDING |
| EV-PVAM-07B-07 | AC-07验收证据：ghost entry 通过 registry/manifest 恢复或进入 IN_DOUBT，不直接 ACK | STEP-PVAM-07B-05/06 | evidence/WORK-PVAM-07B/attempt-*/ac/AC-07/ | 待指派QA | PENDING |
| EV-PVAM-07B-08 | AC-08验收证据：trim job 生成 group 水位、PEL、范围、checksum 和恢复可用性证明 | STEP-PVAM-07B-04/06 | evidence/WORK-PVAM-07B/attempt-*/ac/AC-08/ | 待指派QA | PENDING |
| EV-PVAM-07B-09 | AC-09验收证据：旧 `SETTLEMENT_PERIOD_DONE` 兼容 decoder 无法消歧时进入 DLQ/重试，不猜测路由 | STEP-PVAM-07B-03/06 | evidence/WORK-PVAM-07B/attempt-*/ac/AC-09/ | 待指派QA | PENDING |
| EV-PVAM-07B-10 | AC-10验收证据：v2 producer/consumer 切换、dual-read/短期 dual-publish 和回滚保持 event_id 幂等 | STEP-PVAM-07B-02/03/06 | evidence/WORK-PVAM-07B/attempt-*/ac/AC-10/ | 待指派QA | PENDING |
| EV-PVAM-07B-P01 | v2 schema/registry/disposition源码 | 对应STEP/TC | evidence/WORK-PVAM-07B/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-07B-P02 | 统一publisher与producer diff | 对应STEP/TC | evidence/WORK-PVAM-07B/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-07B-P03 | ACK-aware retention/ghost recovery | 对应STEP/TC | evidence/WORK-PVAM-07B/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-07B-P04 | DEV兼容测试 | 对应STEP/TC | evidence/WORK-PVAM-07B/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-07B-P05 | UAT多group/100001/restart证据 | 对应STEP/TC | evidence/WORK-PVAM-07B/attempt-*/package/ | 待指派QA | PENDING |

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
  --work-id "WORK-PVAM-07B" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --out "evidence/WORK-PVAM-07B/patch"
```

门禁必须证明：

1. `BASE_SHA` 是 `WORK_COMMIT_SHA` 的祖先；
2. 全部新增、修改、删除和 rename 的旧/新路径均落在 `WORK-PVAM-07B` 批准 allowlist；
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
| STEP-PVAM-07B-01 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-07B-02 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-07B-03 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-07B-04 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-07B-05 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-07B-06 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |

### 13.2 实际验证

| 测试 | 环境 | 命令/版本 | 结果 | 证据 | 执行时间 |
|---|---|---|---|---|---|
| TC-PVAM-07B-01 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-07B-* | 待执行 |
| TC-PVAM-07B-02 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-07B-* | 待执行 |
| TC-PVAM-07B-03 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-07B-* | 待执行 |
| TC-PVAM-07B-04 | DEV | 待执行 | NOT_RUN | EV-PVAM-07B-* | 待执行 |
| TC-PVAM-07B-05 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-07B-* | 待执行 |
| TC-PVAM-07B-06 | UAT | 待执行 | NOT_RUN | EV-PVAM-07B-* | 待执行 |
| TC-PVAM-07B-07 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-07B-* | 待执行 |
| TC-PVAM-07B-08 | UAT | 待执行 | NOT_RUN | EV-PVAM-07B-* | 待执行 |
| TC-PVAM-07B-09 | UAT | 待执行 | NOT_RUN | EV-PVAM-07B-* | 待执行 |

### 13.3 未完成项

| 项目 | 原因 | 风险 | 后续动作 | 责任人 | 截止时间 |
|---|---|---|---|---|---|
| UAT/外部材料 | 当前计划阶段未执行 | 不能关闭P0/P1 | 由WORK-08准入后执行 | 待指派 | 待批准 |

## 14. 偏离、发现项与上游回流

| 编号 | 类型 | 发现事实 | 是否影响业务/范围 | 临时动作 | 需要更新 | 最终裁决 |
|---|---|---|---|---|---|---|
| `DEV-PVAM-07B-001` | `预留` | 待执行 | 待判断 | 停工/隔离 | WORK/TASK/DEC/REVIEW | 待裁决 |

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
| v1.0 | 2026-08-04 | 初版施工任务书 | `TASK-PVAM-07B` + `PLAN-PVAM-v1.15` + 固定代码基线 | AI Agent（编制） | DRAFT |
| v1.1 | 2026-08-05 | 依据二轮核验报告完成定点修订并补齐治理追溯 | F-A/F-B/F-H/F-I/F-J/F-K/F-F/F-E/F-L/F-M/F-N 中适用项 | AI Agent（编制） | DRAFT |
| v1.2 | 2026-08-05 | 闭合 G-1：统一 `RecalcProcessResult` 类名并补齐 `should_ack`；历史版本曾调整施工套件审批状态，不改变 CHK/DEC/TASK/WORK 范围 | 历史会话声明（未形成可独立验证组织授权，现由 v1.3 取代） | AI Agent（编制） | SUPERSEDED |
| v1.3 | 2026-08-05 | 第四轮关闭 F3-01～F3-10：治理回退 DRAFT、Traceability v3、patch/DEV 双阶段、状态枚举及设计边界 | 三轮审查报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r6 | 2026-08-06 | 五轮 F5 定点修订：规范 v3 追溯、parent provenance/DEV CLI、控制状态字段及单一事实源 | 五轮审计报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r7 | 2026-08-06 | 六轮 S6：信任 registry 初版、归档哈希、临时目录与 Decimal finite 防护 | 六轮终局审计报告 | AI Agent（编制） | DRAFT |
| v1.3-r8 | 2026-08-06 | 七轮 B7：registry 发布信任根、四工件摘要、AC 来源保真及当前轮次引用 | 七轮终局审计报告 + B7 处置 | AI Agent（编制） | DRAFT |

<!-- END WORK-PVAM-07B_事件路由与Stream保留.md -->

---

<!-- BEGIN WORK-PVAM-08_UAT准入与证据治理.md -->

# WORK-PVAM-08 风险、UAT 准入与机器可读证据包施工任务书

> 文档定位：来源于待组织批准的 `TASK-PVAM-08`，在取得组织授权后转化为可执行施工说明。本文件不重新决定业务规则；实际结果只能写入执行记录与验证交付报告。

## 0. 填写与执行规则

1. 上游修改任务与本 v1.3 施工套件当前均为 `DRAFT`；没有组织授权前，本任务保持 `BLOCKED`，不得启动代码施工或部署。
2. 本任务不修改业务计算代码；RISK/UV 仅生成验证、证据与阻断动作，OPT-001/002 仅生成已批准的测试/治理工具。
3. 基线必须精确等于 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；发现漂移立即登记 `BLOCK-PVAM-08-BASELINE`。
4. 所有新文件/符号已在变更表标为“新增”；其余锚点均来自固定基线。
5. DEV替身不能冒充真实Kafka/Redis/Dask/GPU/MySQL UAT验证。

## 1. 文档信息与追溯关系

| 字段 | 内容 |
|---|---|
| 施工任务编号 | `WORK-PVAM-08` |
| 施工任务名称 | 风险、UAT 准入与机器可读证据包 |
| 所属施工总方案 | `WORK-PLAN-PVAM_v1.3` |
| 来源修改任务 | `TASK-PVAM-08@MODPLAN-PVAM_v1.2`（authorization=PENDING_ORGANIZATIONAL_APPROVAL） |
| 来源问题 | `RISK-001、RISK-002、UV-001～UV-005、OPT-001、OPT-002、GAP-DEC004-2B` |
| 复核闭环追踪号 | RISK/UV/OPT 无预登记 REM/W/V；`UV-002 → UAT-011`；由 AC-11 生成机器可读追踪 manifest |
| 来源检查项 | `CHK-ARCH-001、CHK-DATA-006、CHK-DATA-007、CHK-BIZ-002、CHK-BIZ-007、CHK-BIZ-008、CHK-BIZ-009、CHK-BIZ-011、CHK-EVT-003～007、CHK-PUB-001、CHK-PUB-002、CHK-TEST-001～004` |
| 关联决策 | `DEC-004、DEC-009、DEC-010、DEC-012、DEC-013、DEC-017、DEC-018` |
| 代码基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| SQL基线 | `sql_uat/*@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，仅有效SQL |
| 文档版本 | `v1.3` |
| 负责人 | `待指派 / 实施工程师` |
| 复核人 | `待指派 / 架构与QA` |
| 当前状态 | `BLOCKED` |
| 文档治理状态 | `DRAFT`（`PENDING_ORGANIZATIONAL_APPROVAL`） |
| 前置任务 | 阶段A可与所有DEV任务并行；阶段B依赖DEC-013及WORK-01～07B DEV_VERIFIED |
| 功能开关 | `N/A（治理/验证任务）` |

### 1.1 一对一追溯摘要

```text
CHK-ARCH-001、CHK-DATA-006、CHK-DATA-007、CHK-BIZ-002、CHK-BIZ-007、CHK-BIZ-008、CHK-BIZ-009、CHK-BIZ-011、CHK-EVT-003～007、CHK-PUB-001、CHK-PUB-002、CHK-TEST-001～004
  └─ RISK-001、RISK-002、UV-001～UV-005、OPT-001、OPT-002、GAP-DEC004-2B
       └─ DEC-004、DEC-009、DEC-010、DEC-012、DEC-013、DEC-017、DEC-018
            └─ TASK-PVAM-08 (DRAFT / PENDING_ORGANIZATIONAL_APPROVAL)
                 └─ WORK-PVAM-08
                      ├─ STEP-PVAM-08-01 / STEP-PVAM-08-02 / STEP-PVAM-08-03 / STEP-PVAM-08-04 / STEP-PVAM-08-05 / STEP-PVAM-08-06 / STEP-PVAM-08-07
                      ├─ TC-PVAM-08-01 / TC-PVAM-08-02 / TC-PVAM-08-03 / TC-PVAM-08-04 / TC-PVAM-08-05 / TC-PVAM-08-06 / TC-PVAM-08-07 / TC-PVAM-08-08 / TC-PVAM-08-09
                      └─ EV-PVAM-08-01...
```

## 2. 施工任务生成依据

### 2.1 上游输入

| 输入 | 编号/版本 | 本任务使用的结论 | 状态 |
|---|---|---|---|
| 复核报告 | `Redemption_PV_Amount_Migration_d74_复核报告_v1.5` | RISK-001、RISK-002、UV-001～UV-005、OPT-001、OPT-002、GAP-DEC004-2B 的事实、状态与边界 | CONFIRMED |
| 修改任务书 | `TASK-PVAM-08` | 采用方案、范围、排除项、AC | DRAFT（待组织授权） |
| 检查方案 | `PLAN-PVAM-v1.15` | CHK-ARCH-001、CHK-DATA-006、CHK-DATA-007、CHK-BIZ-002、CHK-BIZ-007、CHK-BIZ-008、CHK-BIZ-009、CHK-BIZ-011、CHK-EVT-003～007、CHK-PUB-001、CHK-PUB-002、CHK-TEST-001～004 | CONTROLLED |
| 正式决策 | DEC-004、DEC-009、DEC-010、DEC-012、DEC-013、DEC-017、DEC-018 | 只执行已关闭裁决；开放项阻断 | CLOSED / 按上游登记 |
| 代码/SQL快照 | 3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2 | 唯一施工对象 | FROZEN |
| 施工模板 | 总方案模板/专项模板 | 章节、状态、证据纪律 | CONTROLLED |

### 2.2 开工条件

- [ ] 当前 HEAD 精确为 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，工作树无未登记变更。
- [ ] `TASK-PVAM-08` 的人工批准记录已归档；本 `WORK` 已由施工负责人和复核人签署。
- [ ] 前置关系满足：阶段A可与所有DEV任务并行；阶段B依赖DEC-013及WORK-01～07B DEV_VERIFIED。
- [ ] 本任务涉及的接口、单位、精度、兼容和回滚边界已由上游任务固定。
- [ ] DEV测试依赖已安装；UAT项具备WORK-08生成的环境/数据/schema manifest。
- [ ] 功能开关默认关闭，回滚路径已演练。

未满足任一关键项时，本任务状态为 `BLOCKED`；不得用假设替代。

## 3. 问题事实与施工目标

### 3.1 已确认问题

| 项目 | 内容 |
|---|---|
| 预期行为 | 不修改奖金业务代码，建立环境/数据/schema/config/callgraph/执行/证据manifest、可复制UAT脚本和机器追踪链；在 DEC-013 未关闭或外部材料缺失时保持 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV`；未生成工件使用 `artifact_status=PENDING`，不伪造 PASS。 |
| 当前行为 | 真实Kafka/Redis/Dask/RAPIDS/MySQL全链路、SQL-Python同数据差分、ACK/PEL/trim/崩溃恢复均未在当前开发环境完成。；DEC-009最小schema manifest、SQL_MODE、assignment对象与批准记录尚需外部提供。；TopologyMutationService生产可达性缺完整archive/部署证明。；候选测试缺原始stdout/stderr/exit/JUnit与固定镜像重跑包。；现有部分测试为脚本/demo，需要pytest可收集包装和机器可读追踪manifest。 |
| 差异 | 当前实现缺少本任务批准的唯一合同、门禁或原子边界。 |
| 影响 | 金额/PV单位、奖金、并发一致性、发布或可恢复性，具体见来源问题。 |
| 严重级别 | P0 / P1 / 优化 |
| 证据位置 | 固定代码基线 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；来源 `TASK-PVAM-08`；检查项 `CHK-ARCH-001、CHK-DATA-006、CHK-DATA-007、CHK-BIZ-002、CHK-BIZ-007、CHK-BIZ-008、CHK-BIZ-009、CHK-BIZ-011、CHK-EVT-003～007、CHK-PUB-001、CHK-PUB-002、CHK-TEST-001～004` |

### 3.2 已确认代码事实

- 真实Kafka/Redis/Dask/RAPIDS/MySQL全链路、SQL-Python同数据差分、ACK/PEL/trim/崩溃恢复均未在当前开发环境完成。
- DEC-009最小schema manifest、SQL_MODE、assignment对象与批准记录尚需外部提供。
- TopologyMutationService生产可达性缺完整archive/部署证明。
- 候选测试缺原始stdout/stderr/exit/JUnit与固定镜像重跑包。
- 现有部分测试为脚本/demo，需要pytest可收集包装和机器可读追踪manifest。

### 3.3 本任务目标

不修改奖金业务代码，建立环境/数据/schema/config/callgraph/执行/证据manifest、可复制UAT脚本和机器追踪链；在 DEC-013 未关闭或外部材料缺失时保持 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV`；未生成工件使用 `artifact_status=PENDING`，不伪造 PASS。

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
| 1 | DEV测试 | 现有test与脚本 | 本地依赖 | 部分可运行 | 不能证明真实中间件 |
| 2 | UAT环境 | 外部测试环境 | 未获准入 | 不可执行 | UV-001等 |
| 3 | Schema | DBA最小manifest | 待提供 | 检查项BLOCKED | UV-002 |
| 4 | Topology | 源码/测试 | 只有代码与测试证据 | 生产可达未知 | RISK-001 |
| 5 | 证据 | 二手报告 | 缺原始包 | 不可复验 | RISK-002 |

### 4.2 当前错误形成点

当前链路在上述入口缺少本任务目标合同，导致已确认问题在写入、计算、路由或发布边界形成并传播。修改必须落在表中稳定符号或明确标记为“新增”的边界；不得通过外围日志掩盖。

### 4.3 受影响消费者

| 消费者 | 依赖内容 | 预期影响 | 是否同步修改 | 对应步骤/测试 |
|---|---|---|---|---|
| 所有WORK任务 | DEV/UAT执行器与证据目录 | 提供统一脚本/manifest | 是 | STEP-08-01~05 |
| 技术复核 | traceability_manifest | 双向追踪 | 是 | TC-031/032 |
| DBA/架构 | schema manifest | 批准与哈希 | 外部 | TC-008/019/029 |
| WORK-06 | Topology callgraph | 触发TOPO-WIRE-01核验现有接线/实施缺失接线分支 | 是 | TC-011/024/030 |

## 5. 施工设计

### 5.1 采用方案

- 新增 `evidence/manifest.schema.json` 和按 `WORK/attempt` 不可覆盖目录；每次执行记录commit/image/config/schema/data/command/exit/time/checksum。
- 新增 `uat/environment_manifest.yaml`、`schema_manifest.yaml`、`config_snapshot_manifest.yaml`、`test_run_manifest.yaml`、`callgraph_manifest.json`。
- 新增 `uat/scripts/check_baseline.sh`、`run_work_dev.sh`、`run_work_uat.sh`、`run_sql_python_diff.py`、`redis_stream_probe.py`、`build_callgraph.py`、`build_traceability_manifest.py`、`verify_evidence_pack.py`。
- 新增 `traceability_manifest.json`，覆盖 CHK→R/RISK/UV→DEC→TASK→WORK→STEP→controlled TC/local TC→EV。
- OPT-001：把脚本测试包成pytest/unittest可收集入口，保留CLI smoke但不计正式通过。
- GAP-DEC004-2B保持DEFERRED；fixture manifest必须明确其不能关闭生产供给链。

选择理由：

- 与有效SQL、已关闭DEC及来源TASK目标一致。
- 采用 additive-first、显式version/manifest/feature flag，支持独立合入和回滚。
- 将纯函数、I/O适配、业务计算、权威提交和证据采集分层，便于DEV替身与UAT真实验证分别取证。

### 5.2 被否决方案

| 方案 | 不采用原因 | 来源 |
|---|---|---|
| 无证据标PASS | 违反Loop闭环 | CHK-TEST-004 |
| 截图代替原始日志 | 不可重放 | 证据规范 |
| 缺schema时推定 | DEC-009要求BLOCK | DEC-009 |
| 基于RISK-001新建生产接线 | UAT_VERIFY不授权代码 | 施工铁律 |
| 把DEC-010测试豁免写成Gate C关闭 | 生产条件仍OPEN | DEC-010 |

### 5.3 修改后调用链与数据契约

| 边界 | 输入 | 处理 | 输出 | 断言/错误行为 | 责任符号 |
|---|---|---|---|---|---|
| 施工入口 | 固定commit + 批准TASK + N/A（治理/验证任务） | 先执行基线/前置检查 | 受控diff | 任一前置失败即BLOCK | `evidence/manifest.schema.json`、目录规范 |
| 核心处理 | strict version/type/period/run合同 | 按STEP顺序执行 | 可测试状态/事件/金额 | 非法类型、状态或proof fail-loud | 见CHG表 |
| 证据出口 | 命令、输入、输出、状态前后 | WORK-08 schema封装 | EV包+SHA-256 | 缺原始证据不得PASS | `uat/scripts/*` |

## 6. 文件与符号级变更清单

| 变更编号 | 文件 | 类/函数/字段/表 | 类型 | 修改前行为 | 要求的修改 | 修改后行为 | 禁止行为 |
|---|---|---|---|---|---|---|---|
| CHG-01 | `evidence/manifest.schema.json` | 证据schema | 新增 | 不存在 | 定义不可变attempt元数据 | 统一证据格式 | 不得覆盖旧attempt |
| CHG-02 | `uat/*.yaml/json` | 环境/schema/config/run/callgraph manifest | 新增 | 不存在 | 模板与校验规则 | 外部材料可审计 | 不得写密钥 |
| CHG-03 | `uat/scripts/check_baseline.sh` / `uat/scripts/run_work_dev.sh` / `uat/scripts/run_work_uat.sh` / `uat/scripts/stop_workload.sh` | 执行器 | 新增 | 不存在 | 固定commit、命令、日志、exit、checksum | 可复制运行 | 不得伪造结果 |
| CHG-04 | `uat/scripts/run_sql_python_diff.py` | 差分器 | 新增 | 不存在 | 保存输入/SQL中间/Python中间/字段diff | Legacy/Corrected分列 | 不得只输出总PASS |
| CHG-05 | `uat/scripts/redis_stream_probe.py` | Stream证据工具 | 新增 | 不存在 | XLEN/XINFO/XPENDING/XRANGE/trim/replay采集 | ACK证据完整 | 不得执行危险trim默认 |
| CHG-06 | `uat/scripts/build_callgraph.py` | 调用图工具 | 新增 | 不存在 | AST/import/entry/deploy引用清单 | Topology与所有P0可达性 | 不得把测试当生产 |
| CHG-07 | `traceability_manifest.json` / `uat/scripts/build_traceability_manifest.py` | 追踪 | 新增 | 不存在 | 机器双向链与完整性校验 | 无孤儿编号 | 不得把TC-000计完成 |
| CHG-08 | 现有脚本测试包装器 | pytest entry | 新增/修改测试 | print/CLI为主 | 可收集且有assert/exit/JUnit | OPT-001落地 | 不得改生产算法 |

### 6.1 本任务代码边界

本任务只能新增测试、证据、manifest、callgraph和执行包装器，不得修改奖金公式、金额转换、业务状态或生产handler。所有RISK/UV保持验证状态；材料缺失不自动升级成代码缺陷。

### 6.2 可复制命令参数规范

所有脚本必须使用强制环境变量，禁止尖括号占位：

```bash
: "${REPO_ROOT:?set REPO_ROOT}"
: "${RUN_ID:?set RUN_ID}"
: "${REDIS_HOST:?set REDIS_HOST}"
: "${REDIS_PORT:?set REDIS_PORT}"
: "${REDIS_DB:?set REDIS_DB}"
: "${UAT_PERIOD:?set UAT_PERIOD}"

git -C "$REPO_ROOT" rev-parse HEAD
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -n "$REDIS_DB" INFO server
```

环境manifest必须分别记录Python redis客户端版本和Redis Server版本，不能互相推断。

### 6.3 Wave 0最小交付

在其他WORK引用`uat/scripts/*`前，08A先交付并DEV验证：

- `check_baseline.sh`：commit、工作树、有效文件过滤、SQL blob；
- `run_work_dev.sh`：原生命令包装，保留exit/stdout/stderr/JUnit；
- `build_callgraph.py`：输出入口、import、启动/部署证据及`CALLGRAPH_CONFIDENCE`；
- `build_traceability_manifest.py`：验证CHK→R→DEC→TASK→WORK→STEP→TC→EV无孤儿；
- `verify_evidence_pack.py`：schema、hash、时间戳、环境与命令完整性。

脚手架只能记录事实，不能生成PASS结论。所有实际执行状态初始为NOT_RUN。

> **DEV 执行口径：** `05_CONTROL/check_baseline_preflight.sh` 与 `05_CONTROL/validate_work_dev.sh` 是唯一强制门禁。STEP 中列出的 `py_compile`、`compileall` 或 `pytest` 命令仅是附加局部检查，不得替代 parent-tree、scope、patch、tree-hash 与专属测试门禁。

## 7. 可执行施工步骤

### STEP-PVAM-08-01：建立证据schema与目录

- 目的：建立证据schema与目录，落实 `TASK-PVAM-08` 的已批准目标。
- 前置条件：无
- 修改文件：`evidence/manifest.schema.json`、目录规范
- 目标符号：schema
- 精确操作：
1. 定义attempt id、hash、环境、命令、exit、stdout/stderr、输入/输出、状态
2. 脚本创建只增不改目录。
- 必须保持：不记录密钥/完整敏感数据
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m json.tool evidence/manifest.schema.json`
- 本步单元验证：`TC-PVAM-08-01`
- 完成证据：`EV-PVAM-08-01`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：schema 无法区分 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV` 与 `artifact_status=PENDING` 时停工

### STEP-PVAM-08-02：建立环境与外部材料manifest

- 目的：建立环境与外部材料manifest，落实 `TASK-PVAM-08` 的已批准目标。
- 前置条件：STEP-08-01
- 修改文件：`uat/*.yaml/json`
- 目标符号：manifest
- 精确操作：
1. 列明DEC-009/013批准、版本、SQL_MODE、对象hash、fixture来源/有效期。
- 必须保持：缺失必须BLOCKED
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python uat/scripts/verify_evidence_pack.py --schema-only`
- 本步单元验证：`TC-PVAM-08-02`
- 完成证据：`EV-PVAM-08-02`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：不得填推测值

### STEP-PVAM-08-03：实现DEV/UAT执行器

- 目的：实现DEV/UAT执行器，落实 `TASK-PVAM-08` 的已批准目标。
- 前置条件：STEP-08-01/02
- 修改文件：`uat/scripts/check_baseline.sh`、`run_work_*.sh`、`stop_workload.sh`
- 目标符号：shell
- 精确操作：
1. 严格 `set -euo pipefail`，校验commit，tee stdout/stderr，保存exit与sha256
2. 支持dry-run。
- 必须保持：不得内置密码/地址
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`bash -n uat/scripts/*.sh`
- 本步单元验证：`TC-PVAM-08-03`
- 完成证据：`EV-PVAM-08-03`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：基线不符立即退出

### STEP-PVAM-08-04：实现SQL差分与Stream探针

- 目的：实现SQL差分与Stream探针，落实 `TASK-PVAM-08` 的已批准目标。
- 前置条件：STEP-08-01/02
- 修改文件：两个Python脚本
- 目标符号：CLI
- 精确操作：
1. 参数化输入/连接从环境读取
2. 默认只读/dry-run
3. 输出机器JSON和原始查询。
- 必须保持：不得默认清表/trim
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile uat/scripts/run_sql_python_diff.py uat/scripts/redis_stream_probe.py`
- 本步单元验证：`TC-PVAM-08-04/05`
- 完成证据：`EV-PVAM-08-04`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：无法隔离时BLOCK

### STEP-PVAM-08-05：实现调用图与追踪manifest

- 目的：实现调用图与追踪manifest，落实 `TASK-PVAM-08` 的已批准目标。
- 前置条件：STEP-08-01
- 修改文件：callgraph/trace builder
- 目标符号：CLI
- 精确操作：
1. 过滤_bak/_final/demo
2. 区分production/test/demo
3. 校验每个AC有STEP/TC/EV。
- 必须保持：不得把grep命中直接当生产可达
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile uat/scripts/build_callgraph.py uat/scripts/build_traceability_manifest.py`
- 本步单元验证：`TC-PVAM-08-06/07`
- 完成证据：`EV-PVAM-08-05`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：存在孤儿P0链不得签署

### STEP-PVAM-08-06：包装现有脚本测试

- 目的：包装现有脚本测试，落实 `TASK-PVAM-08` 的已批准目标。
- 前置条件：STEP-08-03
- 修改文件：测试wrapper
- 目标符号：pytest
- 精确操作：
1. 为具名脚本建立可收集assert/exit
2. CLI smoke保留但标SMOKE。
- 必须保持：不复制生产公式
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m pytest --collect-only -q`
- 本步单元验证：`TC-PVAM-08-08`
- 完成证据：`EV-PVAM-08-06`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：收集0或只print不得验收

### STEP-PVAM-08-07：执行准入检查与生成UAT包

- 目的：执行准入检查与生成UAT包，落实 `TASK-PVAM-08` 的已批准目标。
- 前置条件：STEP-08-01~06
- 修改文件：所有manifest/scripts
- 目标符号：验证
- 精确操作：
1. 阶段 A 生成 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV` 与 `artifact_status=PENDING` 分域矩阵
2. DEC-013关闭后阶段B逐WORK运行并校验包。
- 必须保持：不把未运行标PASS
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python uat/scripts/verify_evidence_pack.py --root evidence`
- 本步单元验证：`TC-PVAM-08-01~09`
- 完成证据：`EV-PVAM-08-07`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任一必需材料缺失保持BLOCKED

## 8. 数据迁移、兼容与重跑

### 8.1 数据变化

| 对象 | 旧格式/状态 | 新格式/状态 | 转换位置 | 版本识别 | 异常数据策略 |
|---|---|---|---|---|---|
| 证据与测试记录 | 散落/二手 | 不可变manifest包 | 执行脚本 | attempt_id/checksum | 缺失保持BLOCKED |

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
| TC-PVAM-08-01 | schema | 证据状态枚举 | validation_status ∈ {NOT_RUN, PASS, FAIL, PENDING_TEST_ENV, BLOCKED} | schema全部接受且要求reason/links | STEP-08-01 | DEV | NOT_RUN |
| TC-PVAM-08-02 | 治理 | 缺schema/DEC批准 | 空manifest | 受影响TC自动标BLOCKED，不推定 | STEP-08-02 | DEV | NOT_RUN |
| TC-PVAM-08-03 | CLI | 基线不匹配 | 工作树HEAD非3891f4b9 | 脚本退出非0且未执行测试 | STEP-08-03 | DEV | NOT_RUN |
| TC-PVAM-08-04 | 差分 | 固定PE样例 | SQL/Python同输入 | 输出字段级0差异和原始中间文件 | STEP-08-04 | DEV+UAT | NOT_RUN |
| TC-PVAM-08-05 | 安全 | Stream probe默认 | 无`--apply-trim` | 只读，无XTRIM | STEP-08-04 | DEV | NOT_RUN |
| TC-PVAM-08-06 | 调用图 | Topology符号 | 源码测试引用+部署archive | 分类production/test/demo；不把测试升级为production | STEP-08-05 | DEV+UAT | NOT_RUN |
| TC-PVAM-08-07 | 追踪 | 全套编号 | 当前WORK套件 | 无孤儿R/AC/STEP/TC/EV；TC-000 retired | STEP-08-05 | DEV | NOT_RUN |
| TC-PVAM-08-08 | 测试收集 | pytest collect | 具名脚本包装 | 收集数>0且每用例有assert | STEP-08-06 | DEV | NOT_RUN |
| TC-PVAM-08-09 | 证据不可变 | 同attempt重复写 | 已有目录 | 拒绝覆盖，创建新attempt id | STEP-08-07 | DEV+UAT | NOT_RUN |

受控检查方案用例映射：`TC-001～TC-032` 全量；`TC-000` 为 RETIRED，不执行、不计完成率。

### 9.2 开发环境自动验证

```bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_SHA="3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2"
: "${WORK_COMMIT_SHA:?set the implementation commit for WORK-PVAM-08}"
: "${PARENT_COMMIT_SHA:?set the controlled parent commit; root WORK uses BASE_SHA}"
: "${PARENT_TREE_SHA:?set the tree of PARENT_COMMIT_SHA}"
: "${PARENT_PROVENANCE_JSON:?set schema-v2 parent provenance JSON}"
: "${APPROVED_COMMIT_REGISTRY_JSON:?set canonical WORK_APPROVED_COMMIT_REGISTRY.json}"
: "${WORK_STAGE:?set A or B for WORK-PVAM-08}"
CONTROL_ROOT="${PVAM_CONTROL_ROOT:?point to the released 05_CONTROL directory}"

# Phase A：只验证固定基线和既有锚点，不要求 Common/Settlement/Ops 等未来目录存在。
bash "$CONTROL_ROOT/check_baseline_preflight.sh" \
  --repo "$REPO_ROOT" --base "$BASE_SHA" --work-id "WORK-PVAM-08"

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
  --work-id "WORK-PVAM-08" \
  --stage "$WORK_STAGE" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --test-command-file "$CONTROL_ROOT/work-test-commands/WORK-PVAM-08.sh" \
  --out "evidence/WORK-PVAM-08/dev"
```

#### 9.2.1 必须落地的关键 `assert` 契约

以下断言骨架必须进入本任务列出的 pytest 文件；fixture 由测试文件实现，不得用复制生产公式的替身替代被测符号。

```python
import json
from pathlib import Path


def test_evidence_and_traceability_contract(tmp_path: Path, evidence_validator, trace_builder) -> None:
    manifest = {"validation_status": "BLOCKED", "reason": "DEC-013 not approved", "command": ["pytest", "-q"], "exit_code": None}
    evidence_validator.validate(manifest)
    out = tmp_path / "traceability.json"
    trace_builder.build(out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["retired_tests"] == ["TC-000"]
    assert data["orphan_required_nodes"] == []
```

通过标准：工作树、index、untracked和rename四类生产目录门禁均为0且输出为空；所有命令 exit code 0；pytest 无未解释 skip；证据schema校验通过。GPU/Dask/真实Redis/Kafka/MySQL未在DEV执行时必须标注 `NOT_RUN/PENDING_TEST_ENV`。

### 9.3 测试环境手工执行包

#### ENV-TC-PVAM-08-01：完整UAT准入与回传

- 对应受控测试：`TC-001～TC-032（TC-000 RETIRED）`
- 环境版本：由 `uat/environment_manifest.yaml` 固定 Python/CUDA/RAPIDS/Dask/Redis/Kafka/DB/镜像/commit。
- 前置服务与数据：DEC-013批准；固定镜像；DEC-009 manifest；专用数据/权限
- 清理/隔离：必须使用专用 topic/group、Redis前缀、period/run_id；禁止复用生产数据。
- 执行命令：

```bash
RUN_ID=full-$(date +%Y%m%d%H%M%S)
bash uat/scripts/run_work_uat.sh --work ALL --run-id "$RUN_ID" --tc TC-001..TC-032
python uat/scripts/verify_evidence_pack.py --root "evidence/$RUN_ID"
```

- SQL/数据库证据命令（仅在专用 UAT schema 和 WORK-08 manifest 校验通过后执行；N/A 项只保留说明）：

```bash
mysql --defaults-extra-file="${MYSQL_CNF:?}" --batch --raw <<'SQL'
SELECT VERSION() AS db_version, @@GLOBAL.sql_mode AS global_sql_mode, @@SESSION.sql_mode AS session_sql_mode;
SHOW CREATE TABLE AR_PERIOD;
SHOW CREATE TABLE AR_CONFIG;
SHOW CREATE TABLE AR_CALC_BONUS_E;
SHOW CREATE TABLE AR_CALC_BONUS_E_SOURCE;
SQL
```

- 执行步骤：
1. 校验commit/image/schema/config/data checksum
2. 按总方案Wave执行各ENV-TC
3. 保存stdout/stderr/exit/JUnit/DB/Redis/Kafka/Dask证据
4. 构建traceability manifest和P0/T0状态矩阵
- 精确预期：
- 每个TC有明确validation_status ∈ {NOT_RUN, PASS, FAIL, PENDING_TEST_ENV, BLOCKED}
- 所有P0/P1证据可重放
- DEC-010豁免与Gate C OPEN分开登记
- 无截图/二手报告单独关闭问题
- 必须回传：完整命令、exit code、stdout/stderr、JUnit/JSON、输入fixture SHA-256、代码commit、镜像、环境版本、执行起止时间、Redis/DB/Kafka/Dask前后证据。
- 失败停止与清理：停止专用consumer/job；保留PEL/状态和证据；禁止在未分析前清理失败现场；按第11节回滚。

### 9.4 SQL 对账样例

| 样例 | SQL输入/来源 | SQL预期 | Python预期 | 比较口径 | 允许差异 |
|---|---|---|---|---|---|
| PE golden | 1500.99*15% | 225.14 | 22514 cents | 字段级diff | 0 |
| TB golden | A total 1000/600, rate10%, pool24 | TOUCH_BASE=60, TB_RATE=.4, BONUS=24.00 | 2400 cents | SQL中间+最终 | 0 |

## 10. 验收标准映射

| 验收编号 | 来源TASK验收项 | 实现步骤 | 测试用例 | 所需证据 | 环境 | 通过条件 |
|---|---|---|---|---|---|---|
| AC-01 | DEC-013 有正式环境/权限批准记录 | STEP-PVAM-08-02/07 | TC-032 | EV-PVAM-08-01 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-02 | source archive、commit、image、schema、config、data 均有 checksum | STEP-PVAM-08-01/02/03/07 | TC-030、TC-031、TC-032 | EV-PVAM-08-02 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-03 | DEC-009 最小 manifest 覆盖生产可达输入、Redis状态、事件/outbox和有效SQL对象 | STEP-PVAM-08-02/07 | TC-008、TC-019、TC-029、TC-032 | EV-PVAM-08-03 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-04 | 全局/会话 SQL_MODE 和数据库 assignment 有原始证据 | STEP-PVAM-08-02/04/07 | TC-008、TC-019、TC-029 | EV-PVAM-08-04 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-05 | RISK-001 有可复核 call graph、部署入口和运行结果；证据触发 T06 `TOPO-WIRE-01` 分支 | STEP-PVAM-08-05/07 | TC-011、TC-024、TC-030、TC-032 | EV-PVAM-08-05 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-06 | 候选报告测试在固定镜像重跑，保留 stdout/stderr/exit/XML | STEP-PVAM-08-03/06/07 | TC-031、TC-032 | EV-PVAM-08-06 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-07 | UAT-001～012 每项均有 manifest、输入、命令、前后状态、diff 和结论 | STEP-PVAM-08-03/04/05/07 | TC-001～TC-032 | EV-PVAM-08-07 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-08 | 失败能追踪到所属 TASK/AC/TC，不被总体统计吞掉 | STEP-PVAM-08-01/05/07 | TC-031、TC-032 | EV-PVAM-08-08 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-09 | SQL-Python 差分明确标注 Legacy parity/corrected approved | STEP-PVAM-08-04/07 | TC-008～TC-021 | EV-PVAM-08-09 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-10 | 故障注入在隔离环境执行，恢复 checksum 与干净重跑一致 | STEP-PVAM-08-03/04/07 | TC-022～TC-029 | EV-PVAM-08-10 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-11 | P0/T0、CHK、TC、R/RISK/UV、REM/W/V、TASK、AC、证据形成机器可读双向追踪 | STEP-PVAM-08-05/07 | TC-031、TC-032 | EV-PVAM-08-11 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-12 | 没有仅凭截图、口头结论或二手报告关闭问题 | STEP-PVAM-08-01/07 | TC-032 | EV-PVAM-08-12 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-13 | OPT-001：脚本测试具有 pytest/unittest 可收集入口并保留 CLI smoke，exit code/报告统一 | STEP-PVAM-08-06/07 | TC-031 | EV-PVAM-08-13 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-14 | `GAP-DEC004-2B` 的 fixture 来源、注入人、checksum、有效期明确，且生产实现状态仍登记 DEFERRED/BLOCKED | STEP-PVAM-08-02/07 | TC-007、TC-032 | EV-PVAM-08-14 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |

没有 STEP、TC 或 EV 映射的AC不得标记完成。任何含UAT的AC在未回传真实环境证据时只能为 `PENDING_TEST_ENV/BLOCKED`。

## 11. 风险、停工与回滚

### 11.1 风险清单

| 风险 | 触发条件 | 影响 | 预防措施 | 监测/证据 | 处置 |
|---|---|---|---|---|---|
| 权限不足 | DEC-013未关闭 | UAT不可执行 | 阶段A/B分离 | 批准记录 | BLOCKED |
| 外部材料不完整 | schema/image/archive缺失 | 结果不可复验 | manifest强校验 | 缺失矩阵 | BLOCKED |
| 危险脚本误操作 | trim/清表默认开启 | 数据破坏 | 默认dry-run/专用prefix | command audit | 立即停工 |
| 证据覆盖 | 重跑覆盖旧日志 | 审计丢失 | immutable attempts | hash index | 拒绝覆盖 |

### 11.2 本任务强制停工条件

- HEAD、SQL blob、模型schema或上游TASK与受控基线不一致。
- 实施必须改变未批准的业务规则、精度、资格、分母、Country或发布职责才能继续。
- 需要修改排除文件/模块或扩大异常白名单才能通过测试。
- 关键mutation存活、SQL黄金样例出现未批准差异、幂等/原子/回滚断言失败。
- UAT权限、schema、数据或隔离条件不足；此时保持 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV`。

### 11.3 部署面与数据面回滚门禁

**当前可执行性：`BLOCKED_EXTERNAL_EVIDENCE`。** 当前材料没有给出真实部署系统、workload/release、镜像、配置对象和健康检查命令，因此不得以本地`export`或通用`git revert`冒充部署回滚。

部署前必须提供并签署`evidence/WORK-PVAM-08/rollback/ROLLBACK-MANIFEST-PVAM-v1.json`，至少包含：

- `deployment_system`、`environment`、`workload_id`、`release_before/after`、`image_before/after`；
- 精确的停止、回滚、恢复、健康检查和重新放量命令；
- Redis/Stream/ledger/run/manifest的备份或快照位置及SHA-256；
- 执行人、复核人、批准时间、允许的数据恢复范围；
- 命令dry-run/隔离演练的退出码和原始日志。

本任务数据面处置：本任务默认不改生产代码；回滚仅撤销证据脚本/CI配置。执行前后必须证明生产路径工作树、index、untracked及rename均为零。

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
| EV-PVAM-08-01 | AC-01验收证据：DEC-013 有正式环境/权限批准记录 | STEP-PVAM-08-02/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-01/ | 待指派QA | PENDING |
| EV-PVAM-08-02 | AC-02验收证据：source archive、commit、image、schema、config、data 均有 checksum | STEP-PVAM-08-01/02/03/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-02/ | 待指派QA | PENDING |
| EV-PVAM-08-03 | AC-03验收证据：DEC-009 最小 manifest 覆盖生产可达输入、Redis状态、事件/outbox和有效SQL对象 | STEP-PVAM-08-02/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-03/ | 待指派QA | PENDING |
| EV-PVAM-08-04 | AC-04验收证据：全局/会话 SQL_MODE 和数据库 assignment 有原始证据 | STEP-PVAM-08-02/04/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-04/ | 待指派QA | PENDING |
| EV-PVAM-08-05 | AC-05验收证据：RISK-001 有可复核 call graph、部署入口和运行结果；证据触发 T06 `TOPO-WIRE-01` 分支 | STEP-PVAM-08-05/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-05/ | 待指派QA | PENDING |
| EV-PVAM-08-06 | AC-06验收证据：候选报告测试在固定镜像重跑，保留 stdout/stderr/exit/XML | STEP-PVAM-08-03/06/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-06/ | 待指派QA | PENDING |
| EV-PVAM-08-07 | AC-07验收证据：UAT-001～012 每项均有 manifest、输入、命令、前后状态、diff 和结论 | STEP-PVAM-08-03/04/05/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-07/ | 待指派QA | PENDING |
| EV-PVAM-08-08 | AC-08验收证据：失败能追踪到所属 TASK/AC/TC，不被总体统计吞掉 | STEP-PVAM-08-01/05/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-08/ | 待指派QA | PENDING |
| EV-PVAM-08-09 | AC-09验收证据：SQL-Python 差分明确标注 Legacy parity/corrected approved | STEP-PVAM-08-04/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-09/ | 待指派QA | PENDING |
| EV-PVAM-08-10 | AC-10验收证据：故障注入在隔离环境执行，恢复 checksum 与干净重跑一致 | STEP-PVAM-08-03/04/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-10/ | 待指派QA | PENDING |
| EV-PVAM-08-11 | AC-11验收证据：P0/T0、CHK、TC、R/RISK/UV、REM/W/V、TASK、AC、证据形成机器可读双向追踪 | STEP-PVAM-08-05/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-11/ | 待指派QA | PENDING |
| EV-PVAM-08-12 | AC-12验收证据：没有仅凭截图、口头结论或二手报告关闭问题 | STEP-PVAM-08-01/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-12/ | 待指派QA | PENDING |
| EV-PVAM-08-13 | AC-13验收证据：OPT-001：脚本测试具有 pytest/unittest 可收集入口并保留 CLI smoke，exit code/报告统一 | STEP-PVAM-08-06/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-13/ | 待指派QA | PENDING |
| EV-PVAM-08-14 | AC-14验收证据：`GAP-DEC004-2B` 的 fixture 来源、注入人、checksum、有效期明确，且生产实现状态仍登记 DEFERRED/BLOCKED | STEP-PVAM-08-02/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-14/ | 待指派QA | PENDING |
| EV-PVAM-08-P01 | 证据schema与manifest模板 | 对应STEP/TC | evidence/WORK-PVAM-08/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-08-P02 | DEV/UAT执行器和安全探针 | 对应STEP/TC | evidence/WORK-PVAM-08/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-08-P03 | SQL-Python差分器与callgraph工具 | 对应STEP/TC | evidence/WORK-PVAM-08/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-08-P04 | pytest包装/collect报告 | 对应STEP/TC | evidence/WORK-PVAM-08/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-08-P05 | 完整UAT回传包与traceability manifest | 对应STEP/TC | evidence/WORK-PVAM-08/attempt-*/package/ | 待指派QA | PENDING |

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
  --work-id "WORK-PVAM-08" \
  --stage "$WORK_STAGE" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --out "evidence/WORK-PVAM-08/patch"
```

门禁必须证明：

1. `BASE_SHA` 是 `WORK_COMMIT_SHA` 的祖先；
2. 全部新增、修改、删除和 rename 的旧/新路径均落在 `WORK-PVAM-08` 批准 allowlist；
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
| STEP-PVAM-08-01 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-08-02 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-08-03 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-08-04 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-08-05 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-08-06 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-08-07 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |

### 13.2 实际验证

| 测试 | 环境 | 命令/版本 | 结果 | 证据 | 执行时间 |
|---|---|---|---|---|---|
| TC-PVAM-08-01 | DEV | 待执行 | NOT_RUN | EV-PVAM-08-* | 待执行 |
| TC-PVAM-08-02 | DEV | 待执行 | NOT_RUN | EV-PVAM-08-* | 待执行 |
| TC-PVAM-08-03 | DEV | 待执行 | NOT_RUN | EV-PVAM-08-* | 待执行 |
| TC-PVAM-08-04 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-08-* | 待执行 |
| TC-PVAM-08-05 | DEV | 待执行 | NOT_RUN | EV-PVAM-08-* | 待执行 |
| TC-PVAM-08-06 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-08-* | 待执行 |
| TC-PVAM-08-07 | DEV | 待执行 | NOT_RUN | EV-PVAM-08-* | 待执行 |
| TC-PVAM-08-08 | DEV | 待执行 | NOT_RUN | EV-PVAM-08-* | 待执行 |
| TC-PVAM-08-09 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-08-* | 待执行 |

### 13.3 未完成项

| 项目 | 原因 | 风险 | 后续动作 | 责任人 | 截止时间 |
|---|---|---|---|---|---|
| UAT/外部材料 | 当前计划阶段未执行 | 不能关闭P0/P1 | 由WORK-08准入后执行 | 待指派 | 待批准 |

## 14. 偏离、发现项与上游回流

| 编号 | 类型 | 发现事实 | 是否影响业务/范围 | 临时动作 | 需要更新 | 最终裁决 |
|---|---|---|---|---|---|---|
| `DEV-PVAM-08-001` | `预留` | 待执行 | 待判断 | 停工/隔离 | WORK/TASK/DEC/REVIEW | 待裁决 |

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
| v1.0 | 2026-08-04 | 初版施工任务书 | `TASK-PVAM-08` + `PLAN-PVAM-v1.15` + 固定代码基线 | AI Agent（编制） | DRAFT |
| v1.1 | 2026-08-05 | 依据二轮核验报告完成定点修订并补齐治理追溯 | F-A/F-B/F-H/F-I/F-J/F-K/F-F/F-E/F-L/F-M/F-N 中适用项 | AI Agent（编制） | DRAFT |
| v1.2 | 2026-08-05 | 闭合 G-1：统一 `RecalcProcessResult` 类名并补齐 `should_ack`；历史版本曾调整施工套件审批状态，不改变 CHK/DEC/TASK/WORK 范围 | 历史会话声明（未形成可独立验证组织授权，现由 v1.3 取代） | AI Agent（编制） | SUPERSEDED |
| v1.3 | 2026-08-05 | 第四轮关闭 F3-01～F3-10：治理回退 DRAFT、Traceability v3、patch/DEV 双阶段、状态枚举及设计边界 | 三轮审查报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r6 | 2026-08-06 | 五轮 F5 定点修订：规范 v3 追溯、parent provenance/DEV CLI、控制状态字段及单一事实源 | 五轮审计报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r7 | 2026-08-06 | 六轮 S6：信任 registry 初版、归档哈希、临时目录与 Decimal finite 防护 | 六轮终局审计报告 | AI Agent（编制） | DRAFT |
| v1.3-r8 | 2026-08-06 | 七轮 B7：registry 发布信任根、四工件摘要、AC 来源保真及当前轮次引用 | 七轮终局审计报告 + B7 处置 | AI Agent（编制） | DRAFT |

<!-- END WORK-PVAM-08_UAT准入与证据治理.md -->
