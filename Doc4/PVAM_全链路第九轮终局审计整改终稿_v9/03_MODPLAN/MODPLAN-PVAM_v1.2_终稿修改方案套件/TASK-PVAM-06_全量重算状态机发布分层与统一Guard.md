# TASK-PVAM-06 全量重算状态机、发布分层与统一 Guard

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 所属总方案 | `MODPLAN-PVAM_v1.2` |
| 任务编号 | `TASK-PVAM-06` |
| 来源检查项 | `CHK-BIZ-006、CHK-ARCH-002、CHK-EVT-003、CHK-PUB-001` |
| 来源问题 | `R-009、R-010` |
| 处置项 | `REM-009、REM-010` |
| 施工项 | `W-009、W-010` |
| 验证项 | `V-009、V-010` |
| 外部触发约束 | `TOPO-WIRE-01` 仅可在 WORK-08 证据触发且受控追溯边更新后实施；当前关联决策为 `DEC-012` |
| 关联决策 | `DEC-007、DEC-008、DEC-010、DEC-012` |
| 严重级别 | `P0` |
| 当前状态 | `DRAFT` |
| 受控基线 | `l343765828/Redemption@2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` |
| 编制日期 | `2026-08-04` |
| 审批人 | `待组织授权人签署` |
| 审批日期 | `待签署` |
| 前置任务 | `TASK-PVAM-01、TASK-PVAM-02、TASK-PVAM-05` |

> `DRAFT` 表示技术内容已修订但尚无可核验组织施工授权；不得启动代码施工、部署或生产发布。


### 1.1A 授权与执行状态分层

- 授权状态依据：`AUTHORIZATION_STATUS-PVAM-v2`；当前为 `PENDING_ORGANIZATIONAL_APPROVAL`。
- 本TASK治理状态：`DRAFT`；授权状态：`PENDING_ORGANIZATIONAL_APPROVAL`。
- 代码实现状态：`NOT_STARTED`；UAT依赖项：`PENDING_TEST_ENV`。
- 批准不改变来源报告的`REJECTED`结论，也不允许绕过WORK级patch、rollback和环境门禁。

## 2. 问题与代码证据

- Elite 全量在 `db_executor` 缺失时令 `persisted=False`，但 `_emit_settlement_done` 仍把状态写为 DONE 并发布 `SETTLEMENT_PERIOD_DONE`。
- `UserStatsService.assert_period_settlement_available` 只检查 Global 与 Placement；Elite 全量另有独立 guard，导致状态覆盖分裂。
- 现有 Global/Placement/Elite 各自维护 status/lock/event，没有统一 epoch、freeze、in-flight drain、coverage、candidate/published 分层。
- 同名完成事件还存在 schema 冲突，具体消费路由由 TASK-07B 处理。

## 3. 本任务修改目标

1. 建立统一 SettlementCoordinator/Epoch Manager 和单一 Guard API。
2. 区分“重算完成”“发布批次就绪”“外部正式发布确认”，禁止 persisted=false 进入最终 DONE。
3. 在真实消息入口、增量服务、拓扑变更、全量入口、奖金读取/发布入口统一执行 guard。
4. 实现 freeze、drain、watermark、coverage、manifest、失败恢复和幂等重跑。
5. 遵守 DEC-007/008：Redis 是 Python 权威，业务系统负责正式读模型发布。
6. 预先承接 DEC-012 的 `TOPO-WIRE-01`：证据确认后验证现有生产接线或实施缺失接线，不再临时另立任务。

## 4. 处置决定与方案选择

### 4.1 状态机

建议状态：

```text
OPEN
QUIESCING
DRAINING
RECALCULATING
RECALC_DONE_PENDING_BATCH
BATCH_READY
PUBLISHING_EXTERNAL
PUBLISHED
FAILED
IN_DOUBT
```

Global、Placement、Elite 是同一 epoch 下的 stage，不再各自宣称全局 DONE。

### 4.2 Guard

唯一 API：

```python
SettlementGuard.assert_write_allowed(period, domain, event_identity)
SettlementGuard.assert_read_allowed(period, required_stage)
SettlementGuard.assert_transition(expected, target, run_id, epoch)
```

检查：global lock/epoch、所有 stage 状态、period closed、in-flight counter、coverage、version、run/generation。

### 4.3 被否决方案

- 在 UserStats guard 里简单再加一个 Elite key；仍是分散硬编码，未来会继续漏。
- `persisted` 布尔值同时表示计算和发布；语义不足。
- 失败时删除状态键回到 OPEN；会丢失恢复证据。
- 用 Redis 锁冒充跨 Redis/业务系统原子发布。
- 只在全量入口检查 guard；消息入口和核心写函数仍可绕过。

## 5. 修改范围与受影响模块

- 新增 `Settlement/SettlementCoordinator.py`、`Settlement/SettlementGuard.py`、`Settlement/SettlementRunManifest.py`。
- 修改 `GlobalRecalculationService`、`PlacementRecalculationService`、`GlobalEliteBonusRecalculationService` 使用统一 stage API。
- 修改 `UserStatsService`、`PlacementIncrementalService`、`EliteBonusService` 核心写入口调用 guard。
- 修改真实 PV Message Consumer 和 `TopologyMutationService` 接入 guard。
- `TOPO-WIRE-01`：由本任务负责把生产拓扑变更入口接入 `TopologyMutationService.orchestrate_topology_mutation` 或证明已有等价正式接线，并补齐 period/version/guard/影响范围重算/回滚。
- 修改 period closed/lock/status key 命名和兼容 adapter。
- 接入 TASK-05 的 `BATCH_READY`/receipt；定义业务系统发布回执 API/event。
- 状态事件 envelope 的详细路由交给 TASK-07B。

## 6. 明确排除项（防越界红线）

- 不在 Python 实现业务系统关系库 writer/read switch。
- 不承诺测试期豁免的生产双 checkpoint 已完成；Gate C 保持 OPEN。
- 不修改奖金公式、Active 规则或与 DEC-012 无关的图算法；Topology 接线只修复生产编排和一致性边界。
- 不用“最后写入者获胜”处理状态冲突。
- 不自动清除 FAILED/IN_DOUBT；人工恢复必须有 by/reason/audit。

## 7. 前置条件与依赖关系

- TASK-01：version/金额域。
- TASK-02：真实消息入口、PeriodSnapshot、normalized identity。
- TASK-05：Elite batch/receipt 合同。
- TASK-07B 依赖本任务冻结最终事件变体与 ACK 后置条件；TASK-07A 可独立先行。
- UAT 依赖 TASK-08 的中间件、部署和故障注入准入。
- T08 的固定 archive/部署 call graph 决定 `TOPO-WIRE-01` 执行“核验现有接线”还是“实施新接线”，不改变 T06 的归属。

## 8. 修改后行为与技术设计

### 8.1 启动序列

```text
CAS OPEN -> QUIESCING
阻断新消息进入写阶段
等待所有 in-flight 增量归零
记录 Kafka/normalized watermark
冻结 period/config/topology/amount schema snapshot
CAS -> RECALCULATING
按 Global -> Placement -> Elite/Bonus stage 执行
每 stage 写 coverage/checksum
全部 stage 完成 -> RECALC_DONE_PENDING_BATCH
生成完整 batch -> BATCH_READY
业务系统接收/写入/校验 -> receipt
receipt 验证 -> PUBLISHED
```

### 8.2 失败与恢复

- 任何 stage 失败 -> FAILED；跨存储结果不确定 -> IN_DOUBT。
- 恢复读取 run manifest、stage ledger、coverage、outbox，决定幂等续跑或新 generation。
- 不允许把 `persisted=False`、零行或 consumer 未处理当作 PUBLISHED。

### 8.3 统一 manifest

至少包含 commit/image/config/period/topology/amount schema、epoch/run/generation、ingress watermarks、stage counts/checksums、batch id、receipt、状态时间线。

### 8.4 `TOPO-WIRE-01` 条件分支

1. T08 提供固定 archive、部署 manifest、consumer/cron/人工入口和 call graph。
2. 若已有生产可达接线：核验其确实调用 TopologyMutationService 或等价事务编排，补齐统一 guard、PeriodSnapshot、amount version、CDC 幂等和 rollback 证据。
3. 若无生产可达接线：修改真实拓扑变更 consumer/启动配置，使其通过 TopologyMutationService 执行旧链提取→图变更→新链提取→影响节点重算；禁止继续直接 `graph_actor.run_update` 后不修复状态。
4. 两种分支都必须通过 TC-011/TC-024，并由 TC-030/TC-032 证明生产可达；测试脚本引用不构成接线证明。

## 9. 任务验收标准（AC）

| AC | 验收标准 | 环境 | 关联 TC |
|---|---|---|---|
| AC-01 | 全仓只存在一个公开 SettlementGuard；旧 guard 仅为弃用 adapter 且无生产直连 | DEV+UAT | TC-024、TC-030 |
| AC-02 | Global/Placement/Elite 任一 RUNNING/FAILED/IN_DOUBT 阻断所有生产写入口 | DEV+UAT | TC-024 |
| AC-03 | 真实消息入口和核心写函数都执行 guard，direct-call 不能绕过 | DEV+UAT | TC-024、TC-030 |
| AC-04 | `persisted=False` 只能进入 pending/batch-ready 前状态，不能 DONE/PUBLISHED | DEV+UAT | TC-029 |
| AC-05 | freeze 后新消息不进入本 epoch；in-flight 归零并有 watermark | DEV+UAT | TC-023、TC-024 |
| AC-06 | 全部 stage 的 period/run/epoch/generation/config/topology/version 一致 | DEV+UAT | TC-025、TC-026 |
| AC-07 | 空结果也生成 manifest/batch 并等待外部 receipt | DEV+UAT | TC-029 |
| AC-08 | 每个状态点崩溃后可恢复，最终 checksum 与干净重跑一致 | UAT | TC-026、TC-028、TC-032 |
| AC-09 | 重复 transition/CAS 幂等；非法跳转阻断并审计 | DEV+UAT | TC-024、TC-026 |
| AC-10 | 业务系统未回 receipt 时，正式读保持上一 committed 版本 | UAT | TC-029、TC-032 |
| AC-11 | 测试 checkpoint 豁免有显式标记，生产 Gate C 不被误关闭 | DEV+UAT | TC-023、TC-026、TC-032 |
| AC-12 | `TOPO-WIRE-01` 有固定 archive/部署证据，并已选择“验证现有接线”或“实施新接线”分支 | DEV+UAT | TC-011、TC-024、TC-030、TC-032 |
| AC-13 | 接线后的拓扑变更入口具备 period/version/guard、影响范围重算、失败/回滚证据；测试脚本不作为生产证明 | UAT | TC-011、TC-024、TC-032 |

> `assert_read_allowed` 仅用于本仓结算引擎内部一致性读取，不构成业务系统正式读模型的门控，避免越过 DEC-007。

## 10. 环境验证与回传证据

### DEV

- 状态转移表、非法跳转、CAS、guard coverage、manifest 单测；
- mock in-flight/watermark、stage failure、receipt failure；
- 全仓调用图证明各入口接线；
- mutation：允许 persisted=false DONE、漏 Elite guard，测试必须失败。

### UAT

关联 `UAT-008、UAT-009、UAT-010、UAT-011`：

- 真实并发订单与全量启动；
- Global/Placement/Elite 组合状态；
- Redis/Kafka/进程/业务系统 receiver 故障；
- 空批次、重复run、旧epoch replay；
- 回传状态时间线、locks、in-flight、offset/watermark、coverage、manifest、receipt、checksum。

## 11. 独立回滚与风险控制

1. 新状态机使用独立 key namespace 与 `SETTLEMENT_COORDINATOR_V2` 开关。
2. 先 mirror 旧状态，不控制写；验证后切 guard authority。
3. 回滚时进入 maintenance/frozen，不能简单恢复旧分散 guard 继续写。
4. 已启动 v2 epoch 必须完成恢复或正式 abort，不能删除 key。
5. 业务系统继续服务上一 committed 版本；candidate/manifest 保留。
